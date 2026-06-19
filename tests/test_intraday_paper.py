from pathlib import Path

import pytest

from src import auto_paper, database, intraday_paper


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_dir = tmp_path / "data"
    db_path = db_dir / "bull_research.db"
    monkeypatch.setattr(database, "DB_DIR", str(db_dir))
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()
    auto_paper.ensure_auto_paper_tables()
    intraday_paper.ensure_intraday_tables()
    return Path(db_path)


def _pick(ticker="TEST.NS", entry=100.0, stop=95.0, target=110.0):
    return {
        "ticker": ticker,
        "decision": "TRADE",
        "setup_type": "BREAKOUT_LONG",
        "entry_trigger": entry,
        "stop_loss": stop,
        "target_1": target,
        "target_2": 115.0,
        "suggested_quantity": 10,
        "confidence_score": 80,
        "historical_verdict": "GOOD",
        "news_sentiment": "NEUTRAL",
        "reasons": ["test pick"],
    }


def _latest_trade():
    conn = database.get_db_connection()
    try:
        return dict(conn.execute("SELECT * FROM auto_paper_trades ORDER BY id DESC LIMIT 1").fetchone())
    finally:
        conn.close()


def test_intraday_live_quote_opens_watching_trade(temp_db, monkeypatch):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-19")

    monkeypatch.setattr(intraday_paper, "is_market_open", lambda now=None: True)
    monkeypatch.setattr(
        intraday_paper.nse_feed,
        "get_quote",
        lambda ticker, cache_seconds=20: {"last_price": 101.2, "source": "nse_public"},
    )

    result = intraday_paper.run_intraday_paper_once()
    trade = _latest_trade()

    assert result["updated"] == 1
    assert result["actions"][0]["action"] == "OPENED"
    assert trade["status"] == "OPEN"
    assert trade["entry_price"] == 101.2


def test_intraday_live_quote_hits_target(temp_db, monkeypatch):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-19")
    conn = database.get_db_connection()
    try:
        conn.execute(
            """
            UPDATE auto_paper_trades
            SET status = 'OPEN', entry_date = '2026-06-19', entry_price = 100
            """
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setattr(intraday_paper, "is_market_open", lambda now=None: True)
    monkeypatch.setattr(
        intraday_paper.nse_feed,
        "get_quote",
        lambda ticker, cache_seconds=20: {"last_price": 111.0, "source": "nse_public"},
    )

    result = intraday_paper.run_intraday_paper_once()
    trade = _latest_trade()

    assert result["updated"] == 1
    assert result["actions"][0]["action"] == "TARGET_HIT"
    assert trade["status"] == "TARGET_HIT"
    assert trade["exit_price"] == 110
    assert trade["pnl"] > 0


def test_intraday_rejects_delayed_fallback_quote(temp_db, monkeypatch):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-19")

    monkeypatch.setattr(intraday_paper, "is_market_open", lambda now=None: True)
    monkeypatch.setattr(
        intraday_paper.nse_feed,
        "get_quote",
        lambda ticker, cache_seconds=20: {"last_price": 101.2, "source": "yfinance_fallback"},
    )

    result = intraday_paper.run_intraday_paper_once()
    trade = _latest_trade()

    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert result["actions"][0]["action"] == "QUOTE_SKIPPED"
    assert trade["status"] == "WATCHING"


def test_intraday_accepts_fresh_yahoo_one_minute_fallback_for_paper(temp_db, monkeypatch):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-19")

    monkeypatch.setattr(intraday_paper, "is_market_open", lambda now=None: True)
    monkeypatch.setattr(
        intraday_paper.nse_feed,
        "get_quote",
        lambda ticker, cache_seconds=20: {
            "last_price": 101.2,
            "source": "yfinance_intraday_fallback",
            "quote_lag_minutes": 2.0,
        },
    )

    result = intraday_paper.run_intraday_paper_once()
    trade = _latest_trade()

    assert result["updated"] == 1
    assert result["actions"][0]["action"] == "OPENED"
    assert result["actions"][0]["source_note"].startswith("Using fresh Yahoo 1-minute")
    assert trade["status"] == "OPEN"


def test_intraday_rejects_stale_yahoo_one_minute_fallback(temp_db, monkeypatch):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-19")

    monkeypatch.setattr(intraday_paper, "is_market_open", lambda now=None: True)
    monkeypatch.setattr(
        intraday_paper.nse_feed,
        "get_quote",
        lambda ticker, cache_seconds=20: {
            "last_price": 101.2,
            "source": "yfinance_intraday_fallback",
            "quote_lag_minutes": 45.0,
        },
    )

    result = intraday_paper.run_intraday_paper_once()
    trade = _latest_trade()

    assert result["updated"] == 0
    assert result["skipped"] == 1
    assert result["actions"][0]["action"] == "QUOTE_SKIPPED"
    assert "stale" in result["actions"][0]["note"]
    assert trade["status"] == "WATCHING"


def test_intraday_skips_when_market_closed(temp_db, monkeypatch):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-19")
    monkeypatch.setattr(intraday_paper, "is_market_open", lambda now=None: False)

    result = intraday_paper.run_intraday_paper_once()

    assert result["status"] == "SKIPPED_MARKET_CLOSED"
