import os
import sys
import xml.etree.ElementTree as ET
import urllib.request
import urllib.parse
import email.utils
import time
import json
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

# Ensure project root is in path if executed directly
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src import database
from src.logger import get_logger

logger = get_logger(__name__)

INDEX_SYMBOLS = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
GEMINI_SENTIMENT_ENABLE_ENV = "BULL_ENABLE_GEMINI_SENTIMENT"
GEMINI_SENTIMENT_MAX_CALLS_ENV = "BULL_GEMINI_SENTIMENT_MAX_CALLS"
GEMINI_SENTIMENT_DEFAULT_MAX_CALLS = 20
GEMINI_SENTIMENT_WINDOW_SECONDS = 24 * 60 * 60

_gemini_credit_lock = threading.Lock()
_gemini_credit_window_started = time.time()
_gemini_credit_calls = 0

def _env_truthy(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

def _gemini_sentiment_enabled() -> bool:
    return _env_truthy(os.getenv(GEMINI_SENTIMENT_ENABLE_ENV))

def _gemini_credit_allowed() -> bool:
    """
    Conservative process-local governor. Gemini is local-only by default and,
    when explicitly enabled, capped to a small daily call budget.
    """
    if not _gemini_sentiment_enabled():
        return False

    try:
        max_calls = int(os.getenv(GEMINI_SENTIMENT_MAX_CALLS_ENV, GEMINI_SENTIMENT_DEFAULT_MAX_CALLS))
    except ValueError:
        max_calls = GEMINI_SENTIMENT_DEFAULT_MAX_CALLS

    if max_calls <= 0:
        return False

    global _gemini_credit_window_started, _gemini_credit_calls
    now = time.time()
    with _gemini_credit_lock:
        if now - _gemini_credit_window_started >= GEMINI_SENTIMENT_WINDOW_SECONDS:
            _gemini_credit_window_started = now
            _gemini_credit_calls = 0

        if _gemini_credit_calls >= max_calls:
            return False

        _gemini_credit_calls += 1
        return True

def parse_rss_date(date_str: str) -> int:
    """
    Convert pubDate string to unix epoch integer.
    E.g. 'Wed, 27 May 2026 07:00:00 GMT'
    """
    if not date_str:
        return int(time.time())
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        return int(dt.timestamp())
    except Exception:
        # Fallback patterns
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %Z",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return int(dt.timestamp())
            except ValueError:
                continue
        return int(time.time())

def analyze_sentiment_local(text: str) -> tuple[float, str]:
    """
    Robust rule-based financial dictionary analyzer.
    Counts positive/negative words and returns (score, label).
    """
    positive_words = {
        'profit', 'surge', 'expansion', 'dividend', 'deal', 'buy', 'win',
        'growth', 'surpasses', 'exceeds', 'rise', 'gain', 'acquisition',
        'partnership', 'success', 'orders', 'beat', 'upgrade', 'bullish',
        'jump', 'record', 'highest', 'advances', 'rally', 'positive',
        'favorable', 'strong', 'recovery', 'breakout', 'surged'
    }
    negative_words = {
        'loss', 'drop', 'deficit', 'slump', 'fine', 'scam', 'investigation',
        'debt', 'sell', 'decrease', 'fall', 'decline', 'lawsuit', 'penalty',
        'downgrade', 'bearish', 'investigate', 'plunges', 'crashes', 'weak',
        'dispute', 'regulatory', 'concerns', 'alert', 'cautions', 'warns', 'probe'
    }
    
    words = text.lower().split()
    pos_count = 0
    neg_count = 0
    for word in words:
        w = word.strip(".,;:?!'\"()[]{}")
        if w in positive_words:
            pos_count += 1
        elif w in negative_words:
            neg_count += 1
            
    total = pos_count + neg_count
    if total == 0:
        return 0.0, "NEUTRAL"
        
    score = (pos_count - neg_count) / total
    
    if score >= 0.15:
        label = "BULLISH"
    elif score <= -0.15:
        label = "BEARISH"
    else:
        label = "NEUTRAL"
        
    return round(score, 2), label

def analyze_sentiment_gemini_custom(text: str, api_key: str) -> tuple[float, str]:
    """
    Lightweight API helper for Google Gemini 1.5 Flash.
    """
    if not api_key or not api_key.strip() or not _gemini_credit_allowed():
        return analyze_sentiment_local(text)

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = (
        "You are a professional financial news analyst. "
        "Analyze the financial sentiment of this stock market headline. "
        "Provide your answer in strict JSON format with two keys:\n"
        "- 'verdict': must be either 'BULLISH', 'BEARISH', or 'NEUTRAL'\n"
        "- 'score': a decimal score from -1.0 (very bearish) to 1.0 (very bullish) explaining the intensity.\n\n"
        f"Headline: \"{text}\"\n\n"
        "Return ONLY the raw JSON object, no markdown, no ```json, no explanation."
    )
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    with urllib.request.urlopen(req, timeout=8) as response:
        res_data = response.read().decode("utf-8")
        res_json = json.loads(res_data)
        
        candidates = res_json.get('candidates', [])
        if not candidates:
            raise ValueError("No candidates found in Gemini response")
        parts = candidates[0].get('content', {}).get('parts', [])
        if not parts:
            raise ValueError("No content parts found in Gemini response")
        text_response = parts[0].get('text', '').strip()
        
        clean_text = text_response
        if clean_text.startswith("```"):
            lines = clean_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            clean_text = "\n".join(lines).strip()
            
        parsed = json.loads(clean_text)
        score = float(parsed.get('score', 0.0))
        label = str(parsed.get('verdict', 'NEUTRAL')).upper().strip()
        if label not in ['BULLISH', 'BEARISH', 'NEUTRAL']:
            label = 'NEUTRAL'
        return round(score, 2), label

def get_sentiment(text: str, gemini_api_key: str = None) -> tuple[float, str]:
    """
    Determine sentiment score and label. Uses local analysis by default.
    Gemini requires BULL_ENABLE_GEMINI_SENTIMENT=true and is capped by
    BULL_GEMINI_SENTIMENT_MAX_CALLS per process-day.
    """
    if gemini_api_key and gemini_api_key.strip() and _gemini_sentiment_enabled():
        try:
            return analyze_sentiment_gemini_custom(text, gemini_api_key)
        except Exception as e:
            logger.warning(f"Gemini API sentiment analysis failed: {e}. Falling back to local dictionary.")
            return analyze_sentiment_local(text)
    return analyze_sentiment_local(text)

def fetch_and_parse_google_news(ticker: str, gemini_api_key: str = None) -> list[dict]:
    """
    Fetches news RSS feed for a single ticker from Google News,
    parses the XML, and performs sentiment analysis on each item.
    """
    ticker_clean = ticker.strip().upper()
    if ticker_clean in INDEX_SYMBOLS:
        return []
        
    search_ticker = ticker_clean
    if ticker_clean.endswith('.NS') or ticker_clean.endswith('.BO'):
        search_ticker = ticker_clean[:-3]
        
    query = f"{search_ticker} stock news"
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    logger.info(f"Fetching RSS feed for {ticker_clean} (query: '{query}') from Google News")
    
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
    except Exception as e:
        logger.error(f"Network error fetching RSS feed for {ticker_clean}: {e}")
        return []
        
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        logger.error(f"XML parse error for {ticker_clean}: {e}")
        return []
        
    # Load sentiment cache to avoid redundant sentiment analysis for already analyzed titles
    sentiment_cache_map = {}
    try:
        # Load up to 30 days of cached news for this ticker to populate sentiment cache
        historical_cache = database.get_news_cache(ticker_clean, max_age_hours=24 * 30)
        for c_item in historical_cache:
            if 'title' in c_item:
                sentiment_cache_map[c_item['title']] = (
                    c_item.get('sentiment_score', 0.0),
                    c_item.get('sentiment_label', 'NEUTRAL')
                )
    except Exception as e:
        logger.debug(f"Could not load historical sentiment cache for {ticker_clean}: {e}")
        
    news_items = []
    items = root.findall('.//item')
    logger.info(f"Found {len(items)} raw RSS items for {ticker_clean}")
    
    for item in items:
        title = item.find('title').text if item.find('title') is not None else ""
        link = item.find('link').text if item.find('link') is not None else ""
        pub_date_str = item.find('pubDate').text if item.find('pubDate') is not None else ""
        
        if not title or not link:
            continue
            
        source_el = item.find('source')
        publisher = source_el.text if (source_el is not None and source_el.text) else "Google News"
        
        pub_time = parse_rss_date(pub_date_str)
        
        # Check sentiment cache first
        if title in sentiment_cache_map:
            score, label = sentiment_cache_map[title]
        else:
            score, label = get_sentiment(title, gemini_api_key)
            # Add to local map to handle duplicate titles in same batch
            sentiment_cache_map[title] = (score, label)
            
        news_items.append({
            'title': title,
            'publisher': publisher,
            'link': link,
            'pub_time': pub_time,
            'sentiment_score': score,
            'sentiment_label': label
        })
        
    return news_items

def fetch_and_parse_yfinance_news(ticker: str, gemini_api_key: str = None) -> list[dict]:
    """
    Fetches news from Yahoo Finance directly, parses it, and performs sentiment analysis.
    """
    ticker_clean = ticker.strip().upper()
    if ticker_clean in INDEX_SYMBOLS:
        return []
        
    logger.info(f"Fetching direct Yahoo Finance news for {ticker_clean}")
    try:
        t_obj = yf.Ticker(ticker_clean)
        yf_news = t_obj.news
        if not yf_news:
            return []
            
        # Get historical cache map to avoid duplicate sentiment runs
        sentiment_cache_map = {}
        try:
            historical_cache = database.get_news_cache(ticker_clean, max_age_hours=24 * 30)
            for c_item in historical_cache:
                if 'title' in c_item:
                    sentiment_cache_map[c_item['title']] = (
                        c_item.get('sentiment_score', 0.0),
                        c_item.get('sentiment_label', 'NEUTRAL')
                    )
        except Exception:
            pass
            
        news_items = []
        for item in yf_news:
            title = item.get('title', '')
            link = item.get('link', '')
            if not title:
                continue
                
            pub_time = int(item.get('providerPublishTime', int(time.time())))
            publisher = item.get('publisher', 'Yahoo Finance')
            
            if title in sentiment_cache_map:
                score, label = sentiment_cache_map[title]
            else:
                score, label = get_sentiment(title, gemini_api_key)
                sentiment_cache_map[title] = (score, label)
                
            news_items.append({
                'title': title,
                'publisher': publisher,
                'link': link,
                'pub_time': pub_time,
                'sentiment_score': score,
                'sentiment_label': label
            })
        return news_items
    except Exception as e:
        logger.error(f"Error fetching direct Yahoo Finance news for {ticker_clean}: {e}")
        return []

def scrape_ticker_news_workflow(ticker: str, gemini_api_key: str = None):
    """
    Scrapes, analyzes, and saves news cache for a single ticker from Google News AND Yahoo Finance.
    """
    try:
        google_news = fetch_and_parse_google_news(ticker, gemini_api_key)
        yfinance_news = fetch_and_parse_yfinance_news(ticker, gemini_api_key)
        
        # Combine and de-duplicate by title
        seen_titles = set()
        combined = []
        
        # Prioritize Yahoo Finance news because it has direct timestamps and links
        for item in yfinance_news + google_news:
            title_clean = item['title'].strip().lower()
            if title_clean not in seen_titles:
                seen_titles.add(title_clean)
                combined.append(item)
                
        if combined:
            database.save_news_cache(ticker, combined)
            logger.info(f"Successfully cached {len(combined)} de-duplicated news items for {ticker}")
        else:
            logger.info(f"No news items retrieved from Google News or Yahoo Finance for {ticker}")
    except Exception as e:
        logger.error(f"Error in scraping workflow for ticker {ticker}: {e}", exc_info=True)

def run_swarm_cycle(max_workers: int = 5):
    """
    Executes a single cycle of the swarm scraper: fetches watchlist tickers,
    runs scraping in parallel using worker threads, and saves items.
    """
    logger.info("Initializing Swarm cycle...")
    database.init_db()  # Make sure schema is created
    
    tickers = database.get_watchlist_tickers()
    if not tickers:
        logger.warning("Watchlist is empty. No tickers to scrape.")
        return
        
    logger.info(f"Watchlist tickers to scrape: {tickers}")
    
    settings = database.get_capital_settings()
    gemini_api_key = settings.get("gemini_api_key", "").strip() or None
    if gemini_api_key and _gemini_sentiment_enabled():
        logger.info("Gemini sentiment enabled by environment. Using semantic analysis with local fallback.")
    elif gemini_api_key:
        logger.info("Gemini API key configured, but Gemini sentiment is disabled by default. Using local dictionary analyzer.")
    else:
        logger.info("No Gemini API key configured. Using local dictionary analyzer.")
        
    # Execute scrape in multi-threaded thread pool
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scrape_ticker_news_workflow, ticker, gemini_api_key): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                future.result()
            except Exception as e:
                logger.error(f"Thread execution failed for ticker {ticker}: {e}")

