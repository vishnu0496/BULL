import asyncio
import math
import random
import threading
import time
from typing import Dict, Tuple, Set

from src.database import get_watchlist_tickers, get_latest_price, get_prices
from src.engine import calculate_atr

# Global thread-safe dictionary mapping ticker -> current_price
LATEST_PRICES: Dict[str, float] = {}
LATEST_PRICE_METADATA: Dict[str, dict] = {}
PRICES_LOCK = threading.Lock()

PRICE_FEED_SOURCE = "simulated"
PRICE_FEED_KIND = "simulated_intraday_tick"
PRICE_BASELINE_SOURCE = "stored_eod_close"

# Set of registered subscriber queues: (queue, loop)
SUBSCRIBERS: Set[Tuple[asyncio.Queue, asyncio.AbstractEventLoop]] = set()
SUBSCRIBERS_LOCK = threading.Lock()

# Background thread state
_feed_thread = None
_stop_feed_event = threading.Event()

def _run_price_feed():
    """Background thread loop that updates simulated prices every second."""
    import pandas as pd
    from src.paper_broker import process_simulated_orders

    last_refresh_time = 0.0
    ticker_data = {}  # ticker -> {'atr': float, 'close_base': float, 'baseline_date': str}

    while not _stop_feed_event.is_set():
        current_time = time.time()
        
        # Refresh watchlist and baseline price + ATR configs every 10 seconds
        if current_time - last_refresh_time > 10.0:
            try:
                tickers = get_watchlist_tickers()
                
                # Clean up tickers no longer in watchlist
                for t in list(ticker_data.keys()):
                    if t not in tickers:
                        ticker_data.pop(t, None)
                        with PRICES_LOCK:
                            LATEST_PRICES.pop(t, None)
                            LATEST_PRICE_METADATA.pop(t, None)
                
                # Fetch baseline close and ATR for new tickers
                for ticker in tickers:
                    if ticker not in ticker_data:
                        close, baseline_date = get_latest_price(ticker)
                        if close is None:
                            # Skip if there's no stored price
                            continue
                        
                        df = get_prices(ticker)
                        if not df.empty and len(df) >= 14:
                            atr_series = calculate_atr(df)
                            atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else close * 0.02
                        else:
                            atr = close * 0.02
                        
                        # Initialize latest price
                        with PRICES_LOCK:
                            if ticker not in LATEST_PRICES:
                                LATEST_PRICES[ticker] = close
                            LATEST_PRICE_METADATA[ticker] = {
                                "source": PRICE_FEED_SOURCE,
                                "is_simulated": True,
                                "price_kind": PRICE_FEED_KIND,
                                "baseline_source": PRICE_BASELINE_SOURCE,
                                "baseline_price": close,
                                "baseline_date": baseline_date,
                                "not_real_market_data": True,
                            }
                        
                        ticker_data[ticker] = {
                            'atr': atr,
                            'close_base': close,
                            'baseline_date': baseline_date
                        }
                
                last_refresh_time = current_time
            except Exception as e:
                # Log or print error, don't crash the loop
                print(f"[Price Feed] Error refreshing configurations: {e}")

        # Simulate price updates for all tickers
        updates = []
        with PRICES_LOCK:
            for ticker, config in ticker_data.items():
                current_price = LATEST_PRICES.get(ticker, config['close_base'])
                atr = config['atr']
                close_base = config['close_base']
                baseline_date = config.get('baseline_date')
                
                # Standard daily volatility = ATR / baseline close
                daily_vol = atr / close_base if close_base > 0 else 0.02
                # Scale daily volatility to 1-second ticks using sqrt(390 * 60)
                scale = math.sqrt(390 * 60)
                tick_vol = daily_vol / scale
                
                # Simulate using normal distribution
                rand = random.normalvariate(0, 1)
                change_pct = rand * tick_vol
                new_price = current_price * (1.0 + change_pct)
                new_price = round(new_price, 2)
                
                # Prevent non-positive prices
                if new_price <= 0.01:
                    new_price = 0.01
                
                LATEST_PRICES[ticker] = new_price
                metadata = {
                    "source": PRICE_FEED_SOURCE,
                    "is_simulated": True,
                    "price_kind": PRICE_FEED_KIND,
                    "baseline_source": PRICE_BASELINE_SOURCE,
                    "baseline_price": close_base,
                    "baseline_date": baseline_date,
                    "not_real_market_data": True,
                    "generated_at": current_time,
                }
                LATEST_PRICE_METADATA[ticker] = metadata
                updates.append({
                    "type": "price",
                    "ticker": ticker,
                    "price": new_price,
                    **metadata,
                })
        
        # Dispatch updates to subscribers if any
        if updates:
            with SUBSCRIBERS_LOCK:
                for queue, loop in list(SUBSCRIBERS):
                    for update in updates:
                        try:
                            # Post to the subscriber's asyncio event loop safely
                            loop.call_soon_threadsafe(queue.put_nowait, update)
                        except Exception:
                            # Subscriber queue might be closed/full
                            pass
            
            # Process simulated orders in paper broker with current LATEST_PRICES snapshot
            try:
                with PRICES_LOCK:
                    prices_snapshot = dict(LATEST_PRICES)
                process_simulated_orders(prices_snapshot)
            except Exception as e:
                print(f"[Price Feed] Error in process_simulated_orders: {e}")
                
        # Dispatch macro updates to subscribers every second
        try:
            from src.macro_monitor import LATEST_MACRO, MACRO_LOCK
            with MACRO_LOCK:
                macro_snapshot = dict(LATEST_MACRO)
            
            macro_update = {
                "type": "macro",
                "crude_oil": macro_snapshot["crude_oil"],
                "usd_inr": macro_snapshot["usd_inr"],
                "us_10y_yield": macro_snapshot["us_10y_yield"],
                "global_risk": macro_snapshot["global_risk"]
            }
            
            with SUBSCRIBERS_LOCK:
                for queue, loop in list(SUBSCRIBERS):
                    try:
                        loop.call_soon_threadsafe(queue.put_nowait, macro_update)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Price Feed] Error sending macro updates: {e}")
            
        time.sleep(1.0)

def start_price_feed():
    """Starts the simulated price feed background thread if not already running."""
    global _feed_thread, _stop_feed_event
    if _feed_thread is not None and _feed_thread.is_alive():
        return
    
    _stop_feed_event.clear()
    _feed_thread = threading.Thread(target=_run_price_feed, daemon=True, name="SimulatedPriceFeed")
    _feed_thread.start()
    print("[Price Feed] Background thread started.")

def stop_price_feed():
    """Stops the simulated price feed background thread."""
    global _feed_thread, _stop_feed_event
    if _feed_thread is not None:
        _stop_feed_event.set()
        _feed_thread.join(timeout=2.0)
        _feed_thread = None
        print("[Price Feed] Background thread stopped.")

async def stream_prices():
    """Async generator yielding price updates to subscribers."""
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()
    
    with SUBSCRIBERS_LOCK:
        SUBSCRIBERS.add((queue, loop))
        
    try:
        while True:
            # Yield updates one by one as they arrive in the queue
            update = await queue.get()
            yield update
    finally:
        with SUBSCRIBERS_LOCK:
            SUBSCRIBERS.discard((queue, loop))

if __name__ == "__main__":
    # Standard test script
    print("Starting simulated price feed in test mode...")
    start_price_feed()
    try:
        for _ in range(5):
            time.sleep(1.0)
            with PRICES_LOCK:
                print(f"Latest prices: {LATEST_PRICES}")
    finally:
        stop_price_feed()
