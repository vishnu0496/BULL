# tests/test_sector_rotation.py
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
import pandas as pd
from src.sector_rotation import refresh_sector_data, get_sector_rankings, get_sector_for_ticker, should_trade_sector

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
        CREATE TABLE IF NOT EXISTS sector_rotation (
            date DATE,
            sector TEXT,
            weekly_return REAL,
            monthly_return REAL,
            rs_score REAL,
            momentum TEXT,
            rank INTEGER,
            signal TEXT,
            PRIMARY KEY (date, sector)
        )
    """)
    raw_conn.commit()

    conn = NonClosingConnection(raw_conn)

    with patch("src.sector_rotation.get_db_connection", return_value=conn), \
         patch("src.database.get_db_connection", return_value=conn):
        yield conn
    sqlite3.Connection.close(raw_conn)

def test_refresh_sector_data():
    # Mock yfinance Index History
    nifty_df = pd.DataFrame({'Close': [100.0] * 30})
    sector_df = pd.DataFrame({'Close': [100.0] * 20 + [105.0] * 10}) # +5% change at end
    
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = sector_df
    
    with patch("src.sector_rotation.yf.Ticker") as mock_yf:
        # First call gets Nifty benchmark, subsequent calls get sectors
        mock_nifty = MagicMock()
        mock_nifty.history.return_value = nifty_df
        mock_yf.side_effect = lambda symbol: mock_nifty if symbol == "^NSEI" else mock_ticker
        
        success = refresh_sector_data()
        assert success is True

    rankings = get_sector_rankings()
    assert len(rankings) > 0
    # The sector should be ranked #1 because it outperformed flat Nifty
    assert rankings[0]["rank"] == 1
    assert rankings[0]["signal"] == "LEAD"

def test_should_trade_sector(mock_db_and_yf):
    conn = mock_db_and_yf
    cursor = conn.cursor()
    
    # Manually insert rankings to test trade logic
    cursor.execute("""
        INSERT INTO sector_rotation (date, sector, weekly_return, monthly_return, rs_score, momentum, rank, signal)
        VALUES ('2026-06-05', 'IT', 4.5, 8.0, 1.08, 'RISING', 2, 'LEAD')
    """)
    cursor.execute("""
        INSERT INTO sector_rotation (date, sector, weekly_return, monthly_return, rs_score, momentum, rank, signal)
        VALUES ('2026-06-05', 'BANK', -2.0, -4.0, 0.88, 'FALLING', 9, 'LAGGING')
    """)
    conn.commit()
    
    # RELIANCE.NS is mapped to ENERGY in engine.py SECTORS
    # TCS.NS is mapped to IT
    # HDFCBANK.NS is mapped to BANK
    
    # Test favorable sector
    decision_it = should_trade_sector("TCS.NS")
    assert decision_it["decision"] == "FAVORABLE"
    assert decision_it["confidence_adjustment"] == 10
    
    # Test unfavorable sector
    decision_bank = should_trade_sector("HDFCBANK.NS")
    assert decision_bank["decision"] == "UNFAVORABLE"
    assert decision_bank["confidence_adjustment"] == -10
