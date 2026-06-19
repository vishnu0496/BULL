"""Automatic paper evidence for BULL daily picks.

This is not live trading. It is BULL holding itself accountable:
store the ranked daily picks, then use later stored candles to see whether
the trigger fired, stop was hit, target was hit, or the idea expired.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
import json
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src import database


FRICTION_RATE = 0.0015
CLOSED_STATUSES = {"TARGET_HIT", "STOP_HIT", "TIME_EXIT"}
ACTIVE_STATUSES = {"WATCHING", "OPEN"}
IST = ZoneInfo("Asia/Kolkata")


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(IST).date().isoformat()


def _inside_capture_window(now: datetime | None = None) -> bool:
    """Only create automatic daily pick snapshots before the trading day starts."""
    current = now.astimezone(IST) if now else datetime.now(IST)
    if current.weekday() >= 5:
        return False
    return time(7, 0) <= current.time() <= time(9, 30)


def _round_money(value: float) -> float:
    return round(float(value), 2)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def ensure_auto_paper_tables() -> None:
    """Create the automatic evidence ledger."""
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auto_paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pick_date DATE NOT NULL,
                ticker TEXT NOT NULL,
                rank INTEGER NOT NULL,
                decision TEXT NOT NULL,
                setup_type TEXT,
                entry_trigger REAL NOT NULL,
                stop_loss REAL NOT NULL,
                target_1 REAL NOT NULL,
                target_2 REAL DEFAULT 0,
                quantity INTEGER DEFAULT 0,
                confidence_score REAL DEFAULT 0,
                historical_verdict TEXT DEFAULT 'UNKNOWN',
                news_sentiment TEXT DEFAULT 'NEUTRAL',
                source_payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'WATCHING',
                entry_date DATE,
                entry_price REAL,
                exit_date DATE,
                exit_price REAL,
                pnl REAL DEFAULT 0,
                r_multiple REAL,
                outcome_note TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(pick_date, ticker, entry_trigger)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "date" not in out.columns and "Date" in out.columns:
        out = out.rename(columns={"Date": "date"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out.dropna(subset=["date", "open", "high", "low", "close"]).sort_values("date").reset_index(drop=True)


def _pick_candidates(picks: list[dict], max_picks: int) -> list[dict]:
    ranked = [item for item in picks if str(item.get("decision", "")).upper() in {"TRADE", "WAIT"}]
    return ranked[: max(1, int(max_picks or 3))]


def capture_daily_picks(
    picks: list[dict] | None = None,
    pick_date: str | None = None,
    max_picks: int = 3,
    force: bool = False,
) -> dict[str, Any]:
    """Persist BULL's top daily ideas so they can be judged later."""
    database.init_db()
    ensure_auto_paper_tables()
    explicit_pick_date = pick_date is not None
    pick_date = pick_date or _today()

    if not explicit_pick_date and not force and not _inside_capture_window():
        return {
            "pick_date": pick_date,
            "captured": 0,
            "inserted": 0,
            "status": "SKIPPED_OUTSIDE_CAPTURE_WINDOW",
            "note": "Automatic evidence snapshots are only captured between 07:00 and 09:30 IST.",
        }

    if picks is None:
        from src.daily_brief import get_daily_picks

        picks = get_daily_picks(max_items=max(8, max_picks))

    candidates = _pick_candidates(picks, max_picks)
    conn = database.get_db_connection()
    inserted = 0
    try:
        if force:
            conn.execute("DELETE FROM auto_paper_trades WHERE pick_date = ?", (pick_date,))
        else:
            existing = conn.execute(
                "SELECT COUNT(*) AS count FROM auto_paper_trades WHERE pick_date = ?",
                (pick_date,),
            ).fetchone()
            if existing and int(existing["count"] or 0) > 0:
                return {
                    "pick_date": pick_date,
                    "captured": int(existing["count"] or 0),
                    "inserted": 0,
                    "status": "SKIPPED_EXISTING",
                    "note": "Daily picks were already captured for this date; preserving the original evidence snapshot.",
                }

        for index, pick in enumerate(candidates, start=1):
            decision = str(pick.get("decision") or "WAIT").upper()
            status = "WATCHING" if decision == "TRADE" else "WATCH_ONLY"
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO auto_paper_trades (
                    pick_date, ticker, rank, decision, setup_type, entry_trigger,
                    stop_loss, target_1, target_2, quantity, confidence_score,
                    historical_verdict, news_sentiment, source_payload_json,
                    status, outcome_note, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pick_date,
                    str(pick.get("ticker") or "").upper(),
                    index,
                    decision,
                    str(pick.get("setup_type") or ""),
                    _safe_float(pick.get("entry_trigger")),
                    _safe_float(pick.get("stop_loss")),
                    _safe_float(pick.get("target_1")),
                    _safe_float(pick.get("target_2")),
                    _safe_int(pick.get("suggested_quantity")),
                    _safe_float(pick.get("confidence_score")),
                    str(pick.get("historical_verdict") or "UNKNOWN").upper(),
                    str(pick.get("news_sentiment") or "NEUTRAL").upper(),
                    json.dumps(pick, sort_keys=True, default=str),
                    status,
                    "Captured for automatic paper evidence." if decision == "TRADE" else "Captured as watch-only; BULL did not call this a trade.",
                    _now_iso(),
                ),
            )
            inserted += cursor.rowcount
        conn.commit()
    finally:
        conn.close()

    return {
        "pick_date": pick_date,
        "captured": len(candidates),
        "inserted": inserted,
        "status": "OK",
    }


