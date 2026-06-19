"""Intraday automatic paper execution for BULL picks.

This is not broker execution. It is a polling paper ledger:
while BULL is running during market hours, it watches captured auto-paper
trades and marks them OPEN / STOP_HIT / TARGET_HIT from acceptable intraday
quotes. NSE public quotes are preferred; fresh Yahoo 1-minute bars are allowed
for paper evidence only when NSE blocks the public endpoint.
"""

from __future__ import annotations

from datetime import datetime, time
import time as sleep_time
from typing import Any
from zoneinfo import ZoneInfo

from src import database, nse_feed
from src.auto_paper import ensure_auto_paper_tables


IST = ZoneInfo("Asia/Kolkata")
LIVE_QUOTE_CACHE_SECONDS = 20
MAX_FALLBACK_QUOTE_LAG_MINUTES = 20.0
CLOSED_STATUSES = {"TARGET_HIT", "STOP_HIT", "TIME_EXIT", "NO_TRIGGER", "INVALID"}
ACCEPTED_INTRADAY_SOURCES = {"nse_public", "yfinance_intraday_fallback"}


def _now_ist() -> datetime:
    return datetime.now(IST)


def _now_iso() -> str:
    return _now_ist().isoformat(timespec="seconds")


def _today() -> str:
    return _now_ist().date().isoformat()


def _round_money(value: float) -> float:
    return round(float(value), 2)


def is_market_open(now: datetime | None = None) -> bool:
    current = now.astimezone(IST) if now else _now_ist()
    if current.weekday() >= 5:
        return False
    return time(9, 15) <= current.time() <= time(15, 30)


