import os
import sqlite3
import pandas as pd
from datetime import datetime

# Database path configuration
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'bull_research.db')

def get_db_connection():
    """Establish a connection to the SQLite database with Row factory and WAL mode enabled."""
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def init_db():
    """Initialize database tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Watchlist table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 2. Historical Prices table (caching yfinance data)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historical_prices (
            ticker TEXT,
            date DATE,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            PRIMARY KEY (ticker, date)
        )
    """)
    
    # 3. Paper Journal (trades) table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            trade_date DATE,
            action TEXT CHECK(action IN ('BUY', 'SELL')),
            quantity INTEGER CHECK(quantity > 0),
            price REAL CHECK(price >= 0),
            notes TEXT,
            logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 4. Daily research setups generated from stored market data.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS research_setups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setup_date DATE,
            ticker TEXT,
            direction TEXT CHECK(direction IN ('BULLISH', 'BEARISH', 'NEUTRAL')),
            entry_trigger REAL,
            stop_loss REAL,
            target_1 REAL,
            target_2 REAL,
            invalidation_rule TEXT,
            confidence_score REAL,
            risk_level TEXT,
            reasons TEXT,
            status TEXT DEFAULT 'PLANNED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(setup_date, ticker, direction, entry_trigger)
        )
    """)

    # 5. Capital Settings table (now includes API keys for Gemini and Zerodha)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS capital_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            total_capital REAL,
            max_risk_per_trade REAL,
            max_trades_per_day INTEGER,
            allow_options INTEGER DEFAULT 0,
            experience_level TEXT DEFAULT 'BEGINNER',
            gemini_api_key TEXT DEFAULT '',
            dhan_client_id TEXT DEFAULT '',
            dhan_access_token TEXT DEFAULT '',
            kite_api_key TEXT DEFAULT '',
            kite_api_secret TEXT DEFAULT '',
            kite_request_token TEXT DEFAULT '',
            autopilot INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Check if we need to add columns to an existing table (for smooth schema migration)
    cursor.execute("PRAGMA table_info(capital_settings)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'gemini_api_key' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN gemini_api_key TEXT DEFAULT ''")
    if 'dhan_client_id' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN dhan_client_id TEXT DEFAULT ''")
    if 'dhan_access_token' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN dhan_access_token TEXT DEFAULT ''")
    if 'kite_api_key' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN kite_api_key TEXT DEFAULT ''")
    if 'kite_api_secret' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN kite_api_secret TEXT DEFAULT ''")
    if 'kite_request_token' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN kite_request_token TEXT DEFAULT ''")
    if 'autopilot' not in columns:
        cursor.execute("ALTER TABLE capital_settings ADD COLUMN autopilot INTEGER DEFAULT 0")
    
    # Seed default row if empty
    cursor.execute("SELECT COUNT(*) FROM capital_settings WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO capital_settings (id, total_capital, max_risk_per_trade, max_trades_per_day, allow_options, experience_level, gemini_api_key, kite_api_key, kite_api_secret, kite_request_token, dhan_client_id, dhan_access_token, autopilot)
            VALUES (1, 5000, 100, 1, 0, 'BEGINNER', '', '', '', '', '', '', 0)
        """)
    else:
        cursor.execute("""
            UPDATE capital_settings
            SET total_capital = 5000,
                max_risk_per_trade = 100,
                max_trades_per_day = 1,
                allow_options = 0,
                experience_level = 'BEGINNER',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
              AND total_capital = 100000
              AND max_risk_per_trade = 2000
              AND max_trades_per_day = 3
              AND allow_options = 1
              AND lower(experience_level) = 'intermediate'
              AND COALESCE(gemini_api_key, '') = ''
              AND COALESCE(kite_api_key, '') = ''
              AND COALESCE(kite_api_secret, '') = ''
              AND COALESCE(kite_request_token, '') = ''
              AND COALESCE(dhan_client_id, '') = ''
              AND COALESCE(dhan_access_token, '') = ''
        """)
        
    # 6. News Cache table to speed up rendering and prevent API rate limits
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            title TEXT,
            publisher TEXT,
            link TEXT,
            pub_time INTEGER,
            sentiment_score REAL,
            sentiment_label TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, link)
        )
    """)

    # 7. Event Calendar Cache table to cache earnings and dividend dates
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_calendar_cache (
            ticker TEXT PRIMARY KEY,
            earnings_date TEXT,
            dividend_date TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()


def save_research_setups(setups):
    """Insert generated research setups into SQLite."""
    if not setups:
        return 0

    conn = get_db_connection()
    cursor = conn.cursor()
    rows_saved = 0
    try:
        for setup in setups:
            cursor.execute("""
                INSERT OR REPLACE INTO research_setups (
                    setup_date, ticker, direction, entry_trigger, stop_loss,
                    target_1, target_2, invalidation_rule, confidence_score,
                    risk_level, reasons, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                setup['setup_date'],
                setup['ticker'],
                setup['direction'],
                setup['entry_trigger'],
                setup['stop_loss'],
                setup['target_1'],
                setup['target_2'],
                setup['invalidation_rule'],
                setup['confidence_score'],
                setup['risk_level'],
                setup['reasons'],
                setup.get('status', 'PLANNED'),
            ))
            rows_saved += cursor.rowcount
        conn.commit()
        return rows_saved
    finally:
        conn.close()


