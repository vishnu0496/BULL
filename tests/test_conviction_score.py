# tests/test_conviction_score.py
import pytest
import sqlite3
import datetime
import pandas as pd
from unittest.mock import patch, MagicMock
from engine import BULLSignalEngine

class NonClosingConnection:
    def __init__(self, conn):
        self._conn = conn
    def __getattr__(self, name):
        return getattr(self._conn, name)
    def close(self):
        pass

@pytest.fixture(autouse=True)
def mock_db_and_trackers():
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.row_factory = sqlite3.Row
    cursor = raw_conn.cursor()
    # Create watchlist table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    raw_conn.commit()

    conn = NonClosingConnection(raw_conn)

    # Default mock objects
    mock_pm = {
        "pre_market_score": 60.0,
        "india_vix": 14.5
    }
    mock_fii = {
        "market_impact": "NEUTRAL",
        "streak_days": 0,
        "streak_type": "NEUTRAL",
        "fii_net": 100.0,
        "dii_net": 100.0
    }
    mock_sec = {
        "sector": "ENERGY",
        "rank": 5,
        "rs_score": 1.0,
        "momentum": "NEUTRAL",
        "signal": "NEUTRAL",
        "decision": "NEUTRAL",
        "confidence_adjustment": 0
    }
    mock_prom = {
        "transaction_type": "NEUTRAL",
        "signal_strength": "WEAK_SIGNAL"
    }
    mock_blackout = {
        "in_blackout": False
    }
    mock_edge = {
        "has_edge": False
    }

    with patch("src.premarket_signals.get_premarket_score", return_value=mock_pm), \
         patch("src.fii_tracker.get_fii_signal", return_value=mock_fii), \
         patch("src.sector_rotation.should_trade_sector", return_value=mock_sec), \
         patch("src.promoter_tracker.get_promoter_signal", return_value=mock_prom), \
         patch("src.earnings_calendar.check_earnings_blackout", return_value=mock_blackout), \
         patch("src.earnings_calendar.get_earnings_edge", return_value=mock_edge), \
         patch("src.database.get_news_cache", return_value=[]), \
         patch("engine.download_data", return_value=MagicMock()), \
         patch("src.database.get_db_connection", return_value=conn):
        yield conn
    sqlite3.Connection.close(raw_conn)

def test_compute_conviction_score():
    engine = BULLSignalEngine(tickers=["RELIANCE.NS"])
    base_result = {
        "rvol": 2.1,
        "rsi": 55.0,
        "rel_strength": 0.06,
        "ml_score": 0.75
    }
    
    score_details = engine.compute_conviction_score("RELIANCE.NS", base_result)
    
    assert "conviction_score" in score_details
    assert "conviction_grade" in score_details
    assert "score_breakdown" in score_details
    
    # Check technical calculations
    # rvol 2.1 => min(3.0, 2.1)/3.0 * 10 = 7.0
    # rsi 55 => perfect zone => 10.0
    # rel_strength 0.06 => > 0.05 => 10.0
    # Technical total = 27.0
    assert score_details["score_breakdown"]["technical"] == 27.0
    
    # Check ML calculations
    # ml_score 0.75 => 0.75 * 25 = 18.75
    assert score_details["score_breakdown"]["ml"] == 18.75
    
    # Grade should be calculated (27.0 + 18.75 + Macro + News + Fund)
    assert score_details["conviction_grade"] in ["A+", "A", "B", "C", "REJECT"]

def test_evaluate_filters_downgrades():
    engine = BULLSignalEngine(tickers=["RELIANCE.NS"])
    
    # Mock evaluate_filters dependencies
    engine.feed = MagicMock()
    # Mock get_bars to return a dataframe
    engine.feed.get_bars.return_value = pd.DataFrame({
        'Open': [100.0], 'High': [102.0], 'Low': [99.0], 'Close': [101.0], 'Volume': [1000]
    })
    
    # Mock historical_data
    engine.historical_data = {
        "RELIANCE.NS": pd.DataFrame({
            'Close': [100.0] * 20, 'Volume': [1000] * 20, 'atr_20': [2.5] * 20
        })
    }
    
    # Let's mock ML prediction
    engine.ensemble = MagicMock()
    engine.ensemble.predict_latest.return_value = 0.75
    
    # 1. Normal run (should pass if we mock other parts as pass)
    with patch("engine.download_data") as mock_dl:
        mock_dl.return_value = pd.DataFrame({'Close': [15.0]}) # VIX
        res = engine.evaluate_filters("RELIANCE.NS", datetime.time(10, 30))
        assert res["passed"] is True
        
    # 2. Strong Bear Open block
    mock_bear_pm = {"pre_market_score": 25.0, "india_vix": 15.0} # < 30
    with patch("src.premarket_signals.get_premarket_score", return_value=mock_bear_pm), \
         patch("engine.download_data", return_value=pd.DataFrame({'Close': [15.0]})):
        res = engine.evaluate_filters("RELIANCE.NS", datetime.time(10, 30))
        assert res["passed"] is False
        assert "STRONG_BEAR_OPEN" in res["reason"]
        
    # 3. FII Sell Streak block
    mock_streak_fii = {"market_impact": "STRONG_BEAR", "streak_days": 4, "streak_type": "SELL"}
    with patch("src.fii_tracker.get_fii_signal", return_value=mock_streak_fii), \
         patch("engine.download_data", return_value=pd.DataFrame({'Close': [15.0]})):
        res = engine.evaluate_filters("RELIANCE.NS", datetime.time(10, 30))
        assert res["passed"] is False
        assert "FII Selling Streak" in res["reason"]

