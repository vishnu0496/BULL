import pandas as pd
import numpy as np
from src.database import get_prices, get_capital_settings
from src.engine import _add_indicators, _round_price

def run_backtest(ticker: str, start_date: str = None, end_date: str = None) -> dict:
    """
    Run a historical backtest for a stock-only Trade Idea Engine setup.
    
    Parameters:
    - ticker (str): The stock ticker to backtest (e.g. 'RELIANCE.NS').
    - start_date (str): Optional start date filter in YYYY-MM-DD format.
    - end_date (str): Optional end date filter in YYYY-MM-DD format.
    
    Returns:
    - dict: Summary dictionary containing:
        - total_trades (int)
        - wins (int)
        - losses (int)
        - win_rate (float)
        - avg_win (float)
        - avg_loss (float)
        - net_profit (float)
        - trades_log (list of dicts)
    """
    # 1. Read historical daily prices for a given ticker from the database
    df = get_prices(ticker)
    if df.empty or len(df) < 60:
        return {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'net_profit': 0.0,
            'kelly_pct': 0.0,
            'trades_log': []
        }
    
    # Calculate indicators on the entire dataframe to avoid future leakage and speed up calculation.
    # Note: Rolling and EWM calculations look strictly backward, so calculating once is leakage-free.
    df = _add_indicators(df)
    
    # 2. Read capital settings (max_risk_per_trade) from SQLite
    settings = get_capital_settings()
    max_risk_per_trade = float(settings.get('max_risk_per_trade', 100.0))
    
    # Parse start and end date filters if provided
    start_dt = pd.to_datetime(start_date) if start_date else None
    end_dt = pd.to_datetime(end_date) if end_date else None
    
    trades_log = []
    active_trade = None
    
    MIN_AVG_TURNOVER = 10_000_000
    N = len(df)
    
    # Extract raw numpy arrays for extremely fast indexing (3-4x speedup)
    dates = df['date'].dt.strftime('%Y-%m-%d').values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    volumes = df['volume'].values
    
    vol_avg_20 = df['vol_avg_20'].values
    turnover_avg_20 = df['turnover_avg_20'].values
    atr_14 = df['atr_14'].values
    rsi_14 = df['rsi_14'].values
    
    sma_20 = df['sma_20'].values
    sma_50 = df['sma_50'].values
    sma_200 = df['sma_200'].values
    ema_9 = df['ema_9'].values
    ema_21 = df['ema_21'].values
    macd = df['macd'].values
    macd_signal = df['macd_signal'].values
    
    high_20_prev = df['high_20_prev'].values
    high_55_prev = df['high_55_prev'].values
    low_10_prev = df['low_10_prev'].values
    
    t = 59  # Day-by-day simulation starting from index 59
    
    while t < N:
        if active_trade is not None:
            # We have an active position. Track exit triggers on subsequent days
            high_t = highs[t]
            low_t = lows[t]
            
            target_hit = high_t >= active_trade['target_1']
            stop_hit = low_t <= active_trade['stop_loss']
            
            if target_hit and stop_hit:
                # Same-day conflict: assume stop-loss is hit first with 0.1% slippage
                exit_price = _round_price(active_trade['stop_loss'] * 0.999)
                exit_type = 'STOP'
                turnover = active_trade['quantity'] * (active_trade['entry_price'] + exit_price)
                taxes = turnover * 0.0003
                pnl = _round_price((active_trade['quantity'] * (exit_price - active_trade['entry_price'])) - taxes)
                trades_log.append({
                    'entry_date': active_trade['entry_date'],
                    'exit_date': dates[t],
                    'entry_price': active_trade['entry_price'],
                    'exit_price': exit_price,
                    'type': exit_type,
                    'quantity': active_trade['quantity'],
                    'pnl': pnl
                })
                active_trade = None
                continue
                
            elif stop_hit:
                # Exit at stop price minus 0.1% slippage
                exit_price = _round_price(active_trade['stop_loss'] * 0.999)
                exit_type = 'STOP'
                turnover = active_trade['quantity'] * (active_trade['entry_price'] + exit_price)
                taxes = turnover * 0.0003
                pnl = _round_price((active_trade['quantity'] * (exit_price - active_trade['entry_price'])) - taxes)
                trades_log.append({
                    'entry_date': active_trade['entry_date'],
                    'exit_date': dates[t],
                    'entry_price': active_trade['entry_price'],
                    'exit_price': exit_price,
                    'type': exit_type,
                    'quantity': active_trade['quantity'],
                    'pnl': pnl
                })
                active_trade = None
                continue
                
            elif target_hit:
                # Exit at target price minus 0.1% slippage
                exit_price = _round_price(active_trade['target_1'] * 0.999)
                exit_type = 'TARGET'
                turnover = active_trade['quantity'] * (active_trade['entry_price'] + exit_price)
                taxes = turnover * 0.0003
                pnl = _round_price((active_trade['quantity'] * (exit_price - active_trade['entry_price'])) - taxes)
                trades_log.append({
                    'entry_date': active_trade['entry_date'],
                    'exit_date': dates[t],
                    'entry_price': active_trade['entry_price'],
                    'exit_price': exit_price,
                    'type': exit_type,
                    'quantity': active_trade['quantity'],
                    'pnl': pnl
                })
                active_trade = None
                continue
                
            else:
                # No exit triggered on day t, continue holding the position
                t += 1
                
        else:
            # No active position.
            if t >= N - 1:
                t += 1
                continue
                
            # Date check
            date_t = pd.to_datetime(df.iloc[t]['date'])
            if start_dt is not None and date_t < start_dt:
                t += 1
                continue
                
            if end_dt is not None and date_t > end_dt:
                t += 1
                continue
                
            # 3. Calculate indicators and technical levels on data up to day t
            close_val = closes[t]
            atr_val = atr_14[t] if not np.isnan(atr_14[t]) else close_val * 0.02
            atr_pct = (atr_val / close_val) * 100 if close_val else 0
            rsi_val = rsi_14[t]
            volume_ratio = volumes[t] / vol_avg_20[t] if vol_avg_20[t] else 0
            avg_turnover = turnover_avg_20[t] if not np.isnan(turnover_avg_20[t]) else 0

            # Technical logic matching generate_trade_idea in engine.py
            trend_stack = close_val > sma_20[t] > sma_50[t]
            long_trend = trend_stack and (np.isnan(sma_200[t]) or close_val > sma_200[t])
            short_trend = close_val < sma_20[t] < sma_50[t]
            momentum_ok = ema_9[t] > ema_21[t] and macd[t] > macd_signal[t]
            rsi_ok = 52 <= rsi_val <= 68
            rsi_overheated = rsi_val > 72
            volume_ok = volume_ratio >= 1.05
            liquidity_ok = avg_turnover >= MIN_AVG_TURNOVER
            volatility_ok = 0.7 <= atr_pct <= 4.5

            breakout_level = max(highs[t-1], high_20_prev[t])
            extended_breakout_level = high_55_prev[t] if not np.isnan(high_55_prev[t]) else breakout_level
            buffer = max(close_val * 0.001, atr_val * 0.06)
            entry = _round_price(breakout_level + buffer)
            support_stop = min(lows[t-1], low_10_prev[t])
            atr_stop = entry - (1.25 * atr_val)
            stop = _round_price(max(support_stop, atr_stop))
            risk_per_share = _round_price(entry - stop)

            if risk_per_share <= 0:
                stop = _round_price(entry - max(atr_val, entry * 0.01))
                risk_per_share = _round_price(entry - stop)

            suggested_qty = int(max_risk_per_trade // risk_per_share) if risk_per_share > 0 else 0
            max_loss = _round_price(suggested_qty * risk_per_share)

            target_1 = _round_price(entry + (1.5 * risk_per_share))

            # Confidence scoring matching engine.py
            score = 0
            if long_trend:
                score += 25
            if momentum_ok:
                score += 15
            if rsi_ok:
                score += 15
            if close_val >= breakout_level * 0.985:
                score += 15
            if close_val >= extended_breakout_level * 0.985:
                score += 5
            if volume_ok:
                score += 10
            if liquidity_ok:
                score += 8
            if volatility_ok:
                score += 7
            if max_loss > 0 and max_loss <= max_risk_per_trade:
                score += 5

            score = int(min(max(score, 0), 95))
            
            direction = 'BULLISH' if long_trend else ('BEARISH' if short_trend else 'NEUTRAL')
            
            # Risk rules/hard blocks check (excluding stale)
            has_hard_block = (
                (not liquidity_ok) or
                (not volatility_ok) or
                (risk_per_share > max_risk_per_trade) or
                (suggested_qty <= 0) or
                rsi_overheated
            )
            
            # 4. If decision on day t is 'TRADE' (BULLISH trend, passes confidence >= 60 and risk rules)
            is_trade = (direction == 'BULLISH') and (score >= 60) and (not has_hard_block)
            
            if is_trade:
                # Simulate entering a trade on day t+1 if day t+1 high >= entry_trigger
                high_next = highs[t+1]
                open_next = df['open'].values[t+1]
                
                if high_next >= entry:
                    # Gap-Up Protection: If open exceeds trigger by more than 1.5%, skip the trade setup
                    gap_pct = ((open_next - entry) / entry) * 100 if entry > 0 else 0
                    if gap_pct > 1.5:
                        t += 1
                        continue
                    
                    # Apply 0.1% entry slippage (buy price slightly higher)
                    actual_entry = _round_price(entry * 1.001)
                    
                    active_trade = {
                        'entry_date': dates[t+1],
                        'entry_price': actual_entry,
                        'stop_loss': stop,
                        'target_1': target_1,
                        'quantity': suggested_qty
                    }
                    # We move to day t+1. In the next iteration, we will check if it exits on day t+1.
                    t += 1
                else:
                    # No entry trigger hit on day t+1
                    t += 1
            else:
                # No setup or wait decision
                t += 1

    # Calculate summary metrics
    total_trades = len(trades_log)
    wins_list = [tr for tr in trades_log if tr['pnl'] > 0]
    losses_list = [tr for tr in trades_log if tr['pnl'] <= 0]
    
    wins = len(wins_list)
    losses = len(losses_list)
    win_rate = float(wins / total_trades) if total_trades > 0 else 0.0
    
    avg_win = float(np.mean([tr['pnl'] for tr in wins_list])) if wins > 0 else 0.0
    avg_loss = float(np.mean([tr['pnl'] for tr in losses_list])) if losses > 0 else 0.0
    net_profit = float(np.sum([tr['pnl'] for tr in trades_log])) if total_trades > 0 else 0.0
    
    # Calculate Kelly Criterion
    if avg_loss == 0:
        kelly_pct = 0.0
    else:
        r = avg_win / abs(avg_loss)
        if r <= 0:
            kelly_pct = 0.0
        else:
            kelly_pct = win_rate - ((1 - win_rate) / r)
            if kelly_pct < 0:
                kelly_pct = 0.0
                
    return {
        'total_trades': total_trades,
        'wins': wins,
        'losses': losses,
        'win_rate': round(win_rate, 4),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'net_profit': round(net_profit, 2),
        'kelly_pct': round(kelly_pct, 4),
        'trades_log': trades_log
    }

def get_stock_verdict(ticker: str) -> dict:
    """
    Run backtest for a ticker and classify its strategy verdict.
    GOOD: total_trades >= 5 AND win_rate >= 45% AND net_profit > 0
    BAD: total_trades >= 5 AND win_rate < 35% AND net_profit < 0
    WEAK: everything else, including low sample size.
    """
    res = run_backtest(ticker)
    total_trades = res['total_trades']
    win_rate = res['win_rate']
    net_profit = res['net_profit']
    avg_win = res['avg_win']
    avg_loss = res['avg_loss']
    
    expectancy = round(net_profit / total_trades, 2) if total_trades > 0 else 0.0
    
    if total_trades < 5:
        verdict = "WEAK"
        reason = "Not enough historical sample."
    elif win_rate >= 0.45 and net_profit > 0:
        verdict = "GOOD"
        reason = f"Favorable edge. Win rate is {win_rate*100:.1f}% across {total_trades} trades with net positive profit."
    elif win_rate < 0.35 and net_profit < 0:
        verdict = "BAD"
        reason = f"Unfavorable edge. Win rate is {win_rate*100:.1f}% across {total_trades} trades with net negative loss."
    else:
        verdict = "WEAK"
        reason = f"Sub-optimal edge. Win rate is {win_rate*100:.1f}% across {total_trades} trades."

    kelly_pct = res.get('kelly_pct', 0.0)
    
    return {
        'ticker': ticker,
        'verdict': verdict,
        'total_trades': total_trades,
        'win_rate': round(win_rate, 4),
        'net_profit': net_profit,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'expectancy': expectancy,
        'kelly_pct': kelly_pct,
        'reason': reason
    }

def get_all_stock_verdicts(tickers: list) -> list:
    """
    Generate verdicts for all stock tickers in the watchlist, excluding indices.
    """
    index_symbols = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
    verdicts = []
    for ticker in tickers:
        if ticker.upper() in index_symbols:
            continue
        try:
            verdicts.append(get_stock_verdict(ticker))
        except Exception as e:
            verdicts.append({
                'ticker': ticker,
                'verdict': 'WEAK',
                'total_trades': 0,
                'win_rate': 0.0,
                'net_profit': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'expectancy': 0.0,
                'kelly_pct': 0.0,
                'reason': f"Error running backtest: {str(e)}"
            })
            
    verdict_priority = {'GOOD': 1, 'WEAK': 2, 'BAD': 3}
    verdicts.sort(key=lambda x: (
        verdict_priority.get(x['verdict'], 4),
        -x['net_profit'],
        -x['win_rate'],
        -x['total_trades']
    ))
    return verdicts

