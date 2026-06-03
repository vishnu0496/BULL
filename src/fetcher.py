import yfinance as yf
import pandas as pd
from datetime import datetime
import time
from src.database import add_to_watchlist, save_prices, get_capital_settings
from src.dhan_integration import get_dhan_client, fetch_historical_data_dhan
from src.logger import get_logger

logger = get_logger(__name__)

def fetch_ticker_metadata(ticker: str):
    """
    Fetch ticker metadata (company name, industry/sector) from yfinance.
    Appends '.NS' to symbol if not already present.
    """
    ticker_clean = ticker.strip().upper()
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            ticker_obj = yf.Ticker(ticker_clean)
            info = ticker_obj.info
            
            # Extract name and industry
            name = info.get('longName') or info.get('shortName') or ticker_clean
            industry = info.get('industry') or info.get('sector') or 'Unknown Sector'
            
            return {
                'ticker': ticker_clean,
                'name': name,
                'industry': industry,
                'success': True,
                'error': None
            }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay ** attempt)
            else:
                return {
                    'ticker': ticker_clean,
                    'name': ticker_clean,
                    'industry': 'Unknown Sector',
                    'success': False,
                    'error': str(e)
                }

def fetch_historical_data(ticker: str, period: str = "1y"):
    """
    Fetch historical daily End of Day (EOD) data for a given ticker.
    Prioritizes DhanHQ API if credentials exist. Falls back to yfinance.
    """
    ticker_clean = ticker.strip().upper()
    
    # 1. Try DhanHQ first
    settings = get_capital_settings()
    dhan_client_id = settings.get('dhan_client_id', '')
    dhan_access_token = settings.get('dhan_access_token', '')
    
    if dhan_client_id and dhan_access_token:
        try:
            client = get_dhan_client(dhan_client_id, dhan_access_token)
            if client:
                df = fetch_historical_data_dhan(client, ticker_clean, period=period)
                if not df.empty:
                    df = df.reset_index()
                    df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
                    df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
                    df = df.ffill()
                    # Anomaly detection
                    if len(df) > 1:
                        pct_change = df['Close'].pct_change().abs()
                        anomalies = df[pct_change > 0.30]
                        for idx, row in anomalies.iterrows():
                            logger.warning(f"Anomaly detected for {ticker_clean} on {row['Date']}. Moved > 30%, potential Stock Split.")
                    return df
        except Exception as e:
            logger.error(f"DhanHQ fetch failed for {ticker_clean}, falling back to yfinance: {e}")

    # 2. Fallback to yfinance
    max_retries = 3
    base_delay = 2
    
    for attempt in range(max_retries):
        try:
            ticker_obj = yf.Ticker(ticker_clean)
            df = ticker_obj.history(period=period)
            
            if df.empty:
                return pd.DataFrame()
                
            # Select required columns and reset index to extract date
            df = df.reset_index()
            # Standardize column casing
            df.columns = [c.capitalize() if c in ['Open', 'High', 'Low', 'Close', 'Volume'] else c for c in df.columns]
            
            # Ensure 'Date' column is formatted
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
                
            df = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']]
            
            # Forward-fill to handle any missing values
            df = df.ffill()
            
            # Anomaly detection: if a stock moves > 30% in a single day, log it
            if len(df) > 1:
                pct_change = df['Close'].pct_change().abs()
                anomalies = df[pct_change > 0.30]
                for idx, row in anomalies.iterrows():
                    print(f"WARNING: Anomaly detected for {ticker_clean} on {row['Date']}. Moved > 30%, potential Stock Split.")
                    
            return df
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(base_delay ** attempt)
            else:
                print(f"Error fetching historical data for {ticker_clean}: {e}")
                return pd.DataFrame()

def sync_ticker(ticker: str, period: str = "1y"):
    """
    Fetch metadata and historical prices for a ticker, updating the database.
    """
    ticker_clean = ticker.strip().upper()
    
    # 1. Fetch metadata first to update name/sector
    meta = fetch_ticker_metadata(ticker_clean)
    if meta['success']:
        add_to_watchlist(ticker_clean, meta['name'], meta['industry'])
        
    # 2. Fetch history
    df_prices = fetch_historical_data(ticker_clean, period=period)
    if not df_prices.empty:
        save_prices(ticker_clean, df_prices)
        return {
            'ticker': ticker_clean,
            'rows_synced': len(df_prices),
            'success': True,
            'name': meta['name'],
            'industry': meta['industry']
        }
    else:
        return {
            'ticker': ticker_clean,
            'rows_synced': 0,
            'success': False,
            'name': meta['name'],
            'industry': meta['industry']
        }
