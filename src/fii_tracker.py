# src/fii_tracker.py
import logging
import sqlite3
import re
import xml.etree.ElementTree as ET
import requests
from datetime import datetime
from src.database import get_db_connection
from src.nse_session import nse_fetch

logger = logging.getLogger("bull.fii_tracker")

def fetch_fii_dii_data():
    """Fetch latest FII/DII flow data from NSE, falling back to Moneycontrol or yFinance on failure."""
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    
    # Try PRIMARY: NSE API
    try:
        logger.info("FII/DII: Fetching primary data from NSE API...")
        data = nse_fetch(url)
        if data and isinstance(data, list):
            grouped = {}
            for item in data:
                date_str = item.get("date")
                category = item.get("category")
                if not date_str or not category:
                    continue
                
                try:
                    dt = datetime.strptime(date_str.strip(), "%d-%b-%Y")
                    db_date = dt.strftime("%Y-%m-%d")
                except Exception as e:
                    logger.warning(f"FII/DII: Error parsing date {date_str}: {e}")
                    continue
                
                if db_date not in grouped:
                    grouped[db_date] = {}
                    
                try:
                    buy = float(str(item.get("buyValue", 0)).replace(",", ""))
                    sell = float(str(item.get("sellValue", 0)).replace(",", ""))
                    net = float(str(item.get("netValue", 0)).replace(",", ""))
                except ValueError:
                    buy, sell, net = 0.0, 0.0, 0.0
                    
                if "FII" in category.upper():
                    grouped[db_date]["fii_buy"] = buy
                    grouped[db_date]["fii_sell"] = sell
                    grouped[db_date]["fii_net"] = net
                elif "DII" in category.upper():
                    grouped[db_date]["dii_buy"] = buy
                    grouped[db_date]["dii_sell"] = sell
                    grouped[db_date]["dii_net"] = net
                    
            # Save to database
            conn = get_db_connection()
            cursor = conn.cursor()
            saved_count = 0
            for db_date, val in grouped.items():
                fii_buy = val.get("fii_buy", 0.0)
                fii_sell = val.get("fii_sell", 0.0)
                fii_net = val.get("fii_net", 0.0)
                dii_buy = val.get("dii_buy", 0.0)
                dii_sell = val.get("dii_sell", 0.0)
                dii_net = val.get("dii_net", 0.0)
                
                if fii_net > 2000:
                    impact = "STRONG_BULL"
                elif fii_net > 500:
                    impact = "MILD_BULL"
                elif fii_net < -2000:
                    impact = "STRONG_BEAR"
                elif fii_net < -500:
                    impact = "MILD_BEAR"
                else:
                    impact = "NEUTRAL"
                    
                cursor.execute("""
                    INSERT OR REPLACE INTO fii_dii_flows (
                        date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact, source, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NSE_API', 'HIGH')
                """, (db_date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, impact))
                saved_count += 1
            conn.commit()
            conn.close()
            logger.info(f"FII/DII: Successfully saved {saved_count} records from NSE API")
            return True
    except Exception as e:
        logger.warning(f"FII/DII: NSE API primary fetch failed: {e}")

    # Try FALLBACK 1: Moneycontrol RSS
    try:
        logger.info("FII/DII: Attempting Fallback 1: Moneycontrol RSS...")
        rss_url = "https://www.moneycontrol.com/rss/latestnews.xml"
        resp = requests.get(rss_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item"):
                title = item.find("title").text or ""
                if "FII" in title.upper() or "FOREIGN INSTITUTIONAL" in title.upper():
                    net_val = 0.0
                    match = re.search(r"(?:FII|FIIs).*?([\+\-]?\d[\d,]*)\s*crore", title, re.IGNORECASE)
                    if match:
                        net_val = float(match.group(1).replace(",", ""))
                        if "SELL" in title.upper() or "SOLD" in title.upper() or "NET SELLER" in title.upper():
                            net_val = -abs(net_val)
                        elif "BUY" in title.upper() or "BOUGHT" in title.upper() or "NET BUYER" in title.upper():
                            net_val = abs(net_val)
                        
                        dii_val = 0.0
                        dii_match = re.search(r"(?:DII|DIIs).*?([\+\-]?\d[\d,]*)\s*crore", title, re.IGNORECASE)
                        if dii_match:
                            dii_val = float(dii_match.group(1).replace(",", ""))
                            dii_index = title.upper().find("DII")
                            if dii_index != -1:
                                sub_str = title.upper()[dii_index:]
                                if "SELL" in sub_str or "SOLD" in sub_str:
                                    dii_val = -abs(dii_val)
                                elif "BUY" in sub_str or "BOUGHT" in sub_str:
                                    dii_val = abs(dii_val)
                                    
                        db_date = datetime.today().strftime("%Y-%m-%d")
                        impact = "STRONG_BULL" if net_val > 2000 else "MILD_BULL" if net_val > 500 else "STRONG_BEAR" if net_val < -2000 else "MILD_BEAR" if net_val < -500 else "NEUTRAL"
                        
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT OR REPLACE INTO fii_dii_flows (
                                date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact, source, confidence
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'MONEYCONTROL_RSS', 'MEDIUM')
                        """, (db_date, abs(net_val) if net_val > 0 else 0.0, abs(net_val) if net_val < 0 else 0.0, net_val, abs(dii_val) if dii_val > 0 else 0.0, abs(dii_val) if dii_val < 0 else 0.0, dii_val, impact))
                        conn.commit()
                        conn.close()
                        logger.info("FII/DII: Successfully saved FII flow from Moneycontrol RSS")
                        return True
    except Exception as e:
        logger.warning(f"FII/DII: Moneycontrol RSS fallback failed: {e}")

    # Try FALLBACK 2: yFinance Inference
    try:
        logger.info("FII/DII: Attempting Fallback 2: yFinance Inference...")
        import yfinance as yf
        df = yf.download("^NSEI", period="5d", interval="1d", progress=False)
        if df is not None and not df.empty and len(df) >= 2:
            # Handle multi-level columns from yfinance (just in case)
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            def get_val(series, col):
                val = series[col]
                if hasattr(val, 'iloc'):
                    return float(val.iloc[0])
                elif isinstance(val, (list, tuple)) or hasattr(val, '__getitem__'):
                    try:
                        return float(val[0])
                    except Exception:
                        return float(val)
                return float(val)

            close = get_val(latest, "Close")
            open_val = get_val(latest, "Open")
            vol = get_val(latest, "Volume")
            prev_vol = get_val(prev, "Volume")
            
            chg_pct = (close - open_val) / open_val * 100
            vol_up = vol > prev_vol
            
            if chg_pct > 0.5 and vol_up:
                net_val = 1200.0
                impact = "MILD_BULL"
            elif chg_pct > 1.2:
                net_val = 2500.0
                impact = "STRONG_BULL"
            elif chg_pct < -1.2:
                net_val = -2500.0
                impact = "STRONG_BEAR"
            elif chg_pct < -0.5 and vol_up:
                net_val = -1200.0
                impact = "MILD_BEAR"
            else:
                net_val = 100.0
                impact = "NEUTRAL"
                
            db_date = datetime.today().strftime("%Y-%m-%d")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO fii_dii_flows (
                    date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact, source, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'INFERRED', 'LOW')
            """, (db_date, abs(net_val) if net_val > 0 else 0.0, abs(net_val) if net_val < 0 else 0.0, net_val, 0.0, 0.0, 0.0, impact))
            conn.commit()
            conn.close()
            logger.info("FII/DII: Inferred FII flows from Nifty50 price and volume")
            return True
    except Exception as e:
        logger.warning(f"FII/DII: yFinance inference fallback failed: {e}")

    # FALLBACK 3: Static Neutral Signal
    try:
        logger.info("FII/DII: Attempting Fallback 3: Static Neutral...")
        db_date = datetime.today().strftime("%Y-%m-%d")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO fii_dii_flows (
                date, fii_buy, fii_sell, fii_net, dii_buy, dii_sell, dii_net, market_impact, source, confidence
            ) VALUES (?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 'NEUTRAL', 'NONE', 'LOW')
        """, (db_date,))
        conn.commit()
        conn.close()
        logger.info("FII/DII: Logged static neutral fallback flow")
        return True
    except Exception as e:
        logger.error(f"FII/DII: All fallbacks failed: {e}")
        return False

def get_fii_signal():
    """Retrieve the latest FII/DII signal, computing streaks and recommendations."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get latest record
        cursor.execute("SELECT * FROM fii_dii_flows ORDER BY date DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            # Return fallback
            return {
                "date": datetime.today().strftime("%Y-%m-%d"),
                "fii_buy": 0.0,
                "fii_sell": 0.0,
                "fii_net": 0.0,
                "dii_buy": 0.0,
                "dii_sell": 0.0,
                "dii_net": 0.0,
                "market_impact": "NEUTRAL",
                "streak_days": 0,
                "streak_type": "NEUTRAL",
                "signal_text": "No FII/DII data available.",
                "action": "HOLD",
                "source": "NONE",
                "confidence": "LOW"
            }
            
        latest = dict(row)
        
        # Query last 10 days to calculate streak
        cursor.execute("SELECT fii_net FROM fii_dii_flows ORDER BY date DESC LIMIT 10")
        rows = cursor.fetchall()
        nets = [r["fii_net"] for r in rows]
        
        streak_days = 0
        streak_type = "NEUTRAL"
        
        if nets:
            first_net = nets[0]
            if first_net > 0:
                streak_type = "BUY"
                for val in nets:
                    if val > 0:
                        streak_days += 1
                    else:
                        break
            elif first_net < 0:
                streak_type = "SELL"
                for val in nets:
                    if val < 0:
                        streak_days += 1
                    else:
                        break
                        
        # Generate signal text and action recommendation
        fii_net = latest["fii_net"]
        dii_net = latest["dii_net"]
        impact = latest["market_impact"]
        
        action = "HOLD"
        if impact == "STRONG_BULL":
            action = "BUY"
            signal_text = f"Strong FII buying (+{fii_net:.1f} Cr) indicates high institutional demand."
        elif impact == "MILD_BULL":
            action = "BUY"
            signal_text = f"Mild FII buying (+{fii_net:.1f} Cr) supports market upside."
        elif impact == "STRONG_BEAR":
            action = "WAIT"
            signal_text = f"Heavy FII selling ({fii_net:.1f} Cr) indicates institutional exit. Stay cautious."
        elif impact == "MILD_BEAR":
            action = "HOLD"
            signal_text = f"Mild FII selling ({fii_net:.1f} Cr) suggests consolidation."
        else:
            signal_text = f"FII activity is flat ({fii_net:.1f} Cr). Market driven by local flows."
            
        if streak_days >= 3 and streak_type == "SELL":
            action = "WAIT"
            signal_text += f" FIIs are on a {streak_days}-day selling streak."
        elif streak_days >= 3 and streak_type == "BUY":
            signal_text += f" FIIs are on a {streak_days}-day buying streak."
            
        return {
            "date": latest["date"],
            "fii_buy": latest["fii_buy"],
            "fii_sell": latest["fii_sell"],
            "fii_net": fii_net,
            "dii_buy": latest["dii_buy"],
            "dii_sell": latest["dii_sell"],
            "dii_net": dii_net,
            "market_impact": impact,
            "streak_days": streak_days,
            "streak_type": streak_type,
            "signal_text": signal_text,
            "action": action,
            "source": latest.get("source", "NSE_API"),
            "confidence": latest.get("confidence", "HIGH")
        }
    finally:
        conn.close()

def get_fii_history(days=30):
    """Retrieve history of FII/DII flows for charting/table."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM fii_dii_flows 
            ORDER BY date DESC 
            LIMIT ?
        """, (days,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
