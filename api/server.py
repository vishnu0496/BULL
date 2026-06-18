"""
BULL Research Dashboard — FastAPI Server
=========================================
Single-file API that delegates ALL business logic to the existing src/ modules.
Run with:  uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
"""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional
import time

MENTOR_PICKS_CACHE = {"data": None, "timestamp": 0}
MENTOR_PICKS_LOCK = None  # Initialized dynamically in lifespan
GLOBAL_MACRO_REGIME = {"sentiment": "NEUTRAL", "timestamp": time.time(), "reason": "No shocks detected."}


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

from apscheduler.schedulers.background import BackgroundScheduler

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so `from src.xxx import ...` works
# regardless of the working directory from which the server is launched.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Source module imports — all business logic lives here, NOT in this file.
# ---------------------------------------------------------------------------
from src import database, engine, backtest, market, news, fetcher, research, utils, sentiment, news_analyst, paper_analytics  # noqa: F401
from src.fno_engine import scan_fno_watchlist
from src.logger import get_logger
from src.universe_engine import compute_skill_gate, get_opportunity_counts, get_universe_payload

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
THREAD_POOL = ThreadPoolExecutor(max_workers=4)


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------
class WatchlistAddBody(BaseModel):
    ticker: str


class PaperTradeBody(BaseModel):
    ticker: str
    trade_date: str
    action: str
    quantity: int
    price: float
    notes: str = ""


class TelegramSetupBody(BaseModel):
    token: str
    chat_id: str


class CapitalSettingsBody(BaseModel):
    total_capital: float
    max_risk_per_trade: float
    max_trades_per_day: int
    allow_options: int = 0
    experience_level: str = "BEGINNER"
    gemini_api_key: str = ""
    dhan_client_id: str = ""
    dhan_access_token: str = ""
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_request_token: str = ""
    autopilot: int = 0


MASKED_SECRET_VALUE = "********"
SECRET_FIELDS = (
    "gemini_api_key",
    "dhan_client_id",
    "dhan_access_token",
    "kite_api_key",
    "kite_api_secret",
    "kite_request_token",
)


def _is_configured_secret(value) -> bool:
    return bool(str(value or "").strip())


def _mask_capital_settings(settings: dict) -> dict:
    public_settings = dict(settings)
    for field in SECRET_FIELDS:
        configured = _is_configured_secret(public_settings.get(field))
        public_settings[f"{field}_configured"] = configured
        public_settings[f"{field}_status"] = "CONFIGURED" if configured else "PENDING"
        public_settings[field] = MASKED_SECRET_VALUE if configured else ""
    return public_settings


def _credential_for_save(incoming_value: str, existing_value: str) -> str:
    value = str(incoming_value or "").strip()
    if not value or value == MASKED_SECRET_VALUE:
        return existing_value or ""
    return value


