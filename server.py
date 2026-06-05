# server.py
import time
import json
import threading
from datetime import datetime, timedelta

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from src.logger import logger
from engine import BULLSignalEngine
from paper_broker import BULLPaperBroker
from src import database
from src import data_health
from src.fno_engine import scan_fno_watchlist
from src.news import fetch_stock_news
from src.news_analyst import summarize_ticker_news
from src.nse_feed import get_indices, get_market_status, get_option_chain
from src.universe_engine import compute_skill_gate, get_opportunity_counts, get_universe_payload

app = FastAPI(title="BULL Stock Terminal Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = BULLSignalEngine()
broker = BULLPaperBroker(initial_capital=100000.0)
NEWS_CACHE = {"timestamp": 0.0, "report": None}
NEWS_CACHE_SECONDS = 900
DATA_SCHEDULER = BackgroundScheduler(timezone="Asia/Kolkata")


def _build_news_report(tickers=None, force_refresh: bool = False):
    database.init_db()
    symbols = list(tickers or engine.tickers)
    now = time.time()
    if (
        not force_refresh
        and tickers is None
        and NEWS_CACHE["report"] is not None
        and now - NEWS_CACHE["timestamp"] < NEWS_CACHE_SECONDS
    ):
        return NEWS_CACHE["report"]

    stock_reports = []
    top_events = []
    for ticker in symbols:
        try:
            items = fetch_stock_news(ticker, gemini_api_key=None, force_refresh=force_refresh)
            report = summarize_ticker_news(ticker, items)
        except Exception as exc:
            report = {
                "ticker": ticker,
                "news_count": 0,
                "net_news_score": 0,
                "verdict": "FETCH_ERROR",
                "summary": f"News fetch failed: {exc}",
                "top_events": [],
            }
        stock_reports.append(report)
        top_events.extend(report.get("top_events", []))

    risky = [r for r in stock_reports if r.get("verdict") in {"NEWS_RISK", "EVENT_CAUTION"}]
    supportive = [r for r in stock_reports if r.get("verdict") == "NEWS_SUPPORTIVE"]
    neutral = [r for r in stock_reports if r.get("verdict") in {"NEWS_NEUTRAL", "NO_NEWS", "FETCH_ERROR"}]

    if risky:
        command = "CAUTION"
        reason = f"{len(risky)} tracked symbols have risky or unclear high-impact news."
    elif supportive:
        command = "SELECTIVE_WATCH"
        reason = f"{len(supportive)} tracked symbols have supportive news. Require technical confirmation."
    else:
        command = "NEWS_NEUTRAL"
        reason = "No strong news edge detected from the free news sources."

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "refresh_seconds": NEWS_CACHE_SECONDS,
        "source_cost": "INR 0 - Google News RSS + yfinance/Yahoo headlines, SQLite cache, local rule-based analysis",
        "desk_command": command,
        "desk_reason": reason,
        "counts": {
            "tracked": len(stock_reports),
            "supportive": len(supportive),
            "risky": len(risky),
            "neutral": len(neutral),
        },
        "supportive_stocks": supportive[:5],
        "risk_stocks": risky[:5],
        "top_events": sorted(top_events, key=lambda item: item.get("materiality_score", 0), reverse=True)[:8],
        "stock_reports": sorted(stock_reports, key=lambda item: item.get("net_news_score", 0), reverse=True),
    }

    if tickers is None:
        NEWS_CACHE["timestamp"] = now
        NEWS_CACHE["report"] = report
    return report


def _apply_news_gate(candidates):
    if not candidates:
        return candidates, _build_news_report(force_refresh=False)

    report = _build_news_report(tickers=[c["ticker"] for c in candidates], force_refresh=False)
    by_ticker = {r["ticker"]: r for r in report.get("stock_reports", [])}
    for candidate in candidates:
        news_report = by_ticker.get(candidate["ticker"], {})
        verdict = news_report.get("verdict", "NO_NEWS")
        candidate["news_verdict"] = verdict
        candidate["news_score"] = news_report.get("net_news_score", 0)
        candidate["news_summary"] = news_report.get("summary", "No fresh news found.")
        candidate["news_gate"] = "BLOCKED" if verdict == "NEWS_RISK" else "CAUTION" if verdict == "EVENT_CAUTION" else "PASS"
        candidate["news_events"] = news_report.get("top_events", [])
    return candidates, report


