from datetime import date

import pandas as pd

from src.database import get_prices, get_watchlist_tickers, save_research_setups


def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df['close'].shift(1)
    true_range = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.rolling(window=window).mean()


def _confidence(base: int, *conditions: bool) -> int:
    score = base + sum(6 for condition in conditions if condition)
    return max(35, min(score, 82))


def _risk_level(atr_pct: float, volume_ratio: float) -> str:
    if atr_pct > 3.5 or volume_ratio < 0.8:
        return "HIGH"
    if atr_pct > 2.2:
        return "MEDIUM"
    return "LOW"


def generate_setup_for_ticker(ticker: str, setup_date: str | None = None):
    """Create one research setup from stored EOD data.

    This is intentionally rule-based. It does not pretend to know live market
    direction; it creates conditional plans to watch after the market opens.
    """
    setup_date = setup_date or date.today().isoformat()
    df = get_prices(ticker)
    if df.empty or len(df) < 60:
        return None

    df = df.sort_values('date').copy()
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['vol_avg_20'] = df['volume'].rolling(20).mean()
    df['atr_14'] = _atr(df)
    df['high_20'] = df['high'].rolling(20).max()
    df['low_20'] = df['low'].rolling(20).min()

    latest = df.iloc[-1]
    if pd.isna(latest['sma_20']) or pd.isna(latest['sma_50']) or pd.isna(latest['atr_14']):
        return None

    close = float(latest['close'])
    prev_high = float(latest['high'])
    prev_low = float(latest['low'])
    atr = max(float(latest['atr_14']), close * 0.005)
    volume_ratio = float(latest['volume'] / latest['vol_avg_20']) if latest['vol_avg_20'] else 1.0
    atr_pct = (atr / close) * 100

    above_trend = close > latest['sma_20'] > latest['sma_50']
    below_trend = close < latest['sma_20'] < latest['sma_50']
    near_breakout = close >= float(latest['high_20']) * 0.985
    near_breakdown = close <= float(latest['low_20']) * 1.015
    volume_expansion = volume_ratio >= 1.15

    if above_trend and (near_breakout or volume_expansion):
        entry = round(prev_high + (0.10 * atr), 2)
        stop = round(max(prev_low, entry - (1.20 * atr)), 2)
        risk = max(entry - stop, atr * 0.75)
        confidence = _confidence(48, above_trend, near_breakout, volume_expansion, atr_pct < 2.8)
        reasons = [
            "Price is above 20-day and 50-day moving averages",
            "Stock is near recent breakout zone" if near_breakout else "Volume expansion supports momentum",
            f"Volume is {volume_ratio:.2f}x its 20-day average",
            "Plan is conditional; wait for price confirmation after the open",
        ]
        return {
            'setup_date': setup_date,
            'ticker': ticker,
            'direction': 'BULLISH',
            'entry_trigger': entry,
            'stop_loss': stop,
            'target_1': round(entry + (1.50 * risk), 2),
            'target_2': round(entry + (2.40 * risk), 2),
            'invalidation_rule': "Avoid if it opens far above target 1, falls back below entry, or broader sector/index is weak.",
            'confidence_score': confidence,
            'risk_level': _risk_level(atr_pct, volume_ratio),
            'reasons': " | ".join(reasons),
            'status': 'PLANNED',
        }

    if below_trend and (near_breakdown or volume_expansion):
        entry = round(prev_low - (0.10 * atr), 2)
        stop = round(min(prev_high, entry + (1.20 * atr)), 2)
        risk = max(stop - entry, atr * 0.75)
        confidence = _confidence(48, below_trend, near_breakdown, volume_expansion, atr_pct < 2.8)
        reasons = [
            "Price is below 20-day and 50-day moving averages",
            "Stock is near recent breakdown zone" if near_breakdown else "Volume expansion supports downside pressure",
            f"Volume is {volume_ratio:.2f}x its 20-day average",
            "Plan is conditional; wait for price confirmation after the open",
        ]
        return {
            'setup_date': setup_date,
            'ticker': ticker,
            'direction': 'BEARISH',
            'entry_trigger': entry,
            'stop_loss': stop,
            'target_1': round(entry - (1.50 * risk), 2),
            'target_2': round(entry - (2.40 * risk), 2),
            'invalidation_rule': "Avoid if it opens far below target 1, reclaims entry, or broader sector/index is strong.",
            'confidence_score': confidence,
            'risk_level': _risk_level(atr_pct, volume_ratio),
            'reasons': " | ".join(reasons),
            'status': 'PLANNED',
        }

    return {
        'setup_date': setup_date,
        'ticker': ticker,
        'direction': 'NEUTRAL',
        'entry_trigger': close,
        'stop_loss': round(close - atr, 2),
        'target_1': round(close + atr, 2),
        'target_2': round(close + (2 * atr), 2),
        'invalidation_rule': "No clean directional setup from stored daily data. Watch only; do not force a trade.",
        'confidence_score': 35,
        'risk_level': _risk_level(atr_pct, volume_ratio),
        'reasons': "Trend, breakout, and volume conditions are not aligned strongly enough.",
        'status': 'PLANNED',
    }


def generate_daily_research_setups(setup_date: str | None = None):
    """Generate and persist setups for every ticker in the watchlist."""
    setup_date = setup_date or date.today().isoformat()
    setups = []
    for ticker in get_watchlist_tickers():
        setup = generate_setup_for_ticker(ticker, setup_date=setup_date)
        if setup:
            setups.append(setup)

    save_research_setups(setups)
    return setups
