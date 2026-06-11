# tests/test_promoter_tracker.py
import pytest
import sqlite3
from unittest.mock import patch, MagicMock
from datetime import datetime
from src.promoter_tracker import fetch_promoter_activity, get_promoter_signal, get_recent_bulk_deals, get_recent_promoter_activity

class NonClosingConnection:
    def __init__(self, conn):
        self._conn = conn
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        pass

@pytest.fixture(autouse=True)
def mock_db_and_session():
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.row_factory = sqlite3.Row
    cursor = raw_conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS promoter_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            ticker TEXT,
            person_name TEXT,
            designation TEXT,
            transaction_type TEXT,
            shares INTEGER,
            value_crore REAL,
            holding_before REAL,
            holding_after REAL,
            signal_strength TEXT,
            classification TEXT,
            source TEXT DEFAULT 'NSE_API',
            confidence TEXT DEFAULT 'HIGH'
        )
    """)
    raw_conn.commit()

    conn = NonClosingConnection(raw_conn)

    with patch("src.promoter_tracker.get_db_connection", return_value=conn), \
         patch("src.database.get_db_connection", return_value=conn):
        yield conn
    sqlite3.Connection.close(raw_conn)

def test_fetch_promoter_activity():
    mock_ann = [
        {
            "symbol": "RELIANCE",
            "subject": "Disposal of shares by Promoter Group",
            "purpose": "Insider Trading Disclosures",
            "desc": "Promoter disposed 800,000 shares value Rs. 20.0 Crores on 04-Jun-2026",
            "anngDate": "05-Jun-2026 15:30:00"
        },
        {
            "symbol": "TCS",
            "subject": "Acquisition of shares by Promoter Group",
            "purpose": "Insider Trading Disclosures",
            "desc": "Promoter acquired 1,000,000 shares value Rs. 35.0 Crores on 04-Jun-2026",
            "anngDate": "05-Jun-2026 15:30:00"
        }
    ]
    
    with patch("src.promoter_tracker.nse_fetch", return_value=mock_ann), \
         patch("src.promoter_tracker.fetch_bulk_deals", return_value=True):
        success = fetch_promoter_activity()
        assert success is True
        
    signal_rel = get_promoter_signal("RELIANCE.NS")
    assert signal_rel["transaction_type"] == "SELL"
    assert signal_rel["signal_strength"] == "STRONG_RED_FLAG" # because value > 5 Cr
    
    signal_tcs = get_promoter_signal("TCS.NS")
    assert signal_tcs["transaction_type"] == "BUY"
    assert signal_tcs["signal_strength"] == "STRONG_SIGNAL" # because value > 5 Cr

def test_bulk_deals_parsing():
    mock_deals = [
        {
            "symbol": "RELIANCE",
            "clientName": "Morgan Stanley",
            "buySell": "BUY",
            "quantity": "250,000",
            "value": "62.50",
            "date": datetime.today().strftime("%d-%b-%Y")
        }
    ]
    
    with patch("src.promoter_tracker.nse_fetch", return_value=mock_deals):
        from src.promoter_tracker import fetch_bulk_deals
        success = fetch_bulk_deals()
        assert success is True
        
    deals = get_recent_bulk_deals()
    assert len(deals) == 1
    assert deals[0]["ticker"] == "RELIANCE.NS"
    assert deals[0]["person_name"] == "Morgan Stanley"
    assert deals[0]["transaction_type"] == "BUY"
    assert deals[0]["classification"] == "BULK_BUY"
