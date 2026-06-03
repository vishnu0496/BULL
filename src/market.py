import numpy as np
import pandas as pd
from src.database import get_prices, get_watchlist_tickers

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder-style smoothed averages."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    prev_close = df['close'].shift(1)
    true_range = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

def analyze_single_ticker(df: pd.DataFrame, name: str = "^NSEI") -> dict:
    """Analyze trend and volatility for a single index ticker."""
    df = df.sort_values('date').copy()
    
    # Coerce to numeric to prevent errors
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['high'] = pd.to_numeric(df['high'], errors='coerce')
    df['low'] = pd.to_numeric(df['low'], errors='coerce')
    df = df.dropna(subset=['close', 'high', 'low'])
    
    if len(df) < 50:
        return {
            'market_bias': 'NEUTRAL',
            'trend_score': 50,
            'volatility_score': 50,
            'reasons': [f"Insufficient data for index {name}. Needed at least 50 rows."]
        }
        
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['rsi_14'] = calculate_rsi(df['close'])
    df['atr_14'] = calculate_atr(df)
    
    latest = df.iloc[-1]
    close_val = float(latest['close'])
    sma20_val = float(latest['sma_20'])
    sma50_val = float(latest['sma_50'])
    rsi_val = float(latest['rsi_14'])
    atr_val = float(latest['atr_14']) if not pd.isna(latest['atr_14']) else 0.0
    
    ret_5d = 0.0
    ret_20d = 0.0
    if len(df) >= 6:
        ret_5d = (close_val / float(df['close'].iloc[-6])) - 1.0
    if len(df) >= 21:
        ret_20d = (close_val / float(df['close'].iloc[-21])) - 1.0
        
    atr_pct = (atr_val / close_val) * 100 if close_val > 0 else 0.0
    
    # 1. SMA Trend Alignment (40 points)
    sma_score = 0
    if close_val > sma20_val:
        sma_score += 15
    if close_val > sma50_val:
        sma_score += 15
    if sma20_val > sma50_val:
        sma_score += 10
        
    # 2. RSI strength (20 points)
    rsi_score = 0
    if rsi_val >= 60:
        rsi_score = 20
    elif rsi_val >= 50:
        rsi_score = 15
    elif rsi_val >= 40:
        rsi_score = 10
    else:
        rsi_score = 0
        
    # 3. Returns (40 points)
    ret5_score = 0
    if ret_5d > 0.02:
        ret5_score = 15
    elif ret_5d > 0.005:
        ret5_score = 12
    elif ret_5d >= -0.005:
        ret5_score = 8
    elif ret_5d >= -0.02:
        ret5_score = 3
    else:
        ret5_score = 0
        
    ret20_score = 0
    if ret_20d > 0.05:
        ret20_score = 25
    elif ret_20d > 0.015:
        ret20_score = 20
    elif ret_20d >= -0.015:
        ret20_score = 12
    elif ret_20d >= -0.05:
        ret20_score = 5
    else:
        ret20_score = 0
        
    trend_score = sma_score + rsi_score + ret5_score + ret20_score
    trend_score = int(min(100, max(0, trend_score)))
    
    # Volatility score (0 to 100)
    # ATR % of 1.0% is moderate (50). 2.0% or above is high (100).
    volatility_score = int(min(100, max(0, atr_pct * 50)))
    
    if trend_score >= 65:
        market_bias = 'BULLISH'
    elif trend_score <= 35:
        market_bias = 'BEARISH'
    else:
        market_bias = 'NEUTRAL'
        
    reasons = [
        f"Analyzed Nifty index/symbol: {name} (Close: {close_val:,.2f})."
    ]
    
    if close_val > sma20_val and sma20_val > sma50_val:
        reasons.append(f"Index is in a healthy uptrend (Close > SMA20 > SMA50).")
    elif close_val < sma20_val and sma20_val < sma50_val:
        reasons.append(f"Index is in a strong downtrend (Close < SMA20 < SMA50).")
    else:
        reasons.append(f"Index trend is mixed. Close is {'above' if close_val > sma20_val else 'below'} SMA20 and {'above' if close_val > sma50_val else 'below'} SMA50.")
        
    reasons.append(f"RSI14 is at {rsi_val:.1f}, indicating {'bullish' if rsi_val >= 55 else 'bearish' if rsi_val <= 45 else 'neutral'} momentum.")
    reasons.append(f"Recent returns: 5-day return is {ret_5d*100:+.2f}%, 20-day return is {ret_20d*100:+.2f}%.")
    
    if volatility_score > 70:
        reasons.append(f"Volatility is high (ATR14 is {atr_pct:.2f}% of price, Volatility Score: {volatility_score}). Expect wide price swings.")
    elif volatility_score < 30:
        reasons.append(f"Volatility is low (ATR14 is {atr_pct:.2f}% of price, Volatility Score: {volatility_score}). Expect consolidation.")
    else:
        reasons.append(f"Volatility is moderate (ATR14 is {atr_pct:.2f}% of price, Volatility Score: {volatility_score}).")
        
    return {
        'market_bias': market_bias,
        'trend_score': trend_score,
        'volatility_score': volatility_score,
        'reasons': reasons
    }

