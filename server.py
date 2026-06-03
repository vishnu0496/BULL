# server.py
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

@app.get("/")
def serve_dashboard():
    return FileResponse(
        "index.html",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )

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

@app.post("/api/trade/close")
def close_trade(trade_id: int, exit_price: float):
    trade = broker.close_trade(trade_id, exit_price)
    if trade:
        return {"status": "success", "trade": trade}
    return {"status": "error", "message": "Trade not found"}

@app.post("/api/trade/close_all")
def close_all_trades(win_rate: float = 0.65):
    updated = broker.close_all_trades(win_rate)
    return {"status": "success", "resolved_count": len(updated), "trades": updated}


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
        "avg_r_multiple": round(sum(t.get("r_multiple", 0.0) for t in closed_trades) / len(closed_trades), 2),
        "trades_taken": len(trades),
        "closed_trades": len(closed_trades),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "open_trades": len([t for t in trades if t["status"] == "OPEN"]),
        "equity_curve": equity_curve
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
