import pytest
import numpy as np
import pandas as pd
from src.engine import calculate_rsi, calculate_vp_poc, calculate_order_blocks

def test_calculate_rsi():
    # Test strict mathematical calculation of RSI
    # Create 14 days of constant price to start, then a gain
    prices = pd.Series([100.0] * 14 + [102.0, 104.0, 103.0])
    
    rsi = calculate_rsi(prices, period=14)
    assert len(rsi) == len(prices)
    
    # RSI on constant price should be 50 (or NaN filled to 50 based on our implementation)
    assert rsi.iloc[13] == 50.0
    
    # Let's manually calculate for day 15 (index 14)
    # price = 102.0, change = 2.0
    # Before this, avg_gain and avg_loss were 0.
    # Actually ewma with adjust=False starts from the first observation.
    # To test strictly without complex ewma math, let's test limits:
    increasing_prices = pd.Series(np.linspace(10, 100, 20))
    rsi_inc = calculate_rsi(increasing_prices, period=14)
    # Since prices are strictly increasing, loss is 0, so rs is infinity, RSI should approach 100
    assert rsi_inc.iloc[-1] == 100.0

    decreasing_prices = pd.Series(np.linspace(100, 10, 20))
    rsi_dec = calculate_rsi(decreasing_prices, period=14)
    # Since prices are strictly decreasing, gain is 0, so rs is 0, RSI should be 0
    assert rsi_dec.iloc[-1] == 0.0

def test_calculate_vp_poc():
    data = {
        'open': [10.0] * 30,
        'high': [15.0] * 30,
        'low': [5.0] * 30,
        'close': [10.0] * 30,
        'volume': [100.0] * 30
    }
    df = pd.DataFrame(data)
    
    # Let's add a spike in volume at a specific price
    df.loc[25, 'volume'] = 10000.0
    df.loc[25, 'high'] = 12.0
    df.loc[25, 'low'] = 11.0
    df.loc[25, 'close'] = 11.5
    
    vp_poc = calculate_vp_poc(df, period=20, bins=10)
    
    # Output series length should match
    assert len(vp_poc) == len(df)
    
    # Ensure it's not NaN at the end
    assert not pd.isna(vp_poc.iloc[-1])
    # The POC should shift towards the spike volume's price
    assert 11 <= vp_poc.iloc[-1] <= 12

def test_calculate_order_blocks():
    # df with required columns
    data = {
        'open': [100.0, 105.0, 102.0, 108.0],
        'high': [106.0, 107.0, 106.0, 115.0],
        'low': [99.0, 103.0, 100.0, 107.0],
        'close': [105.0, 104.0, 101.0, 114.0],
        'volume': [1000, 1000, 1000, 5000],
        'vol_avg_20': [1000, 1000, 1000, 1000]
    }
    df = pd.DataFrame(data)
    # at index 3:
    # close (114) > open (108) => True
    # volume (5000) > vol_avg_20 * 1.5 => 5000 > 1500 => True
    # close (114) > prev_high (106) => True
    # open (108) <= prev_close (101) => False
    
    # Wait, let's adjust index 3 to trigger the OB condition:
    # condition: row['close'] > prev['high'] and row['open'] <= prev['close']
    df.loc[3, 'open'] = 100.0 # <= 101
    
    ob = calculate_order_blocks(df)
    
    assert len(ob) == len(df)
    # ob_level should be prev['low'] = 100.0
    assert ob.iloc[3] == 100.0
