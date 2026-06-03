import pandas as pd
from unittest.mock import patch

from src.paper_analytics import get_paper_trade_analytics


@patch("src.paper_analytics.database.get_paper_trades")
def test_paper_analytics_reconstructs_closed_trade(mock_trades):
    mock_trades.return_value = pd.DataFrame(
        [
            {
                "id": 1,
                "ticker": "TEST.NS",
                "trade_date": "2026-06-01",
                "action": "BUY",
                "quantity": 10,
                "price": 100.0,
                "notes": "source: Research Desk, setup: breakout, confidence: 70%, stop loss: 95",
                "logged_at": "2026-06-01 09:30:00",
            },
            {
                "id": 2,
                "ticker": "TEST.NS",
                "trade_date": "2026-06-02",
                "action": "SELL",
                "quantity": 10,
                "price": 110.0,
                "notes": "target hit",
                "logged_at": "2026-06-02 10:30:00",
            },
        ]
    )

    result = get_paper_trade_analytics()

    assert result["summary"]["total_closed_trades"] == 1
    assert result["summary"]["winning_trades"] == 1
    assert result["summary"]["win_rate"] == 100.0
    assert result["closed_trades"][0]["source"] == "Research Desk"
    assert result["closed_trades"][0]["setup_type"] == "Breakout"
    assert result["closed_trades"][0]["confidence"] == 70.0
    assert result["closed_trades"][0]["r_multiple"] is not None


@patch("src.paper_analytics.database.get_paper_trades")
def test_paper_analytics_handles_empty_journal(mock_trades):
    mock_trades.return_value = pd.DataFrame()

    result = get_paper_trade_analytics()

    assert result["summary"]["total_closed_trades"] == 0
    assert result["summary"]["net_pnl"] == 0
    assert result["equity_curve"] == []
    assert result["learning_summary"]
