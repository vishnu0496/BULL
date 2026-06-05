# src/premarket_signals.py
import logging
import sqlite3
import time
from datetime import datetime, timedelta
import yfinance as yf
from src.database import get_db_connection

logger = logging.getLogger("bull.premarket_signals")

def get_pct_change(ticker_symbol):
    """Retrieve the percentage return from the previous day's close for a ticker."""
    try:
        t = yf.Ticker(ticker_symbol)
        hist = t.history(period="2d")
        if not hist.empty and len(hist) >= 2:
            prev_close = hist.iloc[-2]['Close']
            close = hist.iloc[-1]['Close']
            return float((close - prev_close) / prev_close * 100)
        elif not hist.empty:
            close = hist.iloc[-1]['Close']
            open_val = hist.iloc[-1]['Open']
            if open_val > 0:
                return float((close - open_val) / open_val * 100)
    except Exception as e:
        logger.warning(f"Error fetching percent change for {ticker_symbol}: {e}")
    return 0.0

def get_vix_value():
    """Retrieve current India VIX index level."""
    try:
        t = yf.Ticker("^INDIAVIX")
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist.iloc[-1]['Close'])
    except Exception as e:
        logger.warning(f"Error fetching VIX: {e}")
    return 15.0 # Default baseline VIX

def compute_premarket_score():
    """
    Compute premarket score based on Gift Nifty, US markets, Asia indices, India VIX, and yesterday's FII flows.
    Caches the results to SQLite.
    """
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    # 1. Check SQLite Cache (Within 30 minutes)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM premarket_signals 
            WHERE date = ? 
            ORDER BY generated_at DESC 
            LIMIT 1
        """, (today_str,))
        row = cursor.fetchone()
        if row:
            # Parse timestamp and check age
            gen_time_str = row["generated_at"]
            try:
                gen_dt = datetime.strptime(gen_time_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Sometimes it might be ISO format
                gen_dt = datetime.fromisoformat(gen_time_str.replace('Z', '+00:00'))
            
            # If generated within 30 minutes, return cached
            if (datetime.utcnow() - gen_dt.replace(tzinfo=None)) < timedelta(minutes=30):
                logger.info("Returning cached pre-market signal.")
                return dict(row)
    except Exception as e:
        logger.warning(f"Error reading premarket signal cache: {e}")
    finally:
        conn.close()
        
    logger.info("Computing fresh premarket signals...")
    
    # 2. Fetch Data Components
    gift_nifty_gap = get_pct_change("NI=F")
    sp500_chg = get_pct_change("^GSPC")
    nasdaq_chg = get_pct_change("^IXIC")
    
    nikkei_chg = get_pct_change("^N225")
    hang_seng_chg = get_pct_change("^HSI")
    shanghai_chg = get_pct_change("000001.SS")
    
    india_vix = get_vix_value()
    
    # Fetch yesterday's FII net flow
    fii_yesterday = 0.0
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT fii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            fii_yesterday = float(row["fii_net"])
    except Exception as e:
        logger.warning(f"Error fetching yesterday's FII net: {e}")
    finally:
        conn.close()
        
    # 3. Calculate Premarket Score
    # Starts at 50 (neutral)
    score = 50.0
    
    # Gift Nifty Gap (weight: 1% return adds/subtracts 15 points)
    score += gift_nifty_gap * 15.0
    
    # US Markets (GSPC/IXIC change)
    if sp500_chg > 0.5:
        score += 3.0
    elif sp500_chg < -0.5:
        score -= 3.0
        
    if nasdaq_chg > 0.5:
        score += 3.0
    elif nasdaq_chg < -0.5:
        score -= 3.0
        
    # Asia Score (Average of N225, HSI, Shanghai)
    asia_avg = (nikkei_chg + hang_seng_chg + shanghai_chg) / 3.0
    asia_score = asia_avg
    if asia_avg > 0.5:
        score += 4.0
    elif asia_avg < -0.5:
        score -= 4.0
        
    # India VIX Volatility Penalty
    if india_vix < 13.0:
        score += 5.0  # Ultra low fear
    elif india_vix < 16.0:
        score += 2.0  # Low fear
    elif india_vix > 20.0:
        score -= 10.0 # High fear
    elif india_vix > 24.0:
        score -= 15.0 # Extreme fear
        
    # Yesterday's FII Flow Support
    if fii_yesterday > 1500.0:
        score += 5.0
    elif fii_yesterday < -1500.0:
        score -= 5.0
        
    # Cap score between 0 and 100
    score = max(0.0, min(100.0, score))
    
    # 4. Classify Market Open & Recommendation
    if score >= 75.0:
        classification = "STRONG_BULL_OPEN"
        recommendation = "Strong global and gift cues. Long bias. Look for intraday pullbacks to buy."
    elif score >= 55.0:
        classification = "MILD_BULL_OPEN"
        recommendation = "Positive bias. Favor long setups on breakouts."
    elif score >= 45.0:
        classification = "NEUTRAL_OPEN"
        recommendation = "Rangebound open expected. Stick to strict technical triggers."
    elif score >= 25.0:
        classification = "MILD_BEAR_OPEN"
        recommendation = "Weak global sentiment. Tighten stop losses. Short-sellers active."
    else:
        classification = "STRONG_BEAR_OPEN"
        recommendation = "Heavy global selloff. Avoid fresh long entries. Protect capital."
        
    # 5. Save to database
    conn = get_db_connection()
    cursor = conn.cursor()
    generated_at_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    try:
        cursor.execute("""
            INSERT OR REPLACE INTO premarket_signals (
                date, gift_nifty_gap, sp500_chg, nasdaq_chg, asia_score, india_vix, 
                fii_yesterday, pre_market_score, classification, recommendation, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            today_str, gift_nifty_gap, sp500_chg, nasdaq_chg, asia_score, 
            india_vix, fii_yesterday, score, classification, recommendation, generated_at_str
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Error saving premarket signals to DB: {e}")
    finally:
        conn.close()
        
    return {
        "date": today_str,
        "gift_nifty_gap": gift_nifty_gap,
        "sp500_chg": sp500_chg,
        "nasdaq_chg": nasdaq_chg,
        "asia_score": asia_score,
        "india_vix": india_vix,
        "fii_yesterday": fii_yesterday,
        "pre_market_score": score,
        "classification": classification,
        "recommendation": recommendation,
        "generated_at": generated_at_str
    }

def get_premarket_score():
    """Retrieve the latest premarket signals from SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM premarket_signals ORDER BY date DESC, generated_at DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
        # Fallback if empty
        return {
            "date": datetime.today().strftime("%Y-%m-%d"),
            "gift_nifty_gap": 0.0,
            "sp500_chg": 0.0,
            "nasdaq_chg": 0.0,
            "asia_score": 0.0,
            "india_vix": 15.0,
            "fii_yesterday": 0.0,
            "pre_market_score": 50.0,
            "classification": "NEUTRAL_OPEN",
            "recommendation": "Default rangebound open. No fresh signal calculated.",
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        }
    finally:
        conn.close()