def get_research_setups(setup_date=None):
    """Retrieve generated research setups, newest first."""
    conn = get_db_connection()
    try:
        if setup_date:
            return pd.read_sql_query(
                "SELECT * FROM research_setups WHERE setup_date = ? ORDER BY confidence_score DESC, ticker ASC",
                conn,
                params=(setup_date,)
            )
        return pd.read_sql_query(
            "SELECT * FROM research_setups ORDER BY setup_date DESC, confidence_score DESC, ticker ASC",
            conn
        )
    finally:
        conn.close()

def add_to_watchlist(ticker: str, name: str, industry: str):
    """Add a ticker to the watchlist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR REPLACE INTO watchlist (ticker, name, industry) VALUES (?, ?, ?)",
            (ticker.strip().upper(), name, industry)
        )
        conn.commit()
    finally:
        conn.close()

def remove_from_watchlist(ticker: str):
    """Remove a ticker from the watchlist and its cached historical data."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker.upper(),))
        cursor.execute("DELETE FROM historical_prices WHERE ticker = ?", (ticker.upper(),))
        conn.commit()
    finally:
        conn.close()

def get_watchlist():
    """Retrieve all rows in the watchlist."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM watchlist ORDER BY ticker ASC", conn)
        return df
    finally:
        conn.close()

def get_watchlist_tickers():
    """Retrieve list of tickers currently in watchlist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT ticker FROM watchlist ORDER BY ticker ASC")
        rows = cursor.fetchall()
        return [row['ticker'] for row in rows]
    finally:
        conn.close()

def save_prices(ticker: str, df_prices: pd.DataFrame):
    """
    Save or update price data in historical_prices table.
    df_prices should have a Date index or column, Open, High, Low, Close, Volume.
    """
    if df_prices.empty:
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Standardize format
    df_to_save = df_prices.copy()
    if 'Date' not in df_to_save.columns:
        if isinstance(df_to_save.index, pd.DatetimeIndex):
            df_to_save['Date'] = df_to_save.index.strftime('%Y-%m-%d')
        else:
            df_to_save = df_to_save.reset_index()
            if 'Date' in df_to_save.columns:
                df_to_save['Date'] = pd.to_datetime(df_to_save['Date']).dt.strftime('%Y-%m-%d')
                
    ticker = ticker.upper()
    try:
        for _, row in df_to_save.iterrows():
            cursor.execute("""
                INSERT OR REPLACE INTO historical_prices (ticker, date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ticker,
                row['Date'],
                float(row['Open']),
                float(row['High']),
                float(row['Low']),
                float(row['Close']),
                int(row['Volume'])
            ))
        conn.commit()
    finally:
        conn.close()

def get_prices(ticker: str):
    """Retrieve historical prices for a ticker, sorted by Date ascending."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(
            "SELECT * FROM historical_prices WHERE ticker = ? ORDER BY date ASC",
            conn,
            params=(ticker.upper(),)
        )
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
        return df
    finally:
        conn.close()

def get_latest_price(ticker: str):
    """Fetch the latest stored price and date for a ticker."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT close, date FROM historical_prices WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker.upper(),)
        )
        row = cursor.fetchone()
        if row:
            return float(row['close']), row['date']
        return None, None
    finally:
        conn.close()

def add_paper_trade(ticker: str, trade_date: str, action: str, quantity: int, price: float, notes: str):
    """Add a new paper trade transaction to the journal."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO paper_journal (ticker, trade_date, action, quantity, price, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (ticker.upper(), trade_date, action.upper(), quantity, price, notes))
        conn.commit()
    finally:
        conn.close()

