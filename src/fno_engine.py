"""Watch-only F&O, index option, and commodity scanner for BULL."""

from __future__ import annotations

from datetime import datetime
import math
import time
from typing import Any

import pandas as pd
import requests
import yfinance as yf


NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "*/*",
    "Connection": "keep-alive",
}

COMMODITY_TICKERS = {
    "CRUDEOIL": "CL=F",
    "GOLD": "GC=F",
    "SILVER": "SI=F",
    "NATURALGAS": "NG=F",
}

FNO_CACHE = {"timestamp": 0.0, "setups": []}
FNO_CACHE_SECONDS = 600


def _safe_download(ticker: str, period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """Download yFinance data with graceful fallback to an empty frame."""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = df.columns.droplevel(1)
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()


def _rsi(close: pd.Series, period: int = 14) -> float:
    """Calculate the latest RSI value from a close series."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-8)
    value = 100 - (100 / (1 + rs.iloc[-1]))
    return float(value) if not math.isnan(value) else 50.0


def _atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate the latest ATR value from OHLC data."""
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    value = tr.rolling(period).mean().iloc[-1]
    return float(value) if not math.isnan(value) else float(df["Close"].iloc[-1]) * 0.02


def fetch_option_chain(symbol: str) -> dict[str, Any]:
    """Fetch NSE option chain JSON using a session and browser-like headers."""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=8)
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        response = session.get(url, timeout=12)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc), "records": {"data": []}}


def _max_pain(rows: list[dict]) -> int | None:
    """Estimate max pain strike from option-chain open interest."""
    strikes = sorted({int(row.get("strikePrice", 0)) for row in rows if row.get("strikePrice")})
    if not strikes:
        return None
    pain_by_strike = {}
    for target in strikes:
        pain = 0
        for row in rows:
            strike = int(row.get("strikePrice", 0))
            ce_oi = int(row.get("CE", {}).get("openInterest", 0) or 0)
            pe_oi = int(row.get("PE", {}).get("openInterest", 0) or 0)
            pain += max(0, target - strike) * ce_oi
            pain += max(0, strike - target) * pe_oi
        pain_by_strike[target] = pain
    return min(pain_by_strike, key=pain_by_strike.get)


def scan_index_options(symbol: str = "NIFTY") -> dict:
    """Create a watch-only index option positioning summary."""
    chain = fetch_option_chain(symbol)
    rows = chain.get("records", {}).get("data", []) or []
    if not rows:
        return {
            "instrument": symbol,
            "instrument_type": "index_option",
            "asset_class_id": "index_options",
            "watch_only": True,
            "decision": "WATCH",
            "status": "DATA_UNAVAILABLE",
            "type_badge": "INDEX OPT",
            "key_stat": "PCR unavailable",
            "learn_note": "NSE option-chain data is unavailable right now, so BULL will not infer option positioning.",
            "sebi_warning": "9 out of 10 F&O traders lose money (SEBI study)",
        }

    total_ce = sum(int(row.get("CE", {}).get("openInterest", 0) or 0) for row in rows)
    total_pe = sum(int(row.get("PE", {}).get("openInterest", 0) or 0) for row in rows)
    pcr = total_pe / total_ce if total_ce else 0
    max_ce_row = max(rows, key=lambda row: int(row.get("CE", {}).get("openInterest", 0) or 0))
    max_pe_row = max(rows, key=lambda row: int(row.get("PE", {}).get("openInterest", 0) or 0))
    resistance = int(max_ce_row.get("strikePrice", 0) or 0)
    support = int(max_pe_row.get("strikePrice", 0) or 0)
    max_pain = _max_pain(rows)
    if pcr > 1.5:
        bias = "bullish positioning"
        note = f"Put open interest is heavy. Market is defending support near {support}, but this is watch-only."
    elif pcr < 0.7:
        bias = "bearish positioning"
        note = f"Call open interest is heavy. Market may face resistance near {resistance}, but this is watch-only."
    else:
        bias = "balanced positioning"
        note = f"Options positioning is balanced. Max pain is near {max_pain}; avoid guessing direction."

    return {
        "instrument": symbol,
        "instrument_name": f"{symbol} Option Chain",
        "instrument_type": "index_option",
        "asset_class_id": "index_options",
        "watch_only": True,
        "decision": "WATCH",
        "type_badge": "INDEX OPT",
        "key_stat": f"PCR {pcr:.2f}",
        "pcr": round(pcr, 2),
        "support": support,
        "resistance": resistance,
        "max_pain": max_pain,
        "bias": bias,
        "learn_note": note,
        "sebi_warning": "9 out of 10 F&O traders lose money (SEBI study)",
        "created_at": datetime.now().isoformat(),
    }