def _run_universe_scan_job():
    """Run all allowed scanners and log every generated signal."""
    candidates, scan_report = engine.scan_with_report()
    candidates, _ = _apply_news_gate(candidates)
    for item in candidates:
        broker.log_signal({
            **item,
            "decision": "TRADE",
            "asset_class_id": "nifty50_equity",
            "instrument_type": "equity_cash",
        })
    watch_setups = scan_fno_watchlist(force_refresh=True)
    for item in watch_setups:
        broker.log_signal(item)
    return {"tier1": len(candidates), "tier2_watch": len(watch_setups), "scan_report": scan_report}

@app.get("/")
def serve_dashboard():
    return FileResponse(
        "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/universe.html")
def serve_universe():
    """Serve the Market Universe Command Center page."""
    return FileResponse(
        "universe.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

def job_fetch_fii_dii():
    from src.fii_tracker import fetch_fii_dii_data
    try:
        fetch_fii_dii_data()
    except Exception as e:
        print(f"[Scheduler] Error running fetch_fii_dii: {e}")

def job_refresh_earnings():
    from src.earnings_calendar import refresh_earnings_calendar
    try:
        refresh_earnings_calendar()
    except Exception as e:
        print(f"[Scheduler] Error running refresh_earnings: {e}")

def job_update_post_results():
    from src.earnings_calendar import update_post_result_data
    try:
        update_post_result_data()
    except Exception as e:
        print(f"[Scheduler] Error running update_post_results: {e}")

def job_refresh_sectors():
    from src.sector_rotation import refresh_sector_data
    try:
        refresh_sector_data()
    except Exception as e:
        print(f"[Scheduler] Error running refresh_sectors: {e}")

def job_compute_premarket():
    from src.premarket_signals import compute_premarket_score
    try:
        compute_premarket_score()
    except Exception as e:
        print(f"[Scheduler] Error running compute_premarket: {e}")

def job_fetch_promoters():
    from src.promoter_tracker import fetch_promoter_activity
    try:
        fetch_promoter_activity()
    except Exception as e:
        print(f"[Scheduler] Error running fetch_promoters: {e}")

def run_intelligence_warmup():
    """Fetch all intelligence data once on startup."""
    import time
    time.sleep(5)  # Wait for server to fully start
    
    logger.info("BULL: Starting intelligence warmup...")
    
    try:
        from src.fii_tracker import fetch_fii_dii_data
        fetch_fii_dii_data()
        logger.info("BULL: FII/DII data loaded")
    except Exception as e:
        logger.warning(f"BULL: FII warmup failed: {e}")
    
    try:
        from src.sector_rotation import refresh_sector_data
        refresh_sector_data()
        logger.info("BULL: Sector rotation loaded")
    except Exception as e:
        logger.warning(f"BULL: Sector warmup failed: {e}")
    
    try:
        from src.premarket_signals import compute_premarket_score
        compute_premarket_score()
        logger.info("BULL: Pre-market score computed")
    except Exception as e:
        logger.warning(f"BULL: Pre-market warmup failed: {e}")
    
    try:
        from src.earnings_calendar import refresh_earnings_calendar
        refresh_earnings_calendar()
        logger.info("BULL: Earnings calendar loaded")
    except Exception as e:
        logger.warning(f"BULL: Earnings warmup failed: {e}")
    
    try:
        from src.promoter_tracker import fetch_promoter_activity
        fetch_promoter_activity()
        logger.info("BULL: Promoter activity loaded")
    except Exception as e:
        logger.warning(f"BULL: Promoter warmup failed: {e}")
    
    logger.info("BULL: Intelligence warmup complete.")

@app.on_event("startup")
def startup_event():
    database.init_db()
    data_health.ensure_data_health_table()
    engine.bootstrap_and_train()
    if not DATA_SCHEDULER.running:
        DATA_SCHEDULER.add_job(
            data_health.run_data_health_check,
            "interval",
            minutes=30,
            id="bull_data_health_monitor",
            replace_existing=True,
            next_run_time=datetime.now() + timedelta(minutes=30),
        )
        
        # Add the 6 new daily cron jobs
        DATA_SCHEDULER.add_job(job_fetch_fii_dii, "cron", hour=18, minute=0, id="fii_dii_job", replace_existing=True)
        DATA_SCHEDULER.add_job(job_refresh_earnings, "cron", hour=7, minute=0, id="earnings_job", replace_existing=True)
        DATA_SCHEDULER.add_job(job_update_post_results, "cron", hour=18, minute=0, id="post_earnings_job", replace_existing=True)
        DATA_SCHEDULER.add_job(job_refresh_sectors, "cron", hour=16, minute=30, id="sectors_job", replace_existing=True)
        DATA_SCHEDULER.add_job(job_compute_premarket, "cron", hour=8, minute=30, id="premarket_job", replace_existing=True)
        DATA_SCHEDULER.add_job(job_fetch_promoters, "cron", hour=17, minute=0, id="promoters_job", replace_existing=True)
        
        # Trigger immediately on first boot with staggered start
        DATA_SCHEDULER.add_job(job_fetch_fii_dii, "date", run_date=datetime.now(), id="fii_dii_start", replace_existing=True)
        DATA_SCHEDULER.add_job(job_refresh_earnings, "date", run_date=datetime.now() + timedelta(seconds=2), id="earnings_start", replace_existing=True)
        DATA_SCHEDULER.add_job(job_update_post_results, "date", run_date=datetime.now() + timedelta(seconds=4), id="post_earnings_start", replace_existing=True)
        DATA_SCHEDULER.add_job(job_refresh_sectors, "date", run_date=datetime.now() + timedelta(seconds=6), id="sectors_start", replace_existing=True)
        DATA_SCHEDULER.add_job(job_compute_premarket, "date", run_date=datetime.now() + timedelta(seconds=8), id="premarket_start", replace_existing=True)
        DATA_SCHEDULER.add_job(job_fetch_promoters, "date", run_date=datetime.now() + timedelta(seconds=10), id="promoters_start", replace_existing=True)
        
        DATA_SCHEDULER.start()
        
    threading.Thread(target=run_intelligence_warmup, daemon=True).start()

@app.get("/api/scan")
def run_scanner(background_tasks: BackgroundTasks):
    candidates, scan_report = engine.scan_with_report()
    candidates, news_report = _apply_news_gate(candidates)
    for c in candidates:
        broker.log_engine_signal(c["ticker"], c["price"], c["ml_score"], c["rsi"], c["rvol"])
    return {"status": "success", "data": candidates, "scan_report": scan_report, "news_report": news_report}


@app.get("/api/news-swarm")
def get_news_swarm(force_refresh: bool = False):
    return {"status": "success", "report": _build_news_report(force_refresh=force_refresh)}


@app.get("/api/feed/status")
def get_feed_status():
    return {"status": "success", "feed": engine.feed_health()}


@app.get("/api/data/health")
def get_data_health():
    """Return data-quality status for the tracked universe."""
    return data_health.get_data_health_summary(run_if_empty=True)


@app.get("/api/market/status")
def get_nse_market_status():
    """Return NSE market status using NSE public data with local fallback."""
    return get_market_status()


@app.get("/api/indices")
def get_live_indices():
    """Return the latest live-ish index strip values."""
    return get_indices()


@app.get("/api/indices/stream")
def stream_live_indices():
    """Stream index-strip updates for the topbar."""
    def event_generator():
        while True:
            try:
                payload = get_indices()
            except Exception as exc:
                payload = {"items": [], "error": str(exc), "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S")}
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            time.sleep(60)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/option-chain/{symbol}")
def get_nse_option_chain(symbol: str = "NIFTY"):
    """Return NSE option-chain positioning summary."""
    return get_option_chain(symbol)


