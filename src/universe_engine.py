"""Market universe registry and skill-gate logic for BULL."""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from typing import Any


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
SIGNALS_FILE = os.path.join(PROJECT_ROOT, "signals_log.json")
TRADES_FILE = os.path.join(PROJECT_ROOT, "trades_journal.json")

NIFTY_50 = [
    "ADANIENT.NS", "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS",
    "AXISBANK.NS", "BAJAJ-AUTO.NS", "BAJFINANCE.NS", "BAJAJFINSV.NS",
    "BHARTIARTL.NS", "BPCL.NS", "BRITANNIA.NS", "CIPLA.NS",
    "COALINDIA.NS", "DIVISLAB.NS", "DRREDDY.NS", "EICHERMOT.NS",
    "GRASIM.NS", "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS",
    "HEROMOTOCO.NS", "HINDALCO.NS", "HINDUNILVR.NS", "ICICIBANK.NS",
    "INDUSINDBK.NS", "INFY.NS", "ITC.NS", "JSWSTEEL.NS",
    "KOTAKBANK.NS", "LT.NS", "LTIM.NS", "M&M.NS", "MARUTI.NS",
    "NESTLEIND.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS",
    "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", "SHRIRAMFIN.NS",
    "SUNPHARMA.NS", "TATACONSUM.NS", "TATASTEEL.NS", "TCS.NS",
    "TECHM.NS", "TITAN.NS", "TRENT.NS", "ULTRACEMCO.NS", "WIPRO.NS",
]

ETF_LIST = ["NIFTYBEES.NS", "BANKBEES.NS", "GOLDBEES.NS", "JUNIORBEES.NS", "ITBEES.NS", "PSUBNKBEES.NS"]

FNO_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "SBIN.NS", "AXISBANK.NS", "BAJFINANCE.NS",
    "HINDUNILVR.NS", "ITC.NS", "BHARTIARTL.NS", "WIPRO.NS",
    "TVSMOTOR.NS", "MARUTI.NS", "SUNPHARMA.NS", "DRREDDY.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "ONGC.NS", "NTPC.NS",
    "POWERGRID.NS", "ADANIENT.NS", "ADANIPORTS.NS", "ULTRACEMCO.NS",
    "GRASIM.NS", "ASIANPAINT.NS", "NESTLEIND.NS", "TITAN.NS",
    "HCLTECH.NS", "TECHM.NS", "LTIM.NS", "LT.NS", "BAJAJFINSV.NS",
    "BAJAJ-AUTO.NS", "HEROMOTOCO.NS", "EICHERMOT.NS", "M&M.NS",
    "TATACONSUM.NS", "BRITANNIA.NS", "DIVISLAB.NS", "APOLLOHOSP.NS",
    "CIPLA.NS", "COALINDIA.NS", "BPCL.NS", "IOC.NS", "HINDALCO.NS",
    "VEDL.NS", "JINDALSTEL.NS",
]

MCX_COMMODITIES = ["CRUDEOIL", "GOLD", "SILVER", "NATURALGAS", "COPPER", "ALUMINIUM", "ZINC"]
CURRENCY_PAIRS = ["USDINR", "EURINR", "GBPINR", "JPYINR"]


