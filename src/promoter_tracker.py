# src/promoter_tracker.py
import logging
import sqlite3
import re
import requests
from datetime import datetime, timedelta
from src.database import get_db_connection
from src.nse_session import nse_fetch

logger = logging.getLogger("bull.promoter_tracker")

BSE_TO_NSE_TICKER = {
    "500180": "HDFCBANK.NS",
    "500325": "RELIANCE.NS",
    "532540": "TCS.NS",
    "500209": "INFY.NS",
    "532174": "ICICIBANK.NS",
    "500247": "KOTAKBANK.NS",
    "532215": "AXISBANK.NS",
    "500112": "SBIN.NS",
    "532454": "BHARTIARTL.NS",
    "500875": "ITC.NS",
    "500510": "LT.NS",
    "500696": "HINDUNILVR.NS",
    "500034": "BAJFINANCE.NS",
    "500520": "M&M.NS",
    "532500": "MARUTI.NS",
    "500570": "TATAMOTORS.NS",
    "533278": "COALINDIA.NS",
    "532555": "NTPC.NS",
    "532898": "POWERGRID.NS",
    "524715": "SUNPHARMA.NS",
    "500312": "ONGC.NS",
    "500228": "JSWSTEEL.NS",
    "535789": "HINDALCO.NS",
    "500440": "HINDALCO.NS",
    "500470": "TATASTEEL.NS",
    "532281": "HCLTECH.NS",
    "507685": "WIPRO.NS",
    "500820": "ASIANPAINT.NS",
    "500114": "TITAN.NS",
    "532538": "ULTRACEMCO.NS",
    "532921": "ADANIPORTS.NS",
    "532755": "TECHM.NS",
    "508869": "APOLLOHOSP.NS",
    "500087": "CIPLA.NS",
    "500124": "DRREDDY.NS",
    "505200": "EICHERMOT.NS",
    "500300": "GRASIM.NS",
    "500182": "HEROMOTOCO.NS",
    "532187": "INDUSINDBK.NS",
    "540005": "LTIM.NS",
    "500790": "NESTLEIND.NS",
    "540719": "SBILIFE.NS",
    "500800": "TATACONSUM.NS",
    "512070": "UPL.NS",
    "540777": "HDFCLIFE.NS",
    "500547": "BPCL.NS",
    "530005": "DIVISLAB.NS",
    "532977": "BAJAJ-AUTO.NS",
    "500825": "BRITANNIA.NS"
}