@app.get("/api/universe")
def get_universe():
    """Return asset registry, skill gate, and opportunity counts."""
    return {"status": "success", "data": get_universe_payload(database.DB_PATH)}


@app.get("/api/universe/counts")
def get_universe_counts():
    """Return 24-hour opportunity counts by asset class."""
    return {"status": "success", "counts": get_opportunity_counts(database.DB_PATH)}


@app.get("/api/universe/skill_gate")
def get_universe_skill_gate():
    """Return the honest BULL skill gate state."""
    return {"status": "success", "skill_gate": compute_skill_gate(database.DB_PATH)}


@app.get("/api/fno/watchlist")
def get_fno_watchlist(force_refresh: bool = False):
    """Return watch-only F&O and commodity setups."""
    return {"status": "success", "setups": scan_fno_watchlist(force_refresh=force_refresh)}


@app.post("/api/universe/scan_all")
def scan_all_universe(background_tasks: BackgroundTasks):
    """Trigger a full universe scan and log Tier 1 trade plus Tier 2 watch signals."""
    background_tasks.add_task(_run_universe_scan_job)
    return {"status": "scheduled", "message": "Full universe scan started. Tier 2 remains WATCH only."}

@app.post("/api/trade/execute")
def execute_trade(ticker: str, price: float, atr: float, ml_score: float):
    trade = broker.execute_trade(ticker, price, atr, ml_score)
    return {"status": "success", "trade": trade}

