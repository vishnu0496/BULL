import re
from collections import defaultdict
from datetime import datetime

import pandas as pd

from src import database


FRICTION_RATE = 0.0015


def _safe_float(value, default=0.0):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        if value is None or pd.isna(value):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value):
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return str(value or "")


def _extract_number_after(label_patterns, text):
    if not text:
        return None
    for pattern in label_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _safe_float(match.group(1), None)
    return None


def _extract_stop_loss(notes):
    return _extract_number_after(
        [
            r"(?:stop\s*loss|stoploss|sl|safety\s*exit)\s*[:=@-]?\s*(?:inr|rs\.?|rs|₹)?\s*([0-9]+(?:\.[0-9]+)?)",
            r"(?:exit\s*if\s*below|below)\s*(?:inr|rs\.?|rs|₹)?\s*([0-9]+(?:\.[0-9]+)?)",
        ],
        notes,
    )


def _extract_confidence(notes):
    value = _extract_number_after(
        [
            r"(?:confidence|conf)\s*[:=@-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
            r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:confidence|conf)",
        ],
        notes,
    )
    if value is None:
        return None
    return max(0.0, min(100.0, value))


def _infer_source(notes):
    text = (notes or "").lower()
    if "mentor" in text:
        return "Daily Mentor"
    if "news" in text or "analyst" in text:
        return "News Analyst"
    if "ranking" in text or "backtest" in text or "verdict" in text:
        return "Strategy Ranking"
    if "research" in text or "technical" in text or "breakout" in text:
        return "Research Desk"
    return "Manual"


def _infer_setup_type(notes):
    text = (notes or "").lower()
    if "breakout" in text:
        return "Breakout"
    if "pullback" in text:
        return "Pullback"
    if "trend" in text:
        return "Trend"
    if "news" in text or "event" in text:
        return "News/Event"
    if "manual" in text:
        return "Manual"
    return "Unlabeled"


def _confidence_bucket(confidence):
    if confidence is None:
        return "Unknown"
    if confidence < 50:
        return "0-49"
    if confidence < 60:
        return "50-59"
    if confidence < 70:
        return "60-69"
    return "70+"


def _classify_mistakes(notes, pnl, r_multiple):
    text = (notes or "").lower()
    mistakes = []
    checks = [
        ("entered too early", "Entered too early"),
        ("early entry", "Entered too early"),
        ("ignored stop", "Ignored stop-loss"),
        ("no stop", "No stop-loss written"),
        ("revenge", "Revenge trade"),
        ("fomo", "FOMO entry"),
        ("no trade", "Traded during NO TRADE day"),
        ("overtrade", "Overtrading"),
        ("panic", "Panic exit"),
    ]
    for cue, label in checks:
        if cue in text:
            mistakes.append(label)
    if pnl < 0 and r_multiple is not None and r_multiple < -1.25:
        mistakes.append("Loss exceeded planned risk")
    return sorted(set(mistakes))


def _reconstruct_closed_trades(trades_df):
    if trades_df.empty:
        return []

    df = trades_df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df = df.sort_values(["trade_date", "id"], ascending=[True, True])

    open_lots = defaultdict(list)
    closed_trades = []

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).upper()
        action = str(row.get("action", "")).upper()
        quantity = _safe_int(row.get("quantity"))
        price = _safe_float(row.get("price"))
        notes = str(row.get("notes") or "")
        trade_date = _parse_date(row.get("trade_date"))

        if not ticker or quantity <= 0 or price <= 0:
            continue

        if action == "BUY":
            open_lots[ticker].append(
                {
                    "remaining_qty": quantity,
                    "entry_date": trade_date,
                    "entry_price_raw": price,
                    "entry_price": price * (1 + FRICTION_RATE),
                    "notes": notes,
                    "source": _infer_source(notes),
                    "setup_type": _infer_setup_type(notes),
                    "confidence": _extract_confidence(notes),
                    "stop_loss": _extract_stop_loss(notes),
                }
            )
            continue

        if action != "SELL":
            continue

        sell_remaining = quantity
        effective_exit = price * (1 - FRICTION_RATE)
        while sell_remaining > 0 and open_lots[ticker]:
            lot = open_lots[ticker][0]
            matched_qty = min(sell_remaining, lot["remaining_qty"])
            pnl = matched_qty * (effective_exit - lot["entry_price"])
            planned_risk_per_share = None
            r_multiple = None

            if lot["stop_loss"] is not None and lot["stop_loss"] < lot["entry_price_raw"]:
                planned_risk_per_share = lot["entry_price_raw"] - lot["stop_loss"]
                if planned_risk_per_share > 0:
                    r_multiple = (effective_exit - lot["entry_price"]) / planned_risk_per_share

            mistakes = _classify_mistakes(f"{lot['notes']} {notes}", pnl, r_multiple)

            closed_trades.append(
                {
                    "ticker": ticker,
                    "entry_date": lot["entry_date"],
                    "exit_date": trade_date,
                    "quantity": matched_qty,
                    "entry_price": round(lot["entry_price"], 2),
                    "exit_price": round(effective_exit, 2),
                    "gross_entry": round(lot["entry_price_raw"], 2),
                    "gross_exit": round(price, 2),
                    "pnl": round(pnl, 2),
                    "return_pct": round(((effective_exit - lot["entry_price"]) / lot["entry_price"]) * 100, 2),
                    "result": "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "FLAT",
                    "source": lot["source"],
                    "setup_type": lot["setup_type"],
                    "confidence": lot["confidence"],
                    "confidence_bucket": _confidence_bucket(lot["confidence"]),
                    "stop_loss": lot["stop_loss"],
                    "r_multiple": round(r_multiple, 2) if r_multiple is not None else None,
                    "mistakes": mistakes,
                    "entry_notes": lot["notes"],
                    "exit_notes": notes,
                }
            )

            lot["remaining_qty"] -= matched_qty
            sell_remaining -= matched_qty
            if lot["remaining_qty"] <= 0:
                open_lots[ticker].pop(0)

    return closed_trades