class NewsScraperSwarm(threading.Thread):
    """
    Background worker thread running periodic scraping.
    """
    def __init__(self, interval_seconds: int = 300, max_workers: int = 5):
        super().__init__()
        self.interval_seconds = interval_seconds
        self.max_workers = max_workers
        self.daemon = True
        self.stop_event = threading.Event()
        self.name = "NewsScraperSwarm"
        
    def run(self):
        logger.info(f"NewsScraperSwarm background thread started with interval={self.interval_seconds}s")
        while not self.stop_event.is_set():
            try:
                run_swarm_cycle(max_workers=self.max_workers)
            except Exception as e:
                logger.error(f"Unexpected error in NewsScraperSwarm thread: {e}", exc_info=True)
                
            # Wait for next interval or stop signal
            slept = 0
            while slept < self.interval_seconds and not self.stop_event.is_set():
                time.sleep(1)
                slept += 1
                
        logger.info("NewsScraperSwarm background thread stopped.")
        
    def stop(self):
        self.stop_event.set()

_swarm_instance = None
_swarm_lock = threading.Lock()

def start_swarm(interval_seconds: int = 300, max_workers: int = 5):
    """
    Public API to start the background news scraper swarm.
    """
    global _swarm_instance
    with _swarm_lock:
        if _swarm_instance is not None and _swarm_instance.is_alive():
            logger.info("NewsScraperSwarm is already running.")
            return
        _swarm_instance = NewsScraperSwarm(interval_seconds=interval_seconds, max_workers=max_workers)
        _swarm_instance.start()
        logger.info("NewsScraperSwarm started successfully.")