def get_active_auto_paper_tickers() -> list[str]:
    """Return tickers with evidence rows that still need later candles."""
    ensure_auto_paper_tables()
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT ticker
            FROM auto_paper_trades
            WHERE status IN ('WATCHING', 'OPEN')
            ORDER BY ticker ASC
            """
        ).fetchall()
    finally:
        conn.close()
    return [str(row["ticker"]).upper() for row in rows if row["ticker"]]


def sync_active_trade_prices() -> dict[str, Any]:
    """Refresh stored candles for active evidence tickers before evaluation."""
    tickers = get_active_auto_paper_tickers()
    if not tickers:
        return {"tickers": [], "synced": 0, "failed": [], "status": "NO_ACTIVE_TRADES"}

    from src import fetcher

    failed = []
    synced = 0
    for ticker in tickers:
        try:
            fetcher.sync_ticker(ticker)
            synced += 1
        except Exception as exc:
            failed.append({"ticker": ticker, "error": str(exc)})

    return {
        "tickers": tickers,
        "synced": synced,
        "failed": failed,
        "status": "OK" if not failed else "PARTIAL",
    }


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


def _exit_values(entry_price: float, exit_price: float, stop_loss: float, quantity: int) -> tuple[float, float]:
    effective_entry = entry_price * (1 + FRICTION_RATE)
    effective_exit = exit_price * (1 - FRICTION_RATE)
    pnl = quantity * (effective_exit - effective_entry)
    risk_per_share = entry_price - stop_loss
    r_multiple = ((effective_exit - effective_entry) / risk_per_share) if risk_per_share > 0 else 0.0
    return _round_money(pnl), round(float(r_multiple), 2)


def _resolve_exit(
    rows: pd.DataFrame,
    entry_price: float,
    stop_loss: float,
    target_1: float,
    quantity: int,
    horizon_end: pd.Timestamp,
) -> dict[str, Any] | None:
    if rows.empty:
        return None
    usable = rows[rows["date"] <= horizon_end]
    if usable.empty:
        return None

    for _, candle in usable.iterrows():
        candle_date = pd.to_datetime(candle["date"]).date().isoformat()
        low = float(candle["low"])
        high = float(candle["high"])
        if low <= stop_loss and high >= target_1:
            pnl, r_multiple = _exit_values(entry_price, stop_loss, stop_loss, quantity)
            return {
                "status": "STOP_HIT",
                "exit_date": candle_date,
                "exit_price": _round_money(stop_loss),
                "pnl": pnl,
                "r_multiple": r_multiple,
                "outcome_note": "Stop and target both touched in one candle; conservative rule counts stop first.",
            }
        if low <= stop_loss:
            pnl, r_multiple = _exit_values(entry_price, stop_loss, stop_loss, quantity)
            return {
                "status": "STOP_HIT",
                "exit_date": candle_date,
                "exit_price": _round_money(stop_loss),
                "pnl": pnl,
                "r_multiple": r_multiple,
                "outcome_note": "Automatic paper trade hit stop-loss.",
            }
        if high >= target_1:
            pnl, r_multiple = _exit_values(entry_price, target_1, stop_loss, quantity)
            return {
                "status": "TARGET_HIT",
                "exit_date": candle_date,
                "exit_price": _round_money(target_1),
                "pnl": pnl,
                "r_multiple": r_multiple,
                "outcome_note": "Automatic paper trade hit target 1.",
            }

    last = usable.iloc[-1]
    last_date = pd.to_datetime(last["date"])
    if last_date >= horizon_end:
        exit_price = float(last["close"])
        pnl, r_multiple = _exit_values(entry_price, exit_price, stop_loss, quantity)
        return {
            "status": "TIME_EXIT",
            "exit_date": last_date.date().isoformat(),
            "exit_price": _round_money(exit_price),
            "pnl": pnl,
            "r_multiple": r_multiple,
            "outcome_note": "Idea reached the evaluation horizon; exited at stored close.",
        }
    return None


def evaluate_auto_paper_trades(as_of_date: str | None = None, horizon_days: int = 5) -> dict[str, Any]:
    """Evaluate captured picks against later stored candles."""
    database.init_db()
    ensure_auto_paper_tables()
    as_of = pd.to_datetime(as_of_date).normalize() if as_of_date else None
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM auto_paper_trades
            WHERE status IN ('WATCHING', 'OPEN')
            ORDER BY pick_date ASC, rank ASC
            """
        ).fetchall()
    finally:
        conn.close()

    evaluated = 0
    updated = 0
    for row in rows:
        trade = dict(row)
        pick_day = pd.to_datetime(trade["pick_date"]).normalize()
        horizon_end = pick_day + timedelta(days=max(1, int(horizon_days or 5)))

        prices = _clean_prices(database.get_prices(trade["ticker"]))
        if prices.empty:
            continue
        # Picks are captured before the market opens for pick_day, so that same
        # day's candle is the first valid evidence candle.
        prices = prices[prices["date"] >= pick_day]
        if as_of is not None:
            prices = prices[prices["date"] <= as_of]
        if prices.empty:
            continue

        evaluated += 1
        entry_trigger = float(trade["entry_trigger"])
        stop_loss = float(trade["stop_loss"])
        target_1 = float(trade["target_1"])
        quantity = max(0, int(trade["quantity"] or 0))
        if quantity <= 0 or entry_trigger <= 0 or stop_loss <= 0 or target_1 <= 0:
            _update_trade(trade["id"], status="INVALID", outcome_note="Invalid entry/stop/target/quantity; cannot auto-paper this pick.")
            updated += 1
            continue

        if trade["status"] == "WATCHING":
            entry_row = None
            for _, candle in prices[prices["date"] <= horizon_end].iterrows():
                if float(candle["high"]) >= entry_trigger:
                    entry_row = candle
                    break
            if entry_row is None:
                last_date = pd.to_datetime(prices["date"].max()).normalize()
                if last_date >= horizon_end:
                    _update_trade(
                        trade["id"],
                        status="NO_TRIGGER",
                        outcome_note="Price never crossed BULL's entry trigger during the evaluation horizon.",
                    )
                    updated += 1
                continue

            entry_date = pd.to_datetime(entry_row["date"]).date().isoformat()
            entry_price = _round_money(max(entry_trigger, float(entry_row["open"])))
            _update_trade(
                trade["id"],
                status="OPEN",
                entry_date=entry_date,
                entry_price=entry_price,
                outcome_note="Entry trigger crossed; automatic paper trade opened.",
            )
            trade["status"] = "OPEN"
            trade["entry_date"] = entry_date
            trade["entry_price"] = entry_price
            updated += 1

        if trade["status"] == "OPEN":
            entry_date = pd.to_datetime(trade["entry_date"]).normalize()
            entry_price = float(trade["entry_price"])
            after_entry = prices[prices["date"] >= entry_date]
            exit_data = _resolve_exit(after_entry, entry_price, stop_loss, target_1, quantity, horizon_end)
            if exit_data:
                _update_trade(trade["id"], **exit_data)
                updated += 1

    return {
        "evaluated": evaluated,
        "updated": updated,
        "status": "OK",
    }


