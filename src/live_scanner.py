"""Live market-hours scanning engine for BULL.

Runs a background loop during Indian market hours (9:15 AM – 3:30 PM IST,
Mon–Fri).  Each 2-minute cycle:

1. Polls live quotes for the watchlist / core universe.
2. Fast-filters on volume spike, near-breakout price, and RSI sweet spot.
3. For passing stocks, fires the BullAgent (Gemini) for a full AI analysis.
4. If the agent says TRADE with confidence >= 65, sends a Telegram alert.
5. Deduplicates alerts within the same trading day.
6. Logs every AI pick for the track record.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, time as dt_time
from typing import Any

import pandas as pd
from zoneinfo import ZoneInfo

from src import database, nse_feed
from src.engine import calculate_rsi, calculate_atr
from src.daily_brief import _metadata_map, CORE_UNIVERSE

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

# Market hours
_MARKET_OPEN = dt_time(9, 15)
_MARKET_CLOSE = dt_time(15, 30)

# Scanner thresholds
VOLUME_SPIKE_THRESHOLD = 1.5   # > 1.5x 20-day avg volume
BREAKOUT_PROXIMITY_PCT = 1.0   # within 1% of 20-day high
RSI_LOW = 45
RSI_HIGH = 70
ALERT_CONFIDENCE_MIN = 65

# Module-level state
_scanner_state: dict[str, Any] = {
    "running": False,
    "last_scan_time": None,
    "alerts_today": 0,
    "stocks_scanned": 0,
    "alerted_today": set(),        # tickers already alerted today
    "alert_date": None,            # date string for dedup reset
    "picks_today": [],             # all AI picks this session
}


# ---------------------------------------------------------------------------
# Timezone / market hours
# ---------------------------------------------------------------------------

def is_market_hours(now: datetime | None = None) -> bool:
    """Return True if *now* falls within 9:15–15:30 IST on a weekday."""
    if now is None:
        now = datetime.now(IST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    else:
        now = now.astimezone(IST)

    # Mon=0 … Fri=4
    if now.weekday() > 4:
        return False

    current_time = now.time()
    return _MARKET_OPEN <= current_time <= _MARKET_CLOSE


# ---------------------------------------------------------------------------
# Fast quantitative filter
# ---------------------------------------------------------------------------

def _prepare_technicals(df: pd.DataFrame) -> pd.DataFrame | None:
    """Add RSI, volume avg, and 20-day high columns.  Returns None on bad data."""
    if df is None or len(df) < 25:
        return None
    df = df.copy()
    if "date" not in df.columns and "Date" in df.columns:
        df = df.rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    if len(df) < 25:
        return None

    df["rsi_14"] = calculate_rsi(df["close"])
    df["vol_avg_20"] = df["volume"].rolling(20).mean()
    df["high_20"] = df["high"].rolling(20).max()
    return df


def fast_volume_breakout_filter(
    ticker: str,
    df: pd.DataFrame,
    live_quote: dict[str, Any],
) -> bool:
    """Quick check: does this stock deserve an AI deep-dive right now?

    Criteria (all must pass):
      - Today's volume > 1.5× 20-day average
      - Price within 1% of the 20-day high (potential breakout)
      - RSI between 45–70 (momentum sweet spot, not overbought)
    """
    prepped = _prepare_technicals(df)
    if prepped is None:
        return False

    latest = prepped.iloc[-1]

    # Volume check: use live volume if available, else latest candle
    live_volume = live_quote.get("volume", 0) or 0
    candle_volume = float(latest["volume"]) if not pd.isna(latest["volume"]) else 0
    volume = max(live_volume, candle_volume)
    vol_avg = float(latest["vol_avg_20"]) if not pd.isna(latest["vol_avg_20"]) else 0
    if vol_avg <= 0:
        return False
    volume_ratio = volume / vol_avg
    if volume_ratio < VOLUME_SPIKE_THRESHOLD:
        return False

    # Price near 20-day high
    live_price = float(live_quote.get("last_price", 0) or 0)
    if live_price <= 0:
        live_price = float(latest["close"])
    high_20 = float(latest["high_20"]) if not pd.isna(latest["high_20"]) else float(latest["close"])
    if high_20 <= 0:
        return False
    distance_pct = ((high_20 - live_price) / high_20) * 100
    if distance_pct > BREAKOUT_PROXIMITY_PCT:
        return False

    # RSI sweet spot
    rsi = float(latest["rsi_14"]) if not pd.isna(latest["rsi_14"]) else 50.0
    if not (RSI_LOW <= rsi <= RSI_HIGH):
        return False

    logger.info(
        "[scanner] %s passes fast filter: vol_ratio=%.2f, dist_to_20d_high=%.2f%%, rsi=%.1f",
        ticker, volume_ratio, distance_pct, rsi,
    )
    return True


# ---------------------------------------------------------------------------
# Telegram alert
# ---------------------------------------------------------------------------

def _get_telegram_config() -> tuple[str, str]:
    """Load Telegram bot token and chat ID from environment."""
    # Try notifier's env loader first
    try:
        from notifier import load_env_file
        load_env_file()
    except Exception:
        pass
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    return token, chat_id


def send_telegram_alert(pick: dict[str, Any]) -> bool:
    """Format an AI pick and send it to Telegram.  Returns True on success."""
    token, chat_id = _get_telegram_config()
    if not token or not chat_id:
        logger.warning("[scanner] Telegram not configured — skipping alert")
        return False

    ticker = pick.get("ticker", "?")
    decision = pick.get("decision", "?")
    confidence = pick.get("confidence_score", 0)
    entry = pick.get("entry_trigger", 0)
    stop = pick.get("stop_loss", 0)
    t1 = pick.get("target_1", 0)
    t2 = pick.get("target_2", 0)
    setup = pick.get("setup_type", "")
    reasoning = pick.get("agent_reasoning", "")
    rr = pick.get("risk_reward_ratio", 0)
    reasons = pick.get("reasons", [])

    reasons_text = "\n".join(f"  • {r}" for r in reasons[:4]) if reasons else "  (none)"

    message = (
        f"🔔 *BULL Live Scanner Alert*\n\n"
        f"📈 *{ticker}* — {decision} ({confidence}% confidence)\n"
        f"Setup: {setup}\n\n"
        f"💰 Entry: ₹{entry:.2f}\n"
        f"🛑 Stop: ₹{stop:.2f}\n"
        f"🎯 T1: ₹{t1:.2f} | T2: ₹{t2:.2f}\n"
        f"📊 R:R = {rr:.1f}\n\n"
        f"*Reasons:*\n{reasons_text}\n\n"
        f"_{reasoning}_\n\n"
        f"⏰ {datetime.now(IST).strftime('%H:%M IST')}"
    )

    import requests
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code == 200:
            logger.info("[scanner] Telegram alert sent for %s", ticker)
            return True
        else:
            logger.warning("[scanner] Telegram returned %s: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as exc:
        logger.error("[scanner] Telegram send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# AI deep-dive via BullAgent
# ---------------------------------------------------------------------------

def _run_ai_analysis(ticker: str, df: pd.DataFrame) -> dict[str, Any] | None:
    """Call BullAgent for a full AI analysis.  Returns the agent pick or None."""
    try:
        from src.bull_agent import build_agent_context, analyze_stock

        meta = _metadata_map().get(ticker.upper())
        context = build_agent_context(
            ticker=ticker,
            df=df,
            company_name=meta.name if meta else None,
            sector=meta.sector if meta else None,
        )
        if context.get("insufficient_data"):
            return None

        result = analyze_stock(context)
        if result:
            result["ticker"] = ticker
        return result
    except Exception as exc:
        logger.error("[scanner] AI analysis failed for %s: %s", ticker, exc)
        return None


# ---------------------------------------------------------------------------
# Track-record logging
# ---------------------------------------------------------------------------

def _log_pick(pick: dict[str, Any]) -> None:
    """Record an AI pick.  Uses src.track_record if available, else just logs."""
    try:
        from src.track_record import record_pick
        record_pick(pick)
        return
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("[scanner] track_record.record_pick failed: %s", exc)

    logger.info(
        "[scanner] AI pick: %s %s confidence=%s entry=%.2f stop=%.2f target=%.2f",
        pick.get("ticker"), pick.get("decision"), pick.get("confidence_score"),
        pick.get("entry_trigger", 0), pick.get("stop_loss", 0), pick.get("target_1", 0),
    )


# ---------------------------------------------------------------------------
# Deduplication helpers
# ---------------------------------------------------------------------------

def _reset_daily_state_if_needed() -> None:
    """Clear the alerted set when the calendar date changes."""
    today = datetime.now(IST).strftime("%Y-%m-%d")
    if _scanner_state["alert_date"] != today:
        _scanner_state["alerted_today"] = set()
        _scanner_state["alerts_today"] = 0
        _scanner_state["picks_today"] = []
        _scanner_state["alert_date"] = today
        logger.info("[scanner] New trading day %s — dedup state reset", today)


def _already_alerted(ticker: str) -> bool:
    return ticker.upper() in _scanner_state["alerted_today"]


def _mark_alerted(ticker: str) -> None:
    _scanner_state["alerted_today"].add(ticker.upper())
    _scanner_state["alerts_today"] += 1


# ---------------------------------------------------------------------------
# Single scan cycle
# ---------------------------------------------------------------------------

def run_scan_cycle(tickers: list[str]) -> list[dict[str, Any]]:
    """Run one full scan cycle.  Returns list of new picks that triggered alerts."""
    _reset_daily_state_if_needed()
    new_picks: list[dict[str, Any]] = []
    scanned = 0

    for ticker in tickers:
        try:
            # 1. Skip if already alerted today
            if _already_alerted(ticker):
                continue

            # 2. Get stored daily candles
            df = database.get_prices(ticker)
            if df is None or df.empty:
                continue

            # 3. Get live quote (use tight cache for scanner freshness)
            quote = nse_feed.get_quote(ticker, cache_seconds=30)
            if quote.get("error") or quote.get("status") == "NO_DATA":
                continue

            scanned += 1

            # 4. Fast filter
            if not fast_volume_breakout_filter(ticker, df, quote):
                continue

            logger.info("[scanner] %s passed fast filter — running AI analysis", ticker)

            # 5. AI deep-dive
            ai_pick = _run_ai_analysis(ticker, df)
            if ai_pick is None:
                logger.debug("[scanner] %s: AI returned nothing (fallback unavailable)", ticker)
                continue

            # Stamp the live price into the pick
            ai_pick["live_price"] = quote.get("last_price")
            ai_pick["scan_time"] = datetime.now(IST).isoformat(timespec="seconds")

            # Log every AI pick regardless of decision
            _log_pick(ai_pick)
            _scanner_state["picks_today"].append(ai_pick)

            # 6. Alert if TRADE with high confidence
            decision = str(ai_pick.get("decision", "")).upper()
            confidence = int(ai_pick.get("confidence_score", 0))

            if decision == "TRADE" and confidence >= ALERT_CONFIDENCE_MIN:
                sent = send_telegram_alert(ai_pick)
                if sent:
                    _mark_alerted(ticker)
                new_picks.append(ai_pick)
                logger.info(
                    "[scanner] 🚨 ALERT: %s — %s (%d%% confidence) entry=%.2f",
                    ticker, decision, confidence, ai_pick.get("entry_trigger", 0),
                )
            else:
                logger.info(
                    "[scanner] %s — %s (%d%% confidence), below alert threshold",
                    ticker, decision, confidence,
                )

        except Exception as exc:
            logger.error("[scanner] Error scanning %s: %s", ticker, exc, exc_info=True)

    _scanner_state["stocks_scanned"] = scanned
    _scanner_state["last_scan_time"] = datetime.now(IST).isoformat(timespec="seconds")
    return new_picks


# ---------------------------------------------------------------------------
# Default ticker list
# ---------------------------------------------------------------------------

def _default_tickers() -> list[str]:
    """Return the scanner ticker list: core universe + watchlist extras."""
    tickers = [item.ticker for item in CORE_UNIVERSE]
    try:
        watchlist = [t.upper() for t in database.get_watchlist_tickers()]
        known = set(tickers)
        index_symbols = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
        extras = [t for t in watchlist if t not in known and t not in index_symbols]
        tickers.extend(extras)
    except Exception:
        pass
    return tickers


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_live_scanner_loop(
    tickers: list[str] | None = None,
    interval_seconds: int = 120,
) -> None:
    """Main scanner loop — runs during market hours, sleeps otherwise.

    This function blocks forever (intended for a background thread or process).
    It handles all exceptions internally and never crashes.
    """
    if tickers is None:
        tickers = _default_tickers()

    logger.info("[scanner] Starting live scanner loop with %d tickers, interval=%ds", len(tickers), interval_seconds)
    _scanner_state["running"] = True

    try:
        while True:
            try:
                now = datetime.now(IST)

                if not is_market_hours(now):
                    _scanner_state["running"] = False
                    # Sleep longer outside market hours
                    next_check_seconds = 60
                    # If before market open today (weekday), calculate exact wait
                    if now.weekday() < 5:
                        market_open_today = now.replace(
                            hour=9, minute=15, second=0, microsecond=0,
                        )
                        if now < market_open_today:
                            wait = (market_open_today - now).total_seconds()
                            next_check_seconds = min(wait + 5, 300)
                        else:
                            # After market close — sleep 5 min and re-check
                            next_check_seconds = 300
                    else:
                        # Weekend
                        next_check_seconds = 300

                    logger.debug(
                        "[scanner] Outside market hours (%s). Sleeping %ds.",
                        now.strftime("%H:%M IST %A"), next_check_seconds,
                    )
                    time.sleep(next_check_seconds)
                    continue

                _scanner_state["running"] = True
                logger.info("[scanner] === Scan cycle starting at %s ===", now.strftime("%H:%M:%S IST"))

                picks = run_scan_cycle(tickers)
                if picks:
                    logger.info("[scanner] Cycle complete: %d new alert(s)", len(picks))
                else:
                    logger.info("[scanner] Cycle complete: no new alerts")

            except Exception as exc:
                logger.error("[scanner] Scan cycle crashed (will retry): %s", exc, exc_info=True)

            time.sleep(interval_seconds)

    except KeyboardInterrupt:
        logger.info("[scanner] Stopped by keyboard interrupt")
    finally:
        _scanner_state["running"] = False
        logger.info("[scanner] Live scanner loop exited")


# ---------------------------------------------------------------------------
# Status API (for server integration)
# ---------------------------------------------------------------------------

def get_scanner_status() -> dict[str, Any]:
    """Return current scanner state for the API layer."""
    return {
        "running": _scanner_state["running"],
        "last_scan_time": _scanner_state["last_scan_time"],
        "alerts_today": _scanner_state["alerts_today"],
        "stocks_scanned": _scanner_state["stocks_scanned"],
        "alerted_tickers": sorted(_scanner_state["alerted_today"]),
        "picks_today_count": len(_scanner_state["picks_today"]),
        "alert_date": _scanner_state["alert_date"],
    }


def get_picks_today() -> list[dict[str, Any]]:
    """Return all AI picks from today's scanning session."""
    return list(_scanner_state["picks_today"])
