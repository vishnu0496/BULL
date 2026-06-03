import pytest
import pandas as pd
from unittest.mock import patch
from src.backtest import run_backtest
from src.engine import _round_price

@patch('src.backtest.get_prices')
@patch('src.backtest.get_capital_settings')
def test_slippage_and_taxes_in_backtest(mock_settings, mock_prices):
    # Mock settings
    mock_settings.return_value = {'max_risk_per_trade': 1000.0}
    
    # Create 60 days of data to pass MIN_HISTORY_ROWS / t=59 check
    # Let's craft the 60th and 61st and 62nd days to trigger a trade
    dates = pd.date_range(start='2024-01-01', periods=65)
    
    # Default dull OHLCV
    data = {
        'date': dates,
        'open': [100.0] * 65,
        'high': [101.0] * 65,
        'low': [99.0] * 65,
        'close': [100.0] * 65,
        'volume': [200000] * 65
    }
    df = pd.DataFrame(data)
    
    # We want a setup at t=59 (index 59)
    # Long trend requires close > sma20 > sma50 > sma200
    # Let's just set the values in a way that triggers long trend and trade
    # But instead of relying on all indicators perfectly, it's easier to mock _add_indicators
    pass

# We will patch _add_indicators to bypass the engine logic and force a trade setup
@patch('src.backtest._add_indicators')
@patch('src.backtest.get_prices')
@patch('src.backtest.get_capital_settings')
def test_tax_and_slippage_math(mock_settings, mock_prices, mock_add_indicators):
    mock_settings.return_value = {'max_risk_per_trade': 1000.0}
    
    dates = pd.date_range(start='2024-01-01', periods=65)
    df = pd.DataFrame({
        'date': dates,
        'open': [100.0] * 65,
        'high': [101.0] * 65,
        'low': [99.0] * 65,
        'close': [100.0] * 65,
        'volume': [200000] * 65
    })
    
    # Now we populate the columns required by backtest's indicator checks
    df['sma_20'] = 200.0
    df['sma_50'] = 80.0
    df['sma_200'] = 70.0
    df['ema_9'] = 95.0
    df['ema_21'] = 90.0
    df['macd'] = 2.0
    df['macd_signal'] = 1.0
    df['rsi_14'] = 10.0
    df['vol_avg_20'] = 100000.0
    df['turnover_avg_20'] = 20000000.0
    df['atr_14'] = 2.0
    df['high_20_prev'] = 100.0
    df['high_55_prev'] = 100.0
    df['low_10_prev'] = 98.0
    
    # At t=59, it evaluates. Make this specific index bullish to trigger trade entry on day 60
    df.loc[59, 'sma_20'] = 90.0
    df.loc[59, 'rsi_14'] = 60.0
    
    # At t=59, it evaluates. breakout_level will be max(99.0, 100.0) = 100.0
    # buffer = max(100*0.001, 2.0*0.06) = max(0.1, 0.12) = 0.12
    # entry = 100.12
    # On day 60 (t+1), we need high >= entry to trigger.
    df.loc[60, 'high'] = 105.0
    df.loc[60, 'open'] = 100.0 # open gap <= 1.5% of entry
    
    # Then day 61, let's hit target_1.
    # We need to know target_1.
    # risk_per_share = entry - stop = 100.12 - 97.5 = 2.62
    # target_1 = 100.12 + 1.5 * 2.62 = 104.05
    df.loc[61, 'high'] = 110.0
    
    mock_add_indicators.return_value = df
    mock_prices.return_value = df
    
    res = run_backtest('TEST')
    
    assert res['total_trades'] == 1
    trade = res['trades_log'][0]
    
    # Entry Slippage: 101.12 * 1.001 = 101.22
    expected_entry = _round_price(101.12 * 1.001)
    assert trade['entry_price'] == expected_entry
    
    # Exit Slippage (Target): 104.87 * 0.999 = 104.77
    expected_exit = _round_price(104.87 * 0.999)
    assert trade['exit_price'] == expected_exit
    
    # Quantity: risk_per_share = 2.50. max_risk = 1000. qty = 1000 // 2.50 = 400
    expected_qty = int(1000.0 // 2.50)
    assert trade['quantity'] == expected_qty
    
    # Taxes = turnover * 0.0003
    turnover = expected_qty * (expected_entry + expected_exit)
    taxes = turnover * 0.0003
    expected_pnl = _round_price((expected_qty * (expected_exit - expected_entry)) - taxes)
    assert trade['pnl'] == expected_pnl

