# BULL: Private Local Market Research Desk

BULL is a private, local dashboard for researching Indian stocks before the market opens. It is not an order-placement tool, not a profit guarantee, and not a replacement for risk control.

The current local app is a FastAPI server (`api.server:app`) that serves API routes and the static frontend in `frontend/`.

## What It Does

- Maintains a local stock watchlist.
- Fetches daily historical data through `yfinance`.
- Stores all data in local SQLite.
- Generates rule-based research setups with entry trigger, stop-loss, targets, invalidation rule, confidence score, and risk level.
- Keeps a paper journal for learning and validation.
- Includes experimental ML/LSTM model training code that writes generated artifacts under `models/`.

## Data Disclaimer

This application uses `yfinance`, an unofficial open-source wrapper around Yahoo Finance data. It is not affiliated with or endorsed by Yahoo Finance. Treat this data as personal/research data only. It may be delayed, incomplete, unavailable, or different from broker/exchange data.

## Current Limits

- No real-money trading.
- No broker order placement.
- No real live intraday price feed yet. The browser price stream is simulated from stored end-of-day prices and is labeled as simulated.
- Entry instructions are conditional watch rules, not automatic orders.
- Gemini sentiment is disabled by default even if a key is saved. Set `BULL_ENABLE_GEMINI_SENTIMENT=true` only when you intentionally want to spend Gemini calls.
- Automatic background watchlist news scraping is disabled by default. Set `BULL_ENABLE_BACKGROUND_NEWS_SWARM=true` only when you want the app to scrape news continuously while the server is running.

Treat any setup as valid only after the first few minutes of market noise, such as after 9:20 AM, and only if the price trigger is actually reached.

## Stack

- Python
- FastAPI
- Uvicorn
- SQLite
- pandas
- yfinance
- pytest

## Run

Double-click `run.bat`, or run:

```cmd
cd C:\Users\Vishnu\Documents\BULL
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn api.server:app --host 127.0.0.1 --port 8501 --reload
```

Optional environment flags:

```cmd
set BULL_ENABLE_GEMINI_SENTIMENT=true
set BULL_GEMINI_SENTIMENT_MAX_CALLS=20
set BULL_ENABLE_BACKGROUND_NEWS_SWARM=true
```

Then open:

```text
http://localhost:8501
```

Health check:

```text
http://localhost:8501/api/health
```

## Test

```cmd
cd C:\Users\Vishnu\Documents\BULL
.venv\Scripts\activate
pytest
```

`pytest.ini` limits collection to `tests/`.

## Workflow

1. Add liquid NSE stocks to the watchlist, such as `RELIANCE.NS`, `TCS.NS`, or `INFY.NS`.
2. Sync data from the Data Health page.
3. Generate today's research setups from the Pre-Market Research Desk.
4. Paper-track what happens.
5. Trust only measured results, not the appearance of the dashboard.
