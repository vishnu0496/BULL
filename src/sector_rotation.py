# src/sector_rotation.py
import logging
import sqlite3
import time
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from src.database import get_db_connection

logger = logging.getLogger("bull.sector_rotation")

# 10 primary sectoral indices to track
SECTOR_INDICES = {
    "BANK": "^NSEBANK",
    "IT": "^CNXIT",
    "PHARMA": "^CNXPHARMA",
    "AUTO": "^CNXAUTO",
    "FMCG": "^CNXFMCG",
    "METALS": "^CNXMETAL",
    "ENERGY": "^CNXENERGY",
    "INFRA": "^CNXINFRA",
    "REALTY": "^CNXREALTY",
    "MEDIA": "^CNXMEDIA"
}

# Mapping of engine.py sectors to index keys
SECTOR_TO_INDEX_KEY = {
    "BANK": "BANK",
    "FINANCE": "BANK",
    "IT": "IT",
    "PHARMA": "PHARMA",
    "AUTO": "AUTO",
    "FMCG": "FMCG",
    "METALS": "METALS",
    "ENERGY": "ENERGY",
    "POWER": "ENERGY",
    "INFRA": "INFRA",
    "CEMENT": "INFRA",
    "TELECOM": "MEDIA",
    "MEDIA": "MEDIA",
    "CONSUMER": "FMCG",
    "DEFENCE": "INFRA"
}

