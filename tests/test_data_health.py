from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.data_health import classify_ticker_health, is_market_hours, stale_cutoff_reference


IST = ZoneInfo("Asia/Kolkata")


def test_market_hours_true_for_regular_session():
    now = datetime(2026, 6, 5, 10, 30, tzinfo=IST)
    assert is_market_hours(now) is True


def test_market_hours_false_after_close():
    now = datetime(2026, 6, 5, 16, 1, tzinfo=IST)
    assert is_market_hours(now) is False


def test_classify_missing_when_quote_has_no_price():
    result = classify_ticker_health("RELIANCE.NS", {"status": "NO_DATA"}, now=datetime(2026, 6, 5, 10, 0, tzinfo=IST))
    assert result["status"] == "MISSING"
    assert "No quote" in result["note"]


def test_classify_stale_during_market_hours():
    now = datetime(2026, 6, 5, 10, 0, tzinfo=IST)
    quote = {"last_price": 100.0, "last_update": (now - timedelta(minutes=25)).isoformat(), "change_percent": 0.5}
    result = classify_ticker_health("TCS.NS", quote, news_items=[{"title": "normal"}], now=now)
    assert result["status"] == "STALE"
    assert "minutes old" in result["note"]


def test_classify_suspicious_big_move_without_news():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=IST)
    quote = {"last_price": 100.0, "last_update": now.isoformat(), "change_percent": 16.1}
    result = classify_ticker_health("INFY.NS", quote, news_items=[], now=now)
    assert result["status"] == "SUSPICIOUS"
    assert "16.1%" in result["note"]


def test_classify_ok_for_recent_quote_with_history():
    now = datetime(2026, 6, 5, 12, 0, tzinfo=IST)
    quote = {"last_price": 100.0, "last_update": now.isoformat(), "change_percent": 1.2, "source": "nse_public"}
    result = classify_ticker_health("SBIN.NS", quote, news_items=[], now=now, has_recent_history=True)
    assert result["status"] == "OK"
    assert "passed" in result["note"]


def test_stale_cutoff_reference_is_twenty_minutes_back():
    now = datetime(2026, 6, 5, 11, 0, tzinfo=IST)
    assert stale_cutoff_reference(now) == now - timedelta(minutes=20)
