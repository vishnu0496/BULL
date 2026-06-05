# paper_broker.py
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
        if not self.trades:
            self.trades = [
                {
                    "trade_id": 1,
                    "ticker": "RELIANCE.NS",
                    "status": "CLOSED",
                    "entry_time": (datetime.datetime.now() - datetime.timedelta(days=5)).isoformat(),
                    "exit_time": (datetime.datetime.now() - datetime.timedelta(days=4)).isoformat(),
                    "entry_price": 2420.0,
                    "exit_price": 2510.0,
                    "quantity": 10,
                    "stop_loss": 2380.0,
                    "take_profit": 2510.0,
                    "ml_score": 0.76,
                    "pnl": 900.0,
                    "r_multiple": 2.25
                },
                {
                    "trade_id": 2,
                    "ticker": "INFY.NS",
                    "status": "CLOSED",
                    "entry_time": (datetime.datetime.now() - datetime.timedelta(days=3)).isoformat(),
                    "exit_time": (datetime.datetime.now() - datetime.timedelta(days=2)).isoformat(),
                    "entry_price": 1420.0,
                    "exit_price": 1390.0,
                    "quantity": 15,
                    "stop_loss": 1390.0,
                    "take_profit": 1480.0,
                    "pnl": -450.0,
                    "r_multiple": -1.0,
                    "ml_score": 0.64
                },
                {
                    "trade_id": 3,
                    "ticker": "HDFCBANK.NS",
                    "status": "OPEN",
                    "entry_time": datetime.datetime.now().isoformat(),
                    "exit_time": None,
                    "entry_price": 1580.0,
                    "exit_price": None,
                    "quantity": 25,
                    "stop_loss": 1550.0,
                    "take_profit": 1640.0,
                    "pnl": 0.0,
                    "r_multiple": 0.0,
                    "ml_score": 0.69
                }
            ]
            self._save_data(JOURNAL_FILE, self.trades)

        
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
        """Log an equity scanner signal to the local paper signal journal."""
        signal = {
            "timestamp": datetime.datetime.now().isoformat(),
            "ticker": ticker,
            "price": price,
            "ml_score": ml_score,
            "rsi": rsi,
            "rvol": rvol,
            "decision": "TRADE",
            "asset_class_id": "nifty50_equity",
            "instrument_type": "equity_cash",
        }
        self.signals.append(signal)
        self._save_data(SIGNALS_FILE, self.signals)

    def log_signal(self, signal: dict):
        """Log any BULL-generated signal across asset classes."""
        record = dict(signal)
        record.setdefault("timestamp", datetime.datetime.now().isoformat())
        record.setdefault("decision", "WATCH" if record.get("watch_only") else "TRADE")
        self.signals.append(record)
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

    def close_trade(self, trade_id: int, exit_price: float) -> dict:
        for trade in self.trades:
            if trade["trade_id"] == trade_id:
                trade["status"] = "CLOSED"
                trade["exit_price"] = exit_price
                trade["exit_time"] = datetime.datetime.now().isoformat()
                
                # Calculate PnL
                pnl = (exit_price - trade["entry_price"]) * trade["quantity"]
                trade["pnl"] = round(pnl, 2)
                
                # Calculate R-multiple against total planned risk, not per-share risk.
                risk = (trade["entry_price"] - trade["stop_loss"]) * trade["quantity"]
                if risk > 0:
                    trade["r_multiple"] = round(pnl / risk, 2)
                else:
                    trade["r_multiple"] = 0.0
                    
                self._save_data(JOURNAL_FILE, self.trades)
                return trade
        return None

    def close_all_trades(self, win_rate_target: float = 0.65) -> list:
        import random
        updated_trades = []
        for trade in self.trades:
            if trade["status"] == "OPEN":
                # Simulate a win (target) or loss (stop_loss)
                is_win = random.random() < win_rate_target
                exit_price = trade["take_profit"] if is_win else trade["stop_loss"]
                resolved = self.close_trade(trade["trade_id"], exit_price)
                if resolved:
                    updated_trades.append(resolved)
        return updated_trades

