import requests
import time
import logging
from functools import lru_cache

logger = logging.getLogger("bull.nse")

# Exact headers Chrome 120 sends to NSE — order matters
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate", 
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

NSE_API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "X-Requested-With": "XMLHttpRequest",
}

_session = None
_session_time = 0
SESSION_TTL = 300  # 5 minutes

def get_nse_session(force_new=False) -> requests.Session:
    """
    Returns a requests.Session that NSE accepts as a real browser.
    Reinitializes if session is older than SESSION_TTL seconds.
    """
    global _session, _session_time
    
    now = time.time()
    if not force_new and _session and (now - _session_time) < SESSION_TTL:
        return _session
    
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    
    try:
        # Step 1: Visit homepage to get cookies (exactly like a browser)
        logger.debug("NSE: Initializing session via homepage...")
        resp = session.get(
            "https://www.nseindia.com",
            timeout=10,
            allow_redirects=True
        )
        logger.debug(f"NSE: Homepage status {resp.status_code}, cookies: {list(session.cookies.keys())}")
        
        # Step 2: Critical — wait like a human would
        time.sleep(1.5)
        
        # Step 3: Visit markets page to deepen session
        session.headers.update({"Referer": "https://www.nseindia.com/"})
        session.get(
            "https://www.nseindia.com/market-data/live-equity-market",
            timeout=10
        )
        time.sleep(1.0)
        
        # Step 4: Switch to API headers for data calls
        session.headers.update(NSE_API_HEADERS)
        
        _session = session
        _session_time = now
        logger.info("NSE: Session initialized successfully")
        return session
        
    except Exception as e:
        logger.warning(f"NSE: Session init failed: {e}")
        # Return session anyway — might work for some endpoints
        session.headers.update(NSE_API_HEADERS)
        _session = session
        _session_time = now
        return session


def nse_fetch(url: str, session=None, max_retries=2) -> dict | None:
    """
    Fetch a NSE API URL with retry logic.
    Returns parsed JSON dict or None on failure.
    """
    if session is None:
        session = get_nse_session()
    
    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=12)
            
            if resp.status_code == 200:
                return resp.json()
            
            elif resp.status_code == 403:
                logger.warning(f"NSE: 403 on {url}, reinitializing session (attempt {attempt+1})")
                # Force new session on 403
                session = get_nse_session(force_new=True)
                time.sleep(2.0)
                continue
                
            elif resp.status_code == 429:
                logger.warning("NSE: Rate limited, waiting 10 seconds")
                time.sleep(10)
                continue
                
            else:
                logger.warning(f"NSE: Status {resp.status_code} for {url}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"NSE: Timeout on {url} (attempt {attempt+1})")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"NSE: Error fetching {url}: {e}")
            return None
    
    return None
