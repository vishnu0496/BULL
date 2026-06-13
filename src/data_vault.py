"""BULL Data Vault.

This module is BULL's private market-data memory. It does not replace licensed
real-time exchange feeds, but it makes BULL less fragile by archiving every
source payload we depend on and scoring source health before signals trust it.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
import time
from typing import Any

from src import database, news, nse_feed


INDEX_SYMBOLS = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_text(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)


def payload_hash(payload: Any) -> str:
    """Return a stable hash for a raw payload."""
    return hashlib.sha256(_json_text(payload).encode("utf-8")).hexdigest()


def ensure_data_vault_tables() -> None:
    """Create Data Vault tables if needed."""
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_vault_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                symbol TEXT,
                endpoint TEXT,
                payload_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'OK',
                observed_at TEXT,
                collected_at TEXT NOT NULL,
                note TEXT,
                UNIQUE(source, category, symbol, endpoint, payload_hash)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_vault_source_health (
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                last_success_at TEXT,
                last_error_at TEXT,
                latency_ms REAL DEFAULT 0,
                reliability_score REAL DEFAULT 0,
                error TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(source, category)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def record_event(
    *,
    source: str,
    category: str,
    payload: Any,
    symbol: str | None = None,
    endpoint: str | None = None,
    status: str = "OK",
    observed_at: str | None = None,
    note: str = "",
) -> int:
    """Archive one raw source payload and return its row id."""
    ensure_data_vault_tables()
    text = _json_text(payload)
    digest = payload_hash(payload)
    collected_at = _now_iso()
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO data_vault_events (
                source, category, symbol, endpoint, payload_hash, payload_json,
                status, observed_at, collected_at, note
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source,
                category,
                symbol.upper() if symbol else None,
                endpoint,
                digest,
                text,
                status,
                observed_at,
                collected_at,
                note,
            ),
        )
        row = conn.execute(
            """
            SELECT id FROM data_vault_events
            WHERE source = ? AND category = ? AND COALESCE(symbol, '') = COALESCE(?, '')
              AND COALESCE(endpoint, '') = COALESCE(?, '') AND payload_hash = ?
            """,
            (source, category, symbol.upper() if symbol else None, endpoint, digest),
        ).fetchone()
        conn.commit()
        return int(row["id"]) if row else 0
    finally:
        conn.close()


def record_source_health(
    *,
    source: str,
    category: str,
    ok: bool,
    latency_ms: float,
    error: str | None = None,
) -> None:
    """Store the latest health state for one source/category pair."""
    ensure_data_vault_tables()
    now = _now_iso()
    status = "OK" if ok else "ERROR"
    conn = database.get_db_connection()
    try:
        existing = conn.execute(
            """
            SELECT reliability_score FROM data_vault_source_health
            WHERE source = ? AND category = ?
            """,
            (source, category),
        ).fetchone()
        previous = float(existing["reliability_score"]) if existing else 50.0
        reliability = min(100.0, previous + 5.0) if ok else max(0.0, previous - 15.0)
        conn.execute(
            """
            INSERT INTO data_vault_source_health (
                source, category, status, last_success_at, last_error_at,
                latency_ms, reliability_score, error, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, category) DO UPDATE SET
                status = excluded.status,
                last_success_at = COALESCE(excluded.last_success_at, data_vault_source_health.last_success_at),
                last_error_at = COALESCE(excluded.last_error_at, data_vault_source_health.last_error_at),
                latency_ms = excluded.latency_ms,
                reliability_score = excluded.reliability_score,
                error = excluded.error,
                updated_at = excluded.updated_at
            """,
            (
                source,
                category,
                status,
                now if ok else None,
                None if ok else now,
                round(float(latency_ms), 2),
                round(reliability, 2),
                error or "",
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def collect_quote(symbol: str) -> dict[str, Any]:
    """Collect and archive a quote for one symbol."""
    start = time.perf_counter()
    payload = nse_feed.get_quote(symbol)
    latency = _elapsed_ms(start)
    source = str(payload.get("source") or "unknown")
    ok = payload.get("status") != "NO_DATA" and not payload.get("error")
    event_id = record_event(
        source=source,
        category="price_quote",
        symbol=symbol,
        endpoint="quote",
        payload=payload,
        status="OK" if ok else "ERROR",
        observed_at=payload.get("last_update") or payload.get("fetched_at"),
        note=str(payload.get("fetch_error") or payload.get("error") or ""),
    )
    record_source_health(
        source=source,
        category="price_quote",
        ok=ok,
        latency_ms=latency,
        error=str(payload.get("fetch_error") or payload.get("error") or ""),
    )
    return {
        "symbol": symbol.upper(),
        "source": source,
        "status": "OK" if ok else "ERROR",
        "last_price": payload.get("last_price"),
        "change_percent": payload.get("change_percent"),
        "event_id": event_id,
        "latency_ms": round(latency, 2),
    }


def collect_indices() -> dict[str, Any]:
    """Collect and archive the market index strip."""
    start = time.perf_counter()
    payload = nse_feed.get_indices()
    latency = _elapsed_ms(start)
    source = str(payload.get("source") or "unknown")
    ok = bool(payload.get("items"))
    event_id = record_event(
        source=source,
        category="indices",
        endpoint="indices",
        payload=payload,
        status="OK" if ok else "ERROR",
        observed_at=payload.get("fetched_at"),
    )
    record_source_health(source=source, category="indices", ok=ok, latency_ms=latency)
    return {
        "source": source,
        "status": "OK" if ok else "ERROR",
        "items": len(payload.get("items") or []),
        "event_id": event_id,
        "latency_ms": round(latency, 2),
    }


def collect_market_status() -> dict[str, Any]:
    """Collect and archive market status."""
    start = time.perf_counter()
    payload = nse_feed.get_market_status()
    latency = _elapsed_ms(start)
    source = str(payload.get("source") or "unknown")
    ok = bool(payload.get("status")) and payload.get("status") != "UNKNOWN"
    event_id = record_event(
        source=source,
        category="market_status",
        endpoint="market_status",
        payload=payload,
        status="OK" if ok else "ERROR",
        observed_at=payload.get("fetched_at"),
        note=str(payload.get("fetch_error") or payload.get("error") or ""),
    )
    record_source_health(
        source=source,
        category="market_status",
        ok=ok,
        latency_ms=latency,
        error=str(payload.get("fetch_error") or payload.get("error") or ""),
    )
    return {
        "source": source,
        "status": payload.get("status"),
        "event_id": event_id,
        "latency_ms": round(latency, 2),
    }


def collect_news(symbol: str, force_refresh: bool = False) -> dict[str, Any]:
    """Collect and archive recent free-source headlines for one stock."""
    start = time.perf_counter()
    items = news.fetch_stock_news(symbol, gemini_api_key=None, force_refresh=force_refresh)
    latency = _elapsed_ms(start)
    payload = {"symbol": symbol.upper(), "items": items, "count": len(items), "fetched_at": _now_iso()}
    ok = True
    event_id = record_event(
        source="free_news_cache",
        category="news_headlines",
        symbol=symbol,
        endpoint="stock_news",
        payload=payload,
        status="OK",
        observed_at=payload["fetched_at"],
    )
    record_source_health(source="free_news_cache", category="news_headlines", ok=ok, latency_ms=latency)
    return {
        "symbol": symbol.upper(),
        "source": "free_news_cache",
        "status": "OK",
        "headline_count": len(items),
        "event_id": event_id,
        "latency_ms": round(latency, 2),
    }


def _default_symbols(limit: int) -> list[str]:
    tickers = []
    for ticker in database.get_watchlist_tickers():
        clean = ticker.upper()
        if clean in INDEX_SYMBOLS or clean.startswith("^"):
            continue
        if clean not in tickers:
            tickers.append(clean)
        if len(tickers) >= limit:
            break
    return tickers


def refresh_data_vault(
    tickers: list[str] | None = None,
    limit: int = 12,
    include_news: bool = False,
) -> dict[str, Any]:
    """Refresh BULL's private data archive from available free sources."""
    database.init_db()
    ensure_data_vault_tables()
    safe_limit = max(1, min(int(limit or 12), 60))
    symbols = [t.upper() for t in (tickers or _default_symbols(safe_limit))[:safe_limit]]
    started = _now_iso()
    results: list[dict[str, Any]] = []

    for collector in (collect_market_status, collect_indices):
        try:
            results.append(collector())
        except Exception as exc:
            record_source_health(
                source="data_vault",
                category=collector.__name__,
                ok=False,
                latency_ms=0,
                error=str(exc),
            )
            results.append({"status": "ERROR", "collector": collector.__name__, "error": str(exc)})

    for symbol in symbols:
        try:
            results.append(collect_quote(symbol))
        except Exception as exc:
            record_source_health(source="unknown", category="price_quote", ok=False, latency_ms=0, error=str(exc))
            results.append({"symbol": symbol, "status": "ERROR", "error": str(exc)})

    if include_news:
        for symbol in symbols[: min(8, len(symbols))]:
            try:
                results.append(collect_news(symbol))
            except Exception as exc:
                record_source_health(source="free_news_cache", category="news_headlines", ok=False, latency_ms=0, error=str(exc))
                results.append({"symbol": symbol, "status": "ERROR", "collector": "news", "error": str(exc)})

    status_counts = Counter(item.get("status", "UNKNOWN") for item in results)
    return {
        "started_at": started,
        "finished_at": _now_iso(),
        "symbols": symbols,
        "include_news": bool(include_news),
        "counts": dict(status_counts),
        "results": results,
        "status": "OK" if status_counts.get("ERROR", 0) == 0 else "PARTIAL",
    }


