import os
import sys
import time

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.fetcher import sync_ticker

tickers = [
    "^NSEI",
    "TCS.NS",
    "INFY.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
    "LT.NS",
    "ITC.NS",
    "BHARTIARTL.NS",
    "AXISBANK.NS",
    "KOTAKBANK.NS",
    "MARUTI.NS",
    "TMPV.NS",
    "TMCV.NS",
    "SUNPHARMA.NS",
    "HINDUNILVR.NS",
    "BAJFINANCE.NS"
]

print("==================================================")
print("  BULL Watchlist Seeding & Synchronization Script  ")
print("==================================================")
print(f"Targeting {len(tickers)} symbols. Starting sequential sync...\n")

success_count = 0
failed_tickers = []

for idx, ticker in enumerate(tickers, 1):
    print(f"[{idx}/{len(tickers)}] Syncing {ticker}...", end="", flush=True)
    
    start_time = time.time()
    try:
        # Fetch metadata and daily historical prices (1 Year)
        res = sync_ticker(ticker)
        duration = time.time() - start_time
        
        if res['success']:
            success_count += 1
            print(f" SUCCESS! Synced {res['rows_synced']} daily candles. ({duration:.1f}s)")
        else:
            failed_tickers.append(ticker)
            print(f" FAILED! (No data found or connection timeout) ({duration:.1f}s)")
            
    except Exception as e:
        failed_tickers.append(ticker)
        print(f" ERROR: {str(e)}")
        
    # Politeness gap to prevent rate-limiting/blocks from Yahoo Finance scraper
    time.sleep(0.5)

print("\n==================================================")
print("Synchronization Summary:")
print(f"Successfully Synced: {success_count}/{len(tickers)}")
if failed_tickers:
    print(f"Failed Symbols:      {', '.join(failed_tickers)}")
else:
    print("All symbols synced successfully!")
print("==================================================")