def get_auto_paper_summary(limit: int = 25) -> dict[str, Any]:
    """Return BULL's automatic evidence ledger summary."""
    ensure_auto_paper_tables()
    conn = database.get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM auto_paper_trades ORDER BY pick_date DESC, rank ASC", conn)
    finally:
        conn.close()

    if df.empty:
        return {
            "summary": {
                "tracked_picks": 0,
                "actionable_picks": 0,
                "closed_trades": 0,
                "win_rate": 0.0,
                "net_pnl": 0.0,
                "avg_r_multiple": None,
                "verdict": "EMPTY",
            },
            "recent": [],
            "learning_summary": ["No automatic paper evidence yet. Run BULL Auto Check after daily picks exist."],
        }

    closed = df[df["status"].isin(CLOSED_STATUSES)].copy()
    wins = closed[closed["pnl"] > 0] if not closed.empty else closed
    losses = closed[closed["pnl"] < 0] if not closed.empty else closed
    r_values = pd.to_numeric(closed["r_multiple"], errors="coerce").dropna()
    net_pnl = float(pd.to_numeric(closed["pnl"], errors="coerce").fillna(0).sum()) if not closed.empty else 0.0
    win_rate = (len(wins) / len(closed) * 100) if len(closed) else 0.0

    if len(closed) < 10:
        verdict = "COLLECTING"
    elif net_pnl > 0 and win_rate >= 50:
        verdict = "PROMISING"
    elif net_pnl < 0:
        verdict = "WEAK"
    else:
        verdict = "MIXED"

    recent = df.head(limit).fillna("").to_dict("records")
    learning = []
    if len(closed) == 0:
        learning.append("BULL has captured picks, but no automatic paper trades are closed yet.")
    else:
        learning.append(f"Automatic evidence so far: {len(closed)} closed trade(s), {win_rate:.1f}% win rate, INR {net_pnl:.2f} net PnL.")
    no_trigger = int((df["status"] == "NO_TRIGGER").sum())
    if no_trigger:
        learning.append(f"{no_trigger} idea(s) never crossed the entry trigger. That is useful: no trigger means no trade.")
    stop_hits = int((df["status"] == "STOP_HIT").sum())
    if stop_hits:
        learning.append(f"{stop_hits} automatic trade(s) hit stop-loss. These setups must be studied before increasing confidence.")

    return {
        "summary": {
            "tracked_picks": int(len(df)),
            "actionable_picks": int((df["decision"] == "TRADE").sum()),
            "watch_only_picks": int((df["decision"] == "WAIT").sum()),
            "open_trades": int((df["status"] == "OPEN").sum()),
            "watching_trades": int((df["status"] == "WATCHING").sum()),
            "no_trigger": no_trigger,
            "closed_trades": int(len(closed)),
            "winning_trades": int(len(wins)),
            "losing_trades": int(len(losses)),
            "win_rate": round(win_rate, 2),
            "net_pnl": _round_money(net_pnl),
            "avg_r_multiple": round(float(r_values.mean()), 2) if not r_values.empty else None,
            "verdict": verdict,
        },
        "recent": recent,
        "learning_summary": learning,
    }


def run_auto_paper_cycle(
    picks: list[dict] | None = None,
    max_picks: int = 3,
    horizon_days: int = 5,
    sync_prices: bool = False,
) -> dict[str, Any]:
    """Capture today's ideas, evaluate older ideas, and return the evidence summary."""
    captured = capture_daily_picks(picks=picks, max_picks=max_picks)
    price_sync = sync_active_trade_prices() if sync_prices else {"status": "SKIPPED"}
    evaluated = evaluate_auto_paper_trades(horizon_days=horizon_days)
    summary = get_auto_paper_summary()
    return {
        "captured": captured,
        "price_sync": price_sync,
        "evaluated": evaluated,
        "summary": summary,
        "status": "OK",
    }
