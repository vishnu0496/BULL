"""AI pick tracking system for BULL.

Stores every AI-generated pick, tracks outcomes against market prices,
and produces summary statistics (win rate, avg return, streaks, etc.).

Tables live in the same SQLite database as the rest of BULL
(via ``src.database.get_db_connection``).  Current prices are fetched
through ``src.nse_feed.get_quote`` during evaluation.

Usage:
    from src.track_record import (
        init_track_record_table,
        record_pick,
        evaluate_picks,
        get_track_record_summary,
        get_recent_picks,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from src import database

logger = logging.getLogger(__name__)

# How many calendar days before a PENDING pick with no trigger is marked EXPIRED
EXPIRY_DAYS = 5


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_track_record_table() -> None:
    """Create the ai_track_record table if it doesn't exist."""
    conn = database.get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_track_record (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker          TEXT    NOT NULL,
                pick_date       DATE    NOT NULL,
                decision        TEXT    NOT NULL,
                confidence_score REAL,
                entry_trigger   REAL,
                stop_loss       REAL,
                target_1        REAL,
                target_2        REAL,
                agent_reasoning TEXT,
                agent_source    TEXT    DEFAULT 'bull_agent',
                outcome         TEXT    DEFAULT 'PENDING'
                                        CHECK(outcome IN (
                                            'PENDING','TARGET_HIT','STOP_HIT',
                                            'EXPIRED','NO_TRIGGER')),
                outcome_date    DATE,
                outcome_price   REAL,
                pnl_percent     REAL,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Record a pick
# ---------------------------------------------------------------------------

def record_pick(pick: Dict[str, Any]) -> int:
    """Store a new AI pick and return its row id.

    Expected keys in *pick*:
        ticker, pick_date, decision, confidence_score,
        entry_trigger, stop_loss, target_1, target_2,
        agent_reasoning (optional), agent_source (optional)
    """
    init_track_record_table()
    conn = database.get_db_connection()
    try:
        cur = conn.execute("""
            INSERT INTO ai_track_record
                (ticker, pick_date, decision, confidence_score,
                 entry_trigger, stop_loss, target_1, target_2,
                 agent_reasoning, agent_source, outcome)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        """, (
            pick["ticker"].upper(),
            pick.get("pick_date", datetime.now().strftime("%Y-%m-%d")),
            pick["decision"].upper(),
            pick.get("confidence_score"),
            pick.get("entry_trigger"),
            pick.get("stop_loss"),
            pick.get("target_1"),
            pick.get("target_2"),
            pick.get("agent_reasoning", ""),
            pick.get("agent_source", "bull_agent"),
        ))
        conn.commit()
        row_id = cur.lastrowid
        logger.info("Recorded pick #%d: %s %s", row_id, pick["ticker"], pick["decision"])
        return row_id
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Evaluate pending picks
# ---------------------------------------------------------------------------

def _safe_get_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """Wrap nse_feed.get_quote so import/network errors don't crash evaluation."""
    try:
        from src.nse_feed import get_quote
        quote = get_quote(symbol)
        if quote and quote.get("last_price") and quote["last_price"] > 0:
            return quote
    except Exception as exc:
        logger.warning("Quote fetch failed for %s: %s", symbol, exc)
    return None


def evaluate_picks() -> Dict[str, Any]:
    """Check all PENDING picks against current market prices.

    Returns a summary dict with counts of updated picks.
    """
    init_track_record_table()
    conn = database.get_db_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    today_dt = datetime.now().date()
    results = {"evaluated": 0, "target_hit": 0, "stop_hit": 0, "expired": 0, "unchanged": 0, "errors": 0}

    try:
        rows = conn.execute(
            "SELECT * FROM ai_track_record WHERE outcome = 'PENDING'"
        ).fetchall()

        for row in rows:
            row_id = row["id"]
            ticker = row["ticker"]
            pick_date_str = row["pick_date"]
            entry_trigger = row["entry_trigger"]
            stop_loss = row["stop_loss"]
            target_1 = row["target_1"]
            decision = (row["decision"] or "").upper()

            results["evaluated"] += 1

            # Check expiry first
            try:
                pick_dt = datetime.strptime(pick_date_str, "%Y-%m-%d").date()
                days_old = (today_dt - pick_dt).days
            except (ValueError, TypeError):
                days_old = 0

            if days_old > EXPIRY_DAYS:
                conn.execute(
                    "UPDATE ai_track_record SET outcome='EXPIRED', outcome_date=? WHERE id=?",
                    (today, row_id),
                )
                results["expired"] += 1
                continue

            # Get current price
            quote = _safe_get_quote(ticker)
            if not quote:
                results["errors"] += 1
                continue

            last_price = quote["last_price"]

            # Determine outcome based on decision direction
            is_bullish = decision in ("BUY", "BULLISH", "LONG")

            if is_bullish:
                # For bullish picks: target hit if price >= target_1, stop hit if price <= stop_loss
                if target_1 and last_price >= target_1:
                    pnl = ((last_price - entry_trigger) / entry_trigger * 100) if entry_trigger else None
                    conn.execute(
                        """UPDATE ai_track_record
                           SET outcome='TARGET_HIT', outcome_date=?, outcome_price=?, pnl_percent=?
                           WHERE id=?""",
                        (today, last_price, pnl, row_id),
                    )
                    results["target_hit"] += 1
                elif stop_loss and last_price <= stop_loss:
                    pnl = ((last_price - entry_trigger) / entry_trigger * 100) if entry_trigger else None
                    conn.execute(
                        """UPDATE ai_track_record
                           SET outcome='STOP_HIT', outcome_date=?, outcome_price=?, pnl_percent=?
                           WHERE id=?""",
                        (today, last_price, pnl, row_id),
                    )
                    results["stop_hit"] += 1
                else:
                    results["unchanged"] += 1
            else:
                # For bearish/short picks: target hit if price <= target_1, stop hit if price >= stop_loss
                if target_1 and last_price <= target_1:
                    pnl = ((entry_trigger - last_price) / entry_trigger * 100) if entry_trigger else None
                    conn.execute(
                        """UPDATE ai_track_record
                           SET outcome='TARGET_HIT', outcome_date=?, outcome_price=?, pnl_percent=?
                           WHERE id=?""",
                        (today, last_price, pnl, row_id),
                    )
                    results["target_hit"] += 1
                elif stop_loss and last_price >= stop_loss:
                    pnl = ((entry_trigger - last_price) / entry_trigger * 100) if entry_trigger else None
                    conn.execute(
                        """UPDATE ai_track_record
                           SET outcome='STOP_HIT', outcome_date=?, outcome_price=?, pnl_percent=?
                           WHERE id=?""",
                        (today, last_price, pnl, row_id),
                    )
                    results["stop_hit"] += 1
                else:
                    results["unchanged"] += 1

        conn.commit()
    except Exception as exc:
        logger.error("evaluate_picks failed: %s", exc)
        results["errors"] += 1
    finally:
        conn.close()

    return results


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def get_track_record_summary() -> Dict[str, Any]:
    """Return aggregate stats about the AI's pick history.

    Keys: total_picks, resolved, pending, win_count, loss_count,
          win_rate, avg_return, best_pick, worst_pick, current_streak
    """
    init_track_record_table()
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ai_track_record ORDER BY pick_date DESC, id DESC"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {
            "total_picks": 0,
            "resolved": 0,
            "pending": 0,
            "win_count": 0,
            "loss_count": 0,
            "expired_count": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "best_pick": None,
            "worst_pick": None,
            "current_streak": {"type": "none", "count": 0},
        }

    total = len(rows)
    pending = sum(1 for r in rows if r["outcome"] == "PENDING")
    wins = [r for r in rows if r["outcome"] == "TARGET_HIT"]
    losses = [r for r in rows if r["outcome"] == "STOP_HIT"]
    expired = sum(1 for r in rows if r["outcome"] in ("EXPIRED", "NO_TRIGGER"))
    resolved = len(wins) + len(losses)

    win_rate = (len(wins) / resolved * 100) if resolved > 0 else 0.0

    # Average return across resolved picks that have pnl_percent
    pnl_values = [r["pnl_percent"] for r in rows if r["pnl_percent"] is not None]
    avg_return = sum(pnl_values) / len(pnl_values) if pnl_values else 0.0

    # Best and worst picks
    best_pick = None
    worst_pick = None
    if pnl_values:
        best_row = max(
            (r for r in rows if r["pnl_percent"] is not None),
            key=lambda r: r["pnl_percent"],
        )
        worst_row = min(
            (r for r in rows if r["pnl_percent"] is not None),
            key=lambda r: r["pnl_percent"],
        )
        best_pick = {
            "ticker": best_row["ticker"],
            "pnl_percent": best_row["pnl_percent"],
            "pick_date": best_row["pick_date"],
            "decision": best_row["decision"],
        }
        worst_pick = {
            "ticker": worst_row["ticker"],
            "pnl_percent": worst_row["pnl_percent"],
            "pick_date": worst_row["pick_date"],
            "decision": worst_row["decision"],
        }

    # Current streak (wins/losses in a row from most recent resolved)
    streak_type = "none"
    streak_count = 0
    resolved_rows = [r for r in rows if r["outcome"] in ("TARGET_HIT", "STOP_HIT")]
    if resolved_rows:
        first_outcome = resolved_rows[0]["outcome"]
        streak_type = "win" if first_outcome == "TARGET_HIT" else "loss"
        for r in resolved_rows:
            if r["outcome"] == first_outcome:
                streak_count += 1
            else:
                break

    return {
        "total_picks": total,
        "resolved": resolved,
        "pending": pending,
        "win_count": len(wins),
        "loss_count": len(losses),
        "expired_count": expired,
        "win_rate": round(win_rate, 1),
        "avg_return": round(avg_return, 2),
        "best_pick": best_pick,
        "worst_pick": worst_pick,
        "current_streak": {"type": streak_type, "count": streak_count},
    }


