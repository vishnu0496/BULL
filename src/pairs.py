import pandas as pd
import numpy as np
from src.database import get_prices

def find_correlated_pairs():
    """
    Build a Statistical Arbitrage (Pairs Trading) engine.
    Finds correlated pairs and generates trading signals based on Z-Score.
    """
    # 2. Hardcode a few known highly correlated Indian pairs
    pairs = [
        ["HDFCBANK.NS", "ICICIBANK.NS"],
        ["TCS.NS", "INFY.NS"],
        ["RELIANCE.NS", "ONGC.NS"]
    ]
    
    active_pair_trades = []
    window = 20

    for ticker_A, ticker_B in pairs:
        # 1. Load price data
        df_A = get_prices(ticker_A)
        df_B = get_prices(ticker_B)
        
        if df_A.empty or df_B.empty:
            continue
            
        # Merge on date to ensure alignment
        df = pd.merge(df_A[['date', 'close']], df_B[['date', 'close']], on='date', suffixes=('_A', '_B'))
        df = df.dropna()
        
        if len(df) < window:
            continue
            
        price_A = df['close_A']
        price_B = df['close_B']
        
        # 3. Calculate the spread: spread = price_A - (hedge_ratio * price_B)
        # Using a simple price ratio as the hedge ratio (mean of A / mean of B)
        hedge_ratio = price_A.mean() / price_B.mean()
        spread = price_A - (hedge_ratio * price_B)
        
        # 4. Calculate the rolling Z-Score of the spread
        rolling_mean = spread.rolling(window=window).mean()
        rolling_std = spread.rolling(window=window).std()
        
        z_scores = (spread - rolling_mean) / rolling_std
        
        # Get the current (latest) z-score
        current_z_score = z_scores.iloc[-1]
        
        if pd.isna(current_z_score):
            continue
            
        # 5. Generate signals
        signal = "NEUTRAL"
        suggested_action = "WAIT"
        
        if current_z_score > 2.0:
            signal = f"SHORT {ticker_A}, BUY {ticker_B}"
            suggested_action = "SHORT_SPREAD"
        elif current_z_score < -2.0:
            signal = f"BUY {ticker_A}, SHORT {ticker_B}"
            suggested_action = "BUY_SPREAD"
            
        # 6. Return a list of active pair trade dictionaries
        if suggested_action != "WAIT":
            active_pair_trades.append({
                "tickers": [ticker_A, ticker_B],
                "z_score": float(current_z_score),
                "hedge_ratio": float(hedge_ratio),
                "signal": signal,
                "suggested_action": suggested_action
            })
            
    return active_pair_trades