def stop_swarm():
    """
    Public API to stop the background news scraper swarm.
    """
    global _swarm_instance
    with _swarm_lock:
        if _swarm_instance is not None:
            logger.info("Stopping NewsScraperSwarm...")
            _swarm_instance.stop()
            _swarm_instance.join(timeout=10)
            _swarm_instance = None
            logger.info("NewsScraperSwarm stopped.")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Standalone run for News Scraper Swarm")
    parser.add_argument("--ticker", type=str, help="Scrape a single specific ticker")
    parser.add_argument("--loop", action="store_true", help="Run continuously in a background loop")
    parser.add_argument("--interval", type=int, default=10, help="Interval in seconds for continuous loop")
    
    args = parser.parse_args()
    
    print("=== Standalone News Scraper Swarm ===")
    
    if args.ticker:
        ticker = args.ticker.upper()
        print(f"Scraping news for single ticker: {ticker}")
        settings = database.get_capital_settings()
        gemini_api_key = settings.get("gemini_api_key", "").strip() or None
        news_items = fetch_and_parse_google_news(ticker, gemini_api_key)
        print(f"Found {len(news_items)} items:")
        for idx, item in enumerate(news_items[:10], 1):
            print(f"{idx}. [{item['sentiment_label']}] {item['title']}")
            print(f"   Publisher: {item['publisher']} | Date Epoch: {item['pub_time']}")
            print(f"   Link: {item['link']}")
            print()
            
        # Optional: Save to DB cache
        database.save_news_cache(ticker, news_items)
        print("Scrape complete and saved to database cache.")
        
    elif args.loop:
        print(f"Starting continuous loop with interval {args.interval}s. Press Ctrl+C to exit.")
        start_swarm(interval_seconds=args.interval)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping swarm...")
            stop_swarm()
            print("Swarm stopped.")
            
    else:
        print("Running one single swarm cycle across the whole watchlist...")
        # If watchlist is empty, seed a default ticker just to showcase functionality
        tickers = database.get_watchlist_tickers()
        if not tickers:
            print("Watchlist was empty. Seeding RELIANCE.NS temporarily for demonstration.")
            database.add_to_watchlist("RELIANCE.NS", "Reliance Industries Ltd.", "Energy")
            
        run_swarm_cycle()
        
        # Verify cache content for watchlist tickers
        tickers = database.get_watchlist_tickers()
        print("\nChecking cached news counts in database:")
        for ticker in tickers[:5]:
            cached = database.get_news_cache(ticker, max_age_hours=24)
            print(f"- {ticker}: {len(cached)} cached items in last 24h")