# ---------------------------------------------------------------------------
# Recent picks
# ---------------------------------------------------------------------------

def get_recent_picks(limit: int = 20) -> List[Dict[str, Any]]:
    """Return the most recent picks as a list of dicts."""
    init_track_record_table()
    conn = database.get_db_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM ai_track_record ORDER BY pick_date DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers for external callers
# ---------------------------------------------------------------------------

def get_pick_by_id(pick_id: int) -> Optional[Dict[str, Any]]:
    """Return a single pick by its row id."""
    init_track_record_table()
    conn = database.get_db_connection()
    try:
        row = conn.execute(
            "SELECT * FROM ai_track_record WHERE id = ?", (pick_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_outcome(pick_id: int, outcome: str, price: float = None, pnl: float = None) -> bool:
    """Manually override the outcome of a pick."""
    valid = {"PENDING", "TARGET_HIT", "STOP_HIT", "EXPIRED", "NO_TRIGGER"}
    if outcome not in valid:
        raise ValueError(f"outcome must be one of {valid}")

    conn = database.get_db_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            """UPDATE ai_track_record
               SET outcome=?, outcome_date=?, outcome_price=?, pnl_percent=?
               WHERE id=?""",
            (outcome, today, price, pnl, pick_id),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.error("update_outcome failed for pick #%d: %s", pick_id, exc)
        return False
    finally:
        conn.close()
