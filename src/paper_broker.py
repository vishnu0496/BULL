import time
import re
from datetime import datetime
from src.database import (
    get_capital_settings,
    get_portfolio_holdings,
    add_paper_trade,
    get_paper_trades,
    get_watchlist_tickers
)

# In-memory trade ideas cache to avoid slowing down the price feed with ML predictions every tick
_TRADE_IDEAS_CACHE = {}
_LAST_IDEA_GENERATION = 0.0
IDEA_GENERATION_INTERVAL = 300.0  # 5 minutes

def parse_targets_from_notes(notes: str) -> tuple[float | None, float | None]:
    """Parse Target 1 and Stop Loss from trade notes."""
    if not notes:
        return None, None
    
    target_match = re.search(r"Target 1:\s*([\d\.]+)", notes)
    stop_match = re.search(r"Stop Loss:\s*([\d\.]+)", notes)
    
    target = float(target_match.group(1)) if target_match else None
    stop = float(stop_match.group(1)) if stop_match else None
    return target, stop

def get_last_buy_trade_info(ticker: str) -> tuple[float | None, float | None]:
    """Retrieve last BUY trade targets from paper journal database."""
    try:
        df = get_paper_trades()
        if df.empty:
            return None, None
        df_filtered = df[(df['ticker'].str.upper() == ticker.upper()) & (df['action'].str.upper() == 'BUY')]
        if df_filtered.empty:
            return None, None
        latest_buy = df_filtered.iloc[0]
        notes = latest_buy.get('notes', '')
        return parse_targets_from_notes(notes)
    except Exception as e:
        print(f"[Paper Broker] Error retrieving last buy trade info: {e}")
        return None, None

def get_setup_for_ticker(ticker: str) -> dict:
    """Get or generate trade setup for a ticker using cache to prevent performance lags."""
    global _LAST_IDEA_GENERATION
    ticker = ticker.upper()
    now = time.time()
    if ticker not in _TRADE_IDEAS_CACHE or (now - _LAST_IDEA_GENERATION) > IDEA_GENERATION_INTERVAL:
        try:
            from src.engine import generate_trade_idea
            idea = generate_trade_idea(ticker)
            _TRADE_IDEAS_CACHE[ticker] = idea
            _LAST_IDEA_GENERATION = now
        except Exception as e:
            print(f"[Paper Broker] Error generating trade idea for {ticker}: {e}")
    return _TRADE_IDEAS_CACHE.get(ticker)

def process_simulated_orders(current_prices: dict):
    """
    [DEACTIVATED] Check price triggers and execute mock orders.
    Autonomous execution is completely disabled as per user configuration.
    All trades must be entered and exited manually.
    """
    return

if __name__ == "__main__":
    print("Testing paper broker module...")
    # Standalone test with mock prices
    mock_prices = {"RELIANCE.NS": 2500.0, "TCS.NS": 3400.0}
    process_simulated_orders(mock_prices)
    print("Done testing.")
