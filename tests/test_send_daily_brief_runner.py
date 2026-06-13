from scripts import send_daily_brief


def test_needs_seed_when_cache_empty(monkeypatch):
    monkeypatch.setattr(
        send_daily_brief.database,
        "get_db_health",
        lambda: {"watchlist_count": 0, "price_count": 0},
    )
    monkeypatch.setattr(send_daily_brief, "_latest_price_age_days", lambda: None)

    needs_seed, health = send_daily_brief._needs_seed()

    assert needs_seed is True
    assert health["needs_seed"] is True


def test_needs_seed_false_when_cache_ready(monkeypatch):
    monkeypatch.setattr(
        send_daily_brief.database,
        "get_db_health",
        lambda: {"watchlist_count": 20, "price_count": 5000},
    )
    monkeypatch.setattr(send_daily_brief, "_latest_price_age_days", lambda: 2)

    needs_seed, health = send_daily_brief._needs_seed()

    assert needs_seed is False
    assert health["latest_price_age_days"] == 2
