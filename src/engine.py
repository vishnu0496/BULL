from datetime import datetime

import numpy as np
import pandas as pd

from src.database import get_capital_settings, get_prices, get_watchlist_tickers


MIN_HISTORY_ROWS = 120
MAX_DATA_AGE_DAYS = 4
MIN_AVG_TURNOVER = 10_000_000

_ML_MODEL = None


def _technical_probability_proxy(
    *,
    long_trend: bool,
    momentum_ok: bool,
    rsi_ok: bool,
    volume_ok: bool,
    liquidity_ok: bool,
    volatility_ok: bool,
    close_val: float,
    entry: float,
) -> float:
    """Fallback confidence proxy used when generated ML artifacts are unavailable."""
    score = 0.35
    score += 0.12 if long_trend else 0.0
    score += 0.12 if momentum_ok else 0.0
    score += 0.10 if rsi_ok else 0.0
    score += 0.08 if volume_ok else 0.0
    score += 0.07 if liquidity_ok else 0.0
    score += 0.06 if volatility_ok else 0.0

    if entry > 0:
        distance_to_trigger = max((entry - close_val) / entry, 0.0)
        if distance_to_trigger <= 0.01:
            score += 0.05
        elif distance_to_trigger <= 0.025:
            score += 0.03

    return round(float(min(max(score, 0.05), 0.72)), 4)


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder-style smoothed averages."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = np.where(avg_loss == 0, np.where(avg_gain == 0, 50.0, 100.0), rsi)
    return pd.Series(rsi, index=prices.index).fillna(50)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    prev_close = df['close'].shift(1)
    true_range = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def calculate_vp_poc(df: pd.DataFrame, period: int = 20, bins: int = 10) -> pd.Series:
    """Calculate Volume Profile Point of Control (POC) using vectorized operations."""
    poc_series = pd.Series(index=df.index, dtype=float)
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    volume = df['volume'].values
    typ = (high + low + close) / 3.0
    
    for i in range(period, len(df) + 1):
        window_low = low[i - period:i]
        window_high = high[i - period:i]
        min_p = window_low.min()
        max_p = window_high.max()
        if min_p == max_p:
            poc_series.iloc[i - 1] = min_p
            continue
            
        price_bins = np.linspace(min_p, max_p, bins + 1)
        window_typ = typ[i - period:i]
        window_vol = volume[i - period:i]
        
        idxs = np.digitize(window_typ, price_bins) - 1
        idxs = np.clip(idxs, 0, bins - 1)
        
        volumes = np.bincount(idxs, weights=window_vol, minlength=bins)
        max_vol_bin = np.argmax(volumes)
        
        poc_series.iloc[i - 1] = (price_bins[max_vol_bin] + price_bins[max_vol_bin + 1]) / 2.0
        
    return poc_series.ffill()


def calculate_order_blocks(df: pd.DataFrame) -> pd.Series:
    """Identify bullish order block levels using vectorized numpy arrays."""
    close = df['close'].values
    open_val = df['open'].values
    high = df['high'].values
    low = df['low'].values
    volume = df['volume'].values
    vol_avg = df['vol_avg_20'].values
    
    ob_arr = np.empty(len(df))
    ob_arr[:] = np.nan
    
    # Precompute condition mask for elements 1 to len(df)-1
    cond = (close[1:] > open_val[1:]) & \
           (volume[1:] > vol_avg[1:] * 1.5) & \
           (close[1:] > high[:-1]) & \
           (open_val[1:] <= close[:-1])
           
    ob_level = np.nan
    for i in range(1, len(df)):
        if cond[i-1]:
            ob_level = low[i-1]
        ob_arr[i] = ob_level
        
    return pd.Series(ob_arr, index=df.index).ffill()


def _empty_idea(ticker: str) -> dict:
    return {
        'ticker': ticker,
        'direction': 'NEUTRAL',
        'setup_type': 'NO_SETUP',
        'entry_trigger': 0.0,
        'stop_loss': 0.0,
        'target_1': 0.0,
        'target_2': 0.0,
        'risk_per_share': 0.0,
        'suggested_quantity': 0,
        'max_loss': 0.0,
        'confidence_score': 0,
        'ml_probability': 0.0,
        'kelly_pct': 0.0,
        'hedge_cost': 0.0,
        'hedge_strike': 0.0,
        'reasons': [],
        'decision': 'WAIT',
    }