def test_status_endpoint_empty(mock_db_and_trackers):
    # Initialize all tables in the mock DB
    from src.database import init_db
    init_db()
    
    # Import the function from server
    from server import get_intelligence_status_data
    
    # Run status check when tables are completely empty
    status = get_intelligence_status_data()
    
    assert status["overall"] == "EMPTY"
    for module in ["fii", "sectors", "premarket", "earnings", "promoters"]:
        assert status[module]["status"] == "EMPTY"
        assert status[module]["has_data"] is False

def test_status_endpoint_fresh(mock_db_and_trackers):
    from src.database import init_db
    init_db()
    
    conn = mock_db_and_trackers
    cursor = conn.cursor()
    
    # Insert fresh data (dated today)
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("INSERT INTO fii_dii_flows (date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact) VALUES (?, 100, 50, 50, 80, 40, 40, 'BULLISH')", (today_str,))
    cursor.execute("INSERT INTO sector_rotation (date, sector, weekly_return, monthly_return, rs_score, momentum, rank, signal) VALUES (?, 'BANK', 2.5, 5.0, 1.2, 'RISING', 1, 'LEAD')", (today_str,))
    cursor.execute("INSERT INTO premarket_signals (date, gift_nifty_gap, sp500_chg, nasdaq_chg, asia_score, india_vix, fii_yesterday, pre_market_score, classification, recommendation, generated_at) VALUES (?, 0.5, 0.2, 0.3, 1.0, 14.0, 100.0, 75.0, 'BULL_OPEN', 'Strong bias', ?)", (today_str, today_ts))
    cursor.execute("INSERT INTO earnings_calendar (ticker, result_date, result_type, actual_eps) VALUES ('RELIANCE.NS', ?, 'Quarterly', 15.5)", (today_str,))
    cursor.execute("INSERT INTO promoter_activity (date, ticker, person_name, transaction_type, value_crore) VALUES (?, 'RELIANCE.NS', 'Promoter A', 'BUY', 10.0)", (today_str,))
    conn.commit()
    
    from server import get_intelligence_status_data
    status = get_intelligence_status_data()
    
    assert status["overall"] == "READY"
    for module in ["fii", "sectors", "premarket", "earnings", "promoters"]:
        assert status[module]["status"] == "FRESH"
        assert status[module]["has_data"] is True

def test_status_endpoint_partial(mock_db_and_trackers):
    from src.database import init_db
    init_db()
    
    conn = mock_db_and_trackers
    cursor = conn.cursor()
    
    # Mixed: premarket is FRESH, sectors is STALE (older than 25h), others are EMPTY
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today_ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # STALE dates (e.g., 5 days ago)
    stale_date_str = (datetime.date.today() - datetime.timedelta(days=5)).strftime("%Y-%m-%d")
    
    # 1. Premarket: FRESH
    cursor.execute("INSERT INTO premarket_signals (date, pre_market_score, generated_at) VALUES (?, 60.0, ?)", (today_str, today_ts))
    # 2. Sectors: STALE
    cursor.execute("INSERT INTO sector_rotation (date, sector, weekly_return, monthly_return, rs_score, rank) VALUES (?, 'AUTO', 1.0, 2.0, 0.5, 2)", (stale_date_str,))
    conn.commit()
    
    from server import get_intelligence_status_data
    status = get_intelligence_status_data()
    
    assert status["overall"] == "PARTIAL"
    assert status["premarket"]["status"] == "FRESH"
    assert status["sectors"]["status"] == "STALE"
    assert status["fii"]["status"] == "EMPTY"

def test_nse_session_fallback():
    """Session should return usable object even if NSE is down."""
    from unittest.mock import patch
    from src.nse_session import get_nse_session
    
    with patch('requests.Session.get', side_effect=Exception("Network error")):
        session = get_nse_session(force_new=True)
        assert session is not None

def test_nse_fetch_returns_none_on_failure():
    """nse_fetch should return None gracefully on all failures."""
    from unittest.mock import patch, MagicMock
    from src.nse_session import nse_fetch
    
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    
    with patch('requests.Session.get', return_value=mock_resp):
        result = nse_fetch("https://www.nseindia.com/api/test")
        assert result is None
