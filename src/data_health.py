"""Data quality monitor for BULL's market universe."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src import database
from src.news import fetch_stock_news
from src.nse_feed import get_quote
from src.universe_engine import get_asset_registry


IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN_MINUTE = 9 * 60 + 15
MARKET_CLOSE_MINUTE = 15 * 60 + 30


def ensure_data_health_table() -> None:
    """Create the data health table."""
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_health (
                ticker TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_update TEXT,
                note TEXT,
                checked_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_universe_tickers(limit: int | None = None) -> list[str]:
    """Return equity and ETF tickers from the universe registry."""
    tickers: list[str] = []
    for asset in get_asset_registry():
        if not asset.get("scan_enabled"):
            continue
        if int(asset.get("tier") or 0) > 1:
            continue
        for ticker in asset.get("instruments", []):
            if isinstance(ticker, str) and ticker.endswith(".NS") and ticker not in tickers:
                tickers.append(ticker)
    return tickers[:limit] if limit else tickers


def is_market_hours(now: datetime | None = None) -> bool:
    """Return True during NSE regular market hours."""
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    local = now.astimezone(IST)
    if local.weekday() >= 5:
        return False
    minute = local.hour * 60 + local.minute
    return MARKET_OPEN_MINUTE <= minute <= MARKET_CLOSE_MINUTE


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse a timestamp safely."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed.astimezone(IST)
    except Exception:
        return None


def _has_recent_historical_data(ticker: str, now: datetime | None = None) -> bool:
    """Check whether the daily price cache has a recent trading row."""
    now = now or datetime.now(IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IST)
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            "SELECT MAX(date) AS last_date FROM historical_prices WHERE ticker = ?",
            (ticker,),
        ).fetchone()
    finally:
        conn.close()
    if not row or not row["last_date"]:
        return False
    try:
        last_date = datetime.fromisoformat(str(row["last_date"])).date()
    except Exception:
        return False
    return (now.astimezone(IST).date() - last_date).days <= 4


def classify_ticker_health(
    ticker: str,
    quote: dict[str, Any] | None,
    news_items: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
    has_recent_history: bool = True,
) -> dict[str, str | None]:
    """Classify one ticker as OK, STALE, MISSING, or SUSPICIOUS."""
    checked_dt = (now or datetime.now(IST)).astimezone(IST)
    checked_at = checked_dt.isoformat(timespec="seconds")
    if not quote or quote.get("status") == "NO_DATA" or quote.get("last_price") in (None, 0):
        return {
            "ticker": ticker,
            "status": "MISSING",
            "last_update": quote.get("last_update") if quote else None,
            "note": "No quote returned by NSE or fallback feed.",
            "checked_at": checked_at,
        }

    last_update = quote.get("last_update") or quote.get("timestamp") or quote.get("fetched_at")
    parsed_update = _parse_timestamp(last_update)
    if is_market_hours(now) and parsed_update:
        age_minutes = (checked_dt - parsed_update).total_seconds() / 60
        if age_minutes > 20:
            return {
                "ticker": ticker,
                "status": "STALE",
                "last_update": parsed_update.isoformat(timespec="seconds"),
                "note": f"Last quote is {age_minutes:.1f} minutes old during market hours.",
                "checked_at": checked_at,
            }

    if not has_recent_history:
        return {
            "ticker": ticker,
            "status": "MISSING",
            "last_update": last_update,
            "note": "No daily candle found in the last two trading sessions.",
            "checked_at": checked_at,
        }

    change_percent = abs(float(quote.get("change_percent") or quote.get("pChange") or 0))
    if change_percent > 15 and not news_items:
        return {
            "ticker": ticker,
            "status": "SUSPICIOUS",
            "last_update": last_update,
            "note": f"Price moved {change_percent:.1f}% but no related headline was cached.",
            "checked_at": checked_at,
        }

    return {
        "ticker": ticker,
        "status": "OK",
        "last_update": last_update,
        "note": f"{quote.get('source', 'feed')} quote passed sanity checks.",
        "checked_at": checked_at,
    }


def store_health_rows(rows: list[dict[str, Any]]) -> None:
    """Store ticker health rows in SQLite."""
    ensure_data_health_table()
    conn = database.get_db_connection()
    try:
        conn.executemany(
            """
            INSERT OR REPLACE INTO data_health (ticker, status, last_update, note, checked_at)
            VALUES (:ticker, :status, :last_update, :note, :checked_at)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def run_data_health_check(tickers: list[str] | None = None, include_news: bool = True) -> dict[str, Any]:
    """Run the data quality audit for the tracked universe."""
    ensure_data_health_table()
    database.init_db()
    symbols = tickers or get_universe_tickers()
    now = datetime.now(IST)
    rows: list[dict[str, Any]] = []
    for ticker in symbols:
        try:
            quote = get_quote(ticker)
        except Exception as exc:
            quote = {"status": "NO_DATA", "last_update": None, "error": str(exc)}
        if include_news:
            try:
                news_items = fetch_stock_news(ticker, gemini_api_key=None, force_refresh=False)[:3]
            except Exception:
                news_items = []
        else:
            news_items = [{"title": "News check skipped for fast UI health seed."}]
        recent_history = _has_recent_historical_data(ticker, now)
        rows.append(classify_ticker_health(ticker, quote, news_items, now, recent_history))
    store_health_rows(rows)
    return get_data_health_summary()


def get_data_health_rows() -> list[dict[str, Any]]:
    """Return the latest per-ticker data health rows."""
    ensure_data_health_table()
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            "SELECT ticker, status, last_update, note, checked_at FROM data_health ORDER BY ticker ASC"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_data_health_summary(run_if_empty: bool = False) -> dict[str, Any]:
    """Return a compact data health summary plus rows."""
    rows = get_data_health_rows()
    if run_if_empty and not rows:
        rows = run_data_health_check(get_universe_tickers(limit=8), include_news=False).get("rows", [])
    counts = Counter(str(row.get("status", "")).upper() for row in rows)
    last_check = max((row.get("checked_at") for row in rows if row.get("checked_at")), default=None)
    total = len(rows)
    return {
        "ok": counts.get("OK", 0),
        "stale": counts.get("STALE", 0),
        "missing": counts.get("MISSING", 0),
        "suspicious": counts.get("SUSPICIOUS", 0),
        "total": total,
        "last_check": last_check,
        "rows": rows,
    }


def stale_cutoff_reference(now: datetime | None = None) -> datetime:
    """Return the timestamp that separates fresh and stale market-hour quotes."""
    local = (now or datetime.now(IST)).astimezone(IST)
    return local - timedelta(minutes=20)