# ---------------------------------------------------------------------------
# Helper: run a blocking function on the thread-pool so we never block the
# event loop — all src/ functions are synchronous.
# ---------------------------------------------------------------------------
async def _run_sync(func, *args, **kwargs):
    """Execute a synchronous function in the thread-pool executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        THREAD_POOL, lambda: func(*args, **kwargs)
    )


# ---------------------------------------------------------------------------
# Lifespan — replaces the deprecated @app.on_event("startup")
# ---------------------------------------------------------------------------
def _nightly_sync_job():
    try:
        tickers = database.get_watchlist_tickers()
        for ticker in tickers:
            try:
                fetcher.sync_ticker(ticker)
            except Exception as e:
                logger.error(f"Error syncing {ticker} in nightly job: {e}")
    except Exception as e:
        logger.error(f"Nightly sync job failed: {e}")

def _morning_mentor_job():
    try:
        from src.daily_brief import get_daily_picks
        data = get_daily_picks()
        MENTOR_PICKS_CACHE["data"] = data
        MENTOR_PICKS_CACHE["timestamp"] = time.time()
        try:
            from src import auto_paper
            auto_paper.capture_daily_picks(picks=data, max_picks=3)
        except Exception as auto_exc:
            logger.warning(f"Auto paper capture failed after morning mentor job: {auto_exc}")
    except Exception as e:
        logger.error(f"Morning mentor job failed: {e}")

def _intraday_news_job():
    try:
        settings = database.get_capital_settings()
        gemini_key = settings.get("gemini_api_key", "")
        if gemini_key:
            news_items = news.fetch_stock_news("^NSEI", gemini_api_key=gemini_key)
            if news_items:
                avg_score, avg_label = sentiment.get_aggregated_sentiment(news_items)
                if avg_label == 'BEARISH':
                    GLOBAL_MACRO_REGIME["sentiment"] = "BEARISH_SHOCK"
                    GLOBAL_MACRO_REGIME["reason"] = f"Geopolitical/Macro shock detected: Negative sentiment score {avg_score:.1f}"
                    MENTOR_PICKS_CACHE["data"] = None
                else:
                    GLOBAL_MACRO_REGIME["sentiment"] = "NEUTRAL"
                    GLOBAL_MACRO_REGIME["reason"] = "Market conditions stable."
                GLOBAL_MACRO_REGIME["timestamp"] = time.time()
    except Exception as e:
        logger.error(f"Intraday news job failed: {e}")

def _data_health_job():
    try:
        from src import data_health
        data_health.run_data_health_check(include_news=False)
    except Exception as e:
        logger.error(f"Data health job failed: {e}")

def _data_vault_job():
    try:
        from src import data_vault
        data_vault.refresh_data_vault(limit=20, include_news=False)
    except Exception as e:
        logger.error(f"Data vault job failed: {e}")

def _auto_paper_job():
    try:
        from src import auto_paper
        picks = MENTOR_PICKS_CACHE.get("data")
        auto_paper.run_auto_paper_cycle(picks=picks, max_picks=3, sync_prices=True)
    except Exception as e:
        logger.error(f"Auto paper evidence job failed: {e}")

def _weekly_retraining_job():
    try:
        from src import ml_model, deep_learning
        logger.info("Starting weekly scheduled model auto-retraining...")
        ml_model.train_model()
        deep_learning.train_lstm_model(epochs=20)
        logger.info("Weekly scheduled model auto-retraining completed successfully.")
    except Exception as e:
        logger.error(f"Weekly scheduled model retraining failed: {e}")

def _morning_brief_job():
    try:
        from datetime import datetime
        from src.constants import is_nse_holiday
        from notifier import send_morning_brief
        
        today = datetime.now()
        # Monday is 0, Friday is 4, Saturday is 5, Sunday is 6
        if today.weekday() >= 5:
            logger.info("[Scheduler] Today is a weekend. Skipping morning brief.")
            return
            
        if is_nse_holiday(today):
            logger.info("[Scheduler] Today is an NSE holiday. Skipping morning brief.")
            return
            
        logger.info("[Scheduler] Starting morning brief transmission...")
        send_morning_brief()
    except Exception as e:
        logger.error(f"Failed to run morning brief job: {e}")

def _latest_price_cache_age_days():
    """Return age in days of the newest cached candle, or None when empty."""
    try:
        conn = database.get_db_connection()
        try:
            row = conn.execute("SELECT MAX(date) AS latest_date FROM historical_prices").fetchone()
        finally:
            conn.close()
        latest_value = row["latest_date"] if row else None
        if not latest_value:
            return None
        latest_day = date.fromisoformat(str(latest_value)[:10])
        return (date.today() - latest_day).days
    except Exception:
        return None

async def run_seed():
    """Seed database with Nifty 50 data when the price cache is too thin."""
    try:
        health_info = database.get_db_health()
        watchlist_count = int(health_info.get("watchlist_count") or 0)
        price_count = int(health_info.get("price_count") or 0)
        min_price_rows = max(600, watchlist_count * 60)
        latest_age_days = _latest_price_cache_age_days()
        is_stale = latest_age_days is None or latest_age_days > 4
        if watchlist_count == 0 or price_count < min_price_rows or is_stale:
            logger.info(
                "Database needs seed data. watchlist_count=%s price_count=%s min_price_rows=%s latest_age_days=%s",
                watchlist_count,
                price_count,
                min_price_rows,
                latest_age_days,
            )
            import sys, os
            sys.path.insert(0, os.path.dirname(
                os.path.dirname(__file__)))
            from scripts.data_seeder import main
            await asyncio.to_thread(main)
            logger.info("Seeding complete.")
            try:
                from src.daily_brief import get_daily_picks
                from src import auto_paper
                data = await asyncio.to_thread(get_daily_picks)
                MENTOR_PICKS_CACHE["data"] = data
                MENTOR_PICKS_CACHE["timestamp"] = time.time()
                await asyncio.to_thread(auto_paper.capture_daily_picks, data, None, 3, True)
                await asyncio.to_thread(auto_paper.evaluate_auto_paper_trades)
                logger.info("Daily Mentor cache and auto-paper evidence refreshed after seeding.")
            except Exception as refresh_exc:
                logger.warning(f"Failed to refresh mentor/auto-paper after seeding: {refresh_exc}")
    except Exception as e:
        logger.error(f"Seed failed: {e}", exc_info=True)

def run_seed_sync():
    from scripts.data_seeder import main
    main()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and scheduler on startup."""
    database.init_db()
    
    asyncio.create_task(run_seed())
    
    global MENTOR_PICKS_LOCK
    if MENTOR_PICKS_LOCK is None:
        MENTOR_PICKS_LOCK = asyncio.Lock()
    
    # Start live price stream, macro monitor, and news scraper swarm background workers
    from src.websocket_feed import start_price_feed, stop_price_feed
    from src.swarm import start_swarm, stop_swarm
    from src.macro_monitor import start_macro_monitor, stop_macro_monitor
    
    start_price_feed()
    start_macro_monitor()
    if _env_truthy("BULL_ENABLE_BACKGROUND_NEWS_SWARM"):
        start_swarm(interval_seconds=300)
    else:
        logger.info("Background news swarm is disabled. Set BULL_ENABLE_BACKGROUND_NEWS_SWARM=true to enable automatic watchlist scraping.")
    
    scheduler = BackgroundScheduler()
    scheduler.add_job(_nightly_sync_job, "cron", hour=18, minute=0)
    scheduler.add_job(_morning_mentor_job, "cron", hour=8, minute=0)
    scheduler.add_job(_intraday_news_job, "interval", minutes=2)
    scheduler.add_job(_data_health_job, "interval", minutes=30, id="data_health_job", replace_existing=True)
    scheduler.add_job(_data_vault_job, "interval", minutes=30, id="data_vault_job", replace_existing=True)
    scheduler.add_job(_auto_paper_job, "cron", hour=8, minute=10, id="auto_paper_morning_capture", replace_existing=True)
    scheduler.add_job(_auto_paper_job, "cron", hour=16, minute=10, id="auto_paper_after_close_eval", replace_existing=True)
    scheduler.add_job(_weekly_retraining_job, "cron", day_of_week="sat", hour=20, minute=0)
    scheduler.add_job(_morning_brief_job, "cron", day_of_week="mon-fri", hour=8, minute=45)
    scheduler.start()
    
    # Warm the mentor picks cache in the background on startup
    async def warm_cache():
        try:
            logger.info("Pre-warming Daily Mentor picks cache on startup...")
            async with MENTOR_PICKS_LOCK:
                from src.daily_brief import get_daily_picks
                data = await _run_sync(get_daily_picks)
                MENTOR_PICKS_CACHE["data"] = data
                MENTOR_PICKS_CACHE["timestamp"] = time.time()
                try:
                    from src import auto_paper
                    await _run_sync(auto_paper.capture_daily_picks, data, None, 3, False)
                    await _run_sync(auto_paper.sync_active_trade_prices)
                    await _run_sync(auto_paper.evaluate_auto_paper_trades)
                except Exception as auto_exc:
                    logger.warning(f"Auto paper warmup failed: {auto_exc}")
            logger.info("Daily Mentor picks cache warmed up successfully.")
        except Exception as e:
            logger.error(f"Failed to pre-warm Daily Mentor picks: {e}")
            
    asyncio.create_task(warm_cache())
    
    yield
    
    # Shutdown background workers gracefully
    stop_price_feed()
    stop_macro_monitor()
    stop_swarm()
    scheduler.shutdown()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="BULL Research Dashboard API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow everything for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===================================================================
