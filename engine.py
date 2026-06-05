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

    def compute_conviction_score(self, ticker: str, base_result: dict) -> dict:
        """Calculate a conviction score (0-100) and grade (A+ to C/REJECT) using 5 intelligence layers."""
        from src.fii_tracker import get_fii_signal
        from src.earnings_calendar import check_earnings_blackout, get_earnings_edge
        from src.sector_rotation import should_trade_sector
        from src.premarket_signals import get_premarket_score
        from src.promoter_tracker import get_promoter_signal
        from src.database import get_news_cache

        # 1. Technical Score (max 30 pts)
        rvol = base_result.get("rvol", 1.0)
        rsi = base_result.get("rsi", 50.0)
        rel_strength = base_result.get("rel_strength", 0.0)
        
        tech_rvol = min(3.0, rvol) / 3.0 * 10
        
        if 50 <= rsi <= 65:
            tech_rsi = 10.0
        elif 35 <= rsi < 50 or 65 < rsi <= 70:
            tech_rsi = 5.0
        else:
            tech_rsi = 2.0
            
        tech_rs = 10.0 if rel_strength > 0.05 else (5.0 if rel_strength > 0.0 else 0.0)
        tech_score = round(tech_rvol + tech_rsi + tech_rs, 2)
        tech_score = max(0.0, min(30.0, tech_score))

        # 2. ML Ensemble Score (max 25 pts)
        ml_score = base_result.get("ml_score", 0.5)
        ml_points = round(ml_score * 25.0, 2)
        ml_points = max(0.0, min(25.0, ml_points))

        # 3. Macro Score (max 20 pts)
        pm_data = get_premarket_score()
        pm_score = pm_data.get("pre_market_score", 50.0)
        macro_pm = pm_score / 100.0 * 10.0
        
        fii_data = get_fii_signal()
        impact = fii_data.get("market_impact", "NEUTRAL")
        if impact == "STRONG_BULL":
            macro_fii = 5.0
        elif impact == "MILD_BULL":
            macro_fii = 4.0
        elif impact == "NEUTRAL":
            macro_fii = 3.0
        elif impact == "MILD_BEAR":
            macro_fii = 1.0
        else:
            macro_fii = 0.0
            
        vix = pm_data.get("india_vix", 15.0)
        if vix < 13.0:
            macro_vix = 5.0
        elif vix < 16.0:
            macro_vix = 4.0
        elif vix < 20.0:
            macro_vix = 2.0
        else:
            macro_vix = 0.0
            
        macro_score = round(macro_pm + macro_fii + macro_vix, 2)
        macro_score = max(0.0, min(20.0, macro_score))

        # 4. News Score (max 15 pts)
        news = get_news_cache(ticker)
        news_score = 10.0
        if news:
            sentiments = [n.get("sentiment_score", 0.0) for n in news if n.get("sentiment_score") is not None]
            if sentiments:
                avg_sent = sum(sentiments) / len(sentiments)
                news_score = round((avg_sent + 1.0) / 2.0 * 15.0, 2)
        news_score = max(0.0, min(15.0, news_score))

        # 5. Fundamental Score (max 10 pts)
        prom_data = get_promoter_signal(ticker)
        prom_type = prom_data.get("transaction_type", "NEUTRAL")
        prom_strength = prom_data.get("signal_strength", "WEAK_SIGNAL")
        
        fund_prom = 0.0
        if prom_type == "BUY":
            fund_prom = 4.0 if "STRONG" in prom_strength else 2.0
        elif prom_type == "SELL":
            fund_prom = -4.0
            
        earn_edge = get_earnings_edge(ticker)
        fund_edge = 3.0 if earn_edge.get("has_edge", False) else 0.0
        
        blackout_data = check_earnings_blackout(ticker)
        fund_blackout = 0.0 if blackout_data.get("in_blackout", False) else 3.0
        
        fund_score = round(fund_prom + fund_edge + fund_blackout, 2)
        fund_score = max(0.0, min(10.0, fund_score))

        # Total
        total_score = round(tech_score + ml_points + macro_score + news_score + fund_score, 2)
        total_score = max(0.0, min(100.0, total_score))

        # Grade
        if total_score >= 85:
            grade = "A+"
        elif total_score >= 70:
            grade = "A"
        elif total_score >= 55:
            grade = "B"
        elif total_score >= 40:
            grade = "C"
        else:
            grade = "REJECT"

        return {
            "conviction_score": total_score,
            "conviction_grade": grade,
            "promoter_type": prom_type,
            "promoter_strength": prom_strength,
            "score_breakdown": {
                "technical": tech_score,
                "ml": ml_points,
                "macro": macro_score,
                "news": news_score,
                "fundamental": fund_score
            }
        }

    def evaluate_filters(self, ticker: str, current_time: datetime.time) -> dict:
        from src.fii_tracker import get_fii_signal
        from src.earnings_calendar import check_earnings_blackout
        from src.sector_rotation import should_trade_sector
        from src.premarket_signals import get_premarket_score
        from src.promoter_tracker import get_promoter_signal

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

        # Calculate conviction details first so they are attached to all results
        conviction = self.compute_conviction_score(ticker, base_result)
        base_result.update(conviction)

        # Enforce basic technical/ML/hours filters
        if gap_percent > 2.0:
            return {**base_result, "passed": False, "reason": f"Gap up too large: {gap_percent:.2f}%"}

        if rvol < 1.5:
            return {**base_result, "passed": False, "reason": f"Insufficient RVOL: {rvol:.2f}x"}

        if rsi > 68 or rsi < 35:
            return {**base_result, "passed": False, "reason": f"RSI out of bounds: {rsi:.1f}"}
            
        # Blackout Hours
        if current_time < datetime.time(9, 30) or current_time > datetime.time(15, 0):
            return {**base_result, "passed": False, "reason": f"Blackout Window: {current_time}"}
            
        # Macro VIX Check
        try:
            vix = download_data("^INDIAVIX", period="1d")['Close'].iloc[-1]
            if vix > 22.0:
                return {**base_result, "passed": False, "reason": f"INDIA VIX too high: {vix:.2f}"}
        except Exception:
            pass
            
        # ML Verification
        if ml_score < 0.62:
            return {**base_result, "passed": False, "reason": f"Low ML Confidence: {ml_score:.2%}"}

        # Enforce New Intelligence Layer Checks (Blocks & Downgrades)
        
        # 1. Premarket STRONG_BEAR_OPEN blocking (premarket score < 30)
        pm_data = get_premarket_score()
        if pm_data.get("pre_market_score", 50.0) < 30.0:
            return {**base_result, "passed": False, "reason": "STRONG_BEAR_OPEN: Premarket score below 30"}

        # 2. Earnings Blackout blocking (3 days before to 1 day after)
        blackout_data = check_earnings_blackout(ticker)
        if blackout_data.get("in_blackout", False):
            return {**base_result, "passed": False, "reason": f"Earnings Blackout: Announcement date {blackout_data.get('result_date')}"}

        # 3. FII Consecutive Sell Streak (>= 3 days) -> Downgrade trade to WAIT
        fii_data = get_fii_signal()
        if fii_data.get("streak_days", 0) >= 3 and fii_data.get("streak_type") == "SELL":
            return {**base_result, "passed": False, "reason": f"FII Selling Streak: Downgraded to WAIT ({fii_data.get('streak_days')} days)"}

        # 4. Promoter Sell Red Flag -> Downgrade trade to WAIT
        prom_data = get_promoter_signal(ticker)
        if prom_data.get("transaction_type") == "SELL" and prom_data.get("signal_strength") in ["STRONG_RED_FLAG", "MODERATE_RED_FLAG"]:
            return {**base_result, "passed": False, "reason": f"Promoter Selling Red Flag: Downgraded to WAIT ({prom_data.get('signal_strength')})"}

        # 5. Sector Rotation Lagging -> Downgrade trade to WATCH
        sec_data = should_trade_sector(ticker)
        if sec_data.get("signal") == "LAGGING" or sec_data.get("rs_score", 1.0) < 0.9:
            return {**base_result, "passed": False, "reason": f"Sector Lagging: Downgraded to WATCH (RS: {sec_data.get('rs_score'):.2f})"}
        
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
        if "blackout" in text or "earnings" in text:
            return "TIME"
        if "vix" in text or "premarket" in text or "bear_open" in text or "fii" in text:
            return "MACRO"
        if "ml" in text:
            return "MODEL"
        if "promoter" in text:
            return "FUNDAMENTALS"
        if "sector" in text:
            return "SECTOR"
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
                    "atr": float(result["atr"]),
                    "conviction_score": result.get("conviction_score", 50.0),
                    "conviction_grade": result.get("conviction_grade", "C"),
                    "promoter_type": result.get("promoter_type", "NEUTRAL"),
                    "promoter_strength": result.get("promoter_strength", "WEAK_SIGNAL"),
                    "score_breakdown": result.get("score_breakdown", {})
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
                    "conviction_score": result.get("conviction_score", 50.0),
                    "conviction_grade": result.get("conviction_grade", "C"),
                    "promoter_type": result.get("promoter_type", "NEUTRAL"),
                    "promoter_strength": result.get("promoter_strength", "WEAK_SIGNAL"),
                    "score_breakdown": result.get("score_breakdown", {})
                }
                rejected.append(item)
                if item["category"] not in {"DATA", "TIME"} and item["watch_score"] > 0:
                    watchlist.append(item)
                
        # Sort by conviction score (primary) descending
        candidates = sorted(candidates, key=lambda x: (x["conviction_score"], x["rel_strength"], x["ml_score"]), reverse=True)
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
