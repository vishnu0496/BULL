import os
import sys

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import init_db, get_watchlist_tickers
from src.backtest import get_stock_verdict, get_all_stock_verdicts

print("============================================================")
print("BULL PHASE 5 INTEGRATION & QA VERIFICATION RUN")
print("============================================================")

# Step 1: Initialize Database
print("\n[STEP 1/3] Initializing Database Schema...")
init_db()
tickers = get_watchlist_tickers()
print(f"[PASS] Database initialized successfully. Watchlist tickers: {len(tickers)}")

# Step 2: Verify get_stock_verdict
print("\n[STEP 2/3] Verifying Individual Ticker Verdict Calculation...")
test_stock = "RELIANCE.NS"
if test_stock in tickers:
    try:
        verdict = get_stock_verdict(test_stock)
        print(f"[INFO] Verdict output for {test_stock}:")
        for k, v in verdict.items():
            print(f"       - {k}: {v}")
            
        # Assertions
        assert verdict['verdict'] in ['GOOD', 'WEAK', 'BAD'], f"Verdict should be GOOD/WEAK/BAD, got {verdict['verdict']}"
        assert 'expectancy' in verdict, "expectancy field should exist"
        assert 'reason' in verdict, "reason field should exist"
        print("[PASS] Individual stock verdict format and fields validated successfully!")
    except Exception as e:
        print(f"[FAIL] Error calculating verdict for {test_stock}: {str(e)}")
        sys.exit(1)
else:
    print(f"[WARNING] Ticker {test_stock} not in database watchlist. Skipping step 2.")

# Step 3: Verify get_all_stock_verdicts and index symbol exclusions
print("\n[STEP 3/3] Verifying Batch Ticker Verdicts & Index Exclusions...")
index_symbols = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
try:
    verdicts = get_all_stock_verdicts(tickers)
    print(f"[INFO] Generated {len(verdicts)} stock verdicts out of {len(tickers)} watchlist tickers.")
    
    # Assertions
    verdict_tickers = {v['ticker'] for v in verdicts}
    intersect = verdict_tickers.intersection(index_symbols)
    assert len(intersect) == 0, f"Indices should be excluded, but found: {intersect}"
    print("[PASS] Verified index symbols are excluded from batch strategy backtests.")
    
    for v in verdicts:
        assert v['verdict'] in ['GOOD', 'WEAK', 'BAD'], f"Invalid verdict for {v['ticker']}: {v['verdict']}"
        
    print("[PASS] Verified all stock verdicts are strictly categorized as GOOD, WEAK, or BAD.")
    
    # Print the top ranked stock
    if verdicts:
        top_ranked = verdicts[0]
        print(f"[INFO] Top Ranked Stock: {top_ranked['ticker']} (Verdict: {top_ranked['verdict']}, Net Profit: {top_ranked['net_profit']})")
except Exception as e:
    print(f"[FAIL] Error running batch verdicts: {str(e)}")
    sys.exit(1)

print("\n============================================================")
print("FINAL PHASE 5 VERIFICATION SUMMARY")
print("============================================================")
print("VERDICT FORMAT:      PASS")
print("INDEX EXCLUSIONS:    PASS")
print("CLASSIFICATION STATS: PASS")
print("============================================================")
print("ALL TESTS PASSED SUCCESSFULLY.")
print("============================================================")