def _load_json(path: str, default: Any) -> Any:
    """Load a JSON file and return a safe default on errors."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _parse_time(value: str | None) -> datetime | None:
    """Parse an ISO timestamp into a datetime or None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def get_asset_registry() -> list[dict]:
    """Return BULL's tracked market asset-class registry."""
    return [
        {
            "id": "nifty50_equity",
            "name": "Nifty 50 Stocks",
            "exchange": "NSE",
            "tier": 1,
            "instruments": NIFTY_50,
            "risk_level": "LOW",
            "liquidity_rating": 5,
            "leverage": 1.0,
            "margin_required": False,
            "sebi_warning": False,
            "description": "Shares of India's largest listed companies bought without leverage.",
            "scan_enabled": True,
            "unlock_condition": None,
        },
        {
            "id": "largecap_etfs",
            "name": "Large-cap ETFs",
            "exchange": "NSE",
            "tier": 1,
            "instruments": ETF_LIST,
            "risk_level": "LOW",
            "liquidity_rating": 4,
            "leverage": 1.0,
            "margin_required": False,
            "sebi_warning": False,
            "description": "Baskets like NIFTYBEES or GOLDBEES that trade like stocks.",
            "scan_enabled": True,
            "unlock_condition": None,
        },
        {
            "id": "stock_futures",
            "name": "Stock Futures",
            "exchange": "NSE F&O",
            "tier": 2,
            "instruments": FNO_STOCKS,
            "risk_level": "HIGH",
            "liquidity_rating": 4,
            "leverage": 5.0,
            "margin_required": True,
            "sebi_warning": True,
            "description": "Leveraged contracts that move with individual stocks.",
            "scan_enabled": True,
            "unlock_condition": "Need 60%+ win rate over 30 closed paper trades to unlock stock futures.",
        },
        {
            "id": "index_options",
            "name": "Index Options",
            "exchange": "NSE",
            "tier": 2,
            "instruments": ["NIFTY", "BANKNIFTY"],
            "risk_level": "EXTREME",
            "liquidity_rating": 5,
            "leverage": 10.0,
            "margin_required": True,
            "sebi_warning": True,
            "description": "NIFTY and BANKNIFTY call/put contracts with fast premium movement.",
            "scan_enabled": True,
            "unlock_condition": "Need Advanced skill gate plus 50 paper trades to unlock index options.",
        },
        {
            "id": "stock_options",
            "name": "Stock Options",
            "exchange": "NSE F&O",
            "tier": 2,
            "instruments": FNO_STOCKS[:20],
            "risk_level": "EXTREME",
            "liquidity_rating": 3,
            "leverage": 10.0,
            "margin_required": True,
            "sebi_warning": True,
            "description": "Call/put contracts on individual stocks with expiry and time decay.",
            "scan_enabled": True,
            "unlock_condition": "Need Professional skill gate to unlock stock options.",
        },
        {
            "id": "commodity_futures",
            "name": "Commodity Futures",
            "exchange": "MCX",
            "tier": 2,
            "instruments": MCX_COMMODITIES,
            "risk_level": "HIGH",
            "liquidity_rating": 4,
            "leverage": 5.0,
            "margin_required": True,
            "sebi_warning": True,
            "description": "Contracts on gold, silver, crude oil, natural gas, and metals.",
            "scan_enabled": True,
            "unlock_condition": "Need Intermediate gate and commodity paper journal discipline.",
        },
        {
            "id": "currency_derivatives",
            "name": "Currency Derivatives",
            "exchange": "NSE",
            "tier": 2,
            "instruments": CURRENCY_PAIRS,
            "risk_level": "HIGH",
            "liquidity_rating": 3,
            "leverage": 5.0,
            "margin_required": True,
            "sebi_warning": True,
            "description": "Contracts tracking currency pairs like USD/INR.",
            "scan_enabled": True,
            "unlock_condition": "Need Intermediate gate and macro-risk training.",
        },
        {
            "id": "sme_penny",
            "name": "SME / Penny Stocks",
            "exchange": "NSE/BSE",
            "tier": 3,
            "instruments": [],
            "risk_level": "EXTREME",
            "liquidity_rating": 1,
            "leverage": 1.0,
            "margin_required": False,
            "sebi_warning": False,
            "description": "Illiquid shares where exits can be difficult.",
            "scan_enabled": False,
            "unlock_condition": "Unlock after 6 months of profitable paper trading.",
        },
        {
            "id": "weekly_expiry_day",
            "name": "Weekly Options Expiry Day Trading",
            "exchange": "NSE F&O",
            "tier": 3,
            "instruments": ["NIFTY", "BANKNIFTY"],
            "risk_level": "EXTREME",
            "liquidity_rating": 5,
            "leverage": 20.0,
            "margin_required": True,
            "sebi_warning": True,
            "description": "Very fast expiry-day option trading with high loss risk.",
            "scan_enabled": False,
            "unlock_condition": "Unlock after 6 months of profitable paper trading.",
        },
        {
            "id": "crypto",
            "name": "Crypto",
            "exchange": "Unregulated",
            "tier": 3,
            "instruments": [],
            "risk_level": "EXTREME",
            "liquidity_rating": 2,
            "leverage": 1.0,
            "margin_required": False,
            "sebi_warning": False,
            "description": "Unregulated digital assets outside BULL's Indian market scope.",
            "scan_enabled": False,
            "unlock_condition": "Blocked until BULL has a separate regulated-risk framework.",
        },
        {
            "id": "leveraged_inverse_etfs",
            "name": "Leveraged / Inverse ETFs",
            "exchange": "Global",
            "tier": 3,
            "instruments": [],
            "risk_level": "EXTREME",
            "liquidity_rating": 2,
            "leverage": 2.0,
            "margin_required": False,
            "sebi_warning": False,
            "description": "Products that amplify or invert index movement.",
            "scan_enabled": False,
            "unlock_condition": "Blocked until advanced risk testing is complete.",
        },
    ]


