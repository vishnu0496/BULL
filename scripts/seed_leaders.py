import os
import sys

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import init_db, get_watchlist_tickers
from src.fetcher import sync_ticker

NIFTY_LEADERS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "SBIN.NS", "TATAMOTORS.NS", "TATAPOWER.NS", "ITC.NS", "LT.NS",
    "BHARTIARTL.NS", "AXISBANK.NS", "M&M.NS", "MARUTI.NS", "NTPC.NS",
    "POWERGRID.NS", "COALINDIA.NS", "SUNPHARMA.NS", "HINDALCO.NS", "ONGC.NS"
]

def main():
    print("============================================================")
    print("BULL DATABASE - SEEDING NIFTY MARKET LEADERS")
    print("============================================================")
    
    # Initialize database tables
    init_db()
    
    success_count = 0
    for idx, ticker in enumerate(NIFTY_LEADERS):
        ticker_upper = ticker.upper()
        print(f"[{idx+1}/{len(NIFTY_LEADERS)}] Processing {ticker_upper}...")
        
        # Sync ticker EOD prices & metadata
        try:
            res = sync_ticker(ticker_upper, period="1y")
            if res['success']:
                print(f"   [OK] Synced {res['name']} ({ticker_upper}) - {res['rows_synced']} price rows.")
                success_count += 1
            else:
                print(f"   [FAIL] Sync failed for {ticker_upper}. Check NSE connection.")
        except Exception as e:
            print(f"   [FAIL] Error during sync for {ticker_upper}: {str(e)}")
            
    print("============================================================")
    print(f"SEEDING COMPLETE: Successfully synced {success_count}/{len(NIFTY_LEADERS)} leaders.")
    print("============================================================")

if __name__ == "__main__":
    main()