def analyze_watchlist_aggregate(tickers: list) -> dict:
    """Analyze aggregate trend and volatility across all watchlist stocks."""
    valid_stocks_count = 0
    sum_above_sma20 = 0
    sum_above_sma50 = 0
    sum_sma20_above_sma50 = 0
    sum_rsi = 0.0
    sum_atr_pct = 0.0
    sum_ret_5d = 0.0
    sum_ret_20d = 0.0
    
    for ticker in tickers:
        df = get_prices(ticker)
        if df.empty or len(df) < 50:
            continue
            
        df = df.sort_values('date').copy()
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df['high'] = pd.to_numeric(df['high'], errors='coerce')
        df['low'] = pd.to_numeric(df['low'], errors='coerce')
        df = df.dropna(subset=['close', 'high', 'low'])
        
        if len(df) < 50:
            continue
            
        df['sma_20'] = df['close'].rolling(20).mean()
        df['sma_50'] = df['close'].rolling(50).mean()
        df['rsi_14'] = calculate_rsi(df['close'])
        df['atr_14'] = calculate_atr(df)
        
        latest = df.iloc[-1]
        close_val = float(latest['close'])
        sma20_val = float(latest['sma_20'])
        sma50_val = float(latest['sma_50'])
        rsi_val = float(latest['rsi_14'])
        atr_val = float(latest['atr_14'])
        
        ret_5d = 0.0
        ret_20d = 0.0
        if len(df) >= 6:
            ret_5d = (close_val / float(df['close'].iloc[-6])) - 1.0
        if len(df) >= 21:
            ret_20d = (close_val / float(df['close'].iloc[-21])) - 1.0
            
        atr_pct = (atr_val / close_val) * 100 if close_val > 0 else 0.0
        
        valid_stocks_count += 1
        
        if close_val > sma20_val:
            sum_above_sma20 += 1
        if close_val > sma50_val:
            sum_above_sma50 += 1
        if sma20_val > sma50_val:
            sum_sma20_above_sma50 += 1
            
        sum_rsi += rsi_val
        sum_atr_pct += atr_pct
        sum_ret_5d += ret_5d
        sum_ret_20d += ret_20d
        
    if valid_stocks_count == 0:
        return {
            'market_bias': 'NEUTRAL',
            'trend_score': 50,
            'volatility_score': 50,
            'reasons': ["No watchlist stocks with sufficient data (min 50 days) found to aggregate."]
        }
        
    pct_above_sma20 = sum_above_sma20 / valid_stocks_count
    pct_above_sma50 = sum_above_sma50 / valid_stocks_count
    pct_sma20_above_sma50 = sum_sma20_above_sma50 / valid_stocks_count
    avg_rsi = sum_rsi / valid_stocks_count
    avg_atr_pct = sum_atr_pct / valid_stocks_count
    avg_ret_5d = sum_ret_5d / valid_stocks_count
    avg_ret_20d = sum_ret_20d / valid_stocks_count
    
    # 1. SMA Trend Alignment (40 points)
    sma_score = (pct_above_sma20 * 15) + (pct_above_sma50 * 15) + (pct_sma20_above_sma50 * 10)
    
    # 2. RSI strength (20 points)
    rsi_score = 0
    if avg_rsi >= 60:
        rsi_score = 20
    elif avg_rsi >= 50:
        rsi_score = 15
    elif avg_rsi >= 40:
        rsi_score = 10
    else:
        rsi_score = 0
        
    # 3. Returns (40 points)
    ret5_score = 0
    if avg_ret_5d > 0.02:
        ret5_score = 15
    elif avg_ret_5d > 0.005:
        ret5_score = 12
    elif avg_ret_5d >= -0.005:
        ret5_score = 8
    elif avg_ret_5d >= -0.02:
        ret5_score = 3
    else:
        ret5_score = 0
        
    ret20_score = 0
    if avg_ret_20d > 0.05:
        ret20_score = 25
    elif avg_ret_20d > 0.015:
        ret20_score = 20
    elif avg_ret_20d >= -0.015:
        ret20_score = 12
    elif avg_ret_20d >= -0.05:
        ret20_score = 5
    else:
        ret20_score = 0
        
    trend_score = int(min(100, max(0, sma_score + rsi_score + ret5_score + ret20_score)))
    
    # Volatility score (0 to 100)
    # Average individual stock ATR % of 2.5% is moderate (50). 5.0% or above is high (100).
    volatility_score = int(min(100, max(0, avg_atr_pct * 20)))
    
    if trend_score >= 65:
        market_bias = 'BULLISH'
    elif trend_score <= 35:
        market_bias = 'BEARISH'
    else:
        market_bias = 'NEUTRAL'
        
    reasons = [
        f"Analyzed aggregate breadth of {valid_stocks_count} watchlist stocks (index data missing/insufficient)."
    ]
    reasons.append(
        f"Market Breadth: {pct_above_sma20*100:.1f}% above SMA20; {pct_above_sma50*100:.1f}% above SMA50."
    )
    reasons.append(
        f"Average RSI14 is {avg_rsi:.1f}, indicating {'bullish' if avg_rsi >= 55 else 'bearish' if avg_rsi <= 45 else 'neutral'} momentum."
    )
    reasons.append(
        f"Average recent returns: 5-day return is {avg_ret_5d*100:+.2f}%, 20-day return is {avg_ret_20d*100:+.2f}%."
    )
    
    if volatility_score > 70:
        reasons.append(f"Aggregate volatility is high (avg ATR % is {avg_atr_pct:.2f}%, Volatility Score: {volatility_score}). Expect wide swings.")
    elif volatility_score < 30:
        reasons.append(f"Aggregate volatility is low (avg ATR % is {avg_atr_pct:.2f}%, Volatility Score: {volatility_score}). Expect consolidation.")
    else:
        reasons.append(f"Aggregate volatility is moderate (avg ATR % is {avg_atr_pct:.2f}%, Volatility Score: {volatility_score}).")
        
    return {
        'market_bias': market_bias,
        'trend_score': trend_score,
        'volatility_score': volatility_score,
        'reasons': reasons
    }

def get_market_regime() -> dict:
    """Analyze the overall market bias, trend, and volatility.
    
    Checks for index symbols (^NSEI, NIFTY, ^BSESN, SENSEX) in the database first.
    If no index data exists or contains fewer than 50 days of records, falls back
    to checking watchlist stock averages.
    """
    # 1. Attempt index symbols
    for idx_symbol in ["^NSEI", "NIFTY", "^BSESN", "SENSEX"]:
        df = get_prices(idx_symbol)
        if not df.empty and len(df) >= 50:
            return analyze_single_ticker(df, idx_symbol)
            
    # 2. Fallback to watchlist tickers
    watchlist_tickers = get_watchlist_tickers()
    if watchlist_tickers:
        res = analyze_watchlist_aggregate(watchlist_tickers)
        if not res['reasons'][0].startswith("No watchlist stocks"):
            return res
            
    # 3. No data available at all
    return {
        'market_bias': 'NEUTRAL',
        'trend_score': 50,
        'volatility_score': 50,
        'reasons': [
            "No index or watchlist data with sufficient history (min 50 days) available in database."
        ]
    }