def _asset_class_for_signal(signal: dict) -> str:
    """Map a signal dictionary to a universe asset-class id."""
    explicit = signal.get("asset_class_id")
    if explicit:
        return explicit
    instrument_type = signal.get("instrument_type")
    if instrument_type == "index_option":
        return "index_options"
    if instrument_type == "commodity_future":
        return "commodity_futures"
    if instrument_type == "stock_future":
        return "stock_futures"
    ticker = str(signal.get("ticker", ""))
    if ticker in ETF_LIST:
        return "largecap_etfs"
    if ticker in NIFTY_50 or ticker.endswith(".NS"):
        return "nifty50_equity"
    return "unknown"


def get_opportunity_counts(db_path: str | None = None) -> dict:
    """Return last-24h signal counts grouped by universe asset class."""
    del db_path
    counts = {item["id"]: 0 for item in get_asset_registry()}
    cutoff = datetime.now() - timedelta(hours=24)
    for signal in _load_json(SIGNALS_FILE, []):
        created_at = _parse_time(signal.get("timestamp") or signal.get("created_at"))
        if created_at and created_at < cutoff:
            continue
        if signal.get("decision") not in {None, "TRADE", "WATCH"}:
            continue
        asset_id = _asset_class_for_signal(signal)
        if asset_id in counts:
            counts[asset_id] += 1
    return counts


def compute_skill_gate(db_path: str | None = None) -> dict:
    """Compute the honest paper-trading skill gate from local signal and trade logs."""
    del db_path
    trades = _load_json(TRADES_FILE, [])
    signals = _load_json(SIGNALS_FILE, [])
    cutoff = datetime.now() - timedelta(days=90)
    closed = []
    for trade in trades:
        if trade.get("status") != "CLOSED":
            continue
        exit_time = _parse_time(trade.get("exit_time")) or _parse_time(trade.get("entry_time"))
        if exit_time and exit_time < cutoff:
            continue
        closed.append(trade)

    total_trades = len(closed)
    wins = len([trade for trade in closed if float(trade.get("pnl", 0) or 0) > 0])
    win_rate = (wins / total_trades * 100) if total_trades else 0.0
    total_signals = len(signals)
    acted = len(trades)
    discipline_score = 100.0
    if total_signals:
        overtrade_penalty = max(0, acted - total_signals) * 5
        discipline_score = max(0.0, 100.0 - overtrade_penalty)
    if total_trades < 10:
        discipline_score = min(discipline_score, 55.0)

    score = min(100.0, (win_rate * 0.45) + (min(total_trades, 50) / 50 * 35) + (discipline_score * 0.20))
    if score >= 85 and total_trades >= 50 and win_rate >= 65:
        level = "Professional"
        unlocked_tiers = [1, 2]
        requirement = "Tier 3 remains locked by product policy. Keep 6 profitable paper months."
    elif score >= 70 and total_trades >= 30 and win_rate >= 60:
        level = "Advanced"
        unlocked_tiers = [1, 2]
        requirement = "Need 65%+ win rate over 50 closed paper trades for Professional."
    elif score >= 45 and total_trades >= 15 and win_rate >= 55:
        level = "Intermediate"
        unlocked_tiers = [1]
        requirement = "Need 60%+ win rate over 30 closed paper trades to unlock Tier 2 watch-to-trade review."
    else:
        level = "Beginner"
        unlocked_tiers = [1]
        requirement = "Need 55%+ win rate over 15 closed paper trades to reach Intermediate."

    return {
        "level": level,
        "score": round(score, 2),
        "win_rate_90d": round(win_rate, 2),
        "total_trades": total_trades,
        "logged_signals": total_signals,
        "discipline_score": round(discipline_score, 2),
        "unlocked_tiers": unlocked_tiers,
        "next_unlock_requirement": requirement,
    }


def get_universe_payload(db_path: str | None = None) -> dict:
    """Return registry, skill gate, and opportunity counts in one response."""
    counts = get_opportunity_counts(db_path)
    skill_gate = compute_skill_gate(db_path)
    registry = []
    for item in get_asset_registry():
        enriched = dict(item)
        enriched["opportunity_count"] = counts.get(item["id"], 0)
        enriched["locked"] = item["tier"] not in skill_gate["unlocked_tiers"]
        registry.append(enriched)
    return {
        "registry": registry,
        "skill_gate": skill_gate,
        "opportunity_counts": counts,
    }