def get_paper_trades():
    """Retrieve all transactions logged in the paper journal."""
    conn = get_db_connection()
    try:
        df = pd.read_sql_query("SELECT * FROM paper_journal ORDER BY trade_date DESC, id DESC", conn)
        return df
    finally:
        conn.close()

def get_portfolio_holdings():
    """
    Calculate current active holdings and realized PnL.
    Walks through trades chronologically using the Average Cost Basis method:
      - Average buy price is updated on BUY trades.
      - Number of shares decreases on SELL trades.
      - Realized profit is realized on SELL trades.
    """
    conn = get_db_connection()
    try:
        # Fetch trades in chronological order to correctly construct running metrics
        trades_df = pd.read_sql_query("SELECT * FROM paper_journal ORDER BY trade_date ASC, id ASC", conn)
    finally:
        conn.close()

    holdings = {}
    total_realized_pnl = 0.0

    for _, row in trades_df.iterrows():
        ticker = row['ticker'].upper()
        action = row['action'].upper()
        qty = int(row['quantity'])
        price = float(row['price'])

        if ticker not in holdings:
            holdings[ticker] = {
                'shares': 0,
                'avg_cost': 0.0,
                'realized_pnl': 0.0
            }

        h = holdings[ticker]

        if action == 'BUY':
            new_shares = h['shares'] + qty
            effective_buy_price = price * 1.0015  # Includes 0.15% simulated commission/tax friction
            # Update average cost basis
            h['avg_cost'] = ((h['shares'] * h['avg_cost']) + (qty * effective_buy_price)) / new_shares
            h['shares'] = new_shares
        elif action == 'SELL':
            sell_qty = min(qty, h['shares']) # Avoid selling more than owned
            if sell_qty > 0:
                effective_sell_price = price * 0.9985  # Includes 0.15% simulated commission/tax friction
                # Realized profit = qty * (effective_sell_price - buy_cost)
                realized = sell_qty * (effective_sell_price - h['avg_cost'])
                h['realized_pnl'] += realized
                total_realized_pnl += realized
                h['shares'] -= sell_qty
                if h['shares'] == 0:
                    h['avg_cost'] = 0.0

    # Build detailed holdings list for current active positions (shares > 0)
    active_holdings = []
    for ticker, h in holdings.items():
        if h['shares'] > 0:
            latest_price, latest_date = get_latest_price(ticker)
            if latest_price is None:
                # Fallback to average cost if no price data is stored
                latest_price = h['avg_cost']
                latest_date = "No Cached Price"

            total_cost = h['shares'] * h['avg_cost']
            current_value = h['shares'] * latest_price
            unrealized_pnl = current_value - total_cost
            unrealized_pnl_pct = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0

            active_holdings.append({
                'ticker': ticker,
                'shares': h['shares'],
                'avg_cost': h['avg_cost'],
                'latest_price': latest_price,
                'latest_date': latest_date,
                'total_cost': total_cost,
                'current_value': current_value,
                'unrealized_pnl': unrealized_pnl,
                'unrealized_pnl_pct': unrealized_pnl_pct,
                'realized_pnl': h['realized_pnl']
            })
        elif h['realized_pnl'] != 0.0:
            # We want to record tickers that are closed but had realized PnL
            # so they can contribute to summary stats, though not active positions.
            pass

    return active_holdings, total_realized_pnl