def _add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.sort_values('date').copy()
    out['sma_20'] = out['close'].rolling(20).mean()
    out['sma_50'] = out['close'].rolling(50).mean()
    out['sma_200'] = out['close'].rolling(200).mean()
    out['ema_9'] = out['close'].ewm(span=9, adjust=False).mean()
    out['ema_21'] = out['close'].ewm(span=21, adjust=False).mean()
    out['rsi_14'] = calculate_rsi(out['close'])
    out['atr_14'] = calculate_atr(out)
    ema_12 = out['close'].ewm(span=12, adjust=False).mean()
    ema_26 = out['close'].ewm(span=26, adjust=False).mean()
    out['macd'] = ema_12 - ema_26
    out['macd_signal'] = out['macd'].ewm(span=9, adjust=False).mean()
    out['vol_avg_20'] = out['volume'].rolling(20).mean()
    out['vp_poc_20'] = calculate_vp_poc(out)
    out['order_block'] = calculate_order_blocks(out)
    out['high_20_prev'] = out['high'].shift(1).rolling(20).max()
    out['high_55_prev'] = out['high'].shift(1).rolling(55).max()
    out['low_10_prev'] = out['low'].shift(1).rolling(10).min()
    out['low_20_prev'] = out['low'].shift(1).rolling(20).min()
    out['turnover_avg_20'] = (out['volume'] * out['close']).rolling(20).mean()
    return out


def _is_data_stale(latest_date) -> tuple[bool, str]:
    if pd.isna(latest_date):
        return True, "No latest date found in stored prices."
    latest_day = pd.to_datetime(latest_date).date()
    today = datetime.now().date()
    age = (today - latest_day).days
    if age > MAX_DATA_AGE_DAYS:
        return True, f"Stored data is stale. Latest candle is {latest_day}, which is {age} calendar days old."
    return False, f"Latest stored candle is {latest_day}."


def _round_price(value: float) -> float:
    return round(float(value), 2)


def check_event_blackout(ticker: str) -> tuple[bool, str]:
    """
    Check if a stock has an upcoming earnings report (within 3 days) or ex-dividend date (within 2 days).
    Uses caching to avoid slowing down technical generation.
    Returns:
        tuple[bool, str]: (is_blocked, reason)
    """
    ticker = ticker.upper()
    
    # Check database cache first (cache for 7 days)
    from src.database import get_event_calendar, save_event_calendar
    cached = get_event_calendar(ticker, max_age_days=7)
    
    earnings_str = ""
    dividend_str = ""
    
    if cached:
        earnings_str = cached.get("earnings_date", "")
        dividend_str = cached.get("dividend_date", "")
    else:
        # Fetch fresh from yfinance
        try:
            import yfinance as yf
            t_obj = yf.Ticker(ticker)
            cal = t_obj.calendar
            
            if cal:
                e_date = cal.get('Earnings Date')
                if e_date and isinstance(e_date, list) and len(e_date) > 0:
                    earnings_str = str(e_date[0])
                elif e_date:
                    earnings_str = str(e_date)
                    
                d_date = cal.get('Ex-Dividend Date')
                if d_date:
                    dividend_str = str(d_date)
                    
                # Cache dates
                save_event_calendar(ticker, earnings_str, dividend_str)
        except Exception:
            pass
            
    # Now check blackout conditions
    from datetime import datetime
    today = datetime.now().date()
    
    if earnings_str:
        try:
            e_day = datetime.strptime(earnings_str, "%Y-%m-%d").date()
            delta_days = (e_day - today).days
            # Block trade if earnings report is upcoming within next 3 days, or was today/yesterday (volatile window)
            if -1 <= delta_days <= 3:
                return True, f"Earnings release upcoming/recent: {earnings_str} ({delta_days} days away)."
        except Exception:
            pass
            
    if dividend_str:
        try:
            d_day = datetime.strptime(dividend_str, "%Y-%m-%d").date()
            delta_days = (d_day - today).days
            # Block trade if ex-dividend date is within next 2 days or today (avoid dividend drop risk)
            if 0 <= delta_days <= 2:
                return True, f"Ex-Dividend date is near: {dividend_str} ({delta_days} days away)."
        except Exception:
            pass
            
    return False, ""


