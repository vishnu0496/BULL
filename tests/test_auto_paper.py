from pathlib import Path

import pandas as pd
import pytest

from src import auto_paper, database


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_dir = tmp_path / "data"
    db_path = db_dir / "bull_research.db"
    monkeypatch.setattr(database, "DB_DIR", str(db_dir))
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()
    auto_paper.ensure_auto_paper_tables()
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


def _save_prices(ticker, rows):
    df = pd.DataFrame(rows)
    df = df.rename(
        columns={
            "date": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    database.save_prices(ticker, df)


def test_capture_daily_picks_is_idempotent(temp_db):
    result_1 = auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")
    result_2 = auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")

    summary = auto_paper.get_auto_paper_summary()

    assert result_1["inserted"] == 1
    assert result_2["inserted"] == 0
    assert summary["summary"]["tracked_picks"] == 1
    assert summary["recent"][0]["status"] == "WATCHING"


def test_evaluate_target_hit(temp_db):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")
    _save_prices(
        "TEST.NS",
        [
            {"Date": "2026-06-11", "Open": 101, "High": 111, "Low": 100, "Close": 109, "Volume": 1000},
        ],
    )

    result = auto_paper.evaluate_auto_paper_trades(as_of_date="2026-06-11")
    summary = auto_paper.get_auto_paper_summary()
    row = summary["recent"][0]

    assert result["updated"] >= 2
    assert row["status"] == "TARGET_HIT"
    assert row["entry_price"] == 101
    assert row["exit_price"] == 110
    assert summary["summary"]["closed_trades"] == 1
    assert summary["summary"]["winning_trades"] == 1


def test_stop_wins_when_stop_and_target_touch_same_candle(temp_db):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")
    _save_prices(
        "TEST.NS",
        [
            {"Date": "2026-06-11", "Open": 100, "High": 111, "Low": 94, "Close": 105, "Volume": 1000},
        ],
    )

    auto_paper.evaluate_auto_paper_trades(as_of_date="2026-06-11")
    row = auto_paper.get_auto_paper_summary()["recent"][0]

    assert row["status"] == "STOP_HIT"
    assert "conservative" in row["outcome_note"].lower()


def test_no_trigger_does_not_expire_before_horizon(temp_db):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")
    _save_prices(
        "TEST.NS",
        [
            {"Date": "2026-06-11", "Open": 90, "High": 94, "Low": 88, "Close": 92, "Volume": 1000},
        ],
    )

    auto_paper.evaluate_auto_paper_trades(as_of_date="2026-06-11", horizon_days=5)
    row = auto_paper.get_auto_paper_summary()["recent"][0]

    assert row["status"] == "WATCHING"
    assert "Captured" in row["outcome_note"]


def test_open_trade_does_not_time_exit_before_horizon(temp_db):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")
    _save_prices(
        "TEST.NS",
        [
            {"Date": "2026-06-11", "Open": 101, "High": 105, "Low": 99, "Close": 104, "Volume": 1000},
        ],
    )

    auto_paper.evaluate_auto_paper_trades(as_of_date="2026-06-11", horizon_days=5)
    row = auto_paper.get_auto_paper_summary()["recent"][0]

    assert row["status"] == "OPEN"
    assert row["entry_date"] == "2026-06-11"
    assert row["exit_date"] == ""


def test_no_trigger_after_horizon(temp_db):
    auto_paper.capture_daily_picks([_pick()], pick_date="2026-06-10")
    _save_prices(
        "TEST.NS",
        [
            {"Date": "2026-06-11", "Open": 90, "High": 94, "Low": 88, "Close": 92, "Volume": 1000},
            {"Date": "2026-06-16", "Open": 92, "High": 95, "Low": 89, "Close": 91, "Volume": 1000},
        ],
    )

    auto_paper.evaluate_auto_paper_trades(as_of_date="2026-06-16", horizon_days=5)
    summary = auto_paper.get_auto_paper_summary()
    row = summary["recent"][0]

    assert row["status"] == "NO_TRIGGER"
    assert summary["summary"]["no_trigger"] == 1


def test_wait_pick_is_captured_as_watch_only(temp_db):
    wait_pick = _pick()
    wait_pick["decision"] = "WAIT"

    auto_paper.capture_daily_picks([wait_pick], pick_date="2026-06-10")
    row = auto_paper.get_auto_paper_summary()["recent"][0]

    assert row["status"] == "WATCH_ONLY"
    assert row["decision"] == "WAIT"


def test_automatic_capture_skips_outside_morning_window(temp_db, monkeypatch):
    monkeypatch.setattr(auto_paper, "_inside_capture_window", lambda: False)

    result = auto_paper.capture_daily_picks([_pick()])
    summary = auto_paper.get_auto_paper_summary()

    assert result["status"] == "SKIPPED_OUTSIDE_CAPTURE_WINDOW"
    assert summary["summary"]["tracked_picks"] == 0


def test_sync_active_trade_prices_only_syncs_active_rows(temp_db, monkeypatch):
    wait_pick = _pick(ticker="WAIT.NS")
    wait_pick["decision"] = "WAIT"
    auto_paper.capture_daily_picks([_pick(ticker="ACTIVE.NS"), wait_pick], pick_date="2026-06-10", max_picks=2)

    calls = []

    def fake_sync(ticker):
        calls.append(ticker)

    from src import fetcher

    monkeypatch.setattr(fetcher, "sync_ticker", fake_sync)
    result = auto_paper.sync_active_trade_prices()

    assert calls == ["ACTIVE.NS"]
    assert result["synced"] == 1
    assert result["status"] == "OK"