#  API ROUTES — all defined BEFORE the static-files mount so they
#  take priority over the catch-all static file handler.
# ===================================================================


# ---- Health --------------------------------------------------------
@app.get("/api/health")
async def health():
    try:
        health_info = await _run_sync(database.get_db_health)

        # Per-ticker data density
        tickers = await _run_sync(database.get_watchlist_tickers)
        density = []
        latest_dates = []
        for t in tickers:
            df = await _run_sync(database.get_prices, t)
            latest_close = None
            if not df.empty and "close" in df.columns:
                latest_close = float(df["close"].iloc[-1])
                latest_dates.append(str(df["date"].max())[:10])
            density.append({
                "ticker": t,
                "rows": len(df),
                "total_days": len(df),
                "earliest": str(df["date"].min()) if not df.empty else None,
                "latest": str(df["date"].max()) if not df.empty else None,
                "last_date": str(df["date"].max()) if not df.empty else None,
                "last_close": latest_close,
            })
        health_info["ticker_density"] = density
        watchlist_count = int(health_info.get("watchlist_count", 0) or 0)
        price_count = int(health_info.get("price_count", 0) or 0)
        min_price_rows = max(600, watchlist_count * 60)
        latest_age_days = None
        if latest_dates:
            try:
                latest_day = max(date.fromisoformat(item) for item in latest_dates if item)
                latest_age_days = (date.today() - latest_day).days
            except Exception:
                latest_age_days = None
        health_info["min_price_rows_for_scanner"] = min_price_rows
        health_info["latest_price_age_days"] = latest_age_days
        health_info["seeded"] = (
            watchlist_count > 0
            and price_count >= min_price_rows
            and latest_age_days is not None
            and latest_age_days <= 4
        )
        return health_info
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