@app.get("/api/trades")
def get_trades():
    return {"status": "success", "trades": broker.trades}

@app.post("/api/trade/close")
def close_trade(trade_id: int, exit_price: float):
    trade = broker.close_trade(trade_id, exit_price)
    if trade:
        return {"status": "success", "trade": trade}
    return {"status": "error", "message": "Trade not found"}

@app.post("/api/trade/close_all")
def close_all_trades(win_rate: float = 0.65):
    updated = broker.close_all_trades(win_rate)
    return {"status": "success", "resolved_count": len(updated), "trades": updated}


@app.get("/api/analytics")
def get_analytics():
    trades = broker.trades
    closed_trades = [t for t in trades if t["status"] == "CLOSED"]
    
    if not closed_trades:
        return {
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 1.0,
            "max_drawdown": 0.0,
            "kelly_criterion": 10.0,
            "equity_curve": [100000.0]
        }
        
    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] <= 0]
    
    win_rate = (len(wins) / len(closed_trades)) * 100 if closed_trades else 0
    total_gains = sum(t["pnl"] for t in wins)
    total_losses = abs(sum(t["pnl"] for t in losses))
    profit_factor = total_gains / (total_losses if total_losses > 0 else 1.0)
    
    current_equity = 100000.0
    equity_curve = [current_equity]
    peak = current_equity
    max_dd = 0.0
    
    for t in closed_trades:
        current_equity += t["pnl"]
        equity_curve.append(current_equity)
        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
            
    avg_win = (total_gains / len(wins)) if len(wins) > 0 else 1.0
    avg_loss = (total_losses / len(losses)) if len(losses) > 0 else 1.0
    win_ratio = avg_win / (avg_loss if avg_loss > 0 else 1.0)
    
    w_frac = win_rate / 100
    kelly = 0.0
    if win_ratio > 0:
        kelly = w_frac - ((1 - w_frac) / win_ratio)
    kelly_pct = max(0.0, min(kelly * 100, 20.0))
    
    return {
        "net_pnl": sum(t["pnl"] for t in closed_trades),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "kelly_criterion": round(kelly_pct, 2),
        "avg_r_multiple": round(sum(t.get("r_multiple", 0.0) for t in closed_trades) / len(closed_trades), 2),
        "trades_taken": len(trades),
        "closed_trades": len(closed_trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "open_trades": len([t for t in trades if t["status"] == "OPEN"]),
        "equity_curve": equity_curve
    }

@app.get("/api/fii/latest")
def get_latest_fii():
    from src.fii_tracker import get_fii_signal
    return {"status": "success", "data": get_fii_signal()}

@app.get("/api/fii/history")
def get_fii_history_endpoint(days: int = 30):
    from src.fii_tracker import get_fii_history
    return {"status": "success", "data": get_fii_history(days)}

@app.get("/api/earnings/upcoming")
def get_upcoming_earnings():
    from src.earnings_calendar import get_earnings_this_week
    return {"status": "success", "data": get_earnings_this_week()}

@app.get("/api/earnings/recent")
def get_recent_earnings():
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM earnings_calendar 
            WHERE actual_eps IS NOT NULL 
            ORDER BY result_date DESC 
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return {"status": "success", "data": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.get("/api/sectors/rankings")
def get_sectors_rankings_endpoint():
    from src.sector_rotation import get_sector_rankings
    return {"status": "success", "data": get_sector_rankings()}

@app.get("/api/sectors/rotation")
def get_sectors_rotation():
    conn = database.get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sector_rotation ORDER BY date DESC, rank ASC LIMIT 30")
        rows = cursor.fetchall()
        return {"status": "success", "data": [dict(r) for r in rows]}
    finally:
        conn.close()

@app.get("/api/premarket")
def get_premarket_signals_endpoint():
    from src.premarket_signals import get_premarket_score
    return {"status": "success", "data": get_premarket_score()}

@app.get("/api/promoters/recent")
def get_recent_promoters():
    from src.promoter_tracker import get_recent_promoter_activity
    return {"status": "success", "data": get_recent_promoter_activity(30)}

@app.get("/api/promoters/{ticker}")
def get_promoters_ticker(ticker: str):
    from src.promoter_tracker import get_promoter_signal
    return {"status": "success", "data": get_promoter_signal(ticker)}

def get_intelligence_status_data():
    from datetime import datetime, timedelta
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    status_dict = {}
    
    def check_table_status(table_name, date_col, query_cond="", is_timestamp=False):
        try:
            query = f"SELECT {date_col} FROM {table_name}"
            if query_cond:
                query += f" WHERE {query_cond}"
            query += f" ORDER BY {date_col} DESC LIMIT 1"
            cursor.execute(query)
            row = cursor.fetchone()
            if not row or row[0] is None:
                return "EMPTY", None, False
            
            val = str(row[0])
            if is_timestamp:
                try:
                    dt = datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    dt = datetime.strptime(val.split('.')[0], "%Y-%m-%d %H:%M:%S")
            else:
                dt = datetime.strptime(val, "%Y-%m-%d").replace(hour=18, minute=0, second=0)
            
            age = datetime.now() - dt
            if age < timedelta(hours=25):
                return "FRESH", dt.strftime("%Y-%m-%d %H:%M:%S"), True
            else:
                return "STALE", dt.strftime("%Y-%m-%d %H:%M:%S"), True
        except Exception:
            return "EMPTY", None, False

    # 1. FII
    fii_status, fii_time, fii_has = check_table_status("fii_dii_flows", "date")
    fii_val = "No FII/DII data available."
    fii_src = "NONE"
    fii_conf = "LOW"
    if fii_has:
        cursor.execute("SELECT fii_net, dii_net, source, confidence FROM fii_dii_flows ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            r_dict = dict(row)
            fii_val = f"FII Net: {r_dict['fii_net']:+.1f} Cr, DII Net: {r_dict['dii_net']:+.1f} Cr"
            fii_src = r_dict.get("source") or "NSE_API"
            fii_conf = r_dict.get("confidence") or "HIGH"
    status_dict["fii"] = {
        "status": fii_status,
        "source": fii_src,
        "confidence": fii_conf,
        "last_updated": fii_time,
        "has_data": fii_has,
        "latest_value": fii_val
    }
    
    # 2. Sectors
    sec_status, sec_time, sec_has = check_table_status("sector_rotation", "date")
    sec_val = "No sector data available."
    sec_src = "NONE"
    sec_conf = "LOW"
    if sec_has:
        cursor.execute("SELECT sector, rs_score FROM sector_rotation ORDER BY date DESC, rank ASC LIMIT 1")
        row = cursor.fetchone()
        if row:
            sec_val = f"Top Sector: {row['sector']} (RS: {row['rs_score']:.2f})"
            sec_src = "YFINANCE"
            sec_conf = "HIGH"
    status_dict["sectors"] = {
        "status": sec_status,
        "source": sec_src,
        "confidence": sec_conf,
        "last_updated": sec_time,
        "has_data": sec_has,
        "latest_value": sec_val
    }
    
    # 3. Premarket
    pm_status, pm_time, pm_has = check_table_status("premarket_signals", "generated_at", is_timestamp=True)
    pm_val = "No pre-market score available."
    pm_src = "NONE"
    pm_conf = "LOW"
    if pm_has:
        cursor.execute("SELECT pre_market_score, classification FROM premarket_signals ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            pm_val = f"Score: {row['pre_market_score']:.0f} ({row['classification']})"
            pm_src = "YFINANCE_NSE_API"
            pm_conf = "HIGH"
    status_dict["premarket"] = {
        "status": pm_status,
        "source": pm_src,
        "confidence": pm_conf,
        "last_updated": pm_time,
        "has_data": pm_has,
        "latest_value": pm_val
    }
    
    # 4. Earnings
    earn_status, earn_time, earn_has = check_table_status("earnings_calendar", "result_date", "actual_eps IS NOT NULL")
    earn_val = "No earnings announcements."
    earn_src = "NONE"
    earn_conf = "LOW"
    if earn_has:
        cursor.execute("SELECT COUNT(*) as c FROM earnings_calendar WHERE result_date >= date('now')")
        row = cursor.fetchone()
        upcoming_count = row['c'] if row else 0
        earn_val = f"{upcoming_count} upcoming results this week."
        earn_src = "YFINANCE_NSE"
        earn_conf = "HIGH"
    status_dict["earnings"] = {
        "status": earn_status,
        "source": earn_src,
        "confidence": earn_conf,
        "last_updated": earn_time,
        "has_data": earn_has,
        "latest_value": earn_val
    }
    
    # 5. Promoters
    prom_status, prom_time, prom_has = check_table_status("promoter_activity", "date")
    prom_val = "No promoter activity."
    prom_src = "NONE"
    prom_conf = "LOW"
    if prom_has:
        cursor.execute("SELECT person_name, transaction_type, value_crore, source, confidence FROM promoter_activity ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            r_dict = dict(row)
            prom_val = f"Tx: {r_dict['person_name']} ({r_dict['transaction_type']}) - ₹{r_dict['value_crore']:.2f} Cr"
            prom_src = r_dict.get("source") or "NSE_API"
            prom_conf = r_dict.get("confidence") or "HIGH"
    status_dict["promoters"] = {
        "status": prom_status,
        "source": prom_src,
        "confidence": prom_conf,
        "last_updated": prom_time,
        "has_data": prom_has,
        "latest_value": prom_val
    }
    
    conn.close()
    
    statuses = [status_dict[k]["status"] for k in ["fii", "sectors", "premarket", "earnings", "promoters"]]
    if all(s == "FRESH" for s in statuses):
        overall = "READY"
    elif all(s == "EMPTY" for s in statuses):
        overall = "EMPTY"
    else:
        overall = "PARTIAL"
        
    status_dict["overall"] = overall
    return status_dict

@app.post("/api/intelligence/refresh")
async def refresh_all_intelligence(background_tasks: BackgroundTasks):
    """Manually trigger all intelligence data refresh."""
    background_tasks.add_task(run_intelligence_warmup)
    return {"status": "refresh_started", 
            "message": "All intelligence modules refreshing in background"}

@app.get("/api/intelligence/status")
def get_intelligence_status():
    """Return health status of all 5 intelligence modules."""
    return {"status": "success", "data": get_intelligence_status_data()}

@app.get("/api/conviction/{ticker}")
def get_ticker_conviction(ticker: str):
    import datetime
    now_time = datetime.datetime.now().time()
    if now_time < datetime.time(9, 15) or now_time > datetime.time(15, 30):
        now_time = datetime.time(10, 30)
    result = engine.evaluate_filters(ticker, now_time)
    return {"status": "success", "ticker": ticker, "data": result}

@app.get("/intelligence.html")
def serve_intelligence():
    return FileResponse(
        "intelligence.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
