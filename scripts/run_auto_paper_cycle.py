"""Run BULL automatic paper evidence once.

This script is intentionally independent from the FastAPI web server. It can be
run manually, from Windows Task Scheduler, or from a future hosted worker.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src import auto_paper, database  # noqa: E402
from src.daily_brief import get_daily_picks  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture and evaluate BULL automatic paper evidence.")
    parser.add_argument("--max-picks", type=int, default=3)
    parser.add_argument("--horizon-days", type=int, default=5)
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Skip refreshing active evidence ticker prices before evaluation.",
    )
    args = parser.parse_args()

    database.init_db()
    picks = get_daily_picks(max_items=max(8, args.max_picks))
    result = auto_paper.run_auto_paper_cycle(
        picks=picks,
        max_picks=args.max_picks,
        horizon_days=args.horizon_days,
        sync_prices=not args.no_sync,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