def generate_trade_idea(ticker: str) -> dict:
    """Generate a stricter long-only stock trade idea.

    This engine uses only locally stored daily candles. It creates a conditional
    breakout plan, not a guaranteed trade instruction.
    """
    ticker = ticker.upper()
    settings = get_capital_settings()
    max_risk = float(settings.get('max_risk_per_trade', 100.0))
    idea = _empty_idea(ticker)

    df = get_prices(ticker)
    if len(df) < MIN_HISTORY_ROWS:
        idea['decision'] = 'REJECT'
        idea['reasons'] = [
            f"Only {len(df)} daily candles found. Need at least {MIN_HISTORY_ROWS} candles for a serious trend/risk check."
        ]
        return idea

    raw_df = df.copy()
    df = _add_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    stale, freshness_reason = _is_data_stale(latest['date'])

    close_val = float(latest['close'])
    atr_val = float(latest['atr_14']) if not pd.isna(latest['atr_14']) else close_val * 0.02
    atr_pct = (atr_val / close_val) * 100 if close_val else 0
    rsi_val = float(latest['rsi_14'])
    volume_ratio = float(latest['volume'] / latest['vol_avg_20']) if latest['vol_avg_20'] else 0
    avg_turnover = float(latest['turnover_avg_20']) if not pd.isna(latest['turnover_avg_20']) else 0

    trend_stack = close_val > latest['sma_20'] > latest['sma_50']
    long_trend = trend_stack and (pd.isna(latest['sma_200']) or close_val > latest['sma_200'])
    short_trend = close_val < latest['sma_20'] < latest['sma_50']
    momentum_ok = latest['ema_9'] > latest['ema_21'] and latest['macd'] > latest['macd_signal']
    rsi_ok = 52 <= rsi_val <= 68
    rsi_overheated = rsi_val > 72
    volume_ok = volume_ratio >= 1.05
    liquidity_ok = avg_turnover >= MIN_AVG_TURNOVER
    volatility_ok = 0.7 <= atr_pct <= 4.5

    breakout_level = max(float(prev['high']), float(latest['high_20_prev']))
    extended_breakout_level = float(latest['high_55_prev']) if not pd.isna(latest['high_55_prev']) else breakout_level
    buffer = max(close_val * 0.001, atr_val * 0.06)
    entry = _round_price(breakout_level + buffer)
    support_stop = min(float(prev['low']), float(latest['low_10_prev']))
    atr_stop = entry - (1.25 * atr_val)
    stop = _round_price(max(support_stop, atr_stop))
    risk_per_share = _round_price(entry - stop)

    if risk_per_share <= 0:
        stop = _round_price(entry - max(atr_val, entry * 0.01))
        risk_per_share = _round_price(entry - stop)

    suggested_qty = int(max_risk // risk_per_share) if risk_per_share > 0 else 0
    max_loss = _round_price(suggested_qty * risk_per_share)
    target_1 = _round_price(entry + (1.5 * risk_per_share))
    target_2 = _round_price(entry + (2.5 * risk_per_share))

    # ML Model Prediction
    xgb_probability = None
    lstm_probability = None
    ml_probability = 0.0
    lstm_status_str = ""

    # Try XGBoost prediction first. If generated model artifacts are missing,
    # keep the engine usable with a conservative technical proxy.
    try:
        import joblib
        from src.ml_model import engineer_features
        global _ML_MODEL
        if _ML_MODEL is None:
            _ML_MODEL = joblib.load('models/xgb_model.joblib')
        
        features_df = engineer_features(raw_df)
        model_features = _ML_MODEL.feature_names_in_
        features_df = features_df[model_features]
        features_df = features_df.dropna()
        
        if features_df.empty:
            raise ValueError("No valid features after dropna.")
            
        latest_features = features_df.iloc[-1:]
        xgb_probability = float(_ML_MODEL.predict_proba(latest_features)[0][1])
    except Exception as e:
        ml_probability = _technical_probability_proxy(
            long_trend=long_trend,
            momentum_ok=momentum_ok,
            rsi_ok=rsi_ok,
            volume_ok=volume_ok,
            liquidity_ok=liquidity_ok,
            volatility_ok=volatility_ok,
            close_val=close_val,
            entry=entry,
        )
        lstm_status_str = f" (technical fallback; ML unavailable: {e})"

    # Try LSTM prediction next only when XGBoost succeeded. Without the XGB
    # artifact, the conservative technical proxy above is the intended fallback.
    if xgb_probability is not None:
        try:
            from src.deep_learning import predict_lstm_probability
            lstm_probability = predict_lstm_probability(raw_df)
            lstm_status_str = f" (XGB: {xgb_probability:.2%}, LSTM: {lstm_probability:.2%})"
        except Exception as e:
            lstm_status_str = f" (XGB-only fallback; LSTM error: {e})"

    # Blend probabilities
    if xgb_probability is not None and lstm_probability is not None:
        ml_probability = 0.5 * xgb_probability + 0.5 * lstm_probability
    elif xgb_probability is not None:
        ml_probability = xgb_probability


    if short_trend:
        idea['direction'] = 'BEARISH'
        idea['setup_type'] = 'DOWNTREND_AVOID_LONG'
        idea['entry_trigger'] = _round_price(close_val)
        idea['stop_loss'] = _round_price(close_val + (1.25 * atr_val))
        idea['target_1'] = _round_price(close_val - (1.5 * atr_val))
        idea['target_2'] = _round_price(close_val - (2.5 * atr_val))
        idea['risk_per_share'] = _round_price(idea['stop_loss'] - idea['entry_trigger'])
        idea['suggested_quantity'] = 0
        idea['max_loss'] = 0
        idea['confidence_score'] = int(ml_probability * 100) if ml_probability > 0 else 45
        idea['ml_probability'] = ml_probability
        idea['decision'] = 'WAIT'
        idea['reasons'] = [
            freshness_reason,
            f"ML Probability: {ml_probability:.2%}{lstm_status_str}",
            "Price is in a downtrend. Stock-only v1 does not short-sell and does not buy puts yet.",
            "Avoid long entry until price repairs the trend.",
        ]
        return idea

    reasons = [freshness_reason, f"ML Probability: {ml_probability:.2%}{lstm_status_str}"]

    # Kelly Percentage
    try:
        from src.backtest import get_stock_verdict
        verdict_info = get_stock_verdict(ticker)
        kelly_pct = float(verdict_info.get('kelly_pct', 0.0))
        reasons.append(f"Kelly Fraction: {kelly_pct:.2%}")
    except Exception as e:
        idea['decision'] = 'REJECT'
        idea['reasons'].append(f"Backtest Error: {e}")
        return idea

    if kelly_pct <= 0:
        suggested_qty = 0
        max_loss = 0.0

    idea.update({
        'direction': 'BULLISH' if long_trend else 'NEUTRAL',
        'setup_type': 'BREAKOUT_LONG' if long_trend else 'WATCH_ONLY',
        'entry_trigger': entry,
        'stop_loss': stop,
        'target_1': target_1,
        'target_2': target_2,
        'risk_per_share': risk_per_share,
        'suggested_quantity': suggested_qty,
        'max_loss': max_loss,
        'ml_probability': ml_probability,
        'kelly_pct': kelly_pct,
        'confidence_score': int(ml_probability * 100),
        'reasons': reasons,
    })

    # Retrieve live price only if the feed is real. The current background feed
    # is simulated, so it must not drive trade/no-trade decisions.
    live_price = None
    try:
        from src.websocket_feed import LATEST_PRICES, LATEST_PRICE_METADATA, PRICES_LOCK
        with PRICES_LOCK:
            metadata = LATEST_PRICE_METADATA.get(ticker.upper(), {})
            if ticker.upper() in LATEST_PRICES and not metadata.get("is_simulated", True):
                live_price = LATEST_PRICES[ticker.upper()]
    except Exception:
        pass

    price_to_check = live_price if live_price is not None else close_val
    gap_up_pct = ((float(latest['open']) - entry) / entry) * 100 if entry > 0 else 0
    runup_pct = ((price_to_check - entry) / entry) * 100 if entry > 0 else 0
    is_gap_up_high = float(latest['open']) > entry * 1.015
    is_runup_high = price_to_check > entry * 1.015

    # Earnings & Dividend event blackout checks
    is_blocked, blackout_reason = check_event_blackout(ticker)

    hard_blocks = []
    if stale:
        hard_blocks.append("Data is stale.")
    if not liquidity_ok:
        hard_blocks.append("Liquidity is not good enough.")
    if not volatility_ok:
        hard_blocks.append("Volatility is outside the tradable range.")
    if risk_per_share > max_risk or suggested_qty <= 0:
        hard_blocks.append(f"Risk per share {risk_per_share:.2f} is too large for max risk {max_risk:.2f}.")
    if rsi_overheated:
        hard_blocks.append("RSI is overheated; do not chase.")
    if is_gap_up_high:
        hard_blocks.append(f"Stock opened with a high gap-up (+{gap_up_pct:.1f}% above trigger), exposing the trade to bad risk-to-reward.")
    elif is_runup_high:
        hard_blocks.append(f"Current price (+{runup_pct:.1f}%) has surged too far above trigger, exposing the trade to bad risk-to-reward.")
    if is_blocked:
        hard_blocks.append(blackout_reason)
    if volume_ratio < 1.25:
        hard_blocks.append(f"Breakout volume is weak (Relative Volume: {volume_ratio:.2f}x of 20-day avg). Need at least 1.25x volume to confirm breakout.")

    if hard_blocks:
        idea['decision'] = 'REJECT'
        idea['reasons'].append("Rejected: " + " ".join(hard_blocks))
    elif ml_probability > 0.65 and kelly_pct > 0.05:
        idea['decision'] = 'TRADE'
        idea['reasons'].append(f"ML setup active! ML Prob: {ml_probability:.2%}, Kelly: {kelly_pct:.2%}.")
        try:
            from src.options import estimate_put_hedge_cost
            cost, strike = estimate_put_hedge_cost(ticker, close_val, atr_val)
            idea['hedge_cost'] = cost
            idea['hedge_strike'] = strike
            idea['reasons'].append(f"Protective Hedge: Buy ATM Put (Strike {strike}) for approx INR {cost:.2f}/share.")
        except Exception as e:
            idea['hedge_cost'] = 0.0
            idea['hedge_strike'] = 0.0
            idea['reasons'].append(f"Hedge estimator failed: {e}")
    else:
        idea['decision'] = 'WAIT'
        idea['reasons'].append(f"Criteria not met for TRADE. ML Prob: {ml_probability:.2%}, Kelly: {kelly_pct:.2%}.")

    # Geopolitical & Macro Economic Shock Safeguards
    try:
        from src.macro_monitor import LATEST_MACRO, MACRO_LOCK
        with MACRO_LOCK:
            global_risk = LATEST_MACRO.get("global_risk", {})
            crude_oil = LATEST_MACRO.get("crude_oil", {})
            us10y = LATEST_MACRO.get("us_10y_yield", {})
            
        risk_level = global_risk.get("level", "MEDIUM")
        oil_change = crude_oil.get("change_pct", 0.0)
        yield_change = us10y.get("change_pct", 0.0)
        
        macro_blocks = []
        if risk_level == "HIGH":
            macro_blocks.append(f"HIGH Geopolitical Risk: {global_risk.get('reason', 'Threat alert')}")
        if oil_change > 4.0:
            macro_blocks.append(f"Crude Oil price shock (+{oil_change:.1f}% today)")
        if yield_change > 3.5:
            macro_blocks.append(f"US 10-Year Bond Yield surge (+{yield_change:.1f}% today)")
            
        if macro_blocks and idea['decision'] == 'TRADE':
            idea['decision'] = 'WAIT'
            idea['reasons'].append("⚠️ Macro-Geopolitical Safeguard Override: Downgraded setup to WAIT due to: " + " & ".join(macro_blocks))
    except Exception:
        pass

    return idea


def get_all_trade_ideas() -> list:
    """Generate and rank trade ideas for all watchlist stocks in parallel."""
    from concurrent.futures import ThreadPoolExecutor
    
    tickers = get_watchlist_tickers()
    index_symbols = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
    watchlist_tickers = [t for t in tickers if t.upper() not in index_symbols]
    
    ideas = []
    
    def process_ticker(ticker):
        try:
            return generate_trade_idea(ticker)
        except Exception as exc:
            idea = _empty_idea(ticker)
            idea['decision'] = 'REJECT'
            idea['reasons'] = [f"Engine error while reading this symbol: {exc}"]
            return idea

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_ticker, watchlist_tickers)
        
    for res in results:
        ideas.append(res)

    decision_priority = {'TRADE': 1, 'WAIT': 2, 'REJECT': 3}
    ideas.sort(key=lambda item: (decision_priority.get(item['decision'], 4), -item['confidence_score']))
    return ideas