@app.post("/api/admin/seed")
async def force_seed(background_tasks: BackgroundTasks):
    """Force database seed."""
    background_tasks.add_task(run_seed_sync)
    return {"status": "seeding_started"}


# ---- Daily Brief / Mentor Picks -----------------------------------
@app.get("/api/daily-brief")
async def daily_brief():
    try:
        from src.daily_brief import build_daily_brief
        return await _run_sync(build_daily_brief)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/daily-brief/send")
async def send_daily_brief():
    try:
        from notifier import send_morning_brief
        sent = await _run_sync(send_morning_brief)
        return {"success": bool(sent)}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/mentor/picks")
async def mentor_picks():
    try:
        global MENTOR_PICKS_LOCK
        if MENTOR_PICKS_LOCK is None:
            MENTOR_PICKS_LOCK = asyncio.Lock()
            
        async with MENTOR_PICKS_LOCK:
            if MENTOR_PICKS_CACHE["data"] is not None and time.time() - MENTOR_PICKS_CACHE["timestamp"] < 300:
                return MENTOR_PICKS_CACHE["data"]
                
            from src.daily_brief import get_daily_picks
            picks = await _run_sync(get_daily_picks)
            MENTOR_PICKS_CACHE["data"] = picks
            MENTOR_PICKS_CACHE["timestamp"] = time.time()
            return picks
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Market Regime -------------------------------------------------
@app.get("/api/market/regime")
async def market_regime():
    try:
        regime = await _run_sync(market.get_market_regime)
        return regime
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

@app.get("/api/market/live-regime")
async def live_regime():
    return JSONResponse(GLOBAL_MACRO_REGIME)


@app.get("/api/market/status")
async def nse_market_status():
    try:
        from src.nse_feed import get_market_status
        return await _run_sync(get_market_status)
    except Exception as exc:
        return JSONResponse({"error": str(exc), "status": "UNKNOWN", "is_open": False}, status_code=200)


@app.get("/api/data/health")
async def data_health_summary():
    try:
        from src.data_health import get_data_health_summary
        return await _run_sync(get_data_health_summary, True)
    except Exception as exc:
        return JSONResponse({"error": str(exc), "ok": 0, "stale": 0, "missing": 0, "suspicious": 0, "rows": []}, status_code=200)


@app.post("/api/data/health/check")
async def run_data_health_check():
    try:
        from src.data_health import run_data_health_check
        return await _run_sync(run_data_health_check, None, False)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/data-vault/status")
async def data_vault_status():
    try:
        from src.data_vault import get_data_vault_status
        return await _run_sync(get_data_vault_status)
    except Exception as exc:
        return JSONResponse(
            {
                "error": str(exc),
                "verdict": "ERROR",
                "total_events": 0,
                "recent_events_24h": 0,
                "source_health": [],
                "event_counts_24h": [],
                "latest_events": [],
            },
            status_code=200,
        )


@app.post("/api/data-vault/refresh")
async def run_data_vault_refresh(
    limit: int = Query(12, ge=1, le=60),
    include_news: bool = Query(False),
):
    try:
        from src.data_vault import refresh_data_vault
        return await _run_sync(refresh_data_vault, None, limit, include_news)
    except Exception as exc:
        return JSONResponse({"error": str(exc), "status": "ERROR"}, status_code=500)


@app.get("/api/indices")
async def live_indices():
    try:
        from src.nse_feed import get_indices
        return await _run_sync(get_indices)
    except Exception as exc:
        return JSONResponse({"error": str(exc), "items": []}, status_code=200)


@app.get("/api/indices/stream")
async def stream_live_indices(request: Request):
    import json
    from src.nse_feed import get_indices

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                payload = await _run_sync(get_indices)
            except Exception as exc:
                payload = {"error": str(exc), "items": []}
            yield f"data: {json.dumps(payload, default=str)}\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/option-chain/{symbol}")
async def option_chain(symbol: str = "NIFTY"):
    try:
        from src.nse_feed import get_option_chain
        return await _run_sync(get_option_chain, symbol)
    except Exception as exc:
        return JSONResponse({"error": str(exc), "symbol": symbol.upper()}, status_code=200)


@app.get("/api/premarket")
async def premarket(force_refresh: bool = Query(False)):
    try:
        from src.premarket_signals import compute_premarket_score, get_premarket_score
        data = await _run_sync(compute_premarket_score if force_refresh else get_premarket_score)
        return {"status": "success", "data": data}
    except Exception as exc:
        return JSONResponse(
            {
                "status": "fallback",
                "error": str(exc),
                "data": {
                    "pre_market_score": 50.0,
                    "classification": "NEUTRAL_OPEN",
                    "recommendation": "Premarket data unavailable. Use strict technical triggers.",
                },
            },
            status_code=200,
        )


