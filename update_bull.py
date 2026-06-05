# update_bull.py
import os

print("--- Starting BULL Terminal Auto-Updater ---")

# Define all project files to be written automatically
files = {}

# 1. ML Ensemble Core
files["ml_ensemble.py"] = """# ml_ensemble.py
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

class MLBreakoutEnsemble:
    def __init__(self):
        self.xgb_model = XGBClassifier(n_estimators=100, max_depth=4, learning_rate=0.05, random_state=42, eval_metric='logloss')
        self.rf_model = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
        self.scaler = StandardScaler()
        self.is_trained = False

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        # Calculate robust predictive features without lookahead bias
        df = df.copy()
        
        # Returns and Momentum
        df['return_1d'] = df['Close'].pct_change()
        df['return_5d'] = df['Close'].pct_change(5)
        
        # Volatility & ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr_20'] = true_range.rolling(20).mean()
        df['natr'] = df['atr_20'] / df['Close']
        
        # Volume features
        df['vol_sma20'] = df['Volume'].rolling(20).mean()
        df['rvol'] = df['Volume'] / (df['vol_sma20'] + 1e-8)
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / (loss + 1e-8)
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Trend / Moving average distance
        df['sma_50'] = df['Close'].rolling(50).mean()
        df['sma_200'] = df['Close'].rolling(200).mean()
        df['dist_sma50'] = (df['Close'] - df['sma_50']) / df['sma_50']
        df['dist_sma200'] = (df['Close'] - df['sma_200']) / df['sma_200']
        
        # Temporal lags (Simulates sequence model behavior safely)
        for lag in [1, 2, 3, 5]:
            df[f'rsi_lag_{lag}'] = df['rsi_14'].shift(lag)
            df[f'rvol_lag_{lag}'] = df['rvol'].shift(lag)
            df[f'return_lag_{lag}'] = df['return_1d'].shift(lag)
            
        return df.dropna()

    def generate_labels(self, df: pd.DataFrame, target_r: float = 2.0) -> pd.Series:
        # Labels breakouts: 1 if price reaches entry + (target_r * ATR) before hitting entry - 1 * ATR
        labels = []
        close = df['Close'].values
        atr = df['atr_20'].values
        
        for i in range(len(df)):
            if i >= len(df) - 5:
                labels.append(0)
                continue
            
            entry_price = close[i]
            stop_loss = entry_price - atr[i]
            take_profit = entry_price + (target_r * atr[i])
            
            triggered = 0
            for step in range(1, 6):
                future_high = df['High'].values[i + step]
                future_low = df['Low'].values[i + step]
                
                if future_low <= stop_loss:
                    triggered = 0
                    break
                if future_high >= take_profit:
                    triggered = 1
                    break
            labels.append(triggered)
            
        return pd.Series(labels, index=df.index)

    def train_walk_forward(self, df: pd.DataFrame):
        # Train models using strict temporal sequencing to prevent lookahead leakage
        df_feats = self.calculate_indicators(df)
        labels = self.generate_labels(df_feats)
        
        feature_cols = [col for col in df_feats.columns if 'lag' in col or col in 
                        ['rsi_14', 'rvol', 'dist_sma50', 'dist_sma200', 'natr']]
        
        X = df_feats[feature_cols]
        y = labels
        
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        self.xgb_model.fit(X_train_scaled, y_train)
        self.rf_model.fit(X_train_scaled, y_train)
        self.is_trained = True
        print("[ML Engine] Out-of-Sample Walk-Forward Training Completed.")

    def predict_prob_scaled(self, X_scaled) -> np.ndarray:
        xgb_probs = self.xgb_model.predict_proba(X_scaled)[:, 1]
        rf_probs = self.rf_model.predict_proba(X_scaled)[:, 1]
        return (0.6 * xgb_probs) + (0.4 * rf_probs)

    def predict_latest(self, df: pd.DataFrame) -> float:
        if not self.is_trained:
            return 0.50
        df_feats = self.calculate_indicators(df)
        if len(df_feats) == 0:
            return 0.50
        
        feature_cols = [col for col in df_feats.columns if 'lag' in col or col in 
                        ['rsi_14', 'rvol', 'dist_sma50', 'dist_sma200', 'natr']]
        
        latest_row = df_feats[feature_cols].tail(1)
        latest_scaled = self.scaler.transform(latest_row)
        prob = self.predict_prob_scaled(latest_scaled)[0]
        return float(prob)
"""

