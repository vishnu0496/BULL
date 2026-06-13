import logging
import os
import sys

import pandas as pd
import yfinance as yf

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src import database

# Set up logging so we can see output on Render stdout/stderr
logger = logging.getLogger("bull.data_seeder")
logging.basicConfig(level=logging.INFO)

NIFTY50 = [
  "^NSEI",
  "RELIANCE.NS","TCS.NS","HDFCBANK.NS",
  "INFY.NS","ICICIBANK.NS","HINDUNILVR.NS",
  "ITC.NS","SBIN.NS","BHARTIARTL.NS",
  "KOTAKBANK.NS","BAJFINANCE.NS","AXISBANK.NS",
  "LT.NS","MARUTI.NS","SUNPHARMA.NS",
  "TITAN.NS","WIPRO.NS","ULTRACEMCO.NS",
  "HCLTECH.NS","ADANIENT.NS","TMPV.NS",
  "NTPC.NS","ONGC.NS","POWERGRID.NS",
  "TECHM.NS","NESTLEIND.NS","DRREDDY.NS",
  "BAJAJFINSV.NS","TATASTEEL.NS","JSWSTEEL.NS",
  "GRASIM.NS","ADANIPORTS.NS","COALINDIA.NS",
  "BPCL.NS","DIVISLAB.NS","BRITANNIA.NS",
  "CIPLA.NS","EICHERMOT.NS","TATACONSUM.NS",
  "APOLLOHOSP.NS","HEROMOTOCO.NS","HINDALCO.NS",
  "M&M.NS","BAJAJ-AUTO.NS","ASIANPAINT.NS",
  "VEDL.NS","INDUSINDBK.NS",
  "SHREECEM.NS","PIDILITIND.NS"
]


def _normalize_download(df):
    """Normalize yFinance output into the shape database.save_prices expects."""
    if df is None or df.empty:
        return df
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    out = out.reset_index()
    rename_map = {}
    for col in out.columns:
        normalized = str(col).strip().lower()
        if normalized in {"date", "datetime", "index"}:
            rename_map[col] = "Date"
        elif normalized in {"open", "high", "low", "close", "volume"}:
            rename_map[col] = normalized.capitalize()
    out = out.rename(columns=rename_map)
    required = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [col for col in required if col not in out.columns]
    if missing:
        raise ValueError(f"Missing columns after yFinance download: {missing}")
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    return out[required].ffill()

def main():
    database.init_db()
    
    # Add tickers to watchlist
    for ticker in NIFTY50:
        try:
            database.add_to_watchlist(ticker)
        except Exception:
            pass
    
    # Download price history
    for ticker in NIFTY50:
        try:
            df = yf.download(
                ticker, 
                period="1y", 
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            df = _normalize_download(df)
            if df is not None and len(df) > 0:
                database.save_prices(ticker, df)
                logger.info(f"Seeded {ticker}: {len(df)} rows")
        except Exception as e:
            logger.warning(f"Skip {ticker}: {e}")

if __name__ == "__main__":
    main()
