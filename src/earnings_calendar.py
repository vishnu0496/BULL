# src/earnings_calendar.py
import logging
import sqlite3
import time
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf
from src.database import get_db_connection, get_watchlist_tickers
from src.nse_session import nse_fetch

logger = logging.getLogger("bull.earnings_calendar")

def refresh_earnings_calendar():
    """Fetch upcoming earnings from NSE corporate announcements and supplement with yfinance."""
    # Step 1: Fetch from NSE Corporate Announcements
    url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
    nse_announcements = []
    try:
        data = nse_fetch(url)
        if data and isinstance(data, list):
            nse_announcements = data
    except Exception as e:
        logger.warning(f"Failed to fetch NSE corporate announcements: {e}")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Process NSE announcements
    for ann in nse_announcements:
        symbol = ann.get("symbol")
        desc = ann.get("desc", "")
        purpose = ann.get("purpose", "")
        
        # Check if announcement is about financial results
        is_earnings = False
        for keyword in ["FINANCIAL RESULTS", "BOARD MEETING", "QUARTERLY RESULTS", "AUDITED RESULTS", "UNAUDITED RESULTS"]:
            if keyword in desc.upper() or keyword in purpose.upper():
                is_earnings = True
                break
                
        if is_earnings and symbol:
            ticker = f"{symbol}.NS"
            # Attempt to parse date
            result_date_str = None
            # Often boardMeetingDate is in the response or we can parse from desc or boardMeetingDate
            meeting_date_raw = ann.get("boardMeetingDate") or ann.get("anngDate")
            if meeting_date_raw:
                try:
                    # e.g., "05-Jun-2026" or "05-Jun-2026 15:30"
                    date_part = meeting_date_raw.split(" ")[0].strip()
                    dt = datetime.strptime(date_part, "%d-%b-%Y")
                    result_date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
            
            if result_date_str:
                cursor.execute("""
                    INSERT OR IGNORE INTO earnings_calendar (
                        ticker, result_date, result_type, estimated_eps, actual_eps, 
                        revenue_estimate, actual_revenue, beat_miss, surprise_pct, 
                        price_reaction_1d, historical_beat_rate
                    ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
                """, (ticker, result_date_str, "Financial Results"))

    conn.commit()
    conn.close()

    # Step 2: Enrich watchlist tickers using yfinance
    watchlist_tickers = get_watchlist_tickers()
    for ticker in watchlist_tickers:
        try:
            logger.info(f"Enriching earnings calendar for {ticker} via yfinance...")
            stock = yf.Ticker(ticker)
            
            # 1. Fetch upcoming earnings date from calendar
            calendar = stock.calendar
            if calendar and 'Earnings Date' in calendar:
                dates = calendar['Earnings Date']
                if dates and isinstance(dates, list):
                    for d in dates:
                        # d could be a date or datetime
                        if isinstance(d, (datetime, pd.Timestamp)):
                            result_date = d.strftime("%Y-%m-%d")
                        else:
                            result_date = str(d)
                            
                        # Save upcoming result date
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR IGNORE INTO earnings_calendar (
                                ticker, result_date, result_type, estimated_eps, actual_eps,
                                revenue_estimate, actual_revenue, beat_miss, surprise_pct,
                                price_reaction_1d, historical_beat_rate
                            ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
                        """, (ticker, result_date, "Earnings Calendar"))
                        conn.commit()
                        conn.close()

            # 2. Fetch historical earnings to calculate beat rate
            try:
                # yfinance returns earnings dates with index being Date/Time, columns like EPS Estimate, Reported EPS
                earnings_dates = stock.earnings_dates
                if earnings_dates is not None and not earnings_dates.empty:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    beats = 0
                    totals = 0
                    
                    for idx, row_data in earnings_dates.iterrows():
                        # idx is Timestamp
                        date_str = idx.strftime("%Y-%m-%d")
                        est = row_data.get("EPS Estimate")
                        act = row_data.get("Reported EPS")
                        surprise = row_data.get("Surprise(%)")
                        
                        if pd.isna(est) or pd.isna(act):
                            continue
                            
                        est_val = float(est)
                        act_val = float(act)
                        surprise_val = float(surprise) if not pd.isna(surprise) else 0.0
                        
                        beat_miss = "MET"
                        if act_val > est_val:
                            beat_miss = "BEAT"
                            beats += 1
                        elif act_val < est_val:
                            beat_miss = "MISS"
                        totals += 1
                        
                        # Save historical records
                        cursor.execute("""
                            INSERT OR REPLACE INTO earnings_calendar (
                                ticker, result_date, result_type, estimated_eps, actual_eps,
                                revenue_estimate, actual_revenue, beat_miss, surprise_pct,
                                price_reaction_1d, historical_beat_rate
                            ) VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                        """, (ticker, date_str, "Historical", est_val, act_val, beat_miss, surprise_val))
                    
                    # Update historical beat rate
                    if totals > 0:
                        beat_rate = float(beats) / totals
                        cursor.execute("""
                            UPDATE earnings_calendar 
                            SET historical_beat_rate = ? 
                            WHERE ticker = ?
                        """, (beat_rate, ticker))
                        
                    conn.commit()
                    conn.close()
            except Exception as ex:
                logger.warning(f"Failed to fetch historical earnings for {ticker}: {ex}")
                
            # Avoid hitting yfinance too aggressively
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Failed to enrich earnings calendar for {ticker}: {e}")

    logger.info("Earnings calendar refresh complete.")
    return True

def check_earnings_blackout(ticker, days=3):
    """
    Check if a ticker is currently inside the earnings blackout window.
    Blackout is defined as 3 days before the result_date up to 1 day after the result_date.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        today_str = datetime.today().strftime("%Y-%m-%d")
        
        # Get all results for the ticker
        cursor.execute("""
            SELECT result_date FROM earnings_calendar 
            WHERE ticker = ? AND result_date >= date(?, '-5 day')
            ORDER BY result_date ASC
        """, (ticker.upper(), today_str))
        
        rows = cursor.fetchall()
        in_blackout = False
        days_to_result = None
        result_date_str = None
        
        today_dt = datetime.today().date()
        
        for row in rows:
            res_date_str = row["result_date"]
            res_dt = datetime.strptime(res_date_str, "%Y-%m-%d").date()
            
            diff_days = (res_dt - today_dt).days
            
            # Blackout window: 3 days before and 1 day after (inclusive)
            # so today_dt is between res_dt - 3 days and res_dt + 1 day
            if -1 <= diff_days <= days:
                in_blackout = True
                days_to_result = diff_days
                result_date_str = res_date_str
                break
            
            # Keep track of the closest upcoming result
            if diff_days >= 0:
                if days_to_result is None or diff_days < days_to_result:
                    days_to_result = diff_days
                    result_date_str = res_date_str
                    
        return {
            "in_blackout": in_blackout,
            "days_to_result": days_to_result,
            "result_date": result_date_str
        }
    finally:
        conn.close()

def get_earnings_this_week():
    """Get list of upcoming results for the next 7 days."""
    conn = get_db_connection()
    try:
        today_str = datetime.today().strftime("%Y-%m-%d")
        next_week_str = (datetime.today() + timedelta(days=7)).strftime("%Y-%m-%d")
        
        cursor = conn.cursor()
        # Get upcoming earnings calendar items
        cursor.execute("""
            SELECT e.*, 
                   (SELECT historical_beat_rate FROM earnings_calendar e2 
                    WHERE e2.ticker = e.ticker AND e2.historical_beat_rate IS NOT NULL 
                    LIMIT 1) as beat_rate
            FROM earnings_calendar e
            WHERE result_date BETWEEN ? AND ?
            GROUP BY ticker, result_date
            ORDER BY result_date ASC
        """, (today_str, next_week_str))
        
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            # Fetch beat rate if not present
            if d.get("beat_rate") is None:
                d["beat_rate"] = d.get("historical_beat_rate") or 0.5
            results.append(d)
        return results
    finally:
        conn.close()

def update_post_result_data():
    """For past earnings dates with missing actual results, fetch from yfinance and compute surprise/reaction."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Find records that are past but have NULL actual_eps
    today_str = datetime.today().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT DISTINCT ticker FROM earnings_calendar 
        WHERE result_date < ? AND actual_eps IS NULL
    """, (today_str,))
    
    tickers = [r["ticker"] for r in cursor.fetchall()]
    conn.close()
    
    for ticker in tickers:
        try:
            logger.info(f"Updating post-result data for {ticker}...")
            stock = yf.Ticker(ticker)
            earnings_dates = stock.earnings_dates
            
            if earnings_dates is None or earnings_dates.empty:
                continue
                
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Fetch historical prices to compute 1-day price reaction
            # Price reaction: percentage close change from day of earnings (or day before if after hours) to day after
            cursor.execute("""
                SELECT result_date FROM earnings_calendar 
                WHERE ticker = ? AND result_date < ? AND actual_eps IS NULL
            """, (ticker, today_str))
            
            res_dates = [r["result_date"] for r in cursor.fetchall()]
            
            for res_date in res_dates:
                # Find matching row in earnings_dates
                matched_row = None
                for idx, row_data in earnings_dates.iterrows():
                    if idx.strftime("%Y-%m-%d") == res_date:
                        matched_row = row_data
                        break
                        
                if matched_row is not None:
                    est = matched_row.get("EPS Estimate")
                    act = matched_row.get("Reported EPS")
                    surprise = matched_row.get("Surprise(%)")
                    
                    if not pd.isna(est) and not pd.isna(act):
                        est_val = float(est)
                        act_val = float(act)
                        surprise_val = float(surprise) if not pd.isna(surprise) else 0.0
                        beat_miss = "BEAT" if act_val > est_val else ("MISS" if act_val < est_val else "MET")
                        
                        # Calculate price reaction
                        price_reaction = None
                        try:
                            # Fetch close price around the date
                            res_dt = datetime.strptime(res_date, "%Y-%m-%d")
                            start_p = (res_dt - timedelta(days=3)).strftime("%Y-%m-%d")
                            end_p = (res_dt + timedelta(days=4)).strftime("%Y-%m-%d")
                            
                            hist = stock.history(start=start_p, end=end_p)
                            if not hist.empty:
                                # Get close on the day of result or the closest trading day before/after
                                dates_list = hist.index.strftime("%Y-%m-%d").tolist()
                                if res_date in dates_list:
                                    res_idx = dates_list.index(res_date)
                                    if res_idx + 1 < len(dates_list):
                                        close_before = hist.iloc[res_idx]['Close']
                                        close_after = hist.iloc[res_idx + 1]['Close']
                                        price_reaction = float((close_after - close_before) / close_before * 100)
                                    elif res_idx > 0:
                                        close_before = hist.iloc[res_idx - 1]['Close']
                                        close_after = hist.iloc[res_idx]['Close']
                                        price_reaction = float((close_after - close_before) / close_before * 100)
                        except Exception as ex:
                            logger.warning(f"Could not compute price reaction for {ticker} on {res_date}: {ex}")
                            
                        cursor.execute("""
                            UPDATE earnings_calendar
                            SET estimated_eps = ?, actual_eps = ?, beat_miss = ?, surprise_pct = ?, price_reaction_1d = ?
                            WHERE ticker = ? AND result_date = ?
                        """, (est_val, act_val, beat_miss, surprise_val, price_reaction, ticker, res_date))
                        
            conn.commit()
            conn.close()
            time.sleep(1.0)
        except Exception as e:
            logger.warning(f"Error updating post result data for {ticker}: {e}")
            
    return True

def get_earnings_edge(ticker):
    """Retrieve earnings performance edge metrics for a ticker."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get historical beat rate and surprise average
        cursor.execute("""
            SELECT beat_miss, surprise_pct FROM earnings_calendar 
            WHERE ticker = ? AND beat_miss IS NOT NULL AND beat_miss != 'MET'
            ORDER BY result_date DESC 
            LIMIT 8
        """, (ticker.upper(),))
        
        rows = cursor.fetchall()
        if not rows:
            return {"has_edge": False, "beat_rate": 0.5, "confidence_boost": 0}
            
        beats = sum(1 for r in rows if r["beat_miss"] == "BEAT")
        total = len(rows)
        beat_rate = float(beats) / total if total > 0 else 0.5
        
        has_edge = beat_rate >= 0.6 and total >= 3
        
        # Calculate confidence boost (max +10 points)
        confidence_boost = 0
        if has_edge:
            confidence_boost = min(10, int((beat_rate - 0.5) * 20))
            
        return {
            "has_edge": has_edge,
            "beat_rate": beat_rate,
            "confidence_boost": confidence_boost
        }
    finally:
        conn.close()