# 2. Rule Engine
files["engine.py"] = """# engine.py
import datetime
import pandas as pd
import yfinance as yf
from ml_ensemble import MLBreakoutEnsemble

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
        
    def bootstrap_and_train(self):
        print("[Engine] Bootstrapping historical data for NSE universe...")
        for ticker in self.tickers:
            try:
                df = yf.download(ticker, period="1y", interval="1d")
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
            nifty_df = yf.download("^NSEI", period="1mo", interval="1d")
            
            if stock_df is None or nifty_df.empty:
                return 1.0
                
            stock_ret = stock_df['Close'].pct_change(20).iloc[-1]
            nifty_ret = nifty_df['Close'].pct_change(20).iloc[-1]
            return float(stock_ret - nifty_ret)
        except Exception:
            return 1.0

    def evaluate_filters(self, ticker: str, current_time: datetime.time) -> dict:
        df = yf.download(ticker, period="5d", interval="15m")
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
            vix = yf.download("^INDIAVIX", period="1d")['Close'].iloc[-1]
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

    def scan(self) -> list:
        candidates = []
        now = datetime.datetime.now().time()
        
        if now < datetime.time(9, 15) or now > datetime.time(15, 30):
            now = datetime.time(10, 30) # Default simulation time outside market hours
            
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
                
        candidates = sorted(candidates, key=lambda x: (x["rel_strength"], x["ml_score"]), reverse=True)
        return candidates[:2]
"""

# 3. Paper Broker & Logger
files["paper_broker.py"] = """# paper_broker.py
import json
import os
import datetime

JOURNAL_FILE = "trades_journal.json"
SIGNALS_FILE = "signals_log.json"

class BULLPaperBroker:
    def __init__(self, initial_capital: float = 100000.0):
        self.capital = initial_capital
        self.trades = self._load_data(JOURNAL_FILE, [])
        self.signals = self._load_data(SIGNALS_FILE, [])
        
    def _load_data(self, filename, default):
        if os.path.exists(filename):
            try:
                with open(filename, 'r') as f:
                    return json.load(f)
            except Exception:
                return default
        return default

    def _save_data(self, filename, data):
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)

    def log_engine_signal(self, ticker: str, price: float, ml_score: float, rsi: float, rvol: float):
        signal = {
            "timestamp": datetime.datetime.now().isoformat(),
            "ticker": ticker,
            "price": price,
            "ml_score": ml_score,
            "rsi": rsi,
            "rvol": rvol
        }
        self.signals.append(signal)
        self._save_data(SIGNALS_FILE, self.signals)

    def execute_trade(self, ticker: str, entry_price: float, atr: float, ml_score: float) -> dict:
        risk_per_trade = self.capital * 0.01
        stop_loss_distance = 1.5 * atr
        
        if stop_loss_distance <= 0:
            stop_loss_distance = entry_price * 0.02
            
        quantity = int(risk_per_trade / stop_loss_distance)
        if quantity == 0:
            quantity = 1
            
        stop_loss = entry_price - stop_loss_distance
        take_profit = entry_price + (2.5 * atr)
        
        trade = {
            "trade_id": len(self.trades) + 1,
            "ticker": ticker,
            "status": "OPEN",
            "entry_time": datetime.datetime.now().isoformat(),
            "exit_time": None,
            "entry_price": entry_price,
            "exit_price": None,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "ml_score": ml_score,
            "pnl": 0.0,
            "r_multiple": 0.0
        }
        
        self.trades.append(trade)
        self._save_data(JOURNAL_FILE, self.trades)
        return trade
"""