def ensure_intraday_tables() -> None:
    ensure_auto_paper_tables()
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_paper_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                ticker TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                price REAL,
                source TEXT,
                action TEXT NOT NULL,
                note TEXT DEFAULT '',
                quote_payload TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _active_rows() -> list[dict[str, Any]]:
    ensure_intraday_tables()
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM auto_paper_trades
            WHERE status IN ('WATCHING', 'OPEN')
              AND decision = 'TRADE'
            ORDER BY pick_date ASC, rank ASC
            """
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def _update_trade(row_id: int, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = _now_iso()
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [row_id]
    conn = database.get_db_connection()
    try:
        conn.execute(f"UPDATE auto_paper_trades SET {assignments} WHERE id = ?", values)
        conn.commit()
    finally:
        conn.close()


def _record_tick(
    *,
    trade_id: int | None,
    ticker: str,
    price: float | None,
    source: str,
    action: str,
    note: str,
    quote_payload: dict[str, Any] | None = None,
) -> None:
    import json

    ensure_intraday_tables()
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            INSERT INTO auto_paper_ticks (
                trade_id, ticker, observed_at, price, source, action, note, quote_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                ticker.upper(),
                _now_iso(),
                price,
                source,
                action,
                note,
                json.dumps(quote_payload or {}, default=str, sort_keys=True),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _exit_values(entry_price: float, exit_price: float, stop_loss: float, quantity: int) -> tuple[float, float]:
    friction_rate = 0.0015
    effective_entry = entry_price * (1 + friction_rate)
    effective_exit = exit_price * (1 - friction_rate)
    pnl = quantity * (effective_exit - effective_entry)
    risk_per_share = entry_price - stop_loss
    r_multiple = ((effective_exit - effective_entry) / risk_per_share) if risk_per_share > 0 else 0.0
    return _round_money(pnl), round(float(r_multiple), 2)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _quote_usability(quote: dict[str, Any], source: str, price: float) -> tuple[bool, str]:
    if price <= 0:
        return False, "Skipped intraday paper update; quote has no usable price."
    if source == "nse_public":
        return True, "Using NSE public quote."
    if source == "yfinance_intraday_fallback":
        lag = _safe_float(quote.get("quote_lag_minutes"), default=9999.0)
        if lag <= MAX_FALLBACK_QUOTE_LAG_MINUTES:
            return True, f"Using fresh Yahoo 1-minute intraday fallback for paper only ({lag:.1f} min lag)."
        return False, f"Skipped intraday paper update; Yahoo 1-minute fallback is stale ({lag:.1f} min lag)."
    return False, f"Skipped intraday paper update; quote source is {source}, not an accepted intraday source."


def apply_live_price(trade: dict[str, Any], price: float, source: str) -> dict[str, Any]:
    ticker = str(trade.get("ticker") or "").upper()
    row_id = int(trade["id"])
    status = str(trade.get("status") or "").upper()
    entry_trigger = _safe_float(trade.get("entry_trigger"))
    stop_loss = _safe_float(trade.get("stop_loss"))
    target_1 = _safe_float(trade.get("target_1"))
    quantity = _safe_int(trade.get("quantity"))

    if quantity <= 0 or entry_trigger <= 0 or stop_loss <= 0 or target_1 <= 0:
        _update_trade(row_id, status="INVALID", outcome_note="Invalid intraday paper levels; cannot monitor this trade.")
        _record_tick(
            trade_id=row_id,
            ticker=ticker,
            price=price,
            source=source,
            action="INVALID",
            note="Invalid entry/stop/target/quantity.",
        )
        return {"action": "INVALID", "ticker": ticker}

    if status == "WATCHING":
        if price >= entry_trigger:
            entry_price = _round_money(max(price, entry_trigger))
            _update_trade(
                row_id,
                status="OPEN",
                entry_date=_today(),
                entry_price=entry_price,
                outcome_note=f"Intraday paper entry opened at observed {source} price.",
            )
            _record_tick(
                trade_id=row_id,
                ticker=ticker,
                price=price,
                source=source,
                action="OPENED",
                note=f"Observed price crossed entry trigger {entry_trigger:.2f}.",
            )
            return {"action": "OPENED", "ticker": ticker, "entry_price": entry_price}
        _record_tick(
            trade_id=row_id,
            ticker=ticker,
            price=price,
            source=source,
            action="WATCHING",
            note=f"Observed price below entry trigger {entry_trigger:.2f}.",
        )
        return {"action": "WATCHING", "ticker": ticker}

    if status == "OPEN":
        entry_price = _safe_float(trade.get("entry_price"))
        if entry_price <= 0:
            _record_tick(
                trade_id=row_id,
                ticker=ticker,
                price=price,
                source=source,
                action="NO_ACTION",
                note="Open trade has no valid entry price.",
            )
            return {"action": "NO_ACTION", "ticker": ticker}

        if price <= stop_loss:
            exit_price = _round_money(min(price, stop_loss))
            pnl, r_multiple = _exit_values(entry_price, exit_price, stop_loss, quantity)
            _update_trade(
                row_id,
                status="STOP_HIT",
                exit_date=_today(),
                exit_price=exit_price,
                pnl=pnl,
                r_multiple=r_multiple,
                outcome_note=f"Intraday paper trade hit stop-loss from {source}.",
            )
            _record_tick(
                trade_id=row_id,
                ticker=ticker,
                price=price,
                source=source,
                action="STOP_HIT",
                note=f"Observed price touched stop-loss {stop_loss:.2f}.",
            )
            return {"action": "STOP_HIT", "ticker": ticker, "exit_price": exit_price, "pnl": pnl}

        if price >= target_1:
            exit_price = _round_money(target_1)
            pnl, r_multiple = _exit_values(entry_price, exit_price, stop_loss, quantity)
            _update_trade(
                row_id,
                status="TARGET_HIT",
                exit_date=_today(),
                exit_price=exit_price,
                pnl=pnl,
                r_multiple=r_multiple,
                outcome_note=f"Intraday paper trade hit target 1 from {source}.",
            )
            _record_tick(
                trade_id=row_id,
                ticker=ticker,
                price=price,
                source=source,
                action="TARGET_HIT",
                note=f"Observed price touched target {target_1:.2f}.",
            )
            return {"action": "TARGET_HIT", "ticker": ticker, "exit_price": exit_price, "pnl": pnl}

        _record_tick(
            trade_id=row_id,
            ticker=ticker,
            price=price,
            source=source,
            action="OPEN",
            note="Open trade still between stop-loss and target.",
        )
        return {"action": "OPEN", "ticker": ticker}

    return {"action": "IGNORED", "ticker": ticker}


def run_intraday_paper_once(force: bool = False) -> dict[str, Any]:
    """Poll live quotes once and update active auto-paper trades."""
    database.init_db()
    ensure_intraday_tables()
    if not force and not is_market_open():
        return {
            "status": "SKIPPED_MARKET_CLOSED",
            "market_open": False,
            "checked_at": _now_iso(),
            "actions": [],
        }

    rows = _active_rows()
    actions: list[dict[str, Any]] = []
    skipped = 0
    updated = 0

    for trade in rows:
        ticker = str(trade.get("ticker") or "").upper()
        quote = nse_feed.get_quote(ticker, cache_seconds=LIVE_QUOTE_CACHE_SECONDS)
        source = str(quote.get("source") or "unknown")
        price = _safe_float(quote.get("last_price"))
        usable_quote, usability_note = _quote_usability(quote, source, price)
        if not usable_quote:
            skipped += 1
            _record_tick(
                trade_id=int(trade["id"]),
                ticker=ticker,
                price=price or None,
                source=source,
                action="QUOTE_SKIPPED",
                note=usability_note,
                quote_payload=quote,
            )
            actions.append({"ticker": ticker, "action": "QUOTE_SKIPPED", "source": source, "note": usability_note})
            continue

        action = apply_live_price(trade, price, source)
        action["price"] = price
        action["source"] = source
        action["source_note"] = usability_note
        actions.append(action)
        if action.get("action") in {"OPENED", "STOP_HIT", "TARGET_HIT", "INVALID"}:
            updated += 1

    return {
        "status": "OK",
        "market_open": True,
        "checked_at": _now_iso(),
        "active_trades": len(rows),
        "updated": updated,
        "skipped": skipped,
        "actions": actions,
    }


def get_intraday_paper_status(limit: int = 50) -> dict[str, Any]:
    ensure_intraday_tables()
    conn = database.get_db_connection()
    try:
        active = _active_rows()
        ticks = conn.execute(
            """
            SELECT *
            FROM auto_paper_ticks
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit or 50)),),
        ).fetchall()
    finally:
        conn.close()

    return {
        "market_open": is_market_open(),
        "checked_at": _now_iso(),
        "active_trades": len(active),
        "accepted_sources": sorted(ACCEPTED_INTRADAY_SOURCES),
        "fallback_max_lag_minutes": MAX_FALLBACK_QUOTE_LAG_MINUTES,
        "recent_ticks": [dict(row) for row in ticks],
    }


def run_intraday_loop(interval_seconds: int = 30, max_cycles: int | None = None) -> None:
    interval = max(5, int(interval_seconds or 30))
    cycle = 0
    while True:
        result = run_intraday_paper_once()
        print(result, flush=True)
        cycle += 1
        if max_cycles is not None and cycle >= max_cycles:
            return
        sleep_time.sleep(interval)
