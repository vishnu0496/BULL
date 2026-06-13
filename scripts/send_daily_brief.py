"""Run BULL's daily brief without starting the web server.

This is the free, reliable path for the real product: GitHub Actions can run
this script every weekday morning, refresh the candle cache, and send Telegram.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from notifier import get_telegram_config, send_morning_brief  # noqa: E402
from src import database  # noqa: E402
from src.daily_brief import build_daily_brief, format_telegram_brief  # noqa: E402


def _latest_price_age_days() -> int | None:
    """Return age in days of the newest cached candle, or None when empty."""
    conn = database.get_db_connection()
    try:
        row = conn.execute("SELECT MAX(date) AS latest_date FROM historical_prices").fetchone()
    finally:
        conn.close()
    latest_value = row["latest_date"] if row else None
    if not latest_value:
        return None
    latest_day = date.fromisoformat(str(latest_value)[:10])
    return (date.today() - latest_day).days


def _needs_seed(max_age_days: int = 10) -> tuple[bool, dict]:
    """Decide whether the local cache is ready for a serious daily scan."""
    health = database.get_db_health()
    watchlist_count = int(health.get("watchlist_count") or 0)
    price_count = int(health.get("price_count") or 0)
    min_price_rows = max(600, watchlist_count * 60)
    latest_age_days = _latest_price_age_days()
    needs_seed = (
        watchlist_count == 0
        or price_count < min_price_rows
        or latest_age_days is None
        or latest_age_days > max_age_days
    )
    health.update(
        {
            "min_price_rows_for_scanner": min_price_rows,
            "latest_price_age_days": latest_age_days,
            "needs_seed": needs_seed,
        }
    )
    return needs_seed, health


def _apply_env_risk_settings() -> None:
    """Allow GitHub Actions secrets/vars to set the risk budget."""
    settings = database.get_capital_settings()

    total_capital = float(os.getenv("BULL_TOTAL_CAPITAL") or settings.get("total_capital") or 5000)
    max_risk = float(os.getenv("BULL_MAX_RISK_PER_TRADE") or settings.get("max_risk_per_trade") or 100)
    max_trades = int(os.getenv("BULL_MAX_TRADES_PER_DAY") or settings.get("max_trades_per_day") or 1)

    database.update_capital_settings(
        total_capital=total_capital,
        max_risk_per_trade=max_risk,
        max_trades_per_day=max_trades,
        allow_options=int(settings.get("allow_options") or 0),
        experience_level=str(settings.get("experience_level") or "BEGINNER"),
        gemini_api_key=str(settings.get("gemini_api_key") or ""),
        dhan_client_id=str(settings.get("dhan_client_id") or ""),
        dhan_access_token=str(settings.get("dhan_access_token") or ""),
        kite_api_key=str(settings.get("kite_api_key") or ""),
        kite_api_secret=str(settings.get("kite_api_secret") or ""),
        kite_request_token=str(settings.get("kite_request_token") or ""),
        autopilot=int(settings.get("autopilot") or 0),
    )


def run(seed: bool = True, force_seed: bool = False, dry_run: bool = False) -> int:
    """Refresh data if needed, build the brief, and optionally send Telegram."""
    database.init_db()
    _apply_env_risk_settings()

    needs_seed, health = _needs_seed()
    print(
        "BULL data health: "
        f"watchlist_count={health.get('watchlist_count')} "
        f"price_count={health.get('price_count')} "
        f"latest_price_age_days={health.get('latest_price_age_days')} "
        f"needs_seed={needs_seed}"
    )

    if seed and (force_seed or needs_seed):
        from scripts.data_seeder import main as seed_data

        print("Refreshing BULL market data...")
        seed_data()
        needs_seed, health = _needs_seed()
        print(
            "BULL data health after refresh: "
            f"watchlist_count={health.get('watchlist_count')} "
            f"price_count={health.get('price_count')} "
            f"latest_price_age_days={health.get('latest_price_age_days')} "
            f"needs_seed={needs_seed}"
        )

    brief = build_daily_brief()
    message = format_telegram_brief(brief)
    print("-" * 64)
    print(message)
    print("-" * 64)

    if dry_run:
        print("Dry run complete. Telegram not sent.")
        return 0

    token, chat_id = get_telegram_config()
    if token == "YOUR_BOT_TOKEN_HERE" or chat_id == "YOUR_CHAT_ID_HERE":
        print("Telegram is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return 2

    return 0 if send_morning_brief() else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh data and send the BULL daily Telegram brief.")
    parser.add_argument("--dry-run", action="store_true", help="Print the brief without sending Telegram")
    parser.add_argument("--force-seed", action="store_true", help="Refresh market data even when cache looks ready")
    parser.add_argument("--no-seed", action="store_true", help="Do not refresh market data")
    args = parser.parse_args()
    return run(seed=not args.no_seed, force_seed=args.force_seed, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