@app.get("/api/fii/latest")
async def latest_fii(force_refresh: bool = Query(False)):
    try:
        from src.fii_tracker import fetch_fii_dii_data, get_fii_signal
        if force_refresh:
            await _run_sync(fetch_fii_dii_data)
        return {"status": "success", "data": await _run_sync(get_fii_signal)}
    except Exception as exc:
        return JSONResponse(
            {
                "status": "fallback",
                "error": str(exc),
                "data": {
                    "fii_net": 0.0,
                    "dii_net": 0.0,
                    "market_impact": "NEUTRAL",
                    "action": "HOLD",
                    "source": "NONE",
                    "confidence": "LOW",
                    "signal_text": "FII/DII data unavailable.",
                },
            },
            status_code=200,
        )


@app.get("/api/fii/history")
async def fii_history(days: int = Query(30, ge=1, le=120)):
    try:
        from src.fii_tracker import get_fii_history
        return {"status": "success", "data": await _run_sync(get_fii_history, days)}
    except Exception as exc:
        return JSONResponse({"status": "fallback", "error": str(exc), "data": []}, status_code=200)

# ---- Market Neutral Pairs ------------------------------------------
@app.get("/api/pairs")
async def market_neutral_pairs():
    try:
        from src.pairs import find_correlated_pairs
        pairs = await _run_sync(find_correlated_pairs)
        return pairs
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Trade Ideas ---------------------------------------------------
@app.get("/api/ideas")
async def all_ideas():
    try:
        ideas = await _run_sync(engine.get_all_trade_ideas)
        return ideas
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/ideas/{ticker}")
async def single_idea(ticker: str):
    try:
        idea = await _run_sync(engine.generate_trade_idea, ticker)
        return idea
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Watchlist -----------------------------------------------------
@app.get("/api/watchlist")
async def get_watchlist():
    try:
        df = await _run_sync(database.get_watchlist)
        return df.to_dict(orient="records")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/watchlist")
async def add_watchlist(body: WatchlistAddBody):
    try:
        result = await _run_sync(fetcher.sync_ticker, body.ticker)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/api/watchlist/{ticker}")
