# BULL: Private Indian Market Research Terminal

BULL is a private Indian market research and paper-trading terminal for one user. It is built to help a beginner follow a disciplined morning routine, inspect market context, log paper trades, and measure whether the system's ideas are improving.

It is not a real-money order-placement tool, not a profit guarantee, and not ready for blind live trading.

## Current App

The current primary app is:

```cmd
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://localhost:8000
```

The root `server.py` + root `index.html` terminal is an older experimental surface. Keep it for reference while migrating useful pieces, but use `api.server:app` as the main BULL app.

## Run Locally

Double-click `run.bat`, or run:

```cmd
cd C:\Users\Vishnu\Documents\BULL
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
```

## Daily Use

1. Start BULL with `run.bat`.
2. Open `http://localhost:8000`.
3. Open `http://localhost:8000/setup` once to connect Telegram.
4. Check the Daily Mentor before market open.
5. Log only paper trades until BULL has enough closed-trade evidence.
6. Review Analytics before changing risk.

## Smoke Test

Run this any time after starting BULL locally or after a hosted deploy:

```cmd
.venv\Scripts\python.exe scripts\smoke_test.py --url http://127.0.0.1:8000
```

For Render:

```cmd
.venv\Scripts\python.exe scripts\smoke_test.py --url https://bull-nxlh.onrender.com
```

The smoke test checks:

- `/api/health`
- `/api/morning-status`
- `/setup`
- `/api/mentor/picks`
- whether the database is seeded enough for real scanner work

If it says the database is not seeded, trigger:

```text
POST /api/admin/seed
```

Then rerun the smoke test.

## Hosting Reality

Free Render is useful for demos, but it is not a serious always-on market terminal:

- it can sleep after inactivity
- its filesystem is ephemeral unless a persistent disk is attached
- cold starts and reseeding can delay the app

For reliable hosting, BULL needs one of these:

- a paid Render web service with a persistent disk using `render.yaml`
- a small VPS that runs 24/7
- a laptop/server that stays on all market hours

The repo includes `render.yaml` for the paid persistent-disk Render path. BULL stores SQLite data under `BULL_DATA_DIR` when that environment variable is set; otherwise it uses local `data/`.

## Telegram Setup

Open:

```text
http://localhost:8000/setup
```

The setup page guides you through:

- creating a Telegram bot with BotFather
- detecting your chat ID
- sending a test message
- saving credentials into `.env`

Telegram BotFather and Telegram bot messages are free.

## Free Daily Telegram Job

BULL can send the daily Telegram brief without Render or a VPS by using GitHub Actions.

GitHub repository secrets required:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Optional GitHub repository variables:

- `BULL_TOTAL_CAPITAL`
- `BULL_MAX_RISK_PER_TRADE`
- `BULL_MAX_TRADES_PER_DAY`

The workflow is:

```text
.github/workflows/bull-daily-brief.yml
```

It runs at 8:45 AM IST, Monday to Friday, and can also be triggered manually from the GitHub Actions tab.

To test the runner locally without sending Telegram:

```cmd
.venv\Scripts\python.exe scripts\send_daily_brief.py --dry-run
```

To send immediately from your machine after `.env` is configured:

```cmd
.venv\Scripts\python.exe scripts\send_daily_brief.py
```

## Test

```cmd
cd C:\Users\Vishnu\Documents\BULL
.venv\Scripts\activate
pytest
```

## Current Limits

- No broker order placement.
- No guaranteed live NSE-grade tick feed.
- Public/free data sources can fail or rate-limit.
- ML scores still need more walk-forward validation and paper-trade evidence.
- F&O and commodities remain watch/training surfaces until the skill gate proves discipline.

## Product Direction

BULL should become less like a prediction toy and more like a trading coach plus research terminal:

- reliable daily startup
- clean data health
- morning brief
- paper-trade logging
- analytics feedback loop
- only then stronger live feeds, alerts, and paid APIs
