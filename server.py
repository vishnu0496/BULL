# server.py
import time

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
from engine import BULLSignalEngine
from paper_broker import BULLPaperBroker
from src import database
from src.news import fetch_stock_news
from src.news_analyst import summarize_ticker_news

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

@app.get("/")
def serve_dashboard():
    return FileResponse(
        "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

@app.on_event("startup")
def startup_event():
    engine.bootstrap_and_train()

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

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
