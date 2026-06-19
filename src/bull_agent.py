"""BULL AI Agent — Gemini-powered stock reasoning engine.

This module is the AI brain of BULL. Instead of if-else scoring, it sends
a stock's full context (technicals, news, regime, backtest history) to
Google Gemini and asks it to reason about whether the setup is tradeable.

It returns structured output that matches the existing pick format so the
rest of the system (UI, paper trading, Telegram) works without changes.

If Gemini is unavailable (no key, rate limit, error), it falls back to
the existing rule-based engine — nothing breaks.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
)
# Free tier: 15 RPM.  We stay well under.
MAX_CALLS_PER_MINUTE = 12
_rate_lock = threading.Lock()
_rate_window_start: float = 0.0
_rate_calls: int = 0


def _get_api_key() -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return key if key else None


def _rate_check() -> bool:
    """Process-local sliding-window rate governor."""
    global _rate_window_start, _rate_calls
    now = time.time()
    with _rate_lock:
        if now - _rate_window_start >= 60:
            _rate_window_start = now
            _rate_calls = 0
        if _rate_calls >= MAX_CALLS_PER_MINUTE:
            return False
        _rate_calls += 1
        return True


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are BULL, an expert Indian stock market research AI built for a private \
trader. Your job is to analyze a stock's full context and decide whether it \
is a high-probability swing trade setup for the next 1-5 trading days.

You are direct, honest, and never fake confidence. If the setup is weak, \
say so. If data is stale or missing, say so. You never guarantee profit.

You think in terms of:
- Trend alignment (price vs moving averages)
- Momentum (RSI, volume surge)
- Volatility (ATR-based risk/reward)
- Market regime (is Nifty supporting longs?)
- News catalyst or risk (earnings, probes, order wins)
- Historical edge (has this setup worked before on this stock?)

When you recommend a trade, you give exact entry trigger, stop-loss, and \
target prices. You explain WHY in plain English that a beginner can follow.

You must return your analysis as a JSON object with these exact keys:
{
  "decision": "TRADE" | "WAIT" | "REJECT",
  "confidence_score": 0-100,
  "direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "setup_type": "BREAKOUT_LONG" | "PULLBACK_LONG" | "REVERSAL_LONG" | "WATCH_ONLY" | "NO_SETUP",
  "entry_trigger": <price>,
  "stop_loss": <price>,
  "target_1": <price>,
  "target_2": <price>,
  "risk_reward_ratio": <float>,
  "reasons": ["reason 1", "reason 2", ...],
  "risks": ["risk 1", "risk 2", ...],
  "agent_reasoning": "<2-4 sentence plain-English summary of your thinking>"
}

Rules:
- TRADE means you have genuine conviction with clear entry/stop/target.
- WAIT means the stock is interesting but the setup isn't clean enough yet.
- REJECT means there's no edge here today.
- confidence_score above 75 = strong conviction. 60-75 = moderate. Below 60 = weak.
- entry_trigger must be a price the stock has NOT yet crossed (conditional entry).
- stop_loss must be below entry_trigger for longs.
- target_1 should give at least 1.5:1 reward-to-risk.
- Never set confidence_score above 85 — markets are uncertain.
- If the market regime is BEARISH, be extra cautious. TRADE only with very strong setups.
- If historical edge is BAD or UNKNOWN, default to WAIT unless technicals are exceptional.

Return ONLY the raw JSON object. No markdown, no ```json, no explanation outside the JSON.
"""


