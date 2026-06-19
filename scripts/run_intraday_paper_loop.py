"""Run BULL's intraday paper executor loop locally.

This is the zero-cost way to get closer to live paper execution:
keep your laptop/PC on during market hours and let this script poll NSE quotes.
"""

from __future__ import annotations

import argparse
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.intraday_paper import run_intraday_loop, run_intraday_paper_once  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BULL intraday paper execution.")
    parser.add_argument("--interval", type=int, default=30, help="Polling interval in seconds. Minimum is 5.")
    parser.add_argument("--once", action="store_true", help="Run one intraday check and exit.")
    parser.add_argument("--force", action="store_true", help="Run even if local clock says market is closed.")
    args = parser.parse_args()

    if args.once:
        print(run_intraday_paper_once(force=args.force))
        return 0

    run_intraday_loop(interval_seconds=args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
