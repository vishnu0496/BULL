import os
import sys
import pandas as pd
import numpy as np

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import init_db, get_db_connection, get_capital_settings, get_prices
from src.market import get_market_regime
from src.backtest import run_backtest
from src.fetcher import sync_ticker

def run_verification():
    print("=" * 60)
    print("BULL PHASE 3 INTEGRATION & QA VERIFICATION RUN")
    print("=" * 60)
    
    # 1. Initialize & Verify Database
    print("\n[STEP 1/4] Initializing Database...")
    db_pass = False
    try:
        init_db()
        conn = get_db_connection()
        cursor = conn.cursor()
        tables = ["watchlist", "historical_prices", "paper_journal", "research_setups", "capital_settings"]
        verified_tables = []
        for t in tables:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{t}'")
            row = cursor.fetchone()
            if row is not None:
                verified_tables.append(t)
        conn.close()
        
        if len(verified_tables) == len(tables):
            print("[PASS] Database initialized successfully. All required tables exist:")
            for vt in verified_tables:
                print(f"       - {vt} table verified.")
            db_pass = True
        else:
            missing = set(tables) - set(verified_tables)
            print(f"[FAIL] Database initialized but tables missing: {missing}")
    except Exception as e:
        print(f"[FAIL] Database initialization failed with error: {e}")

    # 2. Verify Capital Settings
    print("\n[STEP 2/4] Verifying Capital Settings...")
    capital_pass = False
    try:
        settings = get_capital_settings()
        required_keys = ['total_capital', 'max_risk_per_trade', 'max_trades_per_day', 'allow_options', 'experience_level']
        missing_keys = [k for k in required_keys if k not in settings]
        
        if not missing_keys:
            print("[PASS] Capital settings loaded correctly:")
            print(f"       - Total Capital: {settings['total_capital']}")
            print(f"       - Max Risk per Trade: {settings['max_risk_per_trade']}")
            print(f"       - Max Trades per Day: {settings['max_trades_per_day']}")
            print(f"       - Allow Options: {settings['allow_options']}")
            print(f"       - Experience Level: {settings['experience_level']}")
            capital_pass = True
        else:
            print(f"[FAIL] Capital settings loaded but missing fields: {missing_keys}")
    except Exception as e:
        print(f"[FAIL] Capital settings loading failed with error: {e}")

    # 3. Verify Market Regime Engine
    print("\n[STEP 3/4] Verifying Market Regime Engine...")
    regime_pass = False
    try:
        regime = get_market_regime()
        required_regime_keys = ['market_bias', 'trend_score', 'volatility_score', 'reasons']
        missing_regime_keys = [k for k in required_regime_keys if k not in regime]
        
        if not missing_regime_keys:
            # Check validation criteria
            bias = regime['market_bias']
            t_score = regime['trend_score']
            v_score = regime['volatility_score']
            reasons = regime['reasons']
            
            bias_valid = bias in ['BULLISH', 'BEARISH', 'NEUTRAL']
            t_valid = isinstance(t_score, (int, float)) and 0 <= t_score <= 100
            v_valid = isinstance(v_score, (int, float)) and 0 <= v_score <= 100
            reasons_valid = isinstance(reasons, list) and len(reasons) > 0
            
            if bias_valid and t_valid and v_valid and reasons_valid:
                print("[PASS] Market Regime Engine returned all required fields with valid types:")
                print(f"       - market_bias: {bias}")
                print(f"       - trend_score: {t_score}")
                print(f"       - volatility_score: {v_score}")
                print(f"       - reasons count: {len(reasons)}")
                for r in reasons[:3]:
                    print(f"         * {r}")
                if len(reasons) > 3:
                    print(f"         * ... and {len(reasons)-3} more reasons.")
                regime_pass = True
            else:
                print("[FAIL] Regime engine returned correct fields but validation failed:")
                print(f"       - market_bias valid? {bias_valid} (value: {bias})")
                print(f"       - trend_score valid? {t_valid} (value: {t_score})")
                print(f"       - volatility_score valid? {v_valid} (value: {v_score})")
                print(f"       - reasons valid? {reasons_valid}")
        else:
            print(f"[FAIL] Regime engine output missing fields: {missing_regime_keys}")
    except Exception as e:
        print(f"[FAIL] Market Regime Engine evaluation failed with error: {e}")

    # 4. Verify Historical Backtesting
    print("\n[STEP 4/4] Verifying Historical Backtesting...")
    backtest_pass = False
    ticker = "RELIANCE.NS"
    try:
        # Check stock price data in database
        prices_df = get_prices(ticker)
        if prices_df.empty or len(prices_df) < 120:
            print(f"[INFO] Insufficient/no cache for {ticker} (Count: {len(prices_df)}). Syncing data from yfinance...")
            try:
                sync_res = sync_ticker(ticker, period="1y")
                if sync_res['success'] and sync_res['rows_synced'] >= 120:
                    print(f"[INFO] Successfully synced {sync_res['rows_synced']} price rows for {ticker}.")
                    prices_df = get_prices(ticker)
                else:
                    print(f"[WARNING] Sync returned success={sync_res['success']} and rows={sync_res['rows_synced']}.")
            except Exception as sync_err:
                print(f"[WARNING] Sync failed: {sync_err}")
                
        if prices_df.empty or len(prices_df) < 120:
            print(f"[FAIL] {ticker} still has insufficient real cached data after sync attempt.")
            print("       Verification will not create fake market data in the production SQLite database.")
            print("       Add/sync a ticker with at least 120 real daily candles, then rerun this script.")
            raise RuntimeError("Insufficient real historical data for backtest verification.")
            
        print(f"[INFO] Running backtest simulation on {ticker} using {len(prices_df)} price candles...")
        bt_res = run_backtest(ticker)
        
        required_bt_keys = ['total_trades', 'wins', 'losses', 'win_rate', 'avg_win', 'avg_loss', 'net_profit', 'trades_log']
        missing_bt_keys = [k for k in required_bt_keys if k not in bt_res]
        
        if not missing_bt_keys:
            print("[PASS] Historical Backtesting execution succeeded. Summary Statistics:")
            print(f"       - Total Trades: {bt_res['total_trades']}")
            print(f"       - Wins: {bt_res['wins']} | Losses: {bt_res['losses']}")
            print(f"       - Win Rate: {bt_res['win_rate'] * 100:.2f}%")
            print(f"       - Avg Win: INR {bt_res['avg_win']:,.2f} | Avg Loss: INR {bt_res['avg_loss']:,.2f}")
            print(f"       - Net Profit: INR {bt_res['net_profit']:,.2f}")
            print(f"       - Detailed Trade Log Entries: {len(bt_res['trades_log'])}")
            backtest_pass = True
        else:
            print(f"[FAIL] Backtesting completed but output missing keys: {missing_bt_keys}")
    except Exception as e:
        print(f"[FAIL] Backtesting verification failed with error: {e}")

    # Summary Panel
    print("\n" + "=" * 60)
    print("FINAL PHASE 3 VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"DATABASE COMPONENT: {'PASS' if db_pass else 'FAIL'}")
    print(f"CAPITAL SETTINGS:   {'PASS' if capital_pass else 'FAIL'}")
    print(f"REGIME COMPONENT:   {'PASS' if regime_pass else 'FAIL'}")
    print(f"BACKTEST COMPONENT: {'PASS' if backtest_pass else 'FAIL'}")
    print("=" * 60)
    
    if db_pass and capital_pass and regime_pass and backtest_pass:
        print("ALL TESTS PASSED SUCCESSFULLY.")
        sys.exit(0)
    else:
        print("SOME INTEGRATION TESTS FAILED. PLEASE INSPECT LOGS ABOVE.")
        sys.exit(1)

if __name__ == "__main__":
    run_verification()
