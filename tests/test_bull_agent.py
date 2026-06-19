"""Tests for the BullAgent AI reasoning engine."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd
import numpy as np

from src import bull_agent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_df():
    """Generate 80 rows of realistic-ish daily OHLCV data."""
    np.random.seed(42)
    dates = pd.bdate_range(end="2026-06-18", periods=80)
    close = 1000 + np.cumsum(np.random.randn(80) * 8)
    df = pd.DataFrame({
        "date": dates,
        "open": close - np.random.rand(80) * 5,
        "high": close + np.random.rand(80) * 10,
        "low": close - np.random.rand(80) * 10,
        "close": close,
        "volume": np.random.randint(500_000, 5_000_000, 80),
    })
    return df


@pytest.fixture()
def sample_context(sample_df):
    """Build a full agent context from sample data."""
    return bull_agent.build_agent_context(
        ticker="RELIANCE.NS",
        df=sample_df,
        settings={"max_risk_per_trade": 100},
        market_bias="NEUTRAL",
        trend_score=55,
        news_items=[
            {"title": "Reliance Q1 profit beats estimates", "sentiment_label": "BULLISH"},
            {"title": "Oil prices remain volatile", "sentiment_label": "NEUTRAL"},
        ],
        backtest_result={"verdict": "GOOD", "win_rate": 0.62, "total_trades": 18, "net_profit": 3200},
        sector_return_20d=2.3,
        sector_rank=2,
        company_name="Reliance Industries",
        sector="Energy",
    )


MOCK_AGENT_RESPONSE = {
    "decision": "TRADE",
    "confidence_score": 74,
    "direction": "BULLISH",
    "setup_type": "BREAKOUT_LONG",
    "entry_trigger": 1050.0,
    "stop_loss": 1030.0,
    "target_1": 1080.0,
    "target_2": 1100.0,
    "risk_reward_ratio": 1.5,
    "reasons": [
        "Price is above SMA20 and SMA50 with rising volume.",
        "RSI at 58 is in the momentum sweet spot.",
        "Sector is a top-2 relative strength performer.",
    ],
    "risks": [
        "Oil price volatility could impact margins.",
        "Market regime is neutral, not strongly bullish.",
    ],
    "agent_reasoning": (
        "Reliance is consolidating near its 20-day high with above-average volume, "
        "suggesting accumulation. The sector is strong and backtest history shows a "
        "62% win rate. Entry above 1050 with a tight stop at 1030 gives 1.5:1 reward-to-risk."
    ),
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_context_has_required_keys(sample_context):
    """Context dict must have all keys the prompt builder expects."""
    assert sample_context["ticker"] == "RELIANCE.NS"
    assert sample_context["company_name"] == "Reliance Industries"
    assert sample_context["sector"] == "Energy"
    assert not sample_context["insufficient_data"]

    ps = sample_context["price_summary"]
    for key in ("close", "date", "sma20", "sma50", "rsi", "atr", "volume_ratio"):
        assert key in ps, f"Missing price_summary key: {key}"

    assert sample_context["regime"]["bias"] == "NEUTRAL"
    assert len(sample_context["news_headlines"]) == 2
    assert sample_context["backtest"]["verdict"] == "GOOD"


def test_build_context_insufficient_data():
    """Short DataFrame should flag insufficient_data=True."""
    df = pd.DataFrame({
        "date": pd.bdate_range(end="2026-06-18", periods=5),
        "open": [100]*5, "high": [101]*5, "low": [99]*5,
        "close": [100]*5, "volume": [1000]*5,
    })
    ctx = bull_agent.build_agent_context("TEST.NS", df)
    assert ctx["insufficient_data"] is True


def test_build_stock_prompt_contains_ticker(sample_context):
    """The prompt text must mention the stock ticker."""
    prompt = bull_agent._build_stock_prompt(sample_context)
    assert "RELIANCE.NS" in prompt
    assert "Reliance Industries" in prompt
    assert "Energy" in prompt


def test_validate_agent_output_valid():
    """Valid agent output passes validation."""
    assert bull_agent._validate_agent_output(MOCK_AGENT_RESPONSE) is True


def test_validate_agent_output_missing_keys():
    """Missing required keys fails validation."""
    bad = {"decision": "TRADE", "confidence_score": 70}
    assert bull_agent._validate_agent_output(bad) is False


def test_validate_agent_output_bad_decision():
    """Invalid decision value fails validation."""
    bad = dict(MOCK_AGENT_RESPONSE)
    bad["decision"] = "BUY_NOW"
    assert bull_agent._validate_agent_output(bad) is False


def test_validate_agent_output_score_out_of_range():
    """Confidence score > 100 fails validation."""
    bad = dict(MOCK_AGENT_RESPONSE)
    bad["confidence_score"] = 150
    assert bull_agent._validate_agent_output(bad) is False


def test_clamp_confidence_caps_at_85():
    """Confidence must be capped at 85."""
    result = {"confidence_score": 92}
    clamped = bull_agent._clamp_confidence(result)
    assert clamped["confidence_score"] == 85


def test_clamp_confidence_leaves_low_score():
    """Scores under 85 pass through unchanged."""
    result = {"confidence_score": 60}
    clamped = bull_agent._clamp_confidence(result)
    assert clamped["confidence_score"] == 60


def test_analyze_stock_no_api_key(sample_context, monkeypatch):
    """Without GEMINI_API_KEY, analyze_stock returns None (fallback)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = bull_agent.analyze_stock(sample_context)
    assert result is None


def test_analyze_stock_insufficient_data():
    """Insufficient data context returns None."""
    ctx = {"ticker": "TEST.NS", "insufficient_data": True}
    result = bull_agent.analyze_stock(ctx)
    assert result is None


@patch.object(bull_agent, "_call_gemini")
def test_analyze_stock_success(mock_gemini, sample_context, monkeypatch):
    """Successful Gemini call returns validated, clamped result."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    # Reset rate limiter
    bull_agent._rate_calls = 0
    bull_agent._rate_window_start = 0.0

    mock_gemini.return_value = dict(MOCK_AGENT_RESPONSE)
    result = bull_agent.analyze_stock(sample_context)

    assert result is not None
    assert result["decision"] == "TRADE"
    assert result["confidence_score"] <= 85
    assert result["source"] == "bull_agent"
    mock_gemini.assert_called_once()


@patch.object(bull_agent, "_call_gemini")
def test_analyze_stock_gemini_returns_none(mock_gemini, sample_context, monkeypatch):
    """Gemini failure returns None for fallback."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    bull_agent._rate_calls = 0
    bull_agent._rate_window_start = 0.0

    mock_gemini.return_value = None
    result = bull_agent.analyze_stock(sample_context)
    assert result is None


@patch.object(bull_agent, "_call_gemini")
def test_analyze_stock_gemini_returns_invalid(mock_gemini, sample_context, monkeypatch):
    """Invalid Gemini response returns None for fallback."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    bull_agent._rate_calls = 0
    bull_agent._rate_window_start = 0.0

    mock_gemini.return_value = {"garbage": True}
    result = bull_agent.analyze_stock(sample_context)
    assert result is None


def test_rate_limiter_blocks_after_max():
    """Rate limiter should block after MAX_CALLS_PER_MINUTE."""
    bull_agent._rate_calls = 0
    bull_agent._rate_window_start = bull_agent.time.time()

    for _ in range(bull_agent.MAX_CALLS_PER_MINUTE):
        assert bull_agent._rate_check() is True

    assert bull_agent._rate_check() is False
