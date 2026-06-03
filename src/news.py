import yfinance as yf
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

from src.database import get_news_cache, save_news_cache, get_capital_settings
from src.sentiment import get_text_sentiment

INDEX_SYMBOLS = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}
NEWS_MAX_AGE_DAYS = 7
FUTURE_TOLERANCE_SECONDS = 6 * 60 * 60


def _is_recent_news(pub_time: int, now_ts: Optional[int] = None, max_age_days: int = NEWS_MAX_AGE_DAYS) -> bool:
    now_ts = now_ts or int(datetime.now().timestamp())
    if pub_time > now_ts + FUTURE_TOLERANCE_SECONDS:
        return False
    return now_ts - pub_time <= max_age_days * 24 * 60 * 60


def _fetch_google_news_rss(ticker: str) -> list[dict]:
    """Fetch free Google News RSS headlines for an Indian stock ticker."""
    symbol = ticker.replace(".NS", "").replace(".BO", "")
    query = quote_plus(f"{symbol} NSE stock India")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        response = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "BULL-local-research-dashboard/1.0"},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception:
        return []

    items = []
    now_ts = int(datetime.now().timestamp())
    for node in root.findall(".//item")[:10]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        publisher = (node.findtext("source") or "Google News").strip()
        pub_date = node.findtext("pubDate")
        try:
            pub_time = int(parsedate_to_datetime(pub_date).timestamp()) if pub_date else int(datetime.now().timestamp())
        except Exception:
            pub_time = int(datetime.now().timestamp())

        if title and _is_recent_news(pub_time, now_ts):
            items.append({
                "ticker": ticker,
                "title": title,
                "publisher": publisher,
                "link": link,
                "pub_time": pub_time,
            })
    return items

def fetch_stock_news(ticker: str, gemini_api_key: str = None, force_refresh: bool = False) -> list[dict]:
    """
    Fetch pre-market and EOD news articles for a ticker.
    Applies the sentiment analysis to each headline, and caches the results in SQLite.
    
    Parameters:
        ticker (str): The stock symbol (e.g. 'RELIANCE.NS').
        gemini_api_key (str): Optional Gemini API Key for semantic sentiment.
        force_refresh (bool): If True, skips cache checks and fetches fresh data.
        
    Returns:
        list[dict]: List of news items with keys: title, link, publisher, pub_time, sentiment_score, sentiment_label
    """
    ticker = ticker.strip().upper()
    
    # Exclude index symbols from stock-specific news fetching
    if ticker in INDEX_SYMBOLS:
        return []
        
    # Check cache first (unless force refresh is True)
    if not force_refresh:
        cached = get_news_cache(ticker, max_age_hours=2)
        if cached:
            return cached
            
    # Fetch fresh from yfinance
    try:
        t_obj = yf.Ticker(ticker)
        yf_news = t_obj.news or []
            
        news_list = []
        
        # Aggressively cache Gemini sentiment analysis results
        sentiment_cache_map = {}
        try:
            # Fetch last 30 days of cache for this ticker to avoid re-analyzing known headlines
            historical_cache = get_news_cache(ticker, max_age_hours=24*30)
            for c_item in historical_cache:
                if 'title' in c_item:
                    sentiment_cache_map[c_item['title']] = (c_item.get('sentiment_score', 0.0), c_item.get('sentiment_label', 'NEUTRAL'))
        except Exception:
            pass

        for item in yf_news:
            title = item.get('title', '')
            if not title:
                continue
            pub_time = int(item.get('providerPublishTime', int(datetime.now().timestamp())))
            if not _is_recent_news(pub_time):
                continue
                
            # Perform sentiment analysis
            if title in sentiment_cache_map:
                score, label = sentiment_cache_map[title]
            else:
                score, label = get_text_sentiment(title, gemini_api_key)
            
            news_list.append({
                'ticker': ticker,
                'title': title,
                'publisher': item.get('publisher', 'Yahoo Finance'),
                'link': item.get('link', ''),
                'pub_time': pub_time,
                'sentiment_score': score,
                'sentiment_label': label
            })

        existing_titles = {item["title"] for item in news_list}
        for item in _fetch_google_news_rss(ticker):
            title = item["title"]
            if title in existing_titles:
                continue
            score, label = sentiment_cache_map.get(title, get_text_sentiment(title, gemini_api_key))
            item["sentiment_score"] = score
            item["sentiment_label"] = label
            news_list.append(item)
            existing_titles.add(title)
            
        # Save to DB cache
        if news_list:
            save_news_cache(ticker, news_list)
            
        return news_list
        
    except Exception:
        # Fallback to expired cache if fetching fails
        try:
            return get_news_cache(ticker, max_age_hours=72)
        except Exception:
            return []

def get_aggregated_sentiment(news_list: list[dict]) -> tuple[float, str]:
    """
    Aggregate individual news sentiment scores to get a single rating for the stock.
    Returns:
        tuple[float, str]: (avg_score, label)
    """
    if not news_list:
        return 0.0, "NEUTRAL"
        
    scores = [item['sentiment_score'] for item in news_list]
    avg_score = sum(scores) / len(scores)
    
    if avg_score >= 0.15:
        label = "BULLISH"
    elif avg_score <= -0.15:
        label = "BEARISH"
    else:
        label = "NEUTRAL"
        
    return round(avg_score, 2), label

def warm_news_cache():
    """
    Background job function to warm up the news cache for top Nifty stocks.
    Triggers a forced refresh so that sentiment is pre-computed.
    """
    settings = get_capital_settings()
    api_key = settings.get('gemini_api_key', '')

    top_stocks = [
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", 
        "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS"
    ]
    for ticker in top_stocks:
        print(f"Warming news cache for {ticker}...")
        try:
            fetch_stock_news(ticker, gemini_api_key=api_key, force_refresh=True)
        except Exception as e:
            print(f"Error warming cache for {ticker}: {e}")