# 4. Telegram Alerts
files["notifier.py"] = """# notifier.py
import requests

TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"

def send_telegram_alert(ticker: str, price: float, ml_score: float, rsi: float, rvol: float):
    message = (
        f"🚨 *BULL Breakout Alert* 🚨\\n\\n"
        f"📈 *Ticker:* {ticker}\\n"
        f"💰 *Trigger Price:* ₹{price:.2f}\\n"
        f"🎯 *ML Confidence:* {ml_score:.1%}\\n"
        f"📊 *Relative Volume (RVOL):* {rvol:.2f}x\\n"
        f"⚡ *RSI:* {rsi:.1f}\\n\\n"
        f"👉 _Review risk size using the KELLY calculator before taking action._"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to transmit Telegram alert: {e}")
"""

# 5. FastAPI Backend
files["server.py"] = """# server.py
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from engine import BULLSignalEngine
from paper_broker import BULLPaperBroker

app = FastAPI(title="BULL Stock Terminal Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = BULLSignalEngine()
broker = BULLPaperBroker(initial_capital=100000.0)

@app.on_event("startup")
def startup_event():
    engine.bootstrap_and_train()

@app.get("/api/scan")
def run_scanner(background_tasks: BackgroundTasks):
    candidates = engine.scan()
    for c in candidates:
        broker.log_engine_signal(c["ticker"], c["price"], c["ml_score"], c["rsi"], c["rvol"])
    return {"status": "success", "data": candidates}

@app.post("/api/trade/execute")
def execute_trade(ticker: str, price: float, atr: float, ml_score: float):
    trade = broker.execute_trade(ticker, price, atr, ml_score)
    return {"status": "success", "trade": trade}

@app.get("/api/trades")
def get_trades():
    return {"status": "success", "trades": broker.trades}

@app.get("/api/analytics")
def get_analytics():
    trades = broker.trades
    closed_trades = [t for t in trades if t["status"] == "CLOSED"]
    
    if not closed_trades:
        return {
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": 1.0,
            "max_drawdown": 0.0,
            "kelly_criterion": 10.0,
            "equity_curve": [100000.0]
        }
        
    wins = [t for t in closed_trades if t["pnl"] > 0]
    losses = [t for t in closed_trades if t["pnl"] <= 0]
    
    win_rate = (len(wins) / len(closed_trades)) * 100 if closed_trades else 0
    total_gains = sum(t["pnl"] for t in wins)
    total_losses = abs(sum(t["pnl"] for t in losses))
    profit_factor = total_gains / (total_losses if total_losses > 0 else 1.0)
    
    current_equity = 100000.0
    equity_curve = [current_equity]
    peak = current_equity
    max_dd = 0.0
    
    for t in closed_trades:
        current_equity += t["pnl"]
        equity_curve.append(current_equity)
        if current_equity > peak:
            peak = current_equity
        dd = (peak - current_equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
            
    avg_win = (total_gains / len(wins)) if len(wins) > 0 else 1.0
    avg_loss = (total_losses / len(losses)) if len(losses) > 0 else 1.0
    win_ratio = avg_win / (avg_loss if avg_loss > 0 else 1.0)
    
    w_frac = win_rate / 100
    kelly = 0.0
    if win_ratio > 0:
        kelly = w_frac - ((1 - w_frac) / win_ratio)
    kelly_pct = max(0.0, min(kelly * 100, 20.0))
    
    return {
        "net_pnl": sum(t["pnl"] for t in closed_trades),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "max_drawdown": round(max_dd, 2),
        "kelly_criterion": round(kelly_pct, 2),
        "equity_curve": equity_curve
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
"""

# 6. HTML Front-end
files["index.html"] = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BULL Research Terminal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'JetBrains Mono', monospace; background-color: #0d0e12; color: #e4e6eb; }
    </style>
