# tests/test_fii_tracker.py
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from datetime import datetime
from src.fii_tracker import fetch_fii_dii_data, get_fii_signal, get_fii_history

class NonClosingConnection:
    def __init__(self, conn):
        self._conn = conn
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        pass

@pytest.fixture(autouse=True)
def mock_db_and_session():
    # Create an in-memory SQLite DB for testing
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.row_factory = sqlite3.Row
    cursor = raw_conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fii_dii_flows (
            date DATE PRIMARY KEY,
            fii_buy REAL,
            fii_sell REAL,
            fii_net REAL,
            dii_buy REAL,
            dii_sell REAL,
            dii_net REAL,
            market_impact TEXT,
            source TEXT DEFAULT 'NSE_API',
            confidence TEXT DEFAULT 'HIGH'
        )
    """)
    raw_conn.commit()
    
    conn = NonClosingConnection(raw_conn)
    
    # Patch get_db_connection to return our in-memory connection
    with patch("src.fii_tracker.get_db_connection", return_value=conn), \
         patch("src.database.get_db_connection", return_value=conn):
        yield conn
    # Perform clean up
    sqlite3.Connection.close(raw_conn)

def test_fetch_fii_dii_data():
    mock_response = [
        {
            "category": "FII/FPI",
            "date": "05-Jun-2026",
            "buyValue": "15,000.00",
            "sellValue": "12,500.00",
            "netValue": "2,500.00"
        },
        {
            "category": "DII",
            "date": "05-Jun-2026",
            "buyValue": "8,000.00",
            "sellValue": "9,000.00",
            "netValue": "-1,000.00"
        }
    ]
    
    with patch("src.fii_tracker.nse_fetch", return_value=mock_response):
        success = fetch_fii_dii_data()
        assert success is True
        
    signal = get_fii_signal()
    assert signal["date"] == "2026-06-05"
    assert signal["fii_net"] == 2500.0
    assert signal["dii_net"] == -1000.0
    assert signal["market_impact"] == "STRONG_BULL"
    assert signal["action"] == "BUY"

def test_market_impact_classifications(mock_db_and_session):
    conn = mock_db_and_session
    cursor = conn.cursor()
    
    # Test MILD_BULL
    cursor.execute("INSERT OR REPLACE INTO fii_dii_flows (date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact) VALUES ('2026-06-06', 1000, 400, 600, 100, 100, 0, 'MILD_BULL')")
    conn.commit()
    signal = get_fii_signal()
    assert signal["market_impact"] == "MILD_BULL"
    assert signal["action"] == "BUY"
    
def test_streak_calculation(mock_db_and_session):
    conn = mock_db_and_session
    cursor = conn.cursor()
    # Insert 4 days of FII selling
    for i in range(1, 5):
        date_str = f"2026-06-0{i}"
        cursor.execute("""
            INSERT INTO fii_dii_flows (date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact)
            VALUES (?, 1000, 2000, -1000, 1000, 500, 500, 'MILD_BEAR')
        """, (date_str,))
    conn.commit()
    
    signal = get_fii_signal()
    assert signal["streak_days"] == 4
    assert signal["streak_type"] == "SELL"
    assert "selling streak" in signal["signal_text"]
    assert signal["action"] == "WAIT" # FII consecutive selling streak >= 3 should suggest WAIT

def test_fallback_behavior():
    # Empty DB should return neutral fallback
    signal = get_fii_signal()
    assert signal["fii_net"] == 0.0
    assert signal["market_impact"] == "NEUTRAL"
    assert signal["action"] == "HOLD"

def test_get_fii_history(mock_db_and_session):
    conn = mock_db_and_session
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fii_dii_flows (date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact)
        VALUES ('2026-06-05', 1000, 500, 500, 800, 600, 200, 'MILD_BULL')
    """)
    conn.commit()
    
    history = get_fii_history(days=5)
    assert len(history) == 1
    assert history[0]["fii_net"] == 500.0
