import yfinance as yf
from src import database
import logging

# Set up logging so we can see output on Render stdout/stderr
logger = logging.getLogger("bull.data_seeder")
logging.basicConfig(level=logging.INFO)

NIFTY50 = [
  "RELIANCE.NS","TCS.NS","HDFCBANK.NS",
  "INFY.NS","ICICIBANK.NS","HINDUNILVR.NS",
  "ITC.NS","SBIN.NS","BHARTIARTL.NS",
  "KOTAKBANK.NS","BAJFINANCE.NS","AXISBANK.NS",
  "LT.NS","MARUTI.NS","SUNPHARMA.NS",
  "TITAN.NS","WIPRO.NS","ULTRACEMCO.NS",
  "HCLTECH.NS","ADANIENT.NS","TATAMOTORS.NS",
  "NTPC.NS","ONGC.NS","POWERGRID.NS",
  "TECHM.NS","NESTLEIND.NS","DRREDDY.NS",
  "BAJAJFINSV.NS","TATASTEEL.NS","JSWSTEEL.NS",
  "GRASIM.NS","ADANIPORTS.NS","COALINDIA.NS",
  "BPCL.NS","DIVISLAB.NS","BRITANNIA.NS",
  "CIPLA.NS","EICHERMOT.NS","TATACONSUM.NS",
  "APOLLOHOSP.NS","HEROMOTOCO.NS","HINDALCO.NS",
  "M&M.NS","BAJAJ-AUTO.NS","ASIANPAINT.NS",
  "LTIM.NS","VEDL.NS","INDUSINDBK.NS",
  "SHREECEM.NS","PIDILITIND.NS"
]

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
                period="6mo", 
                interval="1d",
                progress=False,
                auto_adjust=True
            )
            if df is not None and len(df) > 0:
                database.save_prices(ticker, df)
                logger.info(f"Seeded {ticker}: {len(df)} rows")
        except Exception as e:
            logger.warning(f"Skip {ticker}: {e}")

if __name__ == "__main__":
    main()
