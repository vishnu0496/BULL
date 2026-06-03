# BULL: Private Local Market Research Terminal

BULL is a private, local Indian market research terminal for training, paper trading, and measuring whether trading ideas are actually working.

It is not a real-money order-placement tool, not a profit guarantee, and not ready for live trading.

## Current App

The current Antigravity UI/UX terminal is served by:

```cmd
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Open:

```text
http://localhost:8000
```

The older `api/server.py` + `frontend/` app on port `8501` is legacy. Keep it for reference while migrating useful logic, but use port `8000` as the main BULL terminal.

## What It Does

- Runs a dark Research Terminal UI with Analytics, Pre-Market Desk, Watchlist, scanner, paper journal, and backtest surfaces.
- Uses a paper broker to simulate entries and exits.
- Tracks closed/open paper trades in `trades_journal.json`.
- Shows paper-trading analytics: net PnL, win rate, average R-multiple, profit factor, max drawdown, equity curve, outcome split, R distribution, signal quality, sector view, and trade log.
- Includes experimental ML/ensemble modules for future signal work.

## Current Limits

- No real-money trading.
- No broker order placement.
- No reliable live intraday market feed yet.
- Current paper trades are local simulations, not exchange-confirmed fills.
- ML and signal quality panels are still experimental and need walk-forward validation before being trusted.

## Run

Double-click `run.bat`, or run:

```cmd
cd C:\Users\Vishnu\Documents\BULL
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

Then open:

```text
http://localhost:8000
```

## Test

```cmd
cd C:\Users\Vishnu\Documents\BULL
.venv\Scripts\activate
pytest
```

## Training Workflow

1. Use the scanner and pre-market desk only for paper ideas.
2. Execute simulated paper trades.
3. Close trades as win/loss after the idea plays out.
4. Study Analytics to see whether the system and your execution are improving.
5. Do not increase risk until the paper-trade sample is large enough to trust.
