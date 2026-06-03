from datetime import datetime
import time
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd
import yfinance as yf


class BullFreeMarketFeed:
    """
    Zero-cost market feed adapter.

    This gives BULL a Kite-like internal interface while using free sources.
    It is not exchange-grade streaming data: candles can be delayed, missing,
    or rate-limited by Yahoo/yfinance.
    """

    def __init__(self, cache_seconds: int = 60):
        self.cache_seconds = cache_seconds
        self._cache: Dict[Tuple[str, str, str], Tuple[float, pd.DataFrame]] = {}
        self.last_errors: Dict[str, str] = {}
        self.request_count = 0
        self.cache_hits = 0

    @staticmethod
    def _normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = df.columns.droplevel(1)
        return df.dropna(how="all")

    def get_bars(self, ticker: str, period: str = "5d", interval: str = "15m", force_refresh: bool = False) -> pd.DataFrame:
        key = (ticker, period, interval)
        now = time.time()
        cached = self._cache.get(key)
        if cached and not force_refresh and now - cached[0] < self.cache_seconds:
            self.cache_hits += 1
            return cached[1].copy()

        self.request_count += 1
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
            df = self._normalize_frame(df)
            if df.empty:
                self.last_errors[ticker] = f"No {interval} bars returned"
            else:
                self.last_errors.pop(ticker, None)
            self._cache[key] = (now, df)
            return df.copy()
        except Exception as exc:
            self.last_errors[ticker] = str(exc)
            if cached:
                return cached[1].copy()
            return pd.DataFrame()

    def get_quote(self, ticker: str) -> dict:
        bars = self.get_bars(ticker, period="1d", interval="1m")
        if bars.empty:
            bars = self.get_bars(ticker, period="5d", interval="15m")
        if bars.empty:
            return {
                "ticker": ticker,
                "status": "NO_DATA",
                "price": None,
                "timestamp": None,
                "source": "yfinance",
                "cost": "INR 0",
            }

        latest = bars.iloc[-1]
        timestamp = bars.index[-1]
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        return {
            "ticker": ticker,
            "status": "OK",
            "price": float(latest["Close"]),
            "open": float(latest["Open"]),
            "high": float(latest["High"]),
            "low": float(latest["Low"]),
            "volume": int(latest.get("Volume", 0)),
            "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
            "source": "yfinance",
            "cost": "INR 0",
        }

    def health(self, tickers: Optional[Iterable[str]] = None) -> dict:
        symbols = list(tickers or [])
        checked = []
        ok = 0
        stale_or_missing = 0
        for ticker in symbols:
            bars = self.get_bars(ticker, period="5d", interval="15m")
            status = "OK" if not bars.empty else "NO_DATA"
            if status == "OK":
                ok += 1
                latest = bars.index[-1]
                latest_text = latest.isoformat() if hasattr(latest, "isoformat") else str(latest)
            else:
                stale_or_missing += 1
                latest_text = None
            checked.append({
                "ticker": ticker,
                "status": status,
                "latest_bar": latest_text,
                "error": self.last_errors.get(ticker),
            })

        if not symbols:
            feed_status = "NO_SYMBOLS"
        elif ok == len(symbols):
            feed_status = "HEALTHY_FREE_FEED"
        elif ok > 0:
            feed_status = "DEGRADED_FREE_FEED"
        else:
            feed_status = "NO_INTRADAY_DATA"

        return {
            "provider": "BULL Free Feed",
            "source": "yfinance/Yahoo intraday candles",
            "cost": "INR 0",
            "feed_type": "polling cached candles, not broker WebSocket streaming",
            "cache_seconds": self.cache_seconds,
            "status": feed_status,
            "checked_symbols": len(symbols),
            "healthy_symbols": ok,
            "missing_symbols": stale_or_missing,
            "request_count": self.request_count,
            "cache_hits": self.cache_hits,
            "limitations": [
                "Not tick-by-tick exchange streaming",
                "Can be delayed or rate-limited",
                "No order placement or broker account data",
                "Good enough for paper-trading experiments, not enough for serious execution",
            ],
            "symbols": checked,
        }