def get_db_health():
    """Retrieve SQLite metadata and table diagnostics."""
    health = {
        'db_path': DB_PATH,
        'exists': os.path.exists(DB_PATH),
        'file_size_mb': 0.0,
        'watchlist_count': 0,
        'price_count': 0,
        'journal_count': 0
    }
    
    if health['exists']:
        health['file_size_mb'] = os.path.getsize(DB_PATH) / (1024 * 1024)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM watchlist")
            health['watchlist_count'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM historical_prices")
            health['price_count'] = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM paper_journal")
            health['journal_count'] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            # Database or tables might not be initialized yet
            pass
        finally:
            conn.close()
            
    return health

def get_capital_settings():
    """Retrieve the single capital settings record (id = 1)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT * FROM capital_settings WHERE id = 1")
        row = cursor.fetchone()
        if row:
            d = dict(row)
            # Ensure keys exist even if row doesn't have them for some reason
            # Set defaults for keys if they are null
            for key in ['gemini_api_key', 'dhan_client_id', 'dhan_access_token', 'kite_api_key', 'kite_api_secret', 'kite_request_token']:
                if key not in d:
                    d[key] = ''
            if 'autopilot' not in d or d['autopilot'] is None:
                d['autopilot'] = 0
            return d
        # Fallback
        return {
            'total_capital': 5000.0,
            'max_risk_per_trade': 100.0,
            'max_trades_per_day': 1,
            'allow_options': 0,
            'experience_level': 'BEGINNER',
            'gemini_api_key': '',
            'dhan_client_id': '',
            'dhan_access_token': '',
            'kite_api_key': '',
            'kite_api_secret': '',
            'kite_request_token': '',
            'autopilot': 0
        }
    finally:
        conn.close()

def update_capital_settings(total_capital: float, max_risk_per_trade: float, max_trades_per_day: int, allow_options: int, experience_level: str, gemini_api_key: str = '', dhan_client_id: str = '', dhan_access_token: str = '', kite_api_key: str = '', kite_api_secret: str = '', kite_request_token: str = '', autopilot: int = None):
    """Update or insert the single capital settings record."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # If autopilot is None, fetch existing autopilot value to avoid overwriting it
        if autopilot is None:
            cursor.execute("SELECT autopilot FROM capital_settings WHERE id = 1")
            row = cursor.fetchone()
            if row and 'autopilot' in row.keys():
                autopilot = row['autopilot']
            else:
                autopilot = 0

        cursor.execute("""
            INSERT OR REPLACE INTO capital_settings (id, total_capital, max_risk_per_trade, max_trades_per_day, allow_options, experience_level, gemini_api_key, dhan_client_id, dhan_access_token, kite_api_key, kite_api_secret, kite_request_token, autopilot, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (total_capital, max_risk_per_trade, max_trades_per_day, allow_options, experience_level, gemini_api_key, dhan_client_id, dhan_access_token, kite_api_key, kite_api_secret, kite_request_token, autopilot))
        conn.commit()
    finally:
        conn.close()

def save_news_cache(ticker: str, news_list: list):
    """Save fetched news items to database cache."""
    if not news_list:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for item in news_list:
            cursor.execute("""
                INSERT OR IGNORE INTO news_cache (ticker, title, publisher, link, pub_time, sentiment_score, sentiment_label, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                ticker.upper(),
                item['title'],
                item.get('publisher', 'Unknown'),
                item['link'],
                item.get('pub_time', int(datetime.now().timestamp())),
                item.get('sentiment_score', 0.0),
                item.get('sentiment_label', 'NEUTRAL')
            ))
        conn.commit()
    finally:
        conn.close()

def get_news_cache(ticker: str, max_age_hours: int = 2):
    """Retrieve cached news items for a ticker if fresher than max_age_hours."""
    conn = get_db_connection()
    try:
        query = """
            SELECT * FROM news_cache 
            WHERE ticker = ? AND datetime(fetched_at) >= datetime('now', '-' || ? || ' hour')
            ORDER BY pub_time DESC
        """
        df = pd.read_sql_query(query, conn, params=(ticker.upper(), max_age_hours))
        return df.to_dict('records')
    except Exception:
        return []
    finally:
        conn.close()

def get_event_calendar(ticker: str, max_age_days: int = 7) -> dict:
    """Retrieve cached earnings and dividend dates for a ticker if fresher than max_age_days."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT earnings_date, dividend_date FROM event_calendar_cache
            WHERE ticker = ? AND datetime(updated_at) >= datetime('now', '-' || ? || ' day')
        """, (ticker.upper(), max_age_days))
        row = cursor.fetchone()
        if row:
            return {"earnings_date": row[0], "dividend_date": row[1]}
        return {}
    except Exception:
        return {}
    finally:
        conn.close()

def save_event_calendar(ticker: str, earnings_date: str, dividend_date: str):
    """Cache corporate calendar events in the database."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO event_calendar_cache (ticker, earnings_date, dividend_date, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (ticker.upper(), earnings_date, dividend_date))
        conn.commit()
    except Exception as e:
        print(f"Error saving event calendar cache: {e}")
    finally:
        conn.close()
