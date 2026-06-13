"""Lean daily BULL signal engine.

This module is intentionally boring and dependable. It uses stored daily
candles, simple transparent indicators, and strict risk sizing. The richer ML,
news, and backtest layers can still exist around it, but the morning product
must be able to produce an honest answer without those optional parts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import numpy as np
import pandas as pd

from src import backtest, database, market, news
from src.engine import calculate_atr, calculate_rsi


MIN_SCAN_ROWS = 60
MAX_STALE_DAYS = 4
MIN_AVG_TURNOVER = 50_000_000


@dataclass(frozen=True)
class UniverseItem:
    ticker: str
    name: str
    sector: str


CORE_UNIVERSE: tuple[UniverseItem, ...] = (
    UniverseItem("RELIANCE.NS", "Reliance Industries", "Energy"),
    UniverseItem("TCS.NS", "Tata Consultancy Services", "IT"),
    UniverseItem("HDFCBANK.NS", "HDFC Bank", "Banking"),
    UniverseItem("INFY.NS", "Infosys", "IT"),
    UniverseItem("ICICIBANK.NS", "ICICI Bank", "Banking"),
    UniverseItem("HINDUNILVR.NS", "Hindustan Unilever", "FMCG"),
    UniverseItem("ITC.NS", "ITC", "FMCG"),
    UniverseItem("SBIN.NS", "State Bank of India", "Banking"),
    UniverseItem("BHARTIARTL.NS", "Bharti Airtel", "Telecom"),
    UniverseItem("KOTAKBANK.NS", "Kotak Mahindra Bank", "Banking"),
    UniverseItem("BAJFINANCE.NS", "Bajaj Finance", "Financials"),
    UniverseItem("AXISBANK.NS", "Axis Bank", "Banking"),
    UniverseItem("LT.NS", "Larsen and Toubro", "Capital Goods"),
    UniverseItem("MARUTI.NS", "Maruti Suzuki", "Auto"),
    UniverseItem("SUNPHARMA.NS", "Sun Pharma", "Pharma"),
    UniverseItem("TITAN.NS", "Titan", "Consumer"),
    UniverseItem("WIPRO.NS", "Wipro", "IT"),
    UniverseItem("ULTRACEMCO.NS", "UltraTech Cement", "Cement"),
    UniverseItem("HCLTECH.NS", "HCL Technologies", "IT"),
    UniverseItem("TMPV.NS", "Tata Motors Passenger Vehicles", "Auto"),
    UniverseItem("NTPC.NS", "NTPC", "Power"),
    UniverseItem("ONGC.NS", "ONGC", "Energy"),
    UniverseItem("POWERGRID.NS", "Power Grid", "Power"),
    UniverseItem("COALINDIA.NS", "Coal India", "Metals"),
    UniverseItem("HINDALCO.NS", "Hindalco", "Metals"),
    UniverseItem("M&M.NS", "Mahindra and Mahindra", "Auto"),
)


def _round_price(value: float) -> float:
    return round(float(value), 2)


def _now_date() -> datetime.date:
    return datetime.now().date()


def _metadata_map() -> dict[str, UniverseItem]:
    return {item.ticker.upper(): item for item in CORE_UNIVERSE}


def _clean_numeric_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "date" not in out.columns and "Date" in out.columns:
        out = out.rename(columns={"Date": "date"})
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "open", "high", "low", "close", "volume"])
    return out.sort_values("date").reset_index(drop=True)


def _empty_setup(ticker: str, reason: str) -> dict:
    meta = _metadata_map().get(ticker.upper())
    return {
        "ticker": ticker.upper(),
        "company_name": meta.name if meta else ticker.upper(),
        "sector": meta.sector if meta else "Unknown",
        "direction": "NEUTRAL",
        "setup_type": "NO_SETUP",
        "entry_trigger": 0.0,
        "stop_loss": 0.0,
        "target_1": 0.0,
        "target_2": 0.0,
        "risk_per_share": 0.0,
        "suggested_quantity": 0,
        "max_loss": 0.0,
        "confidence_score": 0,
        "ml_probability": 0.0,
        "kelly_pct": 0.0,
        "hedge_cost": 0.0,
        "hedge_strike": 0.0,
        "reasons": [reason],
        "decision": "REJECT",
        "last_close": 0.0,
        "last_date": None,
        "rsi_14": 0.0,
        "volume_ratio": 0.0,
        "atr_pct": 0.0,
        "return_20d": 0.0,
        "sector_return_20d": 0.0,
        "sector_rank": None,
        "historical_verdict": "UNKNOWN",
        "historical_win_rate": 0.0,
        "historical_trades": 0,
        "historical_net_profit": 0.0,
        "news_sentiment": "NEUTRAL",
        "news_score": 0.0,
        "news_headline_count": 0,
    }


def analyze_price_frame(
    ticker: str,
    df: pd.DataFrame,
    settings: dict | None = None,
    market_bias: str = "NEUTRAL",
) -> dict:
    """Analyze one stock using a transparent swing-trading checklist."""
    ticker = ticker.upper()
    settings = settings or {}
    max_risk = float(settings.get("max_risk_per_trade") or 100.0)
    meta = _metadata_map().get(ticker)

    if df is None or df.empty:
        return _empty_setup(ticker, "No stored candles found for this symbol.")

    df = _clean_numeric_frame(df)
    if len(df) < MIN_SCAN_ROWS:
        return _empty_setup(
            ticker,
            f"Only {len(df)} daily candles found. Need at least {MIN_SCAN_ROWS} for a basic swing scan.",
        )

    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean()
    df["sma_200"] = df["close"].rolling(200).mean()
    df["rsi_14"] = calculate_rsi(df["close"])
    df["atr_14"] = calculate_atr(df)
    df["vol_avg_20"] = df["volume"].rolling(20).mean()
    df["turnover_avg_20"] = (df["volume"] * df["close"]).rolling(20).mean()
    df["high_20_prev"] = df["high"].shift(1).rolling(20).max()
    df["low_10_prev"] = df["low"].shift(1).rolling(10).min()

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close_val = float(latest["close"])
    latest_date = pd.to_datetime(latest["date"]).date()
    age_days = (_now_date() - latest_date).days

    sma20 = float(latest["sma_20"])
    sma50 = float(latest["sma_50"])
    sma200 = float(latest["sma_200"]) if not pd.isna(latest["sma_200"]) else None
    rsi = float(latest["rsi_14"])
    atr = float(latest["atr_14"]) if not pd.isna(latest["atr_14"]) else close_val * 0.02
    atr_pct = (atr / close_val) * 100 if close_val else 0.0
    vol_avg_20 = float(latest["vol_avg_20"]) if not pd.isna(latest["vol_avg_20"]) else 0.0
    volume_ratio = float(latest["volume"] / vol_avg_20) if vol_avg_20 > 0 else 0.0
    avg_turnover = float(latest["turnover_avg_20"]) if not pd.isna(latest["turnover_avg_20"]) else 0.0
    ret_5d = (close_val / float(df["close"].iloc[-6]) - 1.0) if len(df) >= 6 else 0.0
    ret_20d = (close_val / float(df["close"].iloc[-21]) - 1.0) if len(df) >= 21 else 0.0

    high20 = float(latest["high_20_prev"]) if not pd.isna(latest["high_20_prev"]) else float(prev["high"])
    low10 = float(latest["low_10_prev"]) if not pd.isna(latest["low_10_prev"]) else float(prev["low"])
    breakout_level = max(float(prev["high"]), high20)
    buffer = max(close_val * 0.001, atr * 0.08)
    entry = _round_price(breakout_level + buffer)
    stop = _round_price(max(low10, entry - (1.35 * atr)))
    if stop >= entry:
        stop = _round_price(entry - max(atr, entry * 0.012))
    risk_per_share = _round_price(entry - stop)
    target_1 = _round_price(entry + (1.5 * risk_per_share))
    target_2 = _round_price(entry + (2.25 * risk_per_share))
    suggested_qty = int(max_risk // risk_per_share) if risk_per_share > 0 else 0
    max_loss = _round_price(suggested_qty * risk_per_share)

    score = 0
    score += 14 if close_val > sma20 else 0
    score += 12 if sma20 > sma50 else 0
    score += 10 if close_val > sma50 else 0
    score += 8 if sma200 is None or close_val > sma200 else 0
    score += 10 if 48 <= rsi <= 68 else 4 if 42 <= rsi < 48 else 0
    score += 10 if volume_ratio >= 1.15 else 5 if volume_ratio >= 0.95 else 0
    score += 8 if ret_5d > 0 else 0
    score += 8 if ret_20d > 0 else 0
    score += 8 if close_val >= breakout_level * 0.965 else 0
    score += 8 if MIN_AVG_TURNOVER <= avg_turnover else 0
    score += 12 if 0.7 <= atr_pct <= 4.5 else 4 if 0.4 <= atr_pct <= 5.5 else 0
    score = int(min(max(score, 0), 100))

    hard_blocks: list[str] = []
    if age_days > MAX_STALE_DAYS:
        hard_blocks.append(f"latest candle is stale ({latest_date})")
    if market_bias == "BEARISH":
        hard_blocks.append("market regime is bearish")
    if close_val < sma50:
        hard_blocks.append("price is below the 50-day trend line")
    if rsi > 72:
        hard_blocks.append("RSI is overheated; do not chase")
    if avg_turnover < MIN_AVG_TURNOVER:
        hard_blocks.append("average traded value is too low for clean execution")
    if not 0.7 <= atr_pct <= 4.5:
        hard_blocks.append("volatility is outside the preferred range")
    if risk_per_share <= 0 or suggested_qty <= 0:
        hard_blocks.append("risk per share is too large for your risk budget")

    reasons = [
        f"Latest close {close_val:.2f} on {latest_date}; RSI14 {rsi:.1f}.",
        f"Volume is {volume_ratio:.2f}x the 20-day average.",
        f"Trend check: close {'above' if close_val > sma20 else 'below'} SMA20 and {'above' if close_val > sma50 else 'below'} SMA50.",
    ]

    if hard_blocks:
        decision = "WAIT" if score >= 55 else "REJECT"
        reasons.append("Blocked: " + "; ".join(hard_blocks) + ".")
    elif score >= 72:
        decision = "TRADE"
        reasons.append("Conditional long setup: buy only if price crosses the trigger; no trigger means no trade.")
    elif score >= 58:
        decision = "WAIT"
        reasons.append("Watchlist candidate, but the full trade checklist is not strong enough yet.")
    else:
        decision = "REJECT"
        reasons.append("Setup quality is weak today.")

    return {
        "ticker": ticker,
        "company_name": meta.name if meta else ticker,
        "sector": meta.sector if meta else "Unknown",
        "direction": "BULLISH" if close_val > sma20 > sma50 else "NEUTRAL",
        "setup_type": "BREAKOUT_LONG" if decision == "TRADE" else "WATCH_ONLY",
        "entry_trigger": entry,
        "stop_loss": stop,
        "target_1": target_1,
        "target_2": target_2,
        "risk_per_share": risk_per_share,
        "suggested_quantity": suggested_qty,
        "max_loss": max_loss,
        "confidence_score": score,
        "ml_probability": round(score / 100, 4),
        "kelly_pct": 0.0,
        "hedge_cost": 0.0,
        "hedge_strike": 0.0,
        "reasons": reasons,
        "decision": decision,
        "last_close": _round_price(close_val),
        "last_date": str(latest_date),
        "rsi_14": round(rsi, 1),
        "volume_ratio": round(volume_ratio, 2),
        "atr_pct": round(atr_pct, 2),
        "return_20d": round(ret_20d * 100, 2),
    }


def _tickers_to_scan() -> list[str]:
    tickers = [t.upper() for t in database.get_watchlist_tickers()]
    if not tickers:
        return [item.ticker for item in CORE_UNIVERSE]
    index_symbols = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
    known = {item.ticker for item in CORE_UNIVERSE}
    ordered = [item.ticker for item in CORE_UNIVERSE if item.ticker in set(tickers)]
    extras = [ticker for ticker in tickers if ticker not in known and ticker not in index_symbols]
    return ordered + extras


def _decision_priority(decision: str) -> int:
    return {"TRADE": 0, "WAIT": 1, "REJECT": 2}.get(decision, 3)


def _historical_priority(verdict: str) -> int:
    return {"GOOD": 0, "WEAK": 1, "BAD": 2, "UNKNOWN": 3}.get(str(verdict).upper(), 4)


def _apply_sector_overlay(results: list[dict]) -> None:
    """Add sector relative-strength context and modestly adjust confidence."""
    sector_values: dict[str, list[float]] = {}
    for item in results:
        sector = str(item.get("sector") or "Unknown")
        if sector == "Unknown":
            continue
        ret = item.get("return_20d")
        if ret is None:
            continue
        sector_values.setdefault(sector, []).append(float(ret))

    sector_avg = {
        sector: sum(values) / len(values)
        for sector, values in sector_values.items()
        if values
    }
    ranked = sorted(sector_avg.items(), key=lambda pair: pair[1], reverse=True)
    ranks = {sector: index + 1 for index, (sector, _) in enumerate(ranked)}

    for item in results:
        sector = str(item.get("sector") or "Unknown")
        avg = float(sector_avg.get(sector, 0.0))
        rank = ranks.get(sector)
        item["sector_return_20d"] = round(avg, 2)
        item["sector_rank"] = rank
        if rank and rank <= 3 and avg > 0:
            item["confidence_score"] = min(100, int(item.get("confidence_score") or 0) + 5)
            item.setdefault("reasons", []).append(
                f"Sector overlay: {sector} is a top-{rank} relative-strength sector over 20 trading days."
            )
        elif avg < 0:
            item["confidence_score"] = max(0, int(item.get("confidence_score") or 0) - 5)
            item.setdefault("reasons", []).append(
                f"Sector overlay: {sector} is weak over 20 trading days, so confidence is reduced."
            )


def _apply_historical_overlay(results: list[dict]) -> None:
    """Use backtest verdicts to stop weak technical setups from becoming trade picks."""
    for item in results:
        ticker = item.get("ticker")
        if not ticker or item.get("decision") == "REJECT":
            continue
        try:
            verdict = backtest.get_stock_verdict(ticker)
        except Exception as exc:
            verdict = {
                "verdict": "UNKNOWN",
                "win_rate": 0.0,
                "total_trades": 0,
                "net_profit": 0.0,
                "reason": f"Historical edge check failed: {exc}",
            }

        historical_verdict = str(verdict.get("verdict") or "UNKNOWN").upper()
        item["historical_verdict"] = historical_verdict
        item["historical_win_rate"] = float(verdict.get("win_rate") or 0.0)
        item["historical_trades"] = int(verdict.get("total_trades") or 0)
        item["historical_net_profit"] = float(verdict.get("net_profit") or 0.0)

        if historical_verdict == "GOOD":
            item["confidence_score"] = min(100, int(item.get("confidence_score") or 0) + 8)
            item.setdefault("reasons", []).append(
                f"Historical edge: GOOD ({item['historical_win_rate'] * 100:.1f}% win rate across {item['historical_trades']} trades)."
            )
        elif historical_verdict == "BAD":
            if item.get("decision") == "TRADE":
                item["decision"] = "WAIT"
                item["setup_type"] = "WATCH_ONLY"
            item["confidence_score"] = max(0, int(item.get("confidence_score") or 0) - 15)
            item.setdefault("reasons", []).append(
                "Historical edge: BAD for this strategy/ticker, so BULL downgrades it to watch-only."
            )
        else:
            if item.get("decision") == "TRADE":
                item["decision"] = "WAIT"
                item["setup_type"] = "WATCH_ONLY"
            item["confidence_score"] = max(0, int(item.get("confidence_score") or 0) - 6)
            item.setdefault("reasons", []).append(
                "Historical edge: sample is not strong enough yet, so this remains watch-only."
            )


def _apply_news_overlay(results: list[dict], max_news_checks: int) -> None:
    """Apply cached/free headline sentiment to the highest-ranked candidates."""
    candidates = [item for item in results if item.get("decision") != "REJECT"][:max_news_checks]
    for item in candidates:
        ticker = item.get("ticker")
        if not ticker:
            continue
        try:
            items = news.fetch_stock_news(ticker, gemini_api_key=None, force_refresh=False)
            score, label = news.get_aggregated_sentiment(items)
        except Exception:
            items = []
            score, label = 0.0, "NEUTRAL"

        label = str(label or "NEUTRAL").upper()
        item["news_sentiment"] = label
        item["news_score"] = float(score or 0.0)
        item["news_headline_count"] = len(items)

        if label == "BEARISH":
            if item.get("decision") == "TRADE":
                item["decision"] = "WAIT"
                item["setup_type"] = "WATCH_ONLY"
            item["confidence_score"] = max(0, int(item.get("confidence_score") or 0) - 10)
            item.setdefault("reasons", []).append(
                f"News filter: BEARISH headline sentiment from {len(items)} recent headline(s), so BULL downgrades risk."
            )
        elif label == "BULLISH":
            item["confidence_score"] = min(100, int(item.get("confidence_score") or 0) + 3)
            item.setdefault("reasons", []).append(
                f"News filter: BULLISH/positive headline tone from {len(items)} recent headline(s)."
            )
        else:
            item.setdefault("reasons", []).append(
                f"News filter: no bearish headline block found across {len(items)} recent headline(s)."
            )


def scan_daily_setups(tickers: Iterable[str] | None = None, max_items: int = 8) -> list[dict]:
    """Scan stored candles and return ranked daily setups."""
    database.init_db()
    settings = database.get_capital_settings()
    try:
        regime = market.get_market_regime()
        market_bias = str(regime.get("market_bias", "NEUTRAL")).upper()
    except Exception:
        market_bias = "NEUTRAL"

    results = []
    for ticker in tickers or _tickers_to_scan():
        try:
            df = database.get_prices(ticker)
            results.append(analyze_price_frame(ticker, df, settings, market_bias=market_bias))
        except Exception as exc:
            results.append(_empty_setup(ticker, f"Scanner error: {exc}"))

    _apply_sector_overlay(results)
    _apply_historical_overlay(results)

    results.sort(
        key=lambda item: (
            _decision_priority(item.get("decision", "REJECT")),
            _historical_priority(item.get("historical_verdict", "UNKNOWN")),
            -int(item.get("confidence_score") or 0),
            item.get("ticker", ""),
        )
    )
    _apply_news_overlay(results, max(max_items, 8))
    results.sort(
        key=lambda item: (
            _decision_priority(item.get("decision", "REJECT")),
            _historical_priority(item.get("historical_verdict", "UNKNOWN")),
            -int(item.get("confidence_score") or 0),
            item.get("ticker", ""),
        )
    )
    return results[:max_items]


def get_daily_picks(max_items: int = 8) -> list[dict]:
    """Return the ranked picks expected by the existing mentor UI."""
    return scan_daily_setups(max_items=max_items)


def build_daily_brief(max_trade_setups: int = 3) -> dict:
    """Build the structured daily brief used by API and Telegram."""
    database.init_db()
    try:
        regime = market.get_market_regime()
    except Exception:
        regime = {
            "market_bias": "NEUTRAL",
            "trend_score": 50,
            "volatility_score": 50,
            "reasons": ["Market regime check failed; using neutral mode."],
        }

    setups = scan_daily_setups(max_items=10)
    trade_setups = [item for item in setups if item.get("decision") == "TRADE"][:max_trade_setups]
    watch_setups = [item for item in setups if item.get("decision") == "WAIT"][:max_trade_setups]
    trend_score = int(regime.get("trend_score") or 50)
    bias = str(regime.get("market_bias", "NEUTRAL")).upper()
    if bias == "BULLISH" and trend_score >= 65:
        mood = "BULLISH"
    elif bias == "BEARISH" or trend_score <= 35:
        mood = "BEARISH"
    else:
        mood = "CAUTIOUS"

    command = "TRADE" if trade_setups else "WAIT"
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "command": command,
        "market_mood": mood,
        "market_bias": bias,
        "bull_score": trend_score,
        "regime_reasons": regime.get("reasons", []),
        "trade_setups": trade_setups,
        "watch_setups": watch_setups,
        "all_ranked_setups": setups,
        "risk_note": "Conditional research only. Use paper trading until your journal proves an edge.",
    }


def format_telegram_brief(brief: dict | None = None) -> str:
    """Format a phone-friendly Telegram message without relying on markdown art."""
    brief = brief or build_daily_brief()
    day_label = datetime.now().strftime("%A, %d %b %Y")
    lines = [
        f"BULL - {day_label}",
        "",
        f"Market mood: {brief['market_mood']} ({brief['bull_score']}/100)",
    ]

    trades = brief.get("trade_setups", [])
    if trades:
        lines.append(f"Plan: {len(trades)} conditional stock setup(s).")
        lines.append("")
        for index, setup in enumerate(trades, start=1):
            entry = float(setup.get("entry_trigger") or 0)
            stop = float(setup.get("stop_loss") or 0)
            target = float(setup.get("target_1") or 0)
            qty = int(setup.get("suggested_quantity") or 0)
            max_loss = float(setup.get("max_loss") or 0)
            reason = (setup.get("reasons") or ["Technical setup passed the checklist."])[-1]
            lines.extend(
                [
                    f"{index}. {setup.get('ticker', '').replace('.NS', '')}",
                    f"Buy only above: INR {entry:.2f}",
                    f"Stop loss: INR {stop:.2f}",
                    f"Target 1: INR {target:.2f}",
                    f"Quantity: {qty} share(s)",
                    f"Max loss if stop hits: INR {max_loss:.2f}",
                    f"Why: {reason}",
                    "Rule: no trigger, no trade.",
                    "",
                ]
            )
    else:
        reasons = brief.get("regime_reasons") or ["No clean setup passed the full checklist."]
        lines.extend(
            [
                "Plan: No fresh trade today.",
                f"Why: {reasons[0]}",
                "Action: sit in cash, review open paper trades, and wait for a cleaner day.",
            ]
        )

    lines.extend(
        [
            "",
            "Risk rule: this is research, not a profit guarantee. Paper trade until the journal proves the edge.",
        ]
    )
    return "\n".join(line.rstrip() for line in lines).strip()
