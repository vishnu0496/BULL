from datetime import datetime, timedelta

import pandas as pd

from src.daily_brief import analyze_price_frame, format_telegram_brief


def _sample_prices(days=90, start=100.0):
    dates = [datetime.now().date() - timedelta(days=days - idx) for idx in range(days)]
    close = [start + idx * 0.8 for idx in range(days)]
    rows = []
    for idx, value in enumerate(close):
        rows.append(
            {
                "date": dates[idx].isoformat(),
                "open": value - 0.4,
                "high": value + 1.2,
                "low": value - 1.0,
                "close": value,
                "volume": 2_000_000 + idx * 10_000,
            }
        )
    return pd.DataFrame(rows)


def test_analyze_price_frame_returns_ui_contract():
    setup = analyze_price_frame(
        "INFY.NS",
        _sample_prices(),
        {"max_risk_per_trade": 500},
        market_bias="NEUTRAL",
    )

    assert setup["ticker"] == "INFY.NS"
    assert setup["decision"] in {"TRADE", "WAIT", "REJECT"}
    assert setup["entry_trigger"] > setup["stop_loss"]
    assert setup["target_1"] > setup["entry_trigger"]
    assert setup["risk_per_share"] > 0
    assert setup["suggested_quantity"] >= 0
    assert 0 <= setup["confidence_score"] <= 100
    assert setup["reasons"]


def test_format_telegram_brief_includes_risk_rule():
    message = format_telegram_brief(
        {
            "market_mood": "CAUTIOUS",
            "bull_score": 55,
            "trade_setups": [],
            "regime_reasons": ["Market trend is mixed."],
        }
    )

    assert "BULL -" in message
    assert "No fresh trade today" in message
    assert "Risk rule" in message