def _summarize_group(closed_trades, key):
    groups = defaultdict(list)
    for trade in closed_trades:
        groups[trade.get(key) or "Unknown"].append(trade)

    rows = []
    for name, items in groups.items():
        pnl_values = [t["pnl"] for t in items]
        wins = [p for p in pnl_values if p > 0]
        losses = [p for p in pnl_values if p < 0]
        rows.append(
            {
                "name": name,
                "trades": len(items),
                "win_rate": round((len(wins) / len(items)) * 100, 2) if items else 0.0,
                "net_pnl": round(sum(pnl_values), 2),
                "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
                "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
                "avg_r": round(
                    sum(t["r_multiple"] for t in items if t["r_multiple"] is not None)
                    / max(1, len([t for t in items if t["r_multiple"] is not None])),
                    2,
                ),
            }
        )
    return sorted(rows, key=lambda row: (row["net_pnl"], row["win_rate"]), reverse=True)


def _build_equity_curve(closed_trades):
    cumulative = 0.0
    curve = []
    for trade in sorted(closed_trades, key=lambda t: (t["exit_date"], t["ticker"])):
        cumulative += trade["pnl"]
        curve.append(
            {
                "date": trade["exit_date"],
                "ticker": trade["ticker"],
                "pnl": trade["pnl"],
                "cumulative_pnl": round(cumulative, 2),
            }
        )
    return curve


def _build_learning_summary(summary, closed_trades, grouped):
    if summary["total_closed_trades"] == 0:
        return [
            "No closed paper trades yet. Start by logging BUY and SELL practice trades.",
            "Write stop-loss, confidence, and source in notes so BULL can learn from your decisions.",
        ]

    lessons = []
    if summary["win_rate"] >= 55 and summary["net_pnl"] > 0:
        lessons.append("Paper trading is positive so far, but the sample is still only proof-of-process until it reaches 20+ closed trades.")
    elif summary["net_pnl"] < 0:
        lessons.append("Paper trading is currently negative. The next improvement should be stricter entries and stop-loss discipline.")
    else:
        lessons.append("Paper trading is mixed. Keep collecting clean trades before trusting any confidence score.")

    best_source = grouped.get("by_source", [{}])[0] if grouped.get("by_source") else {}
    if best_source:
        lessons.append(f"Best decision source so far: {best_source.get('name')} with {best_source.get('trades')} closed trades.")

    mistake_count = sum(len(t["mistakes"]) for t in closed_trades)
    if mistake_count:
        lessons.append(f"{mistake_count} mistake tags were detected. Reduce repeated mistakes before increasing capital.")
    else:
        lessons.append("No mistake tags detected yet. Add notes like 'entered too early' or 'ignored stop' when they happen.")

    if summary["r_tracked_trades"] == 0:
        lessons.append("R-multiple is not tracked yet because stop-loss values are missing from notes.")

    return lessons


def get_paper_trade_analytics():
    """Return paper-trading feedback metrics from the transaction journal."""
    trades_df = database.get_paper_trades()
    closed_trades = _reconstruct_closed_trades(trades_df)

    pnl_values = [trade["pnl"] for trade in closed_trades]
    wins = [pnl for pnl in pnl_values if pnl > 0]
    losses = [pnl for pnl in pnl_values if pnl < 0]
    r_values = [trade["r_multiple"] for trade in closed_trades if trade["r_multiple"] is not None]

    grouped = {
        "by_ticker": _summarize_group(closed_trades, "ticker"),
        "by_setup_type": _summarize_group(closed_trades, "setup_type"),
        "by_source": _summarize_group(closed_trades, "source"),
        "by_confidence_bucket": _summarize_group(closed_trades, "confidence_bucket"),
    }

    summary = {
        "total_journal_rows": int(len(trades_df)),
        "total_closed_trades": len(closed_trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round((len(wins) / len(closed_trades)) * 100, 2) if closed_trades else 0.0,
        "net_pnl": round(sum(pnl_values), 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
        "profit_factor": round(abs(sum(wins) / sum(losses)), 2) if losses else (round(sum(wins), 2) if wins else 0.0),
        "avg_r_multiple": round(sum(r_values) / len(r_values), 2) if r_values else None,
        "r_tracked_trades": len(r_values),
    }

    mistakes = defaultdict(int)
    for trade in closed_trades:
        for mistake in trade["mistakes"]:
            mistakes[mistake] += 1

    mistake_log = sorted(
        [{"mistake": label, "count": count} for label, count in mistakes.items()],
        key=lambda row: row["count"],
        reverse=True,
    )

    best_symbols = sorted(grouped["by_ticker"], key=lambda row: row["net_pnl"], reverse=True)[:5]
    worst_symbols = sorted(grouped["by_ticker"], key=lambda row: row["net_pnl"])[:5]

    return {
        "summary": summary,
        "equity_curve": _build_equity_curve(closed_trades),
        "closed_trades": sorted(closed_trades, key=lambda t: (t["exit_date"], t["ticker"]), reverse=True),
        "groups": grouped,
        "best_symbols": best_symbols,
        "worst_symbols": worst_symbols,
        "mistake_log": mistake_log,
        "learning_summary": _build_learning_summary(summary, closed_trades, grouped),
    }
