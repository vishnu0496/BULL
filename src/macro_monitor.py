import threading
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import yfinance as yf
from src.logger import get_logger
from src.sentiment import analyze_sentiment_local

logger = get_logger(__name__)

# Global thread-safe dictionary mapping indicator name -> data dict
LATEST_MACRO = {
    "crude_oil": {"price": 75.0, "change_pct": 0.0},
    "usd_inr": {"price": 83.3, "change_pct": 0.0},
    "us_10y_yield": {"price": 4.2, "change_pct": 0.0},
    "global_risk": {"level": "MEDIUM", "score": 0.0, "reason": "System initializing..."}
}
MACRO_LOCK = threading.Lock()

_macro_thread = None
_stop_macro_event = threading.Event()

def get_ticker_macro_data(ticker_symbol: str) -> tuple[float, float]:
    """Retrieve price and 1-day percentage change from yfinance history safely."""
    try:
        ticker = yf.Ticker(ticker_symbol)
        # Fetch 3 days to be absolutely sure we have 2 complete daily candles
        hist = ticker.history(period="3d")
        if hist.empty:
            return 0.0, 0.0
        
        closes = hist["Close"].dropna()
        if len(closes) >= 2:
            current_price = float(closes.iloc[-1])
            prev_price = float(closes.iloc[-2])
            change_pct = ((current_price - prev_price) / prev_price) * 100
            return round(current_price, 2), round(change_pct, 2)
        elif len(closes) == 1:
            return round(float(closes.iloc[0]), 2), 0.0
    except Exception as e:
        logger.error(f"Error fetching macro ticker {ticker_symbol}: {e}")
    return 0.0, 0.0

def fetch_global_risk_sentiment() -> tuple[str, float, str]:
    """
    Queries Google News for geopolitical, war, and macroeconomic shocks.
    Parses headlines and runs local sentiment score calculation.
    """
    query = "geopolitics war inflation fed rate hikes tariff"
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        
        if not items:
            return "MEDIUM", 0.0, "No global shock headlines found."
            
        scores = []
        headlines = []
        for item in items[:15]:  # Process the top 15 news headlines
            title = item.find('title').text if item.find('title') is not None else ""
            if title:
                score, _ = analyze_sentiment_local(title)
                scores.append(score)
                headlines.append(title.lower())
                
        if not scores:
            return "MEDIUM", 0.0, "No valid headlines analyzed."
            
        avg_score = sum(scores) / len(scores)
        
        # Decide risk level based on sentiment
        if avg_score <= -0.12:
            level = "HIGH"
        elif avg_score >= 0.12:
            level = "LOW"
        else:
            level = "MEDIUM"
            
        # Extract a short reason based on key terms in headlines
        reason = "Global macro conditions stable."
        keywords = {
            "war": "Geopolitical conflict headline tension.",
            "inflation": "Global inflation pressures.",
            "fed": "US Federal Reserve rate decision outlook.",
            "tariff": "Trade war/tariff threat signals.",
            "oil": "Crude oil market volatility."
        }
        for kw, text in keywords.items():
            if any(kw in h for h in headlines):
                reason = text
                break
                
        return level, round(avg_score, 2), reason
    except Exception as e:
        logger.error(f"Error fetching global risk sentiment: {e}")
        return "MEDIUM", 0.0, "Failed to monitor geopolitics. Defaulting to safe neutral."

def _run_macro_monitor():
    """Background loop that refreshes global indicators and geopolitics threat levels every 30 seconds."""
    global LATEST_MACRO
    
    logger.info("Macro monitor background loop started.")
    while not _stop_macro_event.is_set():
        try:
            # 1. Fetch Crude Oil, USD/INR, and US 10-Year Bond Yield
            crude_price, crude_change = get_ticker_macro_data("CL=F")
            usd_inr_price, usd_inr_change = get_ticker_macro_data("INR=X")
            us10y_price, us10y_change = get_ticker_macro_data("^TNX")
            
            # 2. Fetch Geopolitical & Macro Risk Sentiment
            risk_level, risk_score, risk_reason = fetch_global_risk_sentiment()
            
            # 3. Update global thread-safe dict
            with MACRO_LOCK:
                if crude_price > 0:
                    LATEST_MACRO["crude_oil"] = {"price": crude_price, "change_pct": crude_change}
                if usd_inr_price > 0:
                    LATEST_MACRO["usd_inr"] = {"price": usd_inr_price, "change_pct": usd_inr_change}
                if us10y_price > 0:
                    LATEST_MACRO["us_10y_yield"] = {"price": us10y_price, "change_pct": us10y_change}
                
                LATEST_MACRO["global_risk"] = {
                    "level": risk_level,
                    "score": risk_score,
                    "reason": risk_reason
                }
            
            logger.info(f"Macro monitor cycle completed: Crude={crude_price} ({crude_change}%), USD/INR={usd_inr_price}, Risk={risk_level}")
        except Exception as e:
            logger.error(f"Error in macro monitor cycle: {e}")
            
        # Sleep for 30 seconds or wake up if stop is called
        slept = 0
        while slept < 30 and not _stop_macro_event.is_set():
            time.sleep(1)
            slept += 1
            
    logger.info("Macro monitor background loop stopped.")

def start_macro_monitor():
    """Starts the macro monitor thread if not active."""
    global _macro_thread, _stop_macro_event
    with MACRO_LOCK:
        if _macro_thread is not None and _macro_thread.is_alive():
            return
        _stop_macro_event.clear()
        _macro_thread = threading.Thread(target=_run_macro_monitor, daemon=True, name="MacroGeopoliticalMonitor")
        _macro_thread.start()
        logger.info("Global Macro Geopolitical Monitor started successfully.")

def stop_macro_monitor():
    """Stops the macro monitor thread."""
    global _macro_thread, _stop_macro_event
    with MACRO_LOCK:
        if _macro_thread is not None:
            _stop_macro_event.set()
            _macro_thread.join(timeout=5)
            _macro_thread = None
            logger.info("Global Macro Geopolitical Monitor stopped.")