def scan_commodity(name: str, yahoo_ticker: str) -> dict:
    """Create a watch-only commodity futures setup from free Yahoo futures data."""
    df = _safe_download(yahoo_ticker)
    if df.empty or len(df) < 20:
        return {
            "instrument": name,
            "instrument_name": f"{name} MCX Watch",
            "instrument_type": "commodity_future",
            "asset_class_id": "commodity_futures",
            "watch_only": True,
            "decision": "WATCH",
            "status": "DATA_UNAVAILABLE",
            "type_badge": "COMMODITY",
            "key_stat": "Data unavailable",
            "learn_note": "Free commodity data is missing or stale, so BULL will only observe.",
            "sebi_warning": "9 out of 10 F&O traders lose money (SEBI study)",
        }

    close = df["Close"]
    price = float(close.iloc[-1])
    change = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(close) > 1 else 0.0
    atr = _atr(df)
    rsi = _rsi(close)
    volume = float(df["Volume"].iloc[-1] or 0)
    avg_volume = float(df["Volume"].tail(20).mean() or 1)
    rvol = volume / avg_volume if avg_volume else 0
    bias = "momentum watch" if rvol >= 1.2 and 35 <= rsi <= 70 else "wait for cleaner volume"
    learn = f"{name} is moving {change:.2f}% with RVOL {rvol:.2f}x. Watch only because commodities are leveraged."
    return {
        "instrument": name,
        "instrument_name": f"{name} Commodity Future",
        "instrument_type": "commodity_future",
        "asset_class_id": "commodity_futures",
        "watch_only": True,
        "decision": "WATCH",
        "type_badge": "COMMODITY",
        "key_stat": f"{change:+.2f}%",
        "price": round(price, 2),
        "rvol": round(float(rvol), 2),
        "rsi": round(float(rsi), 1),
        "atr": round(float(atr), 2),
        "bias": bias,
        "learn_note": learn,
        "sebi_warning": "9 out of 10 F&O traders lose money (SEBI study)",
        "created_at": datetime.now().isoformat(),
    }


def scan_stock_future_proxy(ticker: str) -> dict:
    """Create a watch-only stock-future proxy from spot equity data."""
    df = _safe_download(ticker)
    if df.empty or len(df) < 20:
        return {
            "instrument": ticker,
            "instrument_type": "stock_future",
            "asset_class_id": "stock_futures",
            "watch_only": True,
            "decision": "WATCH",
            "type_badge": "STOCK FUT",
            "key_stat": "Spot proxy unavailable",
            "learn_note": "BULL could not fetch spot data for this futures proxy.",
            "sebi_warning": "9 out of 10 F&O traders lose money (SEBI study)",
        }
    price = float(df["Close"].iloc[-1])
    rsi = _rsi(df["Close"])
    rvol = float(df["Volume"].iloc[-1] / (df["Volume"].tail(20).mean() or 1))
    return {
        "instrument": ticker.replace(".NS", ""),
        "instrument_name": f"{ticker.replace('.NS', '')} Stock Futures Proxy",
        "instrument_type": "stock_future",
        "asset_class_id": "stock_futures",
        "watch_only": True,
        "decision": "WATCH",
        "type_badge": "STOCK FUT",
        "key_stat": "Basis N/A",
        "price": round(price, 2),
        "basis": None,
        "cost_of_carry": None,
        "rvol": round(rvol, 2),
        "rsi": round(rsi, 1),
        "learn_note": "This uses the equity spot chart as a futures proxy. Futures basis needs broker/exchange data.",
        "sebi_warning": "9 out of 10 F&O traders lose money (SEBI study)",
        "created_at": datetime.now().isoformat(),
    }


def scan_fno_watchlist(force_refresh: bool = False) -> list[dict]:
    """Return cached watch-only F&O and commodity setups."""
    now = time.time()
    if not force_refresh and FNO_CACHE["setups"] and now - FNO_CACHE["timestamp"] < FNO_CACHE_SECONDS:
        return FNO_CACHE["setups"]

    setups = [
        scan_index_options("NIFTY"),
        scan_index_options("BANKNIFTY"),
        scan_stock_future_proxy("RELIANCE.NS"),
        scan_stock_future_proxy("HDFCBANK.NS"),
    ]
    for name, ticker in COMMODITY_TICKERS.items():
        setups.append(scan_commodity(name, ticker))

    FNO_CACHE["timestamp"] = now
    FNO_CACHE["setups"] = setups
    return setups
