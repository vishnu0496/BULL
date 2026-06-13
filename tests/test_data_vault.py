from pathlib import Path

import pytest

from src import data_vault, database


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    db_dir = tmp_path / "data"
    db_path = db_dir / "bull_research.db"
    monkeypatch.setattr(database, "DB_DIR", str(db_dir))
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    database.init_db()
    data_vault.ensure_data_vault_tables()
    return Path(db_path)


def test_payload_hash_is_stable_for_same_payload_ordering(temp_db):
    left = {"symbol": "SBIN", "price": 100.5, "meta": {"source": "nse", "ok": True}}
    right = {"price": 100.5, "meta": {"ok": True, "source": "nse"}, "symbol": "SBIN"}

    assert data_vault.payload_hash(left) == data_vault.payload_hash(right)


def test_record_event_deduplicates_identical_payload(temp_db):
    payload = {"symbol": "RELIANCE", "last_price": 1420.25}

    first_id = data_vault.record_event(
        source="nse_public",
        category="price_quote",
        symbol="RELIANCE.NS",
        endpoint="quote",
        payload=payload,
    )
    second_id = data_vault.record_event(
        source="nse_public",
        category="price_quote",
        symbol="RELIANCE.NS",
        endpoint="quote",
        payload=payload,
    )

    conn = database.get_db_connection()
    try:
        count = conn.execute("SELECT COUNT(*) AS c FROM data_vault_events").fetchone()["c"]
    finally:
        conn.close()

    assert first_id == second_id
    assert count == 1


def test_record_source_health_tracks_success_and_error(temp_db):
    data_vault.record_source_health(source="nse_public", category="quote", ok=True, latency_ms=42)
    data_vault.record_source_health(source="nse_public", category="quote", ok=False, latency_ms=100, error="403")

    conn = database.get_db_connection()
    try:
        row = conn.execute(
            """
            SELECT status, last_success_at, last_error_at, reliability_score, error
            FROM data_vault_source_health
            WHERE source = ? AND category = ?
            """,
            ("nse_public", "quote"),
        ).fetchone()
    finally:
        conn.close()

    assert row["status"] == "ERROR"
    assert row["last_success_at"]
    assert row["last_error_at"]
    assert row["error"] == "403"
    assert float(row["reliability_score"]) < 55


def test_collect_quote_archives_quote_payload(temp_db, monkeypatch):
    monkeypatch.setattr(
        data_vault.nse_feed,
        "get_quote",
        lambda symbol: {
            "symbol": symbol.replace(".NS", ""),
            "source": "nse_public",
            "status": "OK",
            "last_price": 915.2,
            "change_percent": 1.25,
            "last_update": "2026-06-13T10:15:00+05:30",
        },
    )

    result = data_vault.collect_quote("SBIN.NS")

    assert result["status"] == "OK"
    assert result["source"] == "nse_public"
    assert result["last_price"] == 915.2

    status = data_vault.get_data_vault_status()
    assert status["total_events"] == 1
    assert status["event_counts_24h"][0]["category"] == "price_quote"


def test_refresh_data_vault_skips_indices_and_limits_watchlist(temp_db, monkeypatch):
    seen_symbols = []
    monkeypatch.setattr(
        database,
        "get_watchlist_tickers",
        lambda: ["^NSEI", "RELIANCE.NS", "TCS.NS", "INFY.NS"],
    )
    monkeypatch.setattr(
        data_vault,
        "collect_market_status",
        lambda: {"collector": "status", "status": "OK"},
    )
    monkeypatch.setattr(
        data_vault,
        "collect_indices",
        lambda: {"collector": "indices", "status": "OK"},
    )
    monkeypatch.setattr(
        data_vault,
        "collect_quote",
        lambda symbol: seen_symbols.append(symbol) or {"symbol": symbol, "status": "OK"},
    )

    result = data_vault.refresh_data_vault(limit=2, include_news=False)

    assert result["status"] == "OK"
    assert result["symbols"] == ["RELIANCE.NS", "TCS.NS"]
    assert seen_symbols == ["RELIANCE.NS", "TCS.NS"]