def fetch_overnight_headlines() -> list[str]:
    import urllib.request
    import xml.etree.ElementTree as ET
    import urllib.parse
    
    query = "nifty sensex stock market india news"
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
    
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    )
    
    headlines = []
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            xml_data = response.read()
        root = ET.fromstring(xml_data)
        items = root.findall('.//item')
        for item in items[:5]:
            title = item.find('title').text if item.find('title') is not None else ""
            if title:
                # Strip source if format is "Headline - Source"
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]
                title = title.strip()
                if title and len(title) > 10:
                    headlines.append(title)
                if len(headlines) >= 3:
                    break
    except Exception:
        pass
        
    return headlines

def generate_morning_brief() -> str:
    """
    Compiles daily market intelligence brief in a phone-friendly WhatsApp style.
    """
    from datetime import datetime
    now = datetime.now()
    day_str = now.strftime("%A %d %b") # e.g. Wednesday 11 Jun
    
    # 1. Premarket Score & Nifty Open Estimator
    pm_score = 50.0
    gift_gap = 0.0
    try:
        from src.premarket_signals import get_premarket_score
        pm = get_premarket_score()
        pm_score = pm.get("pre_market_score", 50.0)
        gift_gap = pm.get("gift_nifty_gap", 0.0)
    except Exception:
        pass

    # 2. Market Mood Logic
    try:
        from src.macro_monitor import LATEST_MACRO
        macro_risk = LATEST_MACRO.get("global_risk", {}).get("level", "MEDIUM")
        risk_score = LATEST_MACRO.get("global_risk", {}).get("score", 0.0)
    except Exception:
        macro_risk = "MEDIUM"
        risk_score = 0.0
        
    high_urgency_neg_news = (macro_risk == "HIGH" or risk_score <= -0.25)
    
    if pm_score >= 65 and not high_urgency_neg_news:
        market_mood = "Bullish 🟢"
    elif pm_score <= 35 or macro_risk == "HIGH":
        market_mood = "Bearish 🔴"
    else:
        market_mood = "Cautious 🟡"

    # 3. FII Daily Flows
    fii_net_formatted = "Data pending"
    try:
        from src.fii_tracker import get_fii_signal
        fii = get_fii_signal()
        if fii and fii.get("source") != "NONE":
            fii_net = fii.get("fii_net", 0.0)
            if fii_net > 0:
                fii_net_formatted = f"Bought ₹{abs(fii_net):.0f} Cr yesterday"
            elif fii_net < 0:
                fii_net_formatted = f"Sold ₹{abs(fii_net):.0f} Cr yesterday"
            else:
                fii_net_formatted = "Neutral yesterday"
    except Exception:
        pass

    # 4. Today's Setups
    mentor_picks = []
    try:
        from src.engine import get_mentor_suggestions
        mentor_picks = get_mentor_suggestions()
    except Exception:
        pass
        
    trade_setups = [s for s in mentor_picks if s.get("decision") == "TRADE"]
    
    # Render WhatsApp message
    if trade_setups:
        trades_count_str = f"{len(trade_setups)} trade{'s' if len(trade_setups) > 1 else ''} today"
        setups_block = ""
        for s in trade_setups[:3]:
            ticker_raw = s['ticker']
            ticker_clean = ticker_raw.replace('.NS','')
            
            # Look up company name
            company_name = ticker_clean
            try:
                from src.database import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM watchlist WHERE ticker = ?", (ticker_raw.upper(),))
                row = cursor.fetchone()
                conn.close()
                if row and row['name']:
                    company_name = row['name']
            except Exception:
                pass
            
            entry = s.get('entry_trigger', 0.0)
            target = s.get('target_1', s.get('target', 0.0))
            stop_loss = s.get('stop_loss', 0.0)
            
            # Suggested quantity based on Vishnu's max risk (₹280)
            risk_per_share = abs(entry - stop_loss)
            qty = 1
            if risk_per_share > 0:
                qty = max(1, int(280 / risk_per_share))
            actual_max_loss = qty * risk_per_share
            
            target_gain_pct = ((target - entry) / entry * 100) if entry > 0 else 0.0
            
            # Plain English reason
            reasons = [r for r in s.get('reasons', []) if not r.startswith("⚠️ AI Sentiment Override")]
            reason_str = reasons[0] if reasons else "Strong buying volume and upward breakout momentum."
            prob = s.get('ml_probability', 0.5)
            
            setups_block += (
                f"{company_name.upper()} ({ticker_clean})\n"
                f"Buy at ₹{entry:.0f}\n"
                f"Keep stop loss at ₹{stop_loss:.0f} (maximum you can lose: ₹{actual_max_loss:.0f})\n"
                f"Target ₹{target:.0f} (+{target_gain_pct:.0f}%)\n"
                f"Reason: {reason_str} ML says {prob*100:.0f} % chance.\n\n"
            )
            
        brief_message = (
            f"🐂 BULL — {day_str}\n\n"
            f"✅ {trades_count_str}:\n\n"
            f"{setups_block.strip()}\n\n"
            f"Open bull-nxlh.onrender.com to log it.\n\n"
            f"—\n"
            f"Market mood: {market_mood}\n"
            f"FII: {fii_net_formatted}\n"
        )
    else:
        brief_message = (
            f"🐂 BULL — {day_str}\n\n"
            f"😴 No trades today.\n"
            f"Market is weak. Sit in cash.\n"
            f"Come back tomorrow.\n\n"
            f"—\n"
            f"Market mood: {market_mood}\n"
        )
    return brief_message.strip()