def get_data_vault_status() -> dict[str, Any]:
    """Return a compact status report for BULL's private data archive."""
    ensure_data_vault_tables()
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat(timespec="seconds")
    conn = database.get_db_connection()
    try:
        total_events = conn.execute("SELECT COUNT(*) AS c FROM data_vault_events").fetchone()["c"]
        recent_events = conn.execute(
            "SELECT COUNT(*) AS c FROM data_vault_events WHERE collected_at >= ?",
            (cutoff,),
        ).fetchone()["c"]
        last_event = conn.execute("SELECT MAX(collected_at) AS ts FROM data_vault_events").fetchone()["ts"]
        source_rows = conn.execute(
            """
            SELECT source, category, status, last_success_at, last_error_at,
                   latency_ms, reliability_score, error, updated_at
            FROM data_vault_source_health
            ORDER BY category ASC, source ASC
            """
        ).fetchall()
        counts = conn.execute(
            """
            SELECT source, category, COUNT(*) AS count, MAX(collected_at) AS last_collected_at
            FROM data_vault_events
            WHERE collected_at >= ?
            GROUP BY source, category
            ORDER BY category ASC, source ASC
            """,
            (cutoff,),
        ).fetchall()
        latest = conn.execute(
            """
            SELECT source, category, symbol, endpoint, status, observed_at, collected_at, note
            FROM data_vault_events
            ORDER BY collected_at DESC, id DESC
            LIMIT 20
            """
        ).fetchall()
        quote_total = conn.execute(
            """
            SELECT COUNT(*) AS c FROM data_vault_events
            WHERE category = 'price_quote' AND collected_at >= ?
            """,
            (cutoff,),
        ).fetchone()["c"]
        yahoo_quotes = conn.execute(
            """
            SELECT COUNT(*) AS c FROM data_vault_events
            WHERE category = 'price_quote' AND collected_at >= ? AND source LIKE 'yfinance%'
            """,
            (cutoff,),
        ).fetchone()["c"]
    finally:
        conn.close()

    yahoo_dependency = round((float(yahoo_quotes) / float(quote_total)) * 100, 2) if quote_total else 0.0
    health = [dict(row) for row in source_rows]
    errors = [row for row in health if row.get("status") == "ERROR"]
    if not total_events:
        verdict = "EMPTY"
    elif errors:
        verdict = "DEGRADED"
    elif yahoo_dependency >= 80:
        verdict = "YAHOO_HEAVY"
    else:
        verdict = "ARCHIVING"

    return {
        "verdict": verdict,
        "total_events": int(total_events or 0),
        "recent_events_24h": int(recent_events or 0),
        "last_event_at": last_event,
        "yahoo_dependency_pct_24h": yahoo_dependency,
        "source_health": health,
        "event_counts_24h": [dict(row) for row in counts],
        "latest_events": [dict(row) for row in latest],
    }
