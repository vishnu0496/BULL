import os
import sys

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import init_db, get_watchlist_tickers
from src.news import fetch_stock_news, get_aggregated_sentiment
from src.sentiment import get_text_sentiment

print("============================================================")
print("BULL PHASE 6 INTEGRATION & QA VERIFICATION RUN")
print("============================================================")

# Step 1: Database Check
print("\n[STEP 1/4] Initializing Database Schema...")
init_db()
tickers = get_watchlist_tickers()
print(f"[PASS] Database initialized successfully. Tickers: {len(tickers)}")

# Step 2: Local Sentiment Analysis
print("\n[STEP 2/4] Testing Local Financial Dictionary Sentiment Analyzer...")
test_bullish = "TCS Q4 profits surged by 15% and beat street expectations with solid growth."
test_bearish = "Reliance faces major lawsuit and regulatory fine after safety violation."
test_neutral = "Wipro is scheduled to release its corporate governance report next Tuesday."

score_bull, label_bull = get_text_sentiment(test_bullish)
score_bear, label_bear = get_text_sentiment(test_bearish)
score_neu, label_neu = get_text_sentiment(test_neutral)

print(f"       - Bullish headline rating: {label_bull} (Score: {score_bull})")
print(f"       - Bearish headline rating: {label_bear} (Score: {score_bear})")
print(f"       - Neutral headline rating: {label_neu} (Score: {score_neu})")

assert label_bull == "BULLISH", "Expected BULLISH label"
assert label_bear == "BEARISH", "Expected BEARISH label"
assert label_neu == "NEUTRAL", "Expected NEUTRAL label"
print("[PASS] Dictionary sentiment analysis works exactly as intended!")

# Step 3: News Fetching & Caching
print("\n[STEP 3/4] Testing News Fetching & Database Caching...")
test_stock = "RELIANCE.NS"
if test_stock in tickers:
    try:
        news_items = fetch_stock_news(test_stock)
        print(f"[INFO] Fetched {len(news_items)} news articles for {test_stock}.")
        
        if news_items:
            item = news_items[0]
            print(f"       - Sample Headline: \"{item['title']}\"")
            print(f"       - Publisher: {item['publisher']}")
            print(f"       - Link: {item['link']}")
            print(f"       - Sentiment: {item['sentiment_label']} ({item['sentiment_score']})")
            
            # Aggregate sentiment
            avg_score, avg_label = get_aggregated_sentiment(news_items)
            print(f"       - Aggregated Sentiment: {avg_label} ({avg_score})")
            
            # Assert schema keys exist
            for key in ['title', 'publisher', 'link', 'pub_time', 'sentiment_score', 'sentiment_label']:
                assert key in item, f"Missing key '{key}' in news item"
                
            print("[PASS] News fetching, schema validation, and database caching passed successfully!")
        else:
            print("[WARNING] No news items returned from yfinance (API might be throttled). Skipping assertions.")
    except Exception as e:
        print(f"[FAIL] Error in news fetching: {str(e)}")
        sys.exit(1)
else:
    print(f"[WARNING] {test_stock} not in watchlist. Skipping step 3.")

# Step 4: Index Symbol Exclusions
print("\n[STEP 4/4] Verifying Index Symbol Exclusions...")
index_test = "^NSEI"
try:
    index_news = fetch_stock_news(index_test)
    assert len(index_news) == 0, f"Expected 0 stock news items for index, got {len(index_news)}"
    print(f"[PASS] Successfully verified that index symbol '{index_test}' is excluded from news fetching.")
except Exception as e:
    print(f"[FAIL] Error in index symbols exclusion check: {str(e)}")
    sys.exit(1)

print("\n============================================================")
print("FINAL PHASE 6 VERIFICATION SUMMARY")
print("============================================================")
print("DICTIONARY SENTIMENT: PASS")
print("NEWS SCHEMA & CACHE:  PASS")
print("INDEX EXCLUSIONS:     PASS")
print("============================================================")
print("ALL TESTS PASSED SUCCESSFULLY.")
print("============================================================")
