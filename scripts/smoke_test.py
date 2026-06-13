"""Smoke-test a local or hosted BULL deployment."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urljoin

import requests


CHECKS = (
    ("health", "GET", "/api/health", True),
    ("morning_status", "GET", "/api/morning-status", True),
    ("setup_page", "GET", "/setup", False),
    ("mentor_picks", "GET", "/api/mentor/picks", False),
)


def _request(base_url: str, method: str, path: str, timeout: int) -> tuple[bool, str, object]:
    """Run one HTTP check and return status, note, and parsed body."""
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    try:
        response = requests.request(method, url, timeout=timeout)
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body: object = response.json()
        else:
            body = response.text[:250]
        if response.ok:
            return True, f"HTTP {response.status_code}", body
        return False, f"HTTP {response.status_code}", body
    except Exception as exc:
        return False, str(exc), None


def run_smoke_test(base_url: str, timeout: int = 20) -> int:
    """Run the deployment smoke test."""
    failures = 0
    print(f"BULL smoke test: {base_url}")
    print("-" * 64)

    health_body = None
    for name, method, path, required in CHECKS:
        ok, note, body = _request(base_url, method, path, timeout)
        if required and not ok:
            failures += 1
        status = "PASS" if ok else "WARN" if not required else "FAIL"
        print(f"{status:4} {name:16} {path:24} {note}")
        if name == "health" and isinstance(body, dict):
            health_body = body

    if isinstance(health_body, dict):
        watchlist_count = int(health_body.get("watchlist_count") or 0)
        price_count = int(health_body.get("price_count") or 0)
        latest_age_days = health_body.get("latest_price_age_days")
        seeded = bool(health_body.get("seeded"))
        print("-" * 64)
        print(
            "watchlist_count="
            f"{watchlist_count} price_count={price_count} "
            f"latest_price_age_days={latest_age_days} seeded={seeded}"
        )
        if not seeded:
            failures += 1
            print("FAIL seed_state       database is not seeded enough for real picks")
            print("     Fix: POST /api/admin/seed or /api/sync-all, then re-run this smoke test.")
        else:
            print("PASS seed_state       database is fresh enough for scanner work")

    print("-" * 64)
    if failures:
        print(f"RESULT: NOT READY ({failures} blocking issue(s))")
        return 1
    print("RESULT: READY")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test BULL local or hosted deployment.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Base BULL URL")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Reserved for future machine-readable output")
    args = parser.parse_args()
    if args.json:
        print(json.dumps({"error": "JSON output is not implemented yet. Use normal text output."}))
        return 2
    return run_smoke_test(args.url, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
