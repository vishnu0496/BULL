# src/constants.py
from datetime import datetime

NSE_HOLIDAYS_2025 = {
  "2025-08-15", "2025-08-27", "2025-10-02",
  "2025-10-20", "2025-10-23", "2025-11-05", 
  "2025-12-25"
}

NSE_HOLIDAYS_2026 = {
  "2026-01-26", "2026-02-19", "2026-03-30",
  "2026-04-02", "2026-04-06", "2026-04-14",
  "2026-04-30", "2026-05-01", "2026-08-15",
  "2026-10-02", "2026-11-09", "2026-12-25"
}

def is_nse_holiday(date_obj) -> bool:
    """Check if a date falls on a weekend or an NSE market holiday."""
    # Weekend check: Monday is 0, Sunday is 6
    if date_obj.weekday() >= 5:
        return True
    
    date_str = date_obj.strftime("%Y-%m-%d")
    return (date_str in NSE_HOLIDAYS_2025) or (date_str in NSE_HOLIDAYS_2026)


DAILY_LESSONS = [
  {
    "title": "What is a Stop Loss?",
    "body": "A stop loss is your safety net. Before you buy any stock, decide the maximum you're willing to lose. Example: buy INFY at ₹1500, stop loss at ₹1470. If it falls to ₹1470 — exit immediately. You lose ₹30, not ₹300. Always set it before you enter.",
    "emoji": "🛡️"
  },
  {
    "title": "What is Volume?",
    "body": "Volume is how many shares were traded today. High volume = many people buying or selling. When a stock breaks to a new high WITH high volume — that's a real move. Without volume — it's fake and usually reverses.",
    "emoji": "📊"
  },
  {
    "title": "What is FII?",
    "body": "FII means Foreign Institutional Investors — big funds from USA, Singapore, UK investing in Indian stocks. When they buy heavily, market goes up. When they sell — market falls. BULL tracks this every day. It's the most important daily number to watch.",
    "emoji": "🌍"
  },
  {
    "title": "What is a Swing Trade?",
    "body": "A swing trade holds a stock for 3-10 days, not minutes. You buy when a stock breaks out strongly, hold while it moves up, exit at target or stop loss. This is what BULL is designed for — not day trading (too stressful) and not long-term investing (too slow).",
    "emoji": "🎯"
  },
  {
    "title": "What is R-Multiple?",
    "body": "R is how much you risked. If you risked ₹100 on a trade and made ₹200 — that's 2R. Professional traders aim for 2R minimum on every trade. This means even with a 50% win rate you make money. Your paper trading analytics show your average R. Target: above 1.5R.",
    "emoji": "⚖️"
  },
  {
    "title": "What is RSI?",
    "body": "RSI (Relative Strength Index) measures if a stock is overbought (too hot) or oversold (too cold). If RSI is above 70, everyone has already bought and the stock might crash. Below 30, it might be a bargain. BULL looks for the sweet spot between 35 and 68.",
    "emoji": "⚡"
  },
  {
    "title": "What is ATR?",
    "body": "Average True Range (ATR) measures how much a stock moves up or down in a day. A high ATR means high volatility (wild moves), while a low ATR means quiet moves. We use ATR to place our safety stop loss so we don't get kicked out by normal daily noise.",
    "emoji": "📏"
  },
  {
    "title": "What is RVOL?",
    "body": "Relative Volume (RVOL) compares today's volume to the average volume. If a stock averages 1 million shares a day and today trades 3 million, RVOL is 3.0x. High RVOL means institutional interest—the big players are buying. Always look for RVOL > 1.5x.",
    "emoji": "📈"
  },
  {
    "title": "What is Conviction Score?",
    "body": "The conviction score is BULL's grading system out of 100. It combines technical filters, relative strength, sector trend, and machine learning probabilities. A higher score means more stars are aligned. Only trade when BULL shows high conviction.",
    "emoji": "🧠"
  },
  {
    "title": "What is Sector Rotation?",
    "body": "Money moves in waves. One week IT stocks rise, the next week banking stocks lead. This is sector rotation. Buying a strong stock in a leading sector gives you a wind at your back. Never buy a stock in a dying sector.",
    "emoji": "🔄"
  },
  {
    "title": "What is a Breakout?",
    "body": "A breakout happens when a stock price pushes above a resistance level (like a previous high) where sellers used to dominate. When it breaks out, it means buyers have taken control. This often triggers a fast upward run.",
    "emoji": "💥"
  },
  {
    "title": "What is Position Sizing?",
    "body": "Position sizing is deciding how many shares to buy. Never risk your entire account on one stock. Professional traders only risk 1% of their capital per trade. If you have ₹10,000, you should only lose ₹100 if the trade fails.",
    "emoji": "💰"
  },
  {
    "title": "What is the Kelly Criterion?",
    "body": "The Kelly Criterion is a mathematical formula used to determine the optimal size of a trade. It balances your win rate and risk-to-reward ratio to calculate how much capital to allocate. BULL uses it to help keep you from over-betting.",
    "emoji": "🧮"
  },
  {
    "title": "What are Earnings?",
    "body": "Earnings are quarterly financial reports where companies share their profits. Stock prices can jump or crash violently on earnings day. BULL uses an avoidance rule to skip trading stocks with earnings due in the next few days to avoid gambling.",
    "emoji": "📅"
  },
  {
    "title": "Who are Promoters?",
    "body": "Promoters are the founders and major owners of a company. When promoters buy their own stock, they believe the company is undervalued. When they sell, they might think the stock is too expensive or need cash. BULL tracks promoter transactions.",
    "emoji": "🤝"
  },
  {
    "title": "What is Put-Call Ratio (PCR)?",
    "body": "The Put-Call Ratio (PCR) measures option market sentiment. Puts are bets that the market falls, and Calls are bets it rises. A high PCR means traders are bearish, while a low PCR means they are bullish. It helps identify extreme market sentiment.",
    "emoji": "📊"
  },
  {
    "title": "What is VIX (Fear Index)?",
    "body": "The VIX measures expected market volatility and fear. When VIX is low, the market is calm. When VIX spikes (above 20), fear is high and stock prices can swing wildly. BULL pauses long setups if the India VIX rises too high.",
    "emoji": "😰"
  },
  {
    "title": "What is Nifty 50?",
    "body": "The Nifty 50 is India's benchmark index representing the 50 largest companies listed on the National Stock Exchange (NSE). It shows the overall health of the Indian stock market. When Nifty rises, the general market sentiment is positive.",
    "emoji": "🇮🇳"
  },
  {
    "title": "What is the NSE?",
    "body": "The National Stock Exchange (NSE) is the leading stock exchange in India, located in Mumbai. It is where shares of major companies like Reliance, TCS, and Infosys are bought and sold electronically during market hours.",
    "emoji": "🏦"
  },
  {
    "title": "What is the BSE?",
    "body": "The Bombay Stock Exchange (BSE) is Asia's oldest stock exchange, established in 1875. Along with the NSE, it is one of the two main exchanges in India where public companies list their shares for trading.",
    "emoji": "🏛️"
  },
  {
    "title": "Mutual Funds vs Stocks",
    "body": "A mutual fund pools money from many investors to buy a basket of stocks managed by professionals. Buying an individual stock is investing in a single company. Stocks offer higher return potential but also carry much higher risk.",
    "emoji": "🧺"
  },
  {
    "title": "What is a SIP?",
    "body": "A Systematic Investment Plan (SIP) is a method where you invest a fixed amount of money regularly (like monthly) into mutual funds or stocks. It helps build wealth over time by averaging out purchase costs and ignoring daily noise.",
    "emoji": "⏳"
  },
  {
    "title": "Bull vs Bear Market",
    "body": "A Bull market is when stock prices are rising and optimism is high. A Bear market is when prices are falling and fear dominates. BULL is designed to scan for breakouts in bull phases and preserve your cash in bear phases.",
    "emoji": "🐂"
  },
  {
    "title": "Support & Resistance",
    "body": "Support is a price floor where buyers usually enter and prevent the stock from falling further. Resistance is a price ceiling where sellers push back and prevent the stock from rising. Breakouts happen when resistance is broken.",
    "emoji": "🧱"
  },
  {
    "title": "Moving Averages",
    "body": "A moving average smooths out price data by creating a constantly updated average price. For example, a 50-day moving average shows the average price over the last 50 days. It helps identify the overall trend direction.",
    "emoji": "📉"
  },
  {
    "title": "Candlestick Charts",
    "body": "A candlestick chart displays the high, low, open, and close prices of a stock for a specific time period. A green candle means the price closed higher than it opened, while a red candle means it closed lower.",
    "emoji": "🕯️"
  },
  {
    "title": "Why 9 out of 10 Traders Lose",
    "body": "Most traders lose money due to lack of discipline, emotional trading, over-leveraging, and not using a stop loss. BULL forces a rules-based system: we trade only when the odds are in our favor and strictly limit our risk.",
    "emoji": "🚫"
  },
  {
    "title": "Importance of a Journal",
    "body": "A trading journal is where you record every trade, including entry price, exit price, reasons, and mistakes. Reviewing your journal allows you to identify what works and stop repeating the same errors. If you don't track, you can't improve.",
    "emoji": "📝"
  },
  {
    "title": "What is Paper Trading?",
    "body": "Paper trading is simulated trading using virtual money. It allows you to practice market analysis, test strategy rules, and build execution discipline without risking real capital. Treat paper trading as seriously as real money.",
    "emoji": "🎮"
  },
  {
    "title": "Patience as a Strategy",
    "body": "Patience is a trader's superpower. Sitting in cash and waiting for a high-probability setup is a valid and active trading decision. Forcing bad trades in a rangebound market is the fastest way to lose capital. Learn to wait.",
    "emoji": "⏸️"
  }
]

