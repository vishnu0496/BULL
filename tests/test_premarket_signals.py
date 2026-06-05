# tests/test_premarket_signals.py
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import datetime, timedelta
from src.premarket_signals import compute_premarket_score, get_premarket_score

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
        CREATE TABLE IF NOT EXISTS premarket_signals (
            date DATE PRIMARY KEY,
            gift_nifty_gap REAL,
            sp500_chg REAL,
            nasdaq_chg REAL,
            margin_impact REAL DEFAULT 0.0,
            asia_score REAL,
            india_vix REAL,
            fii_yesterday REAL,
            pre_market_score REAL,
            classification TEXT,
            recommendation TEXT,
            generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fii_dii_flows (
            date DATE PRIMARY KEY,
            fii_buy REAL,
            fii_sell REAL,
            fii_net REAL,
            dii_buy REAL,
            dii_sell REAL,
            dii_net REAL,
            market_impact TEXT
        )
    """)
    raw_conn.commit()

    conn = NonClosingConnection(raw_conn)

    with patch("src.premarket_signals.get_db_connection", return_value=conn), \
         patch("src.database.get_db_connection", return_value=conn):
        yield conn
    sqlite3.Connection.close(raw_conn)

def test_compute_premarket_score():
    # Mock get_pct_change to return positive results
    # Gift Nifty: +1.2%, SP500: +0.6%, Nasdaq: +0.8%, Asia: +0.7%
    def mock_pct(symbol):
        if symbol == "NI=F": return 1.2
        if symbol == "^GSPC": return 0.6
        if symbol == "^IXIC": return 0.8
        return 0.7 # Asia
        
    with patch("src.premarket_signals.get_pct_change", side_effect=mock_pct), \
         patch("src.premarket_signals.get_vix_value", return_value=12.5): # low fear: +5 pts
        
        signal = compute_premarket_score()
        
    assert signal["pre_market_score"] > 50.0
    assert "BULL_OPEN" in signal["classification"]
    assert "long bias" in signal["recommendation"].lower()

def test_vix_penalization():
    def mock_pct(symbol):
        return -1.0 # global selloff
        
    with patch("src.premarket_signals.get_pct_change", side_effect=mock_pct), \
         patch("src.premarket_signals.get_vix_value", return_value=25.0): # high fear: -15 pts
        
        signal = compute_premarket_score()
        
    assert signal["pre_market_score"] < 40.0
    assert "BEAR_OPEN" in signal["classification"]
    assert "avoid fresh long entries" in signal["recommendation"].lower()

def test_caching_mechanism(mock_db_and_yf):
    conn = mock_db_and_yf
    cursor = conn.cursor()
    
    # Pre-populate cache with a high score
    today_str = datetime.today().strftime("%Y-%m-%d")
    gen_time_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO premarket_signals (
            date, gift_nifty_gap, sp500_chg, nasdaq_chg, asia_score, india_vix,
            fii_yesterday, pre_market_score, classification, recommendation, generated_at
        ) VALUES (?, 1.0, 1.0, 1.0, 1.0, 12.0, 2000.0, 95.0, 'STRONG_BULL_OPEN', 'Test', ?)
    """, (today_str, gen_time_str))
    conn.commit()
    
    # Next call should return cached version (95.0 score) rather than recompute
    with patch("src.premarket_signals.get_pct_change", return_value=0.0):
        signal = compute_premarket_score()
        
    assert signal["pre_market_score"] == 95.0
    assert signal["classification"] == "STRONG_BULL_OPEN"