def fetch_promoter_activity():
    """Fetch insider trading and block deal announcements from NSE and cache them, falling back to BSE on failure."""
    url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
    announcements = []
    success = False
    try:
        logger.info("Promoters: Fetching primary promoter announcements from NSE...")
        data = nse_fetch(url)
        if data and isinstance(data, list):
            announcements = data
            success = True
    except Exception as e:
        logger.warning(f"Promoters: Failed to fetch corporate announcements from NSE: {e}")

    if success and announcements:
        conn = get_db_connection()
        cursor = conn.cursor()
        saved_count = 0
        today_str = datetime.today().strftime("%Y-%m-%d")

        for ann in announcements:
            symbol = ann.get("symbol")
            if not symbol:
                continue
                
            desc = ann.get("desc", "")
            subject = ann.get("subject", "")
            purpose = ann.get("purpose", "")
            
            combined_text = f"{subject} {purpose} {desc}".upper()
            
            is_insider_or_sast = False
            for keyword in ["INSIDER TRADING", "SAST", "PROMOTER", "ACQUISITION", "DISPOSAL", "PLEDGE", "REGULATION 29", "REGULATION 31"]:
                if keyword in combined_text:
                    is_insider_or_sast = True
                    break
                    
            if not is_insider_or_sast:
                continue
                
            # Determine transaction type & classification
            transaction_type = "BUY"
            classification = "BUY"
            
            if any(w in combined_text for w in ["DISPOSAL", "SELL", "SALE"]):
                transaction_type = "SELL"
                classification = "SELL"
            elif "PLEDGE" in combined_text and not any(w in combined_text for w in ["RELEASE", "REVOCATION", "DE-PLEDGE"]):
                transaction_type = "SELL"
                classification = "PLEDGE"
            elif any(w in combined_text for w in ["RELEASE", "REVOCATION", "DE-PLEDGE"]):
                transaction_type = "BUY"
                classification = "RELEASE"
                
            # Parse metadata
            person_name = "Promoter Group"
            designation = "Promoter"
            shares = 0
            value_crore = 1.2 # Default baseline
            holding_before = 0.0
            holding_after = 0.0
            
            # Try to parse shares count
            try:
                shares_match = re.search(r'(\d[\d,]*)\s*(?:SHARES|SEC|QTY)', combined_text)
                if shares_match:
                    shares = int(shares_match.group(1).replace(",", ""))
            except Exception:
                pass
                
            if shares > 0:
                # Estimate value
                value_crore = float((shares * 100) / 10000000)
                
            # Determine Signal Strength
            if transaction_type == "BUY":
                if value_crore > 5.0:
                    signal_strength = "STRONG_SIGNAL"
                    classification = "STRONG_BUY"
                elif value_crore > 0.5:
                    signal_strength = "MODERATE_SIGNAL"
                    classification = "MODERATE_BUY"
                else:
                    signal_strength = "WEAK_SIGNAL"
                    classification = "WEAK_BUY"
            else: # SELL / PLEDGE
                if value_crore > 5.0:
                    signal_strength = "STRONG_RED_FLAG"
                    classification = "STRONG_SELL"
                elif value_crore > 0.5:
                    signal_strength = "MODERATE_RED_FLAG"
                    classification = "MODERATE_SELL"
                else:
                    signal_strength = "NOTE_ONLY"
                    classification = "WEAK_SELL"
                    
            # Parse Date
            ann_date_raw = ann.get("anngDate") or ann.get("boardMeetingDate")
            date_str = today_str
            if ann_date_raw:
                try:
                    date_part = ann_date_raw.split(" ")[0].strip()
                    dt = datetime.strptime(date_part, "%d-%b-%Y")
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
                    
            ticker = f"{symbol}.NS"
            
            cursor.execute("""
                INSERT INTO promoter_activity (
                    date, ticker, person_name, designation, transaction_type, shares,
                    value_crore, holding_before, holding_after, signal_strength, classification,
                    source, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'NSE_API', 'HIGH')
            """, (date_str, ticker, person_name, designation, transaction_type, shares, value_crore, holding_before, holding_after, signal_strength, classification))
            saved_count += 1

        conn.commit()
        conn.close()
        logger.info(f"Promoters: Successfully processed {saved_count} promoter announcements from NSE.")
    else:
        # Fallback to BSE API
        logger.info("Promoters: Attempting fallback to BSE insider trading API...")
        try:
            success = fetch_promoter_activity_bse()
        except Exception as e:
            logger.info(f"Promoters: BSE fallback failed: {e}")
            
    # Try fetching block deals
    fetch_bulk_deals()
    return success

def fetch_promoter_activity_bse():
    """Fetch insider trading announcements from BSE and cache them."""
    formatted_date = datetime.today().strftime("%d/%m/%Y")
    url = f"https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?strCat=-1&strPrevDate={formatted_date}&strScrip=&strSearch=P&strToDate={formatted_date}&strType=C&subcategory=17"
    
    bse_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.bseindia.com/",
        "Accept": "application/json, text/plain, */*"
    }
    
    try:
        resp = requests.get(url, headers=bse_headers, timeout=10)
        if resp.status_code != 200:
            logger.info(f"Promoters: BSE API returned status {resp.status_code}")
            return False
            
        data = resp.json()
        if not data or not isinstance(data, list):
            logger.info("Promoters: BSE API returned empty list or invalid format")
            return False
            
        conn = get_db_connection()
        cursor = conn.cursor()
        saved_count = 0
        db_today_str = datetime.today().strftime("%Y-%m-%d")
        
        for item in data:
            scrip_cd = str(item.get("SCRIP_CD") or item.get("scrip_cd") or item.get("scripCode") or "")
            ticker = BSE_TO_NSE_TICKER.get(scrip_cd)
            if not ticker:
                continue
                
            person_name = item.get("OWNER_NAME") or item.get("owner_name") or item.get("AcquirerName") or item.get("acquirerName") or item.get("PERSON_NAME") or item.get("person_name") or "Insider"
            designation = item.get("DESIGNATION") or item.get("designation") or "Promoter"
            
            transa_type = str(item.get("TRANSA_TYPE") or item.get("transa_type") or item.get("TransactionType") or item.get("transactionType") or "BUY").upper()
            transaction_type = "BUY"
            classification = "BUY"
            
            if any(w in transa_type for w in ["DISPOSAL", "SELL", "SALE"]):
                transaction_type = "SELL"
                classification = "SELL"
                
            shares = 0
            try:
                shares = int(float(str(item.get("SEC_QTY") or item.get("sec_qty") or item.get("Quantity") or 0).replace(",", "")))
            except ValueError:
                pass
                
            value_crore = 1.0
            try:
                raw_val = float(str(item.get("SEC_VAL") or item.get("sec_val") or item.get("Value") or 0).replace(",", ""))
                if raw_val > 100000:
                    value_crore = raw_val / 10000000.0
                else:
                    value_crore = raw_val
            except ValueError:
                if shares > 0:
                    value_crore = float((shares * 100) / 10000000)
                    
            if transaction_type == "BUY":
                if value_crore > 5.0:
                    signal_strength = "STRONG_SIGNAL"
                    classification = "STRONG_BUY"
                elif value_crore > 0.5:
                    signal_strength = "MODERATE_SIGNAL"
                    classification = "MODERATE_BUY"
                else:
                    signal_strength = "WEAK_SIGNAL"
                    classification = "WEAK_BUY"
            else:
                if value_crore > 5.0:
                    signal_strength = "STRONG_RED_FLAG"
                    classification = "STRONG_SELL"
                elif value_crore > 0.5:
                    signal_strength = "MODERATE_RED_FLAG"
                    classification = "MODERATE_SELL"
                else:
                    signal_strength = "NOTE_ONLY"
                    classification = "WEAK_SELL"
                    
            cursor.execute("""
                INSERT INTO promoter_activity (
                    date, ticker, person_name, designation, transaction_type, shares,
                    value_crore, holding_before, holding_after, signal_strength, classification,
                    source, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, ?, ?, 'BSE_API', 'MEDIUM')
            """, (db_today_str, ticker, person_name, designation, transaction_type, shares, value_crore, signal_strength, classification))
            saved_count += 1
            
        conn.commit()
        conn.close()
        logger.info(f"Promoters: Successfully processed {saved_count} promoter announcements from BSE API")
        return True
    except Exception as e:
        logger.info(f"Promoters: BSE fallback failed: {e}")
        return False