def get_mentor_suggestions() -> list:
    """
    Evaluate Nifty leaders in parallel and select the top 2-3 highest-probability swings.
    Applies the full regime, gap-up, AI sentiment, and historical edge checks.
    """
    from concurrent.futures import ThreadPoolExecutor
    from src.backtest import get_stock_verdict
    from src.news import fetch_stock_news, get_aggregated_sentiment
    
    nifty_leaders = [
        "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
        "SBIN.NS", "TATAPOWER.NS", "ITC.NS", "LT.NS", "BHARTIARTL.NS",
        "AXISBANK.NS", "M&M.NS", "MARUTI.NS", "NTPC.NS", "POWERGRID.NS",
        "COALINDIA.NS", "SUNPHARMA.NS", "HINDALCO.NS", "ONGC.NS"
    ]
    
    settings = get_capital_settings()
    gemini_key = settings.get('gemini_api_key', '')
    
    ideas = []
    
    def process_mentor_ticker(ticker):
        try:
            # 1. Generate technical trade idea
            idea = generate_trade_idea(ticker)
            
            # If REJECT, skip
            if idea['decision'] == 'REJECT':
                return None
                
            # 2. Get Backtest verdict edge
            verdict_info = get_stock_verdict(ticker)
            if verdict_info['verdict'] == 'BAD':
                return None
                
            idea['backtest_verdict'] = verdict_info['verdict']
            idea['backtest_win_rate'] = verdict_info['win_rate']
            idea['backtest_net_profit'] = verdict_info['net_profit']
            idea['backtest_expectancy'] = verdict_info['expectancy']
            
            # 3. Attach pre-market news sentiment
            try:
                news_items = fetch_stock_news(ticker, gemini_api_key=gemini_key)
                avg_score, avg_label = get_aggregated_sentiment(news_items)
                idea['sentiment_label'] = avg_label
                idea['sentiment_score'] = avg_score
                idea['news_count'] = len(news_items)
            except Exception:
                idea['sentiment_label'] = 'NEUTRAL'
                idea['sentiment_score'] = 0.0
                idea['news_count'] = 0
                
            # Override decision based on bearish sentiment if active
            if idea['decision'] == 'TRADE' and idea['sentiment_label'] == 'BEARISH':
                idea['decision'] = 'WAIT'
                idea['reasons'].append("⚠️ AI Sentiment Override: Downgraded setup to WAIT due to BEARISH pre-market news sentiment.")
                
            return idea
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(process_mentor_ticker, nifty_leaders)
        
    for res in results:
        if res is not None:
            ideas.append(res)
            
    # Sort ideas:
    # 1. TRADE setups first, then WAIT
    # 2. Confidence score descending
    # 3. Backtest win rate descending
    decision_priority = {'TRADE': 1, 'WAIT': 2}
    ideas.sort(key=lambda item: (
        decision_priority.get(item['decision'], 3),
        -item['confidence_score'],
        -item.get('backtest_win_rate', 0.0)
    ))
    
    # Return top 3
    return ideas[:3]