def _build_stock_prompt(context: dict[str, Any]) -> str:
    """Build the per-stock user prompt from gathered context."""
    ticker = context.get("ticker", "UNKNOWN")
    company = context.get("company_name", ticker)
    sector = context.get("sector", "Unknown")

    # Price summary
    price = context.get("price_summary", {})
    price_block = (
        f"Close: ₹{price.get('close', 0):.2f} on {price.get('date', '?')}\n"
        f"SMA20: ₹{price.get('sma20', 0):.2f}, SMA50: ₹{price.get('sma50', 0):.2f}"
    )
    if price.get("sma200"):
        price_block += f", SMA200: ₹{price['sma200']:.2f}"
    price_block += (
        f"\nRSI(14): {price.get('rsi', 0):.1f}\n"
        f"ATR(14): ₹{price.get('atr', 0):.2f} ({price.get('atr_pct', 0):.2f}% of price)\n"
        f"Volume ratio (today vs 20d avg): {price.get('volume_ratio', 0):.2f}x\n"
        f"5-day return: {price.get('ret_5d', 0):.2f}% | 20-day return: {price.get('ret_20d', 0):.2f}%\n"
        f"20-day high: ₹{price.get('high_20', 0):.2f} | 10-day low: ₹{price.get('low_10', 0):.2f}"
    )

    # Market regime
    regime = context.get("regime", {})
    regime_block = (
        f"Nifty bias: {regime.get('bias', 'NEUTRAL')}, "
        f"Trend score: {regime.get('trend_score', 50)}/100"
    )

    # News
    news_items = context.get("news_headlines", [])
    if news_items:
        news_block = "\n".join(
            f"- [{item.get('sentiment', 'NEUTRAL')}] {item.get('title', '')}"
            for item in news_items[:6]
        )
    else:
        news_block = "No recent news headlines available."

    # Backtest history
    bt = context.get("backtest", {})
    if bt.get("total_trades", 0) > 0:
        bt_block = (
            f"Verdict: {bt.get('verdict', 'UNKNOWN')} | "
            f"Win rate: {bt.get('win_rate', 0)*100:.1f}% across {bt.get('total_trades', 0)} historical trades | "
            f"Net profit: ₹{bt.get('net_profit', 0):.0f}"
        )
    else:
        bt_block = "No backtest history available for this stock."

    # Sector
    sector_block = f"Sector: {sector}"
    if context.get("sector_return_20d") is not None:
        sector_block += f" | Sector 20d return: {context['sector_return_20d']:.2f}%"
    if context.get("sector_rank") is not None:
        sector_block += f" | Sector rank: #{context['sector_rank']}"

    # Capital
    capital = context.get("capital", {})
    capital_block = (
        f"Max risk per trade: ₹{capital.get('max_risk', 100):.0f}"
    )

    return (
        f"Analyze this stock for a swing trade setup:\n\n"
        f"STOCK: {ticker} ({company})\n"
        f"{sector_block}\n\n"
        f"PRICE DATA:\n{price_block}\n\n"
        f"MARKET REGIME:\n{regime_block}\n\n"
        f"RECENT NEWS:\n{news_block}\n\n"
        f"HISTORICAL BACKTEST:\n{bt_block}\n\n"
        f"RISK BUDGET:\n{capital_block}\n"
    )


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------

def _call_gemini(system: str, user_prompt: str, api_key: str) -> dict[str, Any] | None:
    """Call Gemini and return parsed JSON response, or None on failure."""
    url = GEMINI_URL_TEMPLATE.format(model=GEMINI_MODEL, key=api_key)
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.3,
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = response.read().decode("utf-8")
            res_json = json.loads(res_data)

            candidates = res_json.get("candidates", [])
            if not candidates:
                logger.warning("Gemini returned no candidates")
                return None

            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            if not text:
                logger.warning("Gemini returned empty text")
                return None

            # Clean potential markdown wrapping
            clean = text.strip()
            if clean.startswith("```"):
                lines = clean.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                clean = "\n".join(lines).strip()

            return json.loads(clean)

    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            pass
        logger.error("Gemini HTTP %s: %s", exc.code, body)
        return None
    except Exception as exc:
        logger.error("Gemini call failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def build_agent_context(
    ticker: str,
    df,  # pandas DataFrame with price data
    settings: dict | None = None,
    market_bias: str = "NEUTRAL",
    trend_score: int = 50,
    news_items: list[dict] | None = None,
    backtest_result: dict | None = None,
    sector_return_20d: float | None = None,
    sector_rank: int | None = None,
    company_name: str | None = None,
    sector: str | None = None,
) -> dict[str, Any]:
    """Gather all context for a stock into a single dict for the agent."""
    import pandas as pd
    from src.engine import calculate_rsi, calculate_atr

    settings = settings or {}
    max_risk = float(settings.get("max_risk_per_trade") or 100.0)

    # Compute technicals
    df = df.copy()
    if "date" not in df.columns and "Date" in df.columns:
        df = df.rename(columns={"Date": "date"})
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)

    if len(df) < 20:
        return {"ticker": ticker, "insufficient_data": True}

    df["sma_20"] = df["close"].rolling(20).mean()
    df["sma_50"] = df["close"].rolling(50).mean() if len(df) >= 50 else pd.Series([None] * len(df))
    df["sma_200"] = df["close"].rolling(200).mean() if len(df) >= 200 else pd.Series([None] * len(df))
    df["rsi_14"] = calculate_rsi(df["close"])
    df["atr_14"] = calculate_atr(df)
    df["vol_avg_20"] = df["volume"].rolling(20).mean()
    df["high_20"] = df["high"].rolling(20).max()
    df["low_10"] = df["low"].rolling(10).min()

    latest = df.iloc[-1]
    close_val = float(latest["close"])
    latest_date = pd.to_datetime(latest["date"]).strftime("%Y-%m-%d")

    sma20 = float(latest["sma_20"]) if not pd.isna(latest["sma_20"]) else close_val
    sma50 = float(latest["sma_50"]) if not pd.isna(latest.get("sma_50")) else close_val
    sma200 = float(latest["sma_200"]) if not pd.isna(latest.get("sma_200")) else None
    rsi = float(latest["rsi_14"]) if not pd.isna(latest["rsi_14"]) else 50.0
    atr = float(latest["atr_14"]) if not pd.isna(latest["atr_14"]) else close_val * 0.02
    vol_avg = float(latest["vol_avg_20"]) if not pd.isna(latest["vol_avg_20"]) else 1.0
    volume_ratio = float(latest["volume"] / vol_avg) if vol_avg > 0 else 0.0

    ret_5d = ((close_val / float(df["close"].iloc[-6])) - 1) * 100 if len(df) >= 6 else 0.0
    ret_20d = ((close_val / float(df["close"].iloc[-21])) - 1) * 100 if len(df) >= 21 else 0.0

    high_20 = float(latest["high_20"]) if not pd.isna(latest["high_20"]) else close_val
    low_10 = float(latest["low_10"]) if not pd.isna(latest["low_10"]) else close_val

    # News headlines with sentiment
    headline_list = []
    for item in (news_items or [])[:6]:
        headline_list.append({
            "title": item.get("title", ""),
            "sentiment": item.get("sentiment_label", item.get("sentiment", "NEUTRAL")),
        })

    return {
        "ticker": ticker,
        "company_name": company_name or ticker.replace(".NS", ""),
        "sector": sector or "Unknown",
        "insufficient_data": False,
        "price_summary": {
            "close": close_val,
            "date": latest_date,
            "sma20": sma20,
            "sma50": sma50,
            "sma200": sma200,
            "rsi": rsi,
            "atr": atr,
            "atr_pct": (atr / close_val) * 100 if close_val > 0 else 0,
            "volume_ratio": volume_ratio,
            "ret_5d": ret_5d,
            "ret_20d": ret_20d,
            "high_20": high_20,
            "low_10": low_10,
        },
        "regime": {
            "bias": market_bias,
            "trend_score": trend_score,
        },
        "news_headlines": headline_list,
        "backtest": backtest_result or {},
        "sector_return_20d": sector_return_20d,
        "sector_rank": sector_rank,
        "capital": {
            "max_risk": max_risk,
        },
    }


