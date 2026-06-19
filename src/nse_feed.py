"""NSE public endpoint adapter with SQLite caching and yFinance fallback."""

from __future__ import annotations

from datetime import datetime
import json
import time
from typing import Any, Callable
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
import yfinance as yf

from src import database


NSE_HOME = "https://www.nseindia.com"
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
}
CACHE_SECONDS = 180
IST = ZoneInfo("Asia/Kolkata")

_SESSION = requests.Session()
_SESSION.headers.update(NSE_HEADERS)
_COOKIE_TS = 0.0
_NSE_BLOCKED_UNTIL = 0.0
_NSE_BLOCK_SECONDS = 600


def _now_iso() -> str:
    """Return the current local ISO timestamp."""
    return datetime.now().isoformat(timespec="seconds")


def ensure_cache_table() -> None:
    """Create the NSE endpoint cache table."""
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS nse_cache (
                cache_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                fetched_at REAL NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _cache_get(cache_key: str, allow_stale: bool = False, max_age_seconds: int = CACHE_SECONDS) -> dict[str, Any] | None:
    """Return cached payload when fresh, or stale when explicitly allowed."""
    ensure_cache_table()
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            "SELECT payload, fetched_at FROM nse_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    if not allow_stale and time.time() - float(row["fetched_at"]) > max_age_seconds:
        return None
    try:
        payload = json.loads(row["payload"])
        payload.setdefault("cache_age_seconds", round(time.time() - float(row["fetched_at"]), 1))
        return payload
    except Exception:
        return None


def _cache_set(cache_key: str, payload: dict[str, Any]) -> None:
    """Persist a JSON payload in SQLite."""
    ensure_cache_table()
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO nse_cache (cache_key, payload, fetched_at)
            VALUES (?, ?, ?)
            """,
            (cache_key, json.dumps(payload, default=str), time.time()),
        )
        conn.commit()
    finally:
        conn.close()


def _prime_session(force: bool = False) -> None:
    """Refresh NSE cookies before API calls."""
    global _COOKIE_TS
    if not force and time.time() - _COOKIE_TS < 600:
        return
    response = _SESSION.get(NSE_HOME, timeout=8)
    response.raise_for_status()
    _COOKIE_TS = time.time()


def _request_json(
    path: str,
    cache_key: str,
    fallback: Callable[[], dict[str, Any]] | None = None,
    cache_seconds: int = CACHE_SECONDS,
) -> dict[str, Any]:
    """Fetch JSON through NSE session, retry once, cache, then fall back safely."""
    global _NSE_BLOCKED_UNTIL
    cached = _cache_get(cache_key, max_age_seconds=cache_seconds)
    if cached is not None:
        cached["from_cache"] = True
        return cached

    if fallback and time.time() < _NSE_BLOCKED_UNTIL:
        payload = fallback()
        payload.setdefault("fetch_error", "NSE public endpoints recently blocked this client; using fallback feed.")
        _cache_set(cache_key, payload)
        return payload

    url = path if path.startswith("http") else f"{NSE_HOME}{path}"
    errors: list[str] = []
    for attempt in range(2):
        try:
            _prime_session(force=attempt > 0)
            response = _SESSION.get(url, timeout=12)
            if response.status_code != 200:
                raise RuntimeError(f"NSE returned HTTP {response.status_code}")
            payload = response.json()
            _cache_set(cache_key, payload)
            return payload
        except Exception as exc:
            errors.append(str(exc))
            if "403" in str(exc) or "Forbidden" in str(exc):
                _NSE_BLOCKED_UNTIL = time.time() + _NSE_BLOCK_SECONDS
            if attempt == 0:
                time.sleep(2)

    if fallback:
        payload = fallback()
        payload.setdefault("fetch_error", " | ".join(errors[-2:]))
        _cache_set(cache_key, payload)
        return payload
    stale = _cache_get(cache_key, allow_stale=True)
    if stale is not None:
        stale["from_stale_cache"] = True
        stale["fetch_error"] = " | ".join(errors[-2:])
        return stale
    return {"error": " | ".join(errors[-2:]), "source": "NSE unavailable"}


def _clean_symbol(symbol: str) -> str:
    """Convert app symbols such as RELIANCE.NS into NSE symbols."""
    return symbol.upper().replace(".NS", "").replace(".BO", "").strip()


def _flatten_yf_history(history):
    if hasattr(history, "columns") and getattr(history.columns, "nlevels", 1) > 1:
        history = history.copy()
        history.columns = history.columns.droplevel(1)
    return history


def _yf_symbol(symbol: str) -> str:
    return symbol if symbol.startswith("^") or symbol.endswith((".NS", ".BO", "=X", "=F")) else f"{symbol}.NS"


def _timestamp_age_minutes(ts: Any) -> tuple[str | None, float | None]:
    try:
        dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=IST)
        else:
            dt = dt.astimezone(IST)
        age = max(0.0, (datetime.now(IST) - dt).total_seconds() / 60)
        return dt.isoformat(timespec="seconds"), round(age, 1)
    except Exception:
        return None, None


def _yf_intraday_quote(symbol: str) -> dict[str, Any] | None:
    """Return the freshest free Yahoo 1-minute quote we can get."""
    yf_symbol = _yf_symbol(symbol)
    try:
        history = yf.download(
            yf_symbol,
            period="1d",
            interval="1m",
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=6,
        )
        history = _flatten_yf_history(history)
        if history.empty:
            return None
        history = history.dropna(subset=["Close"])
        if history.empty:
            return None
        latest = history.iloc[-1]
        previous = history.iloc[-2] if len(history) > 1 else history.iloc[0]
        price = float(latest["Close"])
        prev_close = float(previous["Close"]) or price
        change = price - prev_close
        bar_timestamp, quote_lag_minutes = _timestamp_age_minutes(history.index[-1])
        return {
            "symbol": symbol,
            "last_price": round(price, 2),
            "change": round(change, 2),
            "change_percent": round((change / prev_close) * 100, 2) if prev_close else 0.0,
            "volume": int(latest.get("Volume", 0) or 0),
            "week_high": None,
            "week_low": None,
            "delivery_percent": None,
            "source": "yfinance_intraday_fallback",
            "last_update": bar_timestamp or _now_iso(),
            "bar_timestamp": bar_timestamp,
            "quote_lag_minutes": quote_lag_minutes,
            "quality": "FREE_INTRADAY_FALLBACK",
            "fetched_at": _now_iso(),
        }
    except Exception:
        return None


def _yf_daily_quote(symbol: str) -> dict[str, Any]:
    """Last-resort daily yFinance quote. Not acceptable for live intraday paper fills."""
    yf_symbol = _yf_symbol(symbol)
    history = yf.download(
        yf_symbol,
        period="5d",
        interval="1d",
        progress=False,
        auto_adjust=False,
        threads=False,
        timeout=6,
    )
    history = _flatten_yf_history(history)
    if history.empty:
        return {"symbol": symbol, "status": "NO_DATA", "source": "yfinance_fallback", "fetched_at": _now_iso()}
    latest = history.iloc[-1]
    previous = history.iloc[-2] if len(history) > 1 else latest
    price = float(latest["Close"])
    prev_close = float(previous["Close"]) or price
    change = price - prev_close
    return {
        "symbol": symbol,
        "last_price": round(price, 2),
        "change": round(change, 2),
        "change_percent": round((change / prev_close) * 100, 2) if prev_close else 0.0,
        "volume": int(latest.get("Volume", 0) or 0),
        "week_high": None,
        "week_low": None,
        "delivery_percent": None,
        "source": "yfinance_fallback",
        "quality": "DAILY_DELAYED_FALLBACK",
        "last_update": _now_iso(),
        "fetched_at": _now_iso(),
    }


def _yf_quote(symbol: str) -> dict[str, Any]:
    """Fallback quote from yFinance, preferring 1-minute bars over daily candles."""
    try:
        intraday = _yf_intraday_quote(symbol)
        if intraday:
            return intraday
        return _yf_daily_quote(symbol)
    except Exception as exc:
        return {"symbol": symbol, "status": "NO_DATA", "error": str(exc), "source": "yfinance_fallback", "fetched_at": _now_iso()}


def get_quote(symbol: str, cache_seconds: int = CACHE_SECONDS) -> dict[str, Any]:
    """Return live-ish quote data for one NSE equity symbol."""
    nse_symbol = _clean_symbol(symbol)

    def fallback() -> dict[str, Any]:
        return _yf_quote(symbol)

    raw = _request_json(
        f"/api/quote-equity?symbol={quote(nse_symbol)}",
        f"quote:{nse_symbol}",
        fallback=fallback,
        cache_seconds=cache_seconds,
    )
    if "priceInfo" not in raw:
        return raw

    price = raw.get("priceInfo", {}) or {}
    security = raw.get("securityWiseDP", {}) or {}
    market = raw.get("marketDeptOrderBook", {}) or {}
    trade_info = market.get("tradeInfo", {}) if isinstance(market, dict) else {}
    return {
        "symbol": symbol,
        "nse_symbol": nse_symbol,
        "last_price": float(price.get("lastPrice") or 0),
        "change": float(price.get("change") or 0),
        "change_percent": float(price.get("pChange") or 0),
        "volume": int(trade_info.get("totalTradedVolume") or raw.get("totalTradedVolume") or 0),
        "week_high": price.get("weekHighLow", {}).get("max") if isinstance(price.get("weekHighLow"), dict) else None,
        "week_low": price.get("weekHighLow", {}).get("min") if isinstance(price.get("weekHighLow"), dict) else None,
        "delivery_percent": security.get("deliveryToTradedQuantity"),
        "source": "nse_public",
        "last_update": _now_iso(),
        "fetched_at": _now_iso(),
    }


def _fallback_market_status() -> dict[str, Any]:
    """Fallback market status from local IST clock."""
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    minutes = now.hour * 60 + now.minute
    is_weekday = now.weekday() < 5
    if is_weekday and 9 * 60 <= minutes < 9 * 60 + 15:
        status = "PRE_OPEN"
    elif is_weekday and 9 * 60 + 15 <= minutes <= 15 * 60 + 30:
        status = "OPEN"
    else:
        status = "CLOSED"
    return {
        "status": status,
        "raw_status": "LOCAL_TIME_FALLBACK",
        "is_open": status == "OPEN",
        "source": "local_clock_fallback",
        "fetched_at": _now_iso(),
    }


def get_market_status() -> dict[str, Any]:
    """Return NSE market status."""
    raw = _request_json("/api/marketStatus", "market_status", fallback=_fallback_market_status)
    states = raw.get("marketState") if isinstance(raw, dict) else None
    if not states:
        return raw if "status" in raw else _fallback_market_status()

    selected = states[0]
    for item in states:
        name = str(item.get("market") or item.get("marketType") or "").lower()
        if "capital" in name or "equity" in name:
            selected = item
            break
    raw_status = str(selected.get("marketStatus") or selected.get("status") or "").upper()
    if "PRE" in raw_status:
        status = "PRE_OPEN"
    elif "OPEN" in raw_status:
        status = "OPEN"
    elif "CLOSE" in raw_status or "CLOSED" in raw_status:
        status = "CLOSED"
    else:
        status = "UNKNOWN"
    return {
        "status": status,
        "raw_status": selected.get("marketStatus") or selected.get("status"),
        "is_open": status == "OPEN",
        "source": "nse_public",
        "fetched_at": _now_iso(),
    }


def _yf_value(symbol: str, label: str) -> dict[str, Any]:
    """Return a simple value item from yFinance."""
    quote_payload = _yf_quote(symbol)
    return {
        "id": label.upper().replace(" ", "_"),
        "label": label,
        "value": quote_payload.get("last_price"),
        "change": quote_payload.get("change", 0),
        "change_percent": quote_payload.get("change_percent", 0),
        "direction": "up" if float(quote_payload.get("change_percent") or 0) > 0 else "down" if float(quote_payload.get("change_percent") or 0) < 0 else "flat",
        "source": quote_payload.get("source", "yfinance"),
    }


def get_indices() -> dict[str, Any]:
    """Return the topbar market index strip."""
    raw = _request_json("/api/allIndices", "indices:all", fallback=lambda: {"data": []})
    rows = raw.get("data", []) if isinstance(raw, dict) else []
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("index") or row.get("indexSymbol") or "").upper()
        if name:
            by_name[name] = row

    mapping = [
        ("NIFTY", ["NIFTY 50", "NIFTY50"]),
        ("BANKNIFTY", ["NIFTY BANK", "BANK NIFTY", "BANKNIFTY"]),
        ("INDIA VIX", ["INDIA VIX"]),
    ]
    items: list[dict[str, Any]] = []
    for label, keys in mapping:
        row = next((by_name.get(key) for key in keys if by_name.get(key)), None)
        if row:
            change_pct = float(row.get("percentChange") or row.get("pChange") or 0)
            items.append(
                {
                    "id": label.replace(" ", "_"),
                    "label": label,
                    "value": float(row.get("last") or row.get("lastPrice") or 0),
                    "change": float(row.get("variation") or row.get("change") or 0),
                    "change_percent": round(change_pct, 2),
                    "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                    "source": "nse_public",
                }
            )

    present = {item["label"] for item in items}
    if "NIFTY" not in present:
        items.append(_yf_value("^NSEI", "NIFTY"))
    if "BANKNIFTY" not in present:
        items.append(_yf_value("^NSEBANK", "BANKNIFTY"))
    if "INDIA VIX" not in present:
        items.append(_yf_value("^INDIAVIX", "INDIA VIX"))

    items.append(_yf_value("USDINR=X", "USDINR"))
    items.append(_yf_value("GOLDBEES.NS", "GOLD"))
    return {"items": items[:5], "source": "nse_public+yfinance_fallback", "fetched_at": _now_iso()}


def get_option_chain(symbol: str = "NIFTY") -> dict[str, Any]:
    """Return option-chain positioning summary."""
    clean = _clean_symbol(symbol)
    raw = _request_json(
        f"/api/option-chain-indices?symbol={quote(clean)}",
        f"option_chain:{clean}",
        fallback=lambda: {"records": {"data": []}, "source": "nse_unavailable"},
    )
    rows = raw.get("records", {}).get("data", []) if isinstance(raw, dict) else []
    if not rows:
        return {
            "symbol": clean,
            "pcr": None,
            "max_pain": None,
            "top_call_oi": [],
            "top_put_oi": [],
            "source": raw.get("source", "nse_public"),
            "fetched_at": _now_iso(),
        }

    total_ce = sum(int(row.get("CE", {}).get("openInterest", 0) or 0) for row in rows)
    total_pe = sum(int(row.get("PE", {}).get("openInterest", 0) or 0) for row in rows)
    strikes = sorted({int(row.get("strikePrice", 0)) for row in rows if row.get("strikePrice")})
    pain_by_strike = {}
    for target in strikes:
        pain = 0
        for row in rows:
            strike = int(row.get("strikePrice", 0) or 0)
            pain += max(0, target - strike) * int(row.get("CE", {}).get("openInterest", 0) or 0)
            pain += max(0, strike - target) * int(row.get("PE", {}).get("openInterest", 0) or 0)
        pain_by_strike[target] = pain
    max_pain = min(pain_by_strike, key=pain_by_strike.get) if pain_by_strike else None
    top_calls = sorted(rows, key=lambda row: int(row.get("CE", {}).get("openInterest", 0) or 0), reverse=True)[:5]
    top_puts = sorted(rows, key=lambda row: int(row.get("PE", {}).get("openInterest", 0) or 0), reverse=True)[:5]
    return {
        "symbol": clean,
        "pcr": round(total_pe / total_ce, 2) if total_ce else None,
        "max_pain": max_pain,
        "top_call_oi": [{"strike": row.get("strikePrice"), "oi": row.get("CE", {}).get("openInterest", 0)} for row in top_calls],
        "top_put_oi": [{"strike": row.get("strikePrice"), "oi": row.get("PE", {}).get("openInterest", 0)} for row in top_puts],
        "source": "nse_public",
        "fetched_at": _now_iso(),
    }
