import os
import sys

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import init_db, add_to_watchlist
from src.fetcher import sync_ticker

NIFTY_50 = [
    "ADANIPORTS.NS", "APOLLOHOSP.NS", "ASIANPAINT.NS", "AXISBANK.NS", "BAJAJ-AUTO.NS",
    "BAJFINANCE.NS", "BHARTIARTL.NS", "BPCL.NS", "BRITANNIA.NS", "CIPLA.NS",
    "COALINDIA.NS", "DIVISLAB.NS", "DRREDDY.NS", "EICHERMOT.NS", "GRASIM.NS",
    "HCLTECH.NS", "HDFCBANK.NS", "HDFCLIFE.NS", "HEROMOTOCO.NS", "HINDALCO.NS",
    "HINDUNILVR.NS", "ICICIBANK.NS", "INDUSINDBK.NS", "INFY.NS", "ITC.NS",
    "JSWSTEEL.NS", "KOTAKBANK.NS", "LT.NS", "LTIM.NS", "M&M.NS",
    "MARUTI.NS", "NESTLEIND.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS",
    "RELIANCE.NS", "SBILIFE.NS", "SBIN.NS", "SUNPHARMA.NS", "TATACONSUM.NS",
    "TATAMOTORS.NS", "TATAPOWER.NS", "TATASTEEL.NS", "TCS.NS", "TECHM.NS",
    "TITAN.NS", "ULTRACEMCO.NS", "UPL.NS", "WIPRO.NS"
]

def main():
    print("============================================================")
    print("BULL DATABASE - SEEDING NIFTY 50 WATCHLIST & HISTORIES")
    print("============================================================")
    
    # Initialize database tables
    init_db()
    
    success_count = 0
    # Add index explicitly to watchlist so it can be synced
    try:
        add_to_watchlist("^NSEI", "NIFTY 50 Index", "Index")
        sync_ticker("^NSEI", period="1y")
        print("   [OK] Synced ^NSEI (Nifty 50 Index)")
    except Exception as e:
        print(f"   [WARN] Index sync failed: {e}")

    for idx, ticker in enumerate(NIFTY_50):
        ticker_upper = ticker.upper()
        print(f"[{idx+1}/{len(NIFTY_50)}] Processing {ticker_upper}...")
        
        try:
            # Add ticker to watchlist first
            add_to_watchlist(ticker_upper, ticker_upper.split('.')[0], "Nifty 50 Sector Leader")
            # Sync ticker price history
            res = sync_ticker(ticker_upper, period="1y")
            if res['success']:
                print(f"   [OK] Synced {res['name']} ({ticker_upper}) - {res['rows_synced']} price rows.")
                success_count += 1
            else:
                print(f"   [FAIL] Sync failed for {ticker_upper}.")
        except Exception as e:
            print(f"   [FAIL] Error during sync for {ticker_upper}: {str(e)}")
            
    print("============================================================")
    print(f"SEEDING COMPLETE: Successfully synced {success_count}/{len(NIFTY_50)} tickers.")
    print("============================================================")

if __name__ == "__main__":
    main()
