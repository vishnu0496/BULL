# engine.py
import datetime
import pandas as pd
import yfinance as yf
from ml_ensemble import MLBreakoutEnsemble

def download_data(ticker, **kwargs):
    df = yf.download(ticker, **kwargs)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df


SECTORS = {
    "BANK": "^NSEI",
    "RELIANCE.NS": "ENERGY",
    "TCS.NS": "IT",
    "INFY.NS": "IT",
    "HDFCBANK.NS": "BANK",
    "ICICIBANK.NS": "BANK",
    "BHARTIARTL.NS": "TELECOM",
    "ITC.NS": "FMCG",
    "HINDUNILVR.NS": "FMCG",
    "TATASTEEL.NS": "METALS"
}

class BULLSignalEngine:
    def __init__(self, tickers=list(SECTORS.keys())):
        self.tickers = [t for t in tickers if t != "BANK"]
        self.ensemble = MLBreakoutEnsemble()
        self.historical_data = {}
        self.last_scan_report = {}
        
    def bootstrap_and_train(self):
        print("[Engine] Bootstrapping historical data for NSE universe...")
        for ticker in self.tickers:
            try:
                df = download_data(ticker, period="1y", interval="1d")
                if not df.empty:
                    self.historical_data[ticker] = df
            except Exception as e:
                print(f"Error bootstrapping {ticker}: {e}")
                
        if "HDFCBANK.NS" in self.historical_data:
            self.ensemble.train_walk_forward(self.historical_data["HDFCBANK.NS"])
        else:
            first_ticker = list(self.historical_data.keys())[0]
            self.ensemble.train_walk_forward(self.historical_data[first_ticker])

    def calculate_sector_relative_strength(self, ticker: str) -> float:
        try:
            stock_df = self.historical_data.get(ticker)
            nifty_df = download_data("^NSEI", period="1mo", interval="1d")
            
            if stock_df is None or nifty_df.empty:
                return 1.0
                
            stock_ret = stock_df['Close'].pct_change(20).iloc[-1]
            nifty_ret = nifty_df['Close'].pct_change(20).iloc[-1]
            return float(stock_ret - nifty_ret)
        except Exception:
            return 1.0

    def evaluate_filters(self, ticker: str, current_time: datetime.time) -> dict:
        df = download_data(ticker, period="5d", interval="15m")
        df_daily = self.historical_data.get(ticker)
        
        if df.empty or df_daily is None:
            return {"passed": False, "reason": "No data"}
            
        latest_15m = df.iloc[-1]
        prev_close = df_daily['Close'].iloc[-1]
        
        # 1. Gap Up filter
        gap_percent = ((latest_15m['Open'] - prev_close) / prev_close) * 100
        if gap_percent > 2.0:
            return {"passed": False, "reason": f"Gap up too large: {gap_percent:.2f}%"}
            
        # 2. RVOL Check
        volume_20d_avg = df_daily['Volume'].tail(20).mean()
        rvol = latest_15m['Volume'] / (volume_20d_avg / 26)
        if rvol < 1.5:
            return {"passed": False, "reason": f"Insufficient RVOL: {rvol:.2f}x"}
            
        # 3. RSI Check
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean().iloc[-1]
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean().iloc[-1]
        rsi = 100 - (100 / (1 + (gain / (loss + 1e-8))))
        if rsi > 68 or rsi < 35:
            return {"passed": False, "reason": f"RSI out of bounds: {rsi:.1f}"}
            
        # 4. Blackout Hours
        if current_time < datetime.time(9, 30) or current_time > datetime.time(15, 0):
            return {"passed": False, "reason": f"Blackout Window: {current_time}"}
            
        # 5. Macro VIX
        try:
            vix = download_data("^INDIAVIX", period="1d")['Close'].iloc[-1]
            if vix > 22.0:
                return {"passed": False, "reason": f"INDIA VIX too high: {vix:.2f}"}
        except Exception:
            pass
            
        # 6. ML Verification
        ml_score = self.ensemble.predict_latest(df_daily)
        if ml_score < 0.62:
            return {"passed": False, "reason": f"Low ML Confidence: {ml_score:.2%}"}
            
        rel_strength = self.calculate_sector_relative_strength(ticker)
        
        return {
            "passed": True,
            "ml_score": ml_score,
            "rsi": rsi,
            "rvol": rvol,
            "rel_strength": rel_strength,
            "atr": df_daily['atr_20'].iloc[-1],
            "price": latest_15m['Close']
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
                rejected.append({
                    "ticker": ticker,
                    "reason": reason,
                    "category": self._reason_category(reason),
                })
                
        candidates = sorted(candidates, key=lambda x: (x["rel_strength"], x["ml_score"]), reverse=True)
        selected = candidates[:2]

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
            "next_action": next_action,
        }
        return selected, self.last_scan_report

    def scan(self) -> list:
        candidates, _ = self.scan_with_report()
        return candidates
