import pandas as pd
import requests
import io
import time
from dhanhq import dhanhq
from datetime import datetime
from typing import Optional

from src.logger import get_logger

logger = get_logger(__name__)

# Global cache for instrument mapping to avoid downloading the large CSV multiple times
_INSTRUMENT_MAP = None

def get_dhan_client(client_id: str, access_token: str) -> Optional[dhanhq]:
    """Initialize and return the DhanHQ client."""
    if not client_id or not access_token:
        return None
    try:
        return dhanhq(client_id, access_token)
    except Exception as e:
        logger.error(f"Failed to initialize DhanHQ client: {e}")
        return None

def get_instrument_map() -> dict:
    """
    Downloads and caches Dhan's instrument master CSV.
    Maps readable NSE tickers (e.g., 'RELIANCE') to Dhan Security IDs.
    Returns a dictionary: {'RELIANCE': '2885', 'TCS': '11536', ...}
    """
    global _INSTRUMENT_MAP
    if _INSTRUMENT_MAP is not None:
        return _INSTRUMENT_MAP

    logger.info("Downloading DhanHQ Instrument Master CSV...")
    try:
        # Dhan's official security ID master list
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        # Parse CSV
        df = pd.read_csv(io.StringIO(response.text), low_memory=False)
        
        # Filter for NSE Equity (EXCH_ID == 'NSE' and SERIES == 'EQ')
        # Note: Dhan's CSV columns are typically: SEM_EXM_EXCH_ID, SEM_TRADING_SYMBOL, SEM_SMST_SECURITY_ID, SEM_SERIES
        nse_eq = df[(df['SEM_EXM_EXCH_ID'] == 'NSE') & (df['SEM_SERIES'] == 'EQ')]
        
        # Create map
        mapping = dict(zip(nse_eq['SEM_TRADING_SYMBOL'], nse_eq['SEM_SMST_SECURITY_ID']))
        _INSTRUMENT_MAP = mapping
        logger.info(f"Successfully mapped {len(mapping)} NSE equity instruments.")
        return mapping
    except Exception as e:
        logger.error(f"Failed to fetch Dhan instrument map: {e}")
        return {}

def fetch_historical_data_dhan(client: dhanhq, ticker: str, period: str = "1y") -> pd.DataFrame:
    """
    Fetches historical daily candle data via DhanHQ API and formats it exactly 
    like the Yahoo Finance output so it seamlessly plugs into our ML Engine.
    
    ticker: 'RELIANCE.NS' -> We strip '.NS' to get 'RELIANCE'
    period: Currently supports mapping '1y', '6mo' to appropriate dates.
    """
    clean_ticker = ticker.replace('.NS', '').strip().upper()
    
    inst_map = get_instrument_map()
    security_id = str(inst_map.get(clean_ticker, ""))
    
    if not security_id:
        logger.error(f"Ticker {clean_ticker} not found in Dhan instrument map.")
        raise ValueError(f"Dhan Mapping Failed for {ticker}")

    # Dhan API uses string dates 'YYYY-MM-DD'
    to_date = datetime.now()
    if period == "1y":
        from_date = to_date.replace(year=to_date.year - 1)
    elif period == "6mo":
        if to_date.month > 6:
            from_date = to_date.replace(month=to_date.month - 6)
        else:
            from_date = to_date.replace(year=to_date.year - 1, month=to_date.month + 6)
    elif period == "max":
        from_date = to_date.replace(year=to_date.year - 5) # Cap max at 5 years
    else:
        # Default 1y
        from_date = to_date.replace(year=to_date.year - 1)

    logger.info(f"Fetching Dhan historical data for {clean_ticker} ({security_id})...")
    
    try:
        # Dhan historical API call for Daily charts
        response = client.historical_daily_data(
            symbol=clean_ticker,
            exchange_segment=client.NSE,
            instrument_type=client.EQUITY,
            expiry_code=0,
            from_date=from_date.strftime('%Y-%m-%d'),
            to_date=to_date.strftime('%Y-%m-%d')
        )
        
        if response.get('status') != 'success':
            raise Exception(f"Dhan API Error: {response.get('remarks')}")
            
        data = response.get('data', {})
        if not data or 'open' not in data or not data['open']:
            raise Exception("No data returned from Dhan API.")

        # Reconstruct DataFrame to match Yahoo Finance shape
        # Dhan returns arrays of values in dict keys: 'start_Time', 'open', 'high', 'low', 'close', 'volume'
        df = pd.DataFrame({
            'Date': pd.to_datetime(data['start_Time']),
            'Open': data['open'],
            'High': data['high'],
            'Low': data['low'],
            'Close': data['close'],
            'Volume': data['volume']
        })
        
        df.set_index('Date', inplace=True)
        # yfinance columns are capitalized Open, High, Low, Close, Volume
        return df
        
    except Exception as e:
        logger.error(f"Dhan fetch failed for {ticker}: {e}")
        raise
