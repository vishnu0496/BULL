# engine.py
import datetime
import pandas as pd
import yfinance as yf
from ml_ensemble import MLBreakoutEnsemble
from src.free_market_feed import BullFreeMarketFeed

def download_data(ticker, **kwargs):
    df = yf.download(ticker, **kwargs)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df


def add_atr_20(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr_20'] = true_range.rolling(20).mean()
    return df


SECTORS = {
    "RELIANCE.NS": "ENERGY",
    "TCS.NS": "IT",
    "INFY.NS": "IT",
    "HCLTECH.NS": "IT",
    "WIPRO.NS": "IT",
    "TECHM.NS": "IT",
    "HDFCBANK.NS": "BANK",
    "ICICIBANK.NS": "BANK",
    "SBIN.NS": "BANK",
    "AXISBANK.NS": "BANK",
    "KOTAKBANK.NS": "BANK",
    "INDUSINDBK.NS": "BANK",
    "BANKBARODA.NS": "BANK",
    "PNB.NS": "BANK",
    "BAJFINANCE.NS": "FINANCE",
    "BAJAJFINSV.NS": "FINANCE",
    "JIOFIN.NS": "FINANCE",
    "LT.NS": "INFRA",
    "ADANIENT.NS": "INFRA",
    "ADANIPORTS.NS": "INFRA",
    "POWERGRID.NS": "POWER",
    "NTPC.NS": "POWER",
    "COALINDIA.NS": "ENERGY",
    "ONGC.NS": "ENERGY",
    "BPCL.NS": "ENERGY",
    "TATASTEEL.NS": "METALS",
    "JSWSTEEL.NS": "METALS",
    "HINDALCO.NS": "METALS",
    "VEDL.NS": "METALS",
    "ITC.NS": "FMCG",
    "HINDUNILVR.NS": "FMCG",
    "NESTLEIND.NS": "FMCG",
    "BRITANNIA.NS": "FMCG",
    "TVSMOTOR.NS": "AUTO",
    "M&M.NS": "AUTO",
    "MARUTI.NS": "AUTO",
    "EICHERMOT.NS": "AUTO",
    "BAJAJ-AUTO.NS": "AUTO",
    "SUNPHARMA.NS": "PHARMA",
    "CIPLA.NS": "PHARMA",
    "DRREDDY.NS": "PHARMA",
    "DIVISLAB.NS": "PHARMA",
    "BHARTIARTL.NS": "TELECOM",
    "ULTRACEMCO.NS": "CEMENT",
    "GRASIM.NS": "CEMENT",
    "TITAN.NS": "CONSUMER",
    "ASIANPAINT.NS": "CONSUMER",
    "DMART.NS": "CONSUMER",
    "TRENT.NS": "CONSUMER",
    "BEL.NS": "DEFENCE",
    "HAL.NS": "DEFENCE",
}

class BULLSignalEngine:
    def __init__(self, tickers=list(SECTORS.keys())):
        self.tickers = list(tickers)
        self.ensemble = MLBreakoutEnsemble()
        self.feed = BullFreeMarketFeed(cache_seconds=60)
        self.historical_data = {}
        self.last_scan_report = {}
        self._nifty_monthly = None
        
    def bootstrap_and_train(self):
        print("[Engine] Bootstrapping historical data for NSE universe...")
        training_source = None
        for ticker in self.tickers:
            try:
                df = download_data(ticker, period="1y", interval="1d")
                if not df.empty:
                    if ticker == "HDFCBANK.NS" or training_source is None:
                        training_source = df
                    self.historical_data[ticker] = add_atr_20(df)
            except Exception as e:
                print(f"Error bootstrapping {ticker}: {e}")
                
        if training_source is not None:
            try:
                self.ensemble.train_walk_forward(training_source)
            except Exception as e:
                print(f"[ML Engine] Training skipped, using neutral fallback scores: {e}")

    def calculate_sector_relative_strength(self, ticker: str) -> float:
        try:
            stock_df = self.historical_data.get(ticker)
            if self._nifty_monthly is None or self._nifty_monthly.empty:
                self._nifty_monthly = download_data("^NSEI", period="1mo", interval="1d")
            nifty_df = self._nifty_monthly
            
            if stock_df is None or nifty_df.empty:
                return 1.0
                
            stock_ret = stock_df['Close'].pct_change(20).iloc[-1]
            nifty_ret = nifty_df['Close'].pct_change(20).iloc[-1]
            return float(stock_ret - nifty_ret)
        except Exception:
            return 1.0

    def evaluate_filters(self, ticker: str, current_time: datetime.time) -> dict:
        df = self.feed.get_bars(ticker, period="5d", interval="15m")
        df_daily = self.historical_data.get(ticker)
        
        if df.empty or df_daily is None:
            return {"passed": False, "reason": "No data", "watch_score": 0.0}
            
        latest_15m = df.iloc[-1]
        prev_close = df_daily['Close'].iloc[-1]
        price = float(latest_15m['Close'])
        rel_strength = self.calculate_sector_relative_strength(ticker)
        
        # 1. Gap Up filter
        gap_percent = ((latest_15m['Open'] - prev_close) / prev_close) * 100
            
        # 2. RVOL Check
        volume_20d_avg = df_daily['Volume'].tail(20).mean()
        rvol = latest_15m['Volume'] / (volume_20d_avg / 26)
            
        # 3. RSI Check
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-8))))

        ml_score = self.ensemble.predict_latest(df_daily)
        watch_score = (
            min(float(rvol), 2.5) / 2.5 * 35
            + max(0.0, 1 - abs(float(rsi) - 52) / 35) * 25
            + float(ml_score) * 25
            + max(-0.1, min(float(rel_strength), 0.1)) * 150
        )

        base_result = {
            "price": price,
            "gap_percent": float(gap_percent),
            "rvol": float(rvol),
            "rsi": float(rsi),
            "ml_score": float(ml_score),
            "rel_strength": float(rel_strength),
            "atr": float(df_daily['atr_20'].iloc[-1]),
            "watch_score": round(float(watch_score), 2),
        }

        if gap_percent > 2.0:
            return {**base_result, "passed": False, "reason": f"Gap up too large: {gap_percent:.2f}%"}

        if rvol < 1.5:
            return {**base_result, "passed": False, "reason": f"Insufficient RVOL: {rvol:.2f}x"}

        if rsi > 68 or rsi < 35:
            return {**base_result, "passed": False, "reason": f"RSI out of bounds: {rsi:.1f}"}
            
        # 4. Blackout Hours
        if current_time < datetime.time(9, 30) or current_time > datetime.time(15, 0):
            return {**base_result, "passed": False, "reason": f"Blackout Window: {current_time}"}
            
        # 5. Macro VIX
        try:
            vix = download_data("^INDIAVIX", period="1d")['Close'].iloc[-1]
            if vix > 22.0:
                return {**base_result, "passed": False, "reason": f"INDIA VIX too high: {vix:.2f}"}
        except Exception:
            pass
            
        # 6. ML Verification
        if ml_score < 0.62:
            return {**base_result, "passed": False, "reason": f"Low ML Confidence: {ml_score:.2%}"}
        
        return {
            **base_result,
            "passed": True,
            "reason": "All scanner filters passed"
        }

    @staticmethod
    def _reason_category(reason: str) -> str:
        text = reason.lower()
        if "no data" in text:
            return "DATA"
        if "gap" in text:
            return "GAP"
        if "rvol" in text:
            return "VOLUME"
        if "rsi" in text:
            return "MOMENTUM"
        if "blackout" in text:
            return "TIME"
        if "vix" in text:
            return "MACRO"
        if "ml" in text:
            return "MODEL"
        return "OTHER"

    def scan_with_report(self) -> tuple[list, dict]:
        candidates = []
        rejected = []
        watchlist = []
        real_now = datetime.datetime.now().time()
        now = real_now
        simulated_time = False
        
        if now < datetime.time(9, 15) or now > datetime.time(15, 30):
            now = datetime.time(10, 30) # Default simulation time outside market hours
            simulated_time = True
            
        for ticker in self.tickers:
            result = self.evaluate_filters(ticker, now)
            if result["passed"]:
                candidates.append({
                    "ticker": ticker,
                    "price": float(result["price"]),
                    "ml_score": float(result["ml_score"]),
                    "rsi": float(result["rsi"]),
                    "rvol": float(result["rvol"]),
                    "rel_strength": float(result["rel_strength"]),
                    "atr": float(result["atr"])
                })
            else:
                reason = result.get("reason", "Rejected by scanner rules")
                item = {
                    "ticker": ticker,
                    "reason": reason,
                    "category": self._reason_category(reason),
                    "watch_score": float(result.get("watch_score", 0.0)),
                    "price": float(result.get("price", 0.0)),
                    "rvol": float(result.get("rvol", 0.0)),
                    "rsi": float(result.get("rsi", 0.0)),
                    "ml_score": float(result.get("ml_score", 0.0)),
                    "rel_strength": float(result.get("rel_strength", 0.0)),
                }
                rejected.append(item)
                if item["category"] not in {"DATA", "TIME"} and item["watch_score"] > 0:
                    watchlist.append(item)
                
        candidates = sorted(candidates, key=lambda x: (x["rel_strength"], x["ml_score"]), reverse=True)
        selected = candidates[:2]
        top_watch = sorted(watchlist, key=lambda x: x["watch_score"], reverse=True)[:3]

        rejection_counts = {}
        for item in rejected:
            rejection_counts[item["category"]] = rejection_counts.get(item["category"], 0) + 1

        top_rejection = max(rejection_counts.items(), key=lambda item: item[1])[0] if rejection_counts else "NONE"
        if selected:
            decision = "CANDIDATES_FOUND"
            next_action = "Review candidates, then paper trade only if news gate and risk sizing also pass."
        elif top_rejection == "VOLUME":
            decision = "NO_TRADE_LOW_VOLUME"
            next_action = "Wait. Breakouts without relative volume are usually weak."
        elif top_rejection == "MODEL":
            decision = "NO_TRADE_LOW_CONFIDENCE"
            next_action = "Wait. The model does not see enough edge in the current patterns."
        elif top_rejection == "DATA":
            decision = "DATA_SYNC_NEEDED"
            next_action = "Refresh data health or check internet/data source availability."
        else:
            decision = "NO_TRADE"
            next_action = "Capital preserved. Re-scan later instead of forcing a trade."

        self.last_scan_report = {
            "decision": decision,
            "scan_time": now.strftime("%H:%M"),
            "real_time": real_now.strftime("%H:%M"),
            "mode": "SIMULATED_MARKET_TIME" if simulated_time else "LIVE_MARKET_TIME",
            "total_symbols": len(self.tickers),
            "passed": len(selected),
            "rejected": len(rejected),
            "rejection_counts": rejection_counts,
            "top_rejection": top_rejection,
            "rejected_examples": rejected[:8],
            "top_watch": top_watch,
            "next_action": next_action,
        }
        return selected, self.last_scan_report

    def scan(self) -> list:
        candidates, _ = self.scan_with_report()
        return candidates

    def feed_health(self) -> dict:
        return self.feed.health(self.tickers)
