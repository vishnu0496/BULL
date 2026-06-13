# BULL Agent Rules

These rules apply to work inside this repository.

## Goal

BULL is a private Indian market research terminal for Vishnu. The real product goal is to identify 2-3 highest-probability profit opportunities each market day, with clear entry, stop-loss, target, reason, and confidence. The point is to help Vishnu make money, not merely to teach trading or show a pretty dashboard.

Discipline, risk control, paper-trade logging, and analytics are not the dream. They are the engineering safety system that prevents BULL from becoming a fake-confidence machine that destroys capital. BULL must aggressively search for profitable opportunities while staying honest about uncertainty, bad data, and market risk.

BULL is not allowed to claim guaranteed profit, because markets do not permit that. It must instead rank opportunities by evidence, reject weak setups, and keep improving from outcomes.

## Current App Boundary

- Primary app: `api.server:app` with the `frontend/` UI on port `8000`.
- Legacy/experimental app: root `server.py` with root `index.html`.
- Before editing routes or UI, verify which surface the user is looking at.
- Keep README, run scripts, and deploy config aligned with the primary app.

## Working Style

- When enough information exists, act. Do not over-plan or re-litigate established decisions.
- Make the smallest change that improves reliability, usability, or measurement.
- Do not add unrelated refactors, abstractions, feature flags, or speculative future-proofing.
- Pause only for destructive actions, real scope changes, production-risk decisions, or secrets only Vishnu can provide.
- Treat free hosting and free market data honestly. If data is delayed, stale, blocked, or inferred, say so.

## Evidence Discipline

- Ground progress claims in tool results from the current session.
- Before saying something is fixed, verify it with tests, endpoint checks, logs, database counts, or browser evidence.
- If tests fail, report the failure exactly enough to act on.
- If a step is skipped or unverified, say that plainly.

## BULL Verification Checklist

Use the checks that match the work:

- `python -m py_compile ...`
- `.venv\Scripts\python.exe -m pytest -q`
- `.venv\Scripts\python.exe scripts\smoke_test.py --url http://127.0.0.1:8000`
- `GET /api/health`
- `GET /api/morning-status`
- `GET /setup`
- Browser check for visible UI, console health, and target interaction when frontend changed.

## Git Discipline

- Do not stage runtime files, secrets, databases, logs, model artifacts, or scratch files.
- Check `git status --short` before staging.
- Push only when the user asks to push or the task explicitly includes pushing.

## Communication

- Lead with the outcome.
- Explain trading and coding concepts in plain English.
- Be honest and direct, but not theatrical.
- Avoid dense jargon, arrow-chain shorthand, and long summaries unless the user asks.