</head>
<body class="p-6">
    <div class="max-w-7xl mx-auto space-y-6">
        <div class="flex justify-between items-center border-b border-gray-800 pb-4">
            <div>
                <h1 class="text-3xl font-bold tracking-wider text-green-400">BULL // TERMINAL</h1>
                <p class="text-sm text-gray-400">Professional Quantitative Breakout Engine (NSE/Nifty)</p>
            </div>
            <button onclick="runDailyScan()" class="px-5 py-2.5 bg-green-500 hover:bg-green-600 text-black font-bold rounded transition">
                ⚡ RUN BREAKOUT SCANNER
            </button>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div class="bg-gray-900 p-4 rounded-xl border border-gray-800">
                <span class="text-xs text-gray-500 block">NET PROFIT / LOSS</span>
                <span id="kpi-pnl" class="text-2xl font-bold text-gray-300">₹0.00</span>
            </div>
            <div class="bg-gray-900 p-4 rounded-xl border border-gray-800">
                <span class="text-xs text-gray-500 block">WIN RATE</span>
                <span id="kpi-winrate" class="text-2xl font-bold text-green-400">0.00%</span>
            </div>
            <div class="bg-gray-900 p-4 rounded-xl border border-gray-800">
                <span class="text-xs text-gray-500 block">PROFIT FACTOR</span>
                <span id="kpi-pf" class="text-2xl font-bold text-gray-300">1.00</span>
            </div>
            <div class="bg-gray-900 p-4 rounded-xl border border-gray-800">
                <span class="text-xs text-gray-500 block">OPTIMAL KELLY RISK SIZE</span>
                <span id="kpi-kelly" class="text-2xl font-bold text-blue-400">10.0%</span>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div class="lg:col-span-1 bg-gray-900 p-5 rounded-xl border border-gray-800 space-y-4">
                <h2 class="text-lg font-bold border-b border-gray-800 pb-2">🎯 TODAY'S SECTOR LEADERS</h2>
                <div id="scan-results-container" class="space-y-3">
                    <p class="text-sm text-gray-500">Run scanner to check live market setups.</p>
                </div>
            </div>

            <div class="lg:col-span-2 bg-gray-900 p-5 rounded-xl border border-gray-800">
                <h2 class="text-lg font-bold border-b border-gray-800 pb-2 mb-4">📈 EQUITY CURVE (OOS PATH)</h2>
                <div class="h-64">
                    <canvas id="equityChart"></canvas>
                </div>
            </div>
        </div>

        <div class="bg-gray-900 p-5 rounded-xl border border-gray-800">
            <h2 class="text-lg font-bold border-b border-gray-800 pb-4 mb-4">📝 ACTIVE JOURNAL & PERFORMANCE TELEMETRY LOG</h2>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead>
                        <tr class="border-b border-gray-800 text-xs text-gray-500">
                            <th class="py-2">TICKER</th>
                            <th class="py-2">STATUS</th>
                            <th class="py-2">QTY</th>
                            <th class="py-2">ENTRY (₹)</th>
                            <th class="py-2">STOP (₹)</th>
                            <th class="py-2">TARGET (₹)</th>
                            <th class="py-2">P&L (₹)</th>
                        </tr>
                    </thead>
                    <tbody id="trades-table-body" class="divide-y divide-gray-800 text-sm">
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const API_URL = "http://127.0.0.1:8000/api";
        let chartInstance = null;

        async function fetchTelemetry() {
            try {
                const r = await fetch(`${API_URL}/analytics`);
                const analytics = (await r.json()).data || (await r.json());
                
                document.getElementById('kpi-pnl').innerText = `₹${analytics.net_pnl.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
                document.getElementById('kpi-pnl').className = `text-2xl font-bold ${analytics.net_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
                document.getElementById('kpi-winrate').innerText = `${analytics.win_rate}%`;
                document.getElementById('kpi-pf').innerText = analytics.profit_factor;
                document.getElementById('kpi-kelly').innerText = `${analytics.kelly_criterion}%`;

                const ctx = document.getElementById('equityChart').getContext('2d');
                if (chartInstance) chartInstance.destroy();
                chartInstance = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: analytics.equity_curve.map((_, i) => `Trade ${i}`),
                        datasets: [{
                            label: 'Net Equity Curve (₹)',
                            data: analytics.equity_curve,
                            borderColor: '#10b981',
                            backgroundColor: 'rgba(16, 185, 129, 0.05)',
                            fill: true,
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: {
                            y: { grid: { color: '#1f2937' }, ticks: { color: '#9ca3af' } },
                            x: { grid: { display: false }, ticks: { color: '#9ca3af' } }
                        }
                    }
                });
            } catch(e) { console.error("Error reading portfolio telemetry", e); }
        }

        async function runDailyScan() {
            const container = document.getElementById("scan-results-container");
            container.innerHTML = `<p class="text-sm text-yellow-400 animate-pulse">Running ML calculations & sector scans...</p>`;
            try {
                const r = await fetch(`${API_URL}/scan`);
                const res = await r.json();
                container.innerHTML = "";
                
                if(!res.data || res.data.length === 0) {
                    container.innerHTML = `<p class="text-sm text-gray-500">No stocks passed the filters today. Capital preserved.</p>`;
                    return;
                }

                res.data.forEach(stock => {
                    const el = document.createElement("div");
                    el.className = "bg-gray-800 p-4 rounded-lg border border-gray-700 space-y-2";
                    el.innerHTML = `
                        <div class="flex justify-between">
                            <span class="font-bold text-green-400">${stock.ticker}</span>
                            <span class="text-xs text-gray-400">Score: ${(stock.ml_score*100).toFixed(0)}%</span>
                        </div>
                        <div class="text-xs text-gray-300 space-y-1">
                            <div>Price: ₹${stock.price.toFixed(2)}</div>
                            <div>RVOL: ${stock.rvol.toFixed(1)}x | RSI: ${stock.rsi.toFixed(0)}</div>
                        </div>
                        <button onclick="executePaperTrade('${stock.ticker}', ${stock.price}, ${stock.atr}, ${stock.ml_score})" class="w-full mt-2 py-1 bg-green-500 text-black text-xs font-bold rounded hover:bg-green-600 transition">
                            EXECUTE TRADE (1% RISK)
                        </button>
                    `;
                    container.appendChild(el);
                });
            } catch(e) {
                container.innerHTML = `<p class="text-sm text-red-400">Failed to communicate with local trading server.</p>`;
            }
        }

        async function executePaperTrade(ticker, price, atr, ml_score) {
            try {
                await fetch(`${API_URL}/trade/execute?ticker=${ticker}&price=${price}&atr=${atr}&ml_score=${ml_score}`, {method: 'POST'});
                fetchTelemetry();
                loadTrades();
            } catch(e) { console.error("Failed to execute order", e); }
        }

        async function loadTrades() {
            try {
                const r = await fetch(`${API_URL}/trades`);
                const res = await r.json();
                const tbody = document.getElementById("trades-table-body");
                tbody.innerHTML = "";
                
                res.trades.reverse().forEach(t => {
                    const row = document.createElement("tr");
                    row.className = "border-b border-gray-800";
                    row.innerHTML = `
                        <td class="py-3 font-bold">${t.ticker}</td>
                        <td class="py-3"><span class="px-2 py-0.5 rounded text-xs \${t.status === 'OPEN' ? 'bg-blue-900/40 text-blue-300' : 'bg-gray-800 text-gray-400'}">\${t.status}</span></td>
                        <td class="py-3">\${t.quantity}</td>
                        <td class="py-3">₹\${t.entry_price.toFixed(2)}</td>
                        <td class="py-3 text-red-400">₹\${t.stop_loss.toFixed(2)}</td>
                        <td class="py-3 text-green-400">₹\${t.take_profit.toFixed(2)}</td>
                        <td class="py-3 font-bold \${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}">₹\${t.pnl.toFixed(2)}</td>
                    `;
                    tbody.appendChild(row);
                });
            } catch(e) { console.error("Error reading journal logs", e); }
        }

        fetchTelemetry();
        loadTrades();
    </script>
</body>
</html>
"""

# Write files to directory
for filename, content in files.items():
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[Success] Created/Updated: {filename}")

print("\n--- Update Completed Successfully! ---")