def refresh_sector_data():
    """Fetch sector index data from yfinance, calculate RS and momentum, and save to SQLite."""
    try:
        today_str = datetime.today().strftime("%Y-%m-%d")
        logger.info("Refreshing sector rotation data...")
        
        # Download Nifty 50 benchmark
        nifty = yf.Ticker("^NSEI")
        nifty_hist = nifty.history(period="3mo")
        if nifty_hist.empty or len(nifty_hist) < 22:
            logger.warning("Could not download benchmark Nifty 50 history.")
            return False
            
        nifty_close_today = nifty_hist.iloc[-1]['Close']
        nifty_close_5d = nifty_hist.iloc[-5]['Close'] if len(nifty_hist) >= 5 else nifty_hist.iloc[0]['Close']
        nifty_close_20d = nifty_hist.iloc[-20]['Close'] if len(nifty_hist) >= 20 else nifty_hist.iloc[0]['Close']
        
        nifty_ret_5d = (nifty_close_today - nifty_close_5d) / nifty_close_5d
        nifty_ret_20d = (nifty_close_today - nifty_close_20d) / nifty_close_20d
        
        sectors_data = []
        for sector_name, symbol in SECTOR_INDICES.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="3mo")
                if hist.empty or len(hist) < 22:
                    logger.warning(f"Could not download history for sector index {symbol}")
                    continue
                    
                close_today = hist.iloc[-1]['Close']
                close_5d = hist.iloc[-5]['Close'] if len(hist) >= 5 else hist.iloc[0]['Close']
                close_20d = hist.iloc[-20]['Close'] if len(hist) >= 20 else hist.iloc[0]['Close']
                
                ret_5d = (close_today - close_5d) / close_5d
                ret_20d = (close_today - close_20d) / close_20d
                
                # RS score = (1 + sector_return_1m) / (1 + nifty_return_1m)
                rs_score = (1 + ret_20d) / (1 + nifty_ret_20d)
                
                # Momentum classification
                if ret_5d > 0 and ret_20d > 0:
                    momentum = "RISING"
                elif ret_5d < 0 and ret_20d < 0:
                    momentum = "FALLING"
                else:
                    momentum = "NEUTRAL"
                    
                sectors_data.append({
                    "sector": sector_name,
                    "weekly_return": float(ret_5d * 100),
                    "monthly_return": float(ret_20d * 100),
                    "rs_score": float(rs_score),
                    "momentum": momentum
                })
                time.sleep(0.5) # Avoid rapid requests
            except Exception as e:
                logger.warning(f"Error processing sector {sector_name} ({symbol}): {e}")
                
        if not sectors_data:
            return False
            
        # Rank sectors by RS score
        sectors_data.sort(key=lambda x: x["rs_score"], reverse=True)
        
        # Save to database
        conn = get_db_connection()
        cursor = conn.cursor()
        for idx, s in enumerate(sectors_data):
            rank = idx + 1
            # Signal: Rank 1-3 Lead, 4-7 Neutral, 8-10 Lagging
            if rank <= 3:
                signal = "LEAD"
            elif rank <= 7:
                signal = "NEUTRAL"
            else:
                signal = "LAGGING"
                
            cursor.execute("""
                INSERT OR REPLACE INTO sector_rotation (
                    date, sector, weekly_return, monthly_return, rs_score, momentum, rank, signal
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (today_str, s["sector"], s["weekly_return"], s["monthly_return"], s["rs_score"], s["momentum"], rank, signal))
            
        conn.commit()
        conn.close()
        logger.info(f"Sector rotation data saved successfully for date: {today_str}")
        return True
    except Exception as e:
        logger.error(f"Error in refresh_sector_data: {e}")
        return False

def get_sector_rankings():
    """Retrieve the latest sector rotation rankings from the database."""
    conn = get_db_connection()
    try:
        # First, find the latest date available in sector_rotation table
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(date) as max_date FROM sector_rotation")
        row = cursor.fetchone()
        if not row or row["max_date"] is None:
            # Table is empty, return empty list or run refresh synchronously
            return []
            
        latest_date = row["max_date"]
        
        cursor.execute("""
            SELECT * FROM sector_rotation 
            WHERE date = ? 
            ORDER BY rank ASC
        """, (latest_date,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_sector_for_ticker(ticker):
    """Get the mapped sector name for a ticker, using the engine's SECTORS dictionary structure."""
    # We import SECTORS here to avoid circular imports
    from engine import SECTORS
    clean_ticker = ticker.upper()
    raw_sector = SECTORS.get(clean_ticker)
    if not raw_sector:
        # Fallback based on name search or default
        return "GENERAL"
    return raw_sector

def should_trade_sector(ticker):
    """
    Evaluate if a ticker is in a strong or lagging sector.
    Returns a dict with rankings, RS score, momentum, signal, and decision/adjustments.
    """
    raw_sector = get_sector_for_ticker(ticker)
    index_key = SECTOR_TO_INDEX_KEY.get(raw_sector, "BANK") # Default to BANK if not found
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get the latest date
        cursor.execute("SELECT MAX(date) as max_date FROM sector_rotation")
        row = cursor.fetchone()
        latest_date = row["max_date"] if row else None
        
        if not latest_date:
            return {
                "sector": raw_sector,
                "rank": 5,
                "rs_score": 1.0,
                "momentum": "NEUTRAL",
                "signal": "NEUTRAL",
                "decision": "NEUTRAL",
                "confidence_adjustment": 0,
                "note": "No sector data available. Defaulting to Neutral."
            }
            
        cursor.execute("""
            SELECT * FROM sector_rotation 
            WHERE date = ? AND sector = ?
        """, (latest_date, index_key))
        
        sec_row = cursor.fetchone()
        if not sec_row:
            return {
                "sector": raw_sector,
                "rank": 5,
                "rs_score": 1.0,
                "momentum": "NEUTRAL",
                "signal": "NEUTRAL",
                "decision": "NEUTRAL",
                "confidence_adjustment": 0,
                "note": f"Sector index mapping for {index_key} not found. Defaulting to Neutral."
            }
            
        sec = dict(sec_row)
        rank = sec["rank"]
        rs_score = sec["rs_score"]
        momentum = sec["momentum"]
        signal = sec["signal"]
        
        decision = "NEUTRAL"
        confidence_adjustment = 0
        note = "Sector momentum is average."
        
        if signal == "LEAD":
            decision = "FAVORABLE"
            confidence_adjustment = 10
            note = f"Favorable: {raw_sector} is a top sector (Rank {rank}, RS: {rs_score:.2f})."
        elif signal == "LAGGING" or rs_score < 0.95:
            decision = "UNFAVORABLE"
            confidence_adjustment = -10
            note = f"Unfavorable: {raw_sector} is a lagging sector (Rank {rank}, RS: {rs_score:.2f})."
            
        return {
            "sector": raw_sector,
            "rank": rank,
            "rs_score": rs_score,
            "momentum": momentum,
            "signal": signal,
            "decision": decision,
            "confidence_adjustment": confidence_adjustment,
            "note": note
        }
    finally:
        conn.close()
