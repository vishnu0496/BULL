# tests/test_earnings_calendar.py
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta
from src.earnings_calendar import (
    refresh_earnings_calendar, check_earnings_blackout, 
    get_earnings_this_week, update_post_result_data, get_earnings_edge
)

class NonClosingConnection:
    def __init__(self, conn):
        self._conn = conn
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        pass

@pytest.fixture(autouse=True)
def mock_db_and_yf():
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.row_factory = sqlite3.Row
    cursor = raw_conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS earnings_calendar (
            ticker TEXT,
            result_date DATE,
            result_type TEXT,
            estimated_eps REAL,
            actual_eps REAL,
            revenue_estimate REAL,
            actual_revenue REAL,
            beat_miss TEXT,
            surprise_pct REAL,
            price_reaction_1d REAL,
            historical_beat_rate REAL,
            PRIMARY KEY (ticker, result_date)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("INSERT INTO watchlist (ticker, name, industry) VALUES ('RELIANCE.NS', 'Reliance', 'Energy')")
    raw_conn.commit()

    conn = NonClosingConnection(raw_conn)

    with patch("src.earnings_calendar.get_db_connection", return_value=conn), \
         patch("src.earnings_calendar.get_watchlist_tickers", return_value=["RELIANCE.NS"]), \
         patch("src.database.get_db_connection", return_value=conn):
        yield conn
    sqlite3.Connection.close(raw_conn)

def test_refresh_earnings_calendar():
    mock_nse = [
        {
            "symbol": "RELIANCE",
            "desc": "Board meeting to consider Financial Results for the quarter",
            "purpose": "Financial Results",
            "boardMeetingDate": "10-Jun-2026"
        }
    ]
    
    mock_stock = MagicMock()
    mock_stock.calendar = {'Earnings Date': [datetime(2026, 6, 12)]}
    # Create mock earnings_dates dataframe
    idx = pd.DatetimeIndex([datetime(2026, 3, 10)])
    mock_stock.earnings_dates = pd.DataFrame({
        "EPS Estimate": [50.0],
        "Reported EPS": [55.0],
        "Surprise(%)": [10.0]
    }, index=idx)
    
    with patch("src.earnings_calendar.nse_fetch", return_value=mock_nse), \
         patch("src.earnings_calendar.yf.Ticker", return_value=mock_stock):
        success = refresh_earnings_calendar()
        assert success is True

    # Check database insertions
    this_week = get_earnings_this_week()
    assert len(this_week) > 0
    # Beat rate should be calculated
    edge = get_earnings_edge("RELIANCE.NS")
    assert edge["beat_rate"] == 1.0
    assert edge["has_edge"] is False # because total < 3

def test_check_earnings_blackout(mock_db_and_yf):
    conn = mock_db_and_yf
    cursor = conn.cursor()
    
    today = datetime.today()
    result_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    
    cursor.execute("""
        INSERT INTO earnings_calendar (ticker, result_date, result_type)
        VALUES ('RELIANCE.NS', ?, 'Quarterly')
    """, (result_date,))
    conn.commit()
    
    # Check blackout (upcoming in 2 days)
    status = check_earnings_blackout("RELIANCE.NS")
    assert status["in_blackout"] is True
    assert status["days_to_result"] == 2
    
    # Check non-blackout for another ticker
    status_other = check_earnings_blackout("TCS.NS")
    assert status_other["in_blackout"] is False

def test_earnings_edge_calculation(mock_db_and_yf):
    conn = mock_db_and_yf
    cursor = conn.cursor()
    
    # Insert 4 historical beats
    for i in range(1, 5):
        date_str = f"2025-06-0{i}"
        cursor.execute("""
            INSERT INTO earnings_calendar (ticker, result_date, beat_miss, surprise_pct)
            VALUES ('RELIANCE.NS', ?, 'BEAT', 12.5)
        """, (date_str,))
    conn.commit()
    
    edge = get_earnings_edge("RELIANCE.NS")
    assert edge["has_edge"] is True
    assert edge["beat_rate"] == 1.0
    assert edge["confidence_boost"] == 10