def fetch_bulk_deals():
    """Fetch recent bulk deals from NSE block-deal endpoint and cache them."""
    url = "https://www.nseindia.com/api/block-deals"
    try:
        data = nse_fetch(url)
        if not data or not isinstance(data, list):
            return False
            
        conn = get_db_connection()
        cursor = conn.cursor()
        saved = 0
        today_str = datetime.today().strftime("%Y-%m-%d")
        
        for deal in data:
            symbol = deal.get("symbol")
            if not symbol:
                continue
            
            client_name = deal.get("clientName", "Institutional Client")
            buy_sell = deal.get("buySell", "BUY").upper()
            qty = 0
            try:
                qty = int(str(deal.get("quantity", 0)).replace(",", ""))
            except ValueError:
                pass
                
            val_crore = 1.0
            try:
                val_crore = float(str(deal.get("value", 0)).replace(",", "")) / 100.0
            except ValueError:
                pass
                
            date_raw = deal.get("date")
            date_str = today_str
            if date_raw:
                try:
                    dt = datetime.strptime(date_raw.strip(), "%d-%b-%Y")
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    pass
                    
            ticker = f"{symbol}.NS"
            sig_strength = "MODERATE_SIGNAL" if buy_sell == "BUY" else "MODERATE_RED_FLAG"
            classification = f"BULK_{buy_sell}"
            
            cursor.execute("""
                INSERT INTO promoter_activity (
                    date, ticker, person_name, designation, transaction_type, shares,
                    value_crore, holding_before, holding_after, signal_strength, classification,
                    source, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0.0, 0.0, ?, ?, 'NSE_API', 'HIGH')
            """, (date_str, ticker, client_name, "Bulk Deal Client", buy_sell, qty, val_crore, sig_strength, classification))
            saved += 1
            
        conn.commit()
        conn.close()
        logger.info(f"Saved {saved} bulk/block deals.")
        return True
    except Exception as e:
        logger.warning(f"Failed to fetch bulk/block deals: {e}")
        return False

def get_promoter_signal(ticker):
    """Get the latest promoter activity signal for a ticker."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT * FROM promoter_activity 
            WHERE ticker = ? 
            ORDER BY date DESC, id DESC 
            LIMIT 1
        """, (ticker.upper(),))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "ticker": ticker.upper(),
            "date": None,
            "person_name": "No activity",
            "designation": "",
            "transaction_type": "NEUTRAL",
            "shares": 0,
            "value_crore": 0.0,
            "signal_strength": "WEAK_SIGNAL",
            "classification": "NEUTRAL"
        }
    finally:
        conn.close()

def get_recent_bulk_deals(days=5):
    """Retrieve bulk deal records from the past few days."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        today_str = datetime.today().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT * FROM promoter_activity 
            WHERE date >= date(?, '-' || ? || ' day') AND classification LIKE 'BULK_%'
            ORDER BY date DESC, id DESC
        """, (today_str, days))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_recent_promoter_activity(days=30):
    """Retrieve recent promoter and bulk transaction activity."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        today_str = datetime.today().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT * FROM promoter_activity 
            WHERE date >= date(?, '-' || ? || ' day')
            ORDER BY date DESC, id DESC
        """, (today_str, days))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