# ---------------------------------------------------------------------------
# Main agent interface
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"decision", "confidence_score", "entry_trigger", "stop_loss", "target_1"}
_VALID_DECISIONS = {"TRADE", "WAIT", "REJECT"}


def _validate_agent_output(result: dict[str, Any]) -> bool:
    """Check that the agent returned a usable response."""
    if not isinstance(result, dict):
        return False
    if not _REQUIRED_KEYS.issubset(result.keys()):
        return False
    if str(result.get("decision", "")).upper() not in _VALID_DECISIONS:
        return False
    try:
        score = int(result["confidence_score"])
        if not 0 <= score <= 100:
            return False
    except (TypeError, ValueError):
        return False
    return True


def _clamp_confidence(result: dict[str, Any]) -> dict[str, Any]:
    """Enforce the hard cap — never above 85."""
    result = dict(result)
    try:
        score = int(result.get("confidence_score", 0))
        result["confidence_score"] = min(score, 85)
    except (TypeError, ValueError):
        result["confidence_score"] = 50
    return result


def analyze_stock(context: dict[str, Any]) -> dict[str, Any] | None:
    """Run the Gemini agent on a single stock context.

    Returns the agent's structured pick dict, or None if the agent is
    unavailable (no key, rate limit, error).  The caller is responsible
    for falling back to rule-based scoring when this returns None.
    """
    if context.get("insufficient_data"):
        return None

    api_key = _get_api_key()
    if not api_key:
        logger.info("No GEMINI_API_KEY set — falling back to rule-based scoring")
        return None

    if not _rate_check():
        logger.warning("Gemini rate limit reached — falling back to rule-based scoring")
        return None

    user_prompt = _build_stock_prompt(context)
    result = _call_gemini(SYSTEM_PROMPT, user_prompt, api_key)

    if result is None:
        return None

    if not _validate_agent_output(result):
        logger.warning(
            "Agent returned invalid output for %s: %s",
            context.get("ticker"),
            json.dumps(result, default=str)[:200],
        )
        return None

    result = _clamp_confidence(result)
    result["source"] = "bull_agent"
    result["model"] = GEMINI_MODEL

    return result