async def remove_watchlist(ticker: str):
    try:
        await _run_sync(database.remove_from_watchlist, ticker)
        return {"success": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Sync ----------------------------------------------------------
@app.post("/api/sync/{ticker}")
async def sync_ticker(ticker: str):
    try:
        result = await _run_sync(fetcher.sync_ticker, ticker, "1y")
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/sync-all")
async def sync_all():
    try:
        tickers = await _run_sync(database.get_watchlist_tickers)
        results = []
        for t in tickers:
            try:
                res = await _run_sync(fetcher.sync_ticker, t, "1y")
                results.append({
                    "ticker": t,
                    "success": res.get("success", False),
                    "rows_synced": res.get("rows_synced", 0),
                })
            except Exception as inner_exc:
                results.append({
                    "ticker": t,
                    "success": False,
                    "rows_synced": 0,
                    "error": str(inner_exc),
                })
        return results
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Backtest (heavy) ----------------------------------------------
@app.get("/api/backtest/{ticker}")
async def run_backtest(ticker: str):
    try:
        result = await _run_sync(backtest.run_backtest, ticker)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Verdicts (heavy) ----------------------------------------------
@app.get("/api/verdicts")
async def verdicts():
    try:
        tickers = await _run_sync(database.get_watchlist_tickers)
        result = await _run_sync(backtest.get_all_stock_verdicts, tickers)
        return result
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- News -----------------------------------------------------------
@app.get("/api/news/{ticker}")
async def get_news(ticker: str):
    try:
        settings = await _run_sync(database.get_capital_settings)
        gemini_key = settings.get("gemini_api_key", "")
        items = await _run_sync(news.fetch_stock_news, ticker, gemini_key)
        return items
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/news-analyst/report")
async def news_analyst_report(force_refresh: bool = Query(False), limit: int = Query(12)):
    try:
        safe_limit = max(1, min(int(limit), 25))
        report = await _run_sync(news_analyst.build_daily_analyst_report, force_refresh, safe_limit)
        return report
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Capital Settings -----------------------------------------------
@app.get("/api/capital")
async def get_capital():
    try:
        settings = await _run_sync(database.get_capital_settings)
        return _mask_capital_settings(settings)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.put("/api/capital")
async def update_capital(body: CapitalSettingsBody):
    try:
        existing_settings = await _run_sync(database.get_capital_settings)
        await _run_sync(
            database.update_capital_settings,
            total_capital=body.total_capital,
            max_risk_per_trade=body.max_risk_per_trade,
            max_trades_per_day=body.max_trades_per_day,
            allow_options=body.allow_options,
            experience_level=body.experience_level,
            gemini_api_key=_credential_for_save(body.gemini_api_key, existing_settings.get("gemini_api_key", "")),
            dhan_client_id=_credential_for_save(body.dhan_client_id, existing_settings.get("dhan_client_id", "")),
            dhan_access_token=_credential_for_save(body.dhan_access_token, existing_settings.get("dhan_access_token", "")),
            kite_api_key=_credential_for_save(body.kite_api_key, existing_settings.get("kite_api_key", "")),
            kite_api_secret=_credential_for_save(body.kite_api_secret, existing_settings.get("kite_api_secret", "")),
            kite_request_token=_credential_for_save(body.kite_request_token, existing_settings.get("kite_request_token", "")),
            autopilot=body.autopilot,
        )
        return {"success": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Paper-Trade Journal --------------------------------------------
@app.get("/api/journal")
async def get_journal():
    try:
        df = await _run_sync(database.get_paper_trades)
        return df.to_dict(orient="records")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)

@app.get("/api/trades")
async def get_trades():
    try:
        from paper_broker import BULLPaperBroker
        broker = BULLPaperBroker(initial_capital=100000.0)
        return {"status": "success", "trades": broker.trades}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/journal/analytics")
async def journal_analytics():
    try:
        return await _run_sync(paper_analytics.get_paper_trade_analytics)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/auto-paper/summary")
async def auto_paper_summary():
    try:
        from src import auto_paper
        return await _run_sync(auto_paper.get_auto_paper_summary)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/auto-paper/run")
async def run_auto_paper():
    try:
        from src import auto_paper
        picks = MENTOR_PICKS_CACHE.get("data")
        if picks is None:
            from src.daily_brief import get_daily_picks
            picks = await _run_sync(get_daily_picks)
            MENTOR_PICKS_CACHE["data"] = picks
            MENTOR_PICKS_CACHE["timestamp"] = time.time()
        return await _run_sync(auto_paper.run_auto_paper_cycle, picks, 3, 5, True)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/journal")
async def add_journal_entry(body: PaperTradeBody):
    try:
        await _run_sync(
            database.add_paper_trade,
            body.ticker,
            body.trade_date,
            body.action,
            body.quantity,
            body.price,
            body.notes,
        )
        
        # Sync to trades_journal.json to keep skill_gate in sync
        try:
            from datetime import datetime
            from paper_broker import BULLPaperBroker
            broker = BULLPaperBroker(initial_capital=100000.0)
            from src.paper_broker import parse_targets_from_notes
            target_1, stop_loss = parse_targets_from_notes(body.notes)
            
            # Check if BUY or SELL
            if body.action.upper() == 'BUY':
                broker.trades.append({
                    "trade_id": len(broker.trades) + 1,
                    "ticker": body.ticker.upper(),
                    "status": "OPEN",
                    "entry_time": datetime.utcnow().isoformat() + "Z",
                    "exit_time": None,
                    "entry_price": body.price,
                    "exit_price": None,
                    "quantity": body.quantity,
                    "stop_loss": stop_loss or (body.price * 0.98),
                    "take_profit": target_1 or (body.price * 1.04),
                    "pnl": 0.0,
                    "r_multiple": 0.0
                })
                broker._save_data("trades_journal.json", broker.trades)
            elif body.action.upper() == 'SELL':
                for trade in broker.trades:
                    if trade["ticker"] == body.ticker.upper() and trade["status"] == "OPEN":
                        trade["status"] = "CLOSED"
                        trade["exit_price"] = body.price
                        trade["exit_time"] = datetime.utcnow().isoformat() + "Z"
                        pnl = (body.price - trade["entry_price"]) * trade["quantity"]
                        trade["pnl"] = round(pnl, 2)
                        risk = (trade["entry_price"] - trade["stop_loss"]) * trade["quantity"]
                        if risk > 0:
                            trade["r_multiple"] = round(pnl / risk, 2)
                        else:
                            trade["r_multiple"] = 0.0
                        break
                broker._save_data("trades_journal.json", broker.trades)
                
            # Log to signals_log.json
            broker.log_signal({
                "ticker": body.ticker.upper(),
                "price": body.price,
                "ml_score": 0.75,
                "rsi": 55.0,
                "rvol": 1.5,
                "stop_loss": stop_loss or (body.price * 0.98),
                "take_profit": target_1 or (body.price * 1.04),
                "watch_only": False,
                "action": body.action.upper(),
                "quantity": body.quantity,
                "notes": body.notes
            })
        except Exception as e:
            logger.warning(f"Failed to sync trade/signal to JSON files: {e}")
            
        return {"success": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Portfolio Holdings ---------------------------------------------
@app.get("/api/portfolio")
async def get_portfolio():
    try:
        holdings, total_realized_pnl = await _run_sync(database.get_portfolio_holdings)
        return {
            "holdings": holdings,
            "total_realized_pnl": total_realized_pnl,
        }
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Live Prices Stream ---------------------------------------------
@app.get("/api/prices/stream")
async def stream_prices_endpoint(request: Request):
    from fastapi.responses import StreamingResponse
    import json
    from src.websocket_feed import stream_prices
    
    async def event_generator():
        try:
            async for update in stream_prices():
                if await request.is_disconnected():
                    break
                yield f"data: {json.dumps(update)}\n\n"
        except asyncio.CancelledError:
            pass
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ---- Historical Prices ---------------------------------------------
@app.get("/api/prices/{ticker}")
async def get_prices(ticker: str):
    try:
        df = await _run_sync(database.get_prices, ticker)
        records = df.to_dict(orient="records")
        # Ensure datetime columns are JSON-serializable
        for rec in records:
            for key, val in rec.items():
                if hasattr(val, "isoformat"):
                    rec[key] = val.isoformat()
        return records
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Research Setups ------------------------------------------------
@app.get("/api/research/setups")
async def get_research_setups(date: Optional[str] = Query(None)):
    try:
        df = await _run_sync(database.get_research_setups, date)
        return df.to_dict(orient="records")
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


# ---- Market Universe -----------------------------------------------
@app.get("/api/universe")
async def universe_registry():
    """Return asset registry, skill gate, and opportunity counts."""
    return {"status": "success", "data": get_universe_payload(database.DB_PATH)}


@app.get("/api/universe/counts")
async def universe_counts():
    """Return 24-hour opportunity counts by asset class."""
    return {"status": "success", "counts": get_opportunity_counts(database.DB_PATH)}


@app.get("/api/universe/skill_gate")
async def universe_skill_gate():
    """Return the honest BULL skill gate state."""
    return {"status": "success", "skill_gate": compute_skill_gate(database.DB_PATH)}


@app.get("/api/fno/watchlist")
async def fno_watchlist(force_refresh: bool = False):
    """Return watch-only F&O and commodity setups."""
    return {"status": "success", "setups": scan_fno_watchlist(force_refresh=force_refresh)}


@app.post("/api/universe/scan_all")
async def universe_scan_all(background_tasks: BackgroundTasks):
    """Trigger full universe scan; Tier 2 remains watch-only."""
    background_tasks.add_task(scan_fno_watchlist, True)
    return {"status": "scheduled", "message": "Universe scan scheduled. Tier 2 remains WATCH only."}


# ---- Daily Lesson ---------------------------------------------------
@app.get("/api/daily-lesson")
def get_daily_lesson():
    from src.constants import DAILY_LESSONS
    from datetime import datetime, timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = utc_now.astimezone(kolkata_tz)
    day_of_year = now_ist.timetuple().tm_yday
    lesson = DAILY_LESSONS[day_of_year % len(DAILY_LESSONS)]
    return lesson


# ---- Morning Status -------------------------------------------------
@app.get("/api/morning-status")
def get_morning_status():
    from src.constants import is_nse_holiday
    from datetime import datetime, timezone, timedelta
    from paper_broker import BULLPaperBroker
    broker = BULLPaperBroker(initial_capital=100000.0)

    # Timezone-aware IST
    utc_now = datetime.now(timezone.utc)
    kolkata_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = utc_now.astimezone(kolkata_tz)

    # Calculate status
    # Weekday check: Mon=0, Sun=6
    if now_ist.weekday() >= 5 or is_nse_holiday(now_ist):
        status = "WEEKEND"
    else:
        # Market hours: 9:15 AM to 3:30 PM (IST)
        market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        if now_ist < market_start:
            status = "BEFORE_MARKET"
        elif now_ist <= market_end:
            status = "OPEN"
        else:
            status = "AFTER_MARKET"

    # Streak count and open trade count
    open_trade_count = len([t for t in broker.trades if t.get("status") == "OPEN"])

    # Calculate streak count
    dates = set()
    for t in broker.trades:
        t_time = t.get("entry_time") or t.get("trade_date")
        if t_time:
            try:
                dt = datetime.strptime(t_time[:10], "%Y-%m-%d").date()
                dates.add(dt)
            except Exception:
                pass

    streak_count = 0
    if dates:
        today_ist = now_ist.date()
        curr = today_ist
        if curr not in dates:
            curr = today_ist - timedelta(days=1)
            if curr not in dates:
                curr = None
        if curr is not None:
            while curr in dates:
                streak_count += 1
                curr -= timedelta(days=1)

    # Time until next market day / opening/closing time
    hours_left = 0
    mins_left = 0
    if status == "BEFORE_MARKET":
        market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
        diff = market_start - now_ist
        hours_left = diff.seconds // 3600
        mins_left = (diff.seconds % 3600) // 60
    elif status == "OPEN":
        market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
        diff = market_end - now_ist
        hours_left = diff.seconds // 3600
        mins_left = (diff.seconds % 3600) // 60

    # Also find last trade logged date/days ago
    last_trade_days_ago = -1
    if broker.trades:
        parsed_dates = []
        for t in broker.trades:
            t_time = t.get("entry_time") or t.get("trade_date")
            if t_time:
                try:
                    dt = datetime.strptime(t_time[:10], "%Y-%m-%d").date()
                    parsed_dates.append(dt)
                except Exception:
                    pass
        if parsed_dates:
            last_date = max(parsed_dates)
            last_trade_days_ago = (now_ist.date() - last_date).days

    # Suggestions/setups
    setup_ticker = None
    try:
        mentor_picks = MENTOR_PICKS_CACHE.get("data") or []
        trade_setups = [s for s in mentor_picks if s.get("decision") == "TRADE"]
        if trade_setups:
            setup_ticker = trade_setups[0]["ticker"].replace(".NS", "")
    except Exception:
        pass

    return {
        "status": status,
        "open_trade_count": open_trade_count,
        "streak_count": streak_count,
        "hours_left": hours_left,
        "mins_left": mins_left,
        "last_trade_days_ago": last_trade_days_ago,
        "setup_ticker": setup_ticker
    }


# ===================================================================
#  FRONTEND STATIC FILES  —  mounted AFTER all /api routes
# ===================================================================

# ---- Setup Wizard --------------------------------------------------
@app.get("/setup")
async def serve_setup():
    setup_path = os.path.join(FRONTEND_DIR, "setup.html")
    if os.path.isfile(setup_path):
        return FileResponse(
            setup_path,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
    return JSONResponse(
        {"error": "setup.html not found. Place setup.html in the frontend/ directory."},
        status_code=404,
    )


@app.get("/setup/detect_chat_id")
async def detect_chat_id(token: str):
    import requests
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        resp = await _run_sync(requests.get, url, timeout=8)
        if resp.status_code == 200:
            res_data = resp.json()
            if res_data.get("ok"):
                result = res_data.get("result", [])
                if result:
                    # Find the latest message to get chat id
                    for item in reversed(result):
                        message = item.get("message") or item.get("edited_message") or item.get("channel_post")
                        if message and "chat" in message:
                            return {"success": True, "chat_id": str(message["chat"]["id"])}
                return {"success": False, "error": "No messages found. Please message your bot first."}
            return {"success": False, "error": f"Telegram API error: {res_data.get('description')}"}
        return {"success": False, "error": f"HTTP error {resp.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Connection error: {str(e)}"}


@app.post("/setup/test_message")
async def setup_test_message(body: TelegramSetupBody):
    import requests
    url = f"https://api.telegram.org/bot{body.token}/sendMessage"
    payload = {
        "chat_id": body.chat_id,
        "text": "🐂 BULL is connected. Good morning.",
        "parse_mode": "Markdown"
    }
    try:
        resp = await _run_sync(requests.post, url, json=payload, timeout=8)
        if resp.status_code == 200:
            return {"success": True}
        return {"success": False, "error": resp.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/setup/save")
async def setup_save_config(body: TelegramSetupBody):
    try:
        env_path = os.path.join(PROJECT_ROOT, ".env")
        # Write to .env
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"TELEGRAM_BOT_TOKEN={body.token}\n")
            f.write(f"TELEGRAM_CHAT_ID={body.chat_id}\n")
        
        # Load into os.environ immediately
        os.environ["TELEGRAM_BOT_TOKEN"] = body.token
        os.environ["TELEGRAM_CHAT_ID"] = body.chat_id
        
        # Also sync notifier in-memory token config
        from notifier import load_env_file as reload_notifier_env
        reload_notifier_env()
        
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


# Root path → serve index.html
@app.get("/")
async def serve_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
    return JSONResponse(
        {"error": "Frontend not found. Place index.html in the frontend/ directory."},
        status_code=404,
    )


# Mount static files only if the directory exists (avoids crash on startup)
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


# ===================================================================
#  Direct execution:  python -m api.server   or   python api/server.py
# ===================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
