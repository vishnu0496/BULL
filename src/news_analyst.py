from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable

from src import database
from src.news import fetch_stock_news, get_aggregated_sentiment


INDEX_SYMBOLS = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}

EVENT_RULES = [
    ("EARNINGS", {"result", "results", "profit", "revenue", "margin", "quarter", "q1", "q2", "q3", "q4", "earnings"}),
    ("ORDER_WIN", {"order", "contract", "deal", "project", "tender", "award", "agreement"}),
    ("REGULATION", {"rbi", "sebi", "government", "ministry", "policy", "tariff", "duty", "regulation", "approval"}),
    ("LEGAL_RISK", {"probe", "fraud", "scam", "investigation", "lawsuit", "penalty", "fine", "raid"}),
    ("BROKER_VIEW", {"upgrade", "downgrade", "target price", "buy rating", "sell rating", "neutral rating"}),
    ("CORPORATE_ACTION", {"dividend", "split", "bonus", "buyback", "merger", "demerger"}),
    ("MACRO_COMMODITY", {"crude", "oil", "gas", "metal", "coal", "commodity", "gold", "copper", "aluminium"}),
    ("CURRENCY_RATE", {"rupee", "dollar", "usd/inr", "forex", "yield", "rate cut", "rate hike", "interest rate"}),
    ("MANAGEMENT", {"ceo", "cfo", "resigns", "appoints", "management", "board"}),
]

EVENT_WEIGHTS = {
    "LEGAL_RISK": 95,
    "REGULATION": 85,
    "EARNINGS": 80,
    "ORDER_WIN": 72,
    "CORPORATE_ACTION": 68,
    "MACRO_COMMODITY": 64,
    "CURRENCY_RATE": 62,
    "BROKER_VIEW": 58,
    "MANAGEMENT": 55,
    "GENERAL": 35,
}

POSITIVE_CUES = {
    "profit", "growth", "beats", "beat", "surge", "rally", "order", "contract",
    "upgrade", "buy", "dividend", "bonus", "buyback", "approval", "wins", "record",
}

NEGATIVE_CUES = {
    "loss", "decline", "fall", "drops", "slump", "downgrade", "sell", "probe",
    "fraud", "penalty", "fine", "lawsuit", "warning", "weak", "debt", "default",
}

SECTOR_IMPACT_RULES = {
    "crude oil up": {
        "positive": {"ONGC.NS", "COALINDIA.NS"},
        "negative_keywords": {"paint", "aviation", "airline", "chemical"},
    },
    "rupee weak": {
        "positive": {"TCS.NS", "INFY.NS"},
        "negative_keywords": {"import", "oil", "forex debt"},
    },
    "rates up": {
        "negative_keywords": {"bank", "nbfc", "finance", "real estate"},
    },
}


def _tokens(text: str) -> set[str]:
    clean = text.lower().replace("-", " ").replace("/", " ")
    return {part.strip(".,;:?!'\"()[]{}") for part in clean.split() if part.strip()}


def classify_event(title: str) -> str:
    title_lower = title.lower()
    token_set = _tokens(title)
    for event_type, cues in EVENT_RULES:
        if any(cue in title_lower or cue in token_set for cue in cues):
            return event_type
    return "GENERAL"


def score_materiality(title: str, event_type: str, sentiment_score: float) -> tuple[int, str]:
    base = EVENT_WEIGHTS.get(event_type, EVENT_WEIGHTS["GENERAL"])
    token_set = _tokens(title)
    if token_set & POSITIVE_CUES:
        base += 8
    if token_set & NEGATIVE_CUES:
        base += 12
    base += int(min(abs(float(sentiment_score or 0.0)) * 18, 18))
    score = max(0, min(base, 100))

    if score >= 85:
        return score, "CRITICAL"
    if score >= 70:
        return score, "HIGH"
    if score >= 50:
        return score, "MEDIUM"
    return score, "LOW"


def infer_impact(ticker: str, title: str, sentiment_label: str, event_type: str) -> tuple[str, str]:
    title_lower = title.lower()
    ticker = ticker.upper()

    if event_type == "LEGAL_RISK":
        return "NEGATIVE", "Legal/regulatory risk can damage price confidence quickly."
    if event_type == "ORDER_WIN":
        return "POSITIVE", "Order or contract news can support future revenue visibility."
    if event_type == "BROKER_VIEW" and "downgrade" in title_lower:
        return "NEGATIVE", "Broker downgrade can create short-term selling pressure."
    if event_type == "BROKER_VIEW" and "upgrade" in title_lower:
        return "POSITIVE", "Broker upgrade can attract momentum buying."
    if event_type == "CORPORATE_ACTION":
        return "POSITIVE", "Corporate action headlines often improve attention and liquidity."
    if "crude" in title_lower or "oil" in title_lower:
        if ticker in SECTOR_IMPACT_RULES["crude oil up"]["positive"]:
            return "POSITIVE", "Oil/energy linked stock may benefit from crude strength."
        return "CAUTION", "Crude-linked news can affect input costs and market mood."
    if "rupee" in title_lower or "usd" in title_lower:
        if ticker in SECTOR_IMPACT_RULES["rupee weak"]["positive"]:
            return "POSITIVE", "Exporter-linked stock may benefit from rupee weakness."
        return "CAUTION", "Currency movement can affect foreign flows and import costs."

    if sentiment_label == "BULLISH":
        return "POSITIVE", "Headline sentiment is supportive, but event impact must still match price action."
    if sentiment_label == "BEARISH":
        return "NEGATIVE", "Headline sentiment is negative enough to demand caution."
    return "NEUTRAL", "No strong directional impact detected from this headline."


def analyze_news_item(ticker: str, item: dict) -> dict:
    title = str(item.get("title", ""))
    event_type = classify_event(title)
    sentiment_score = float(item.get("sentiment_score", 0.0) or 0.0)
    sentiment_label = str(item.get("sentiment_label", "NEUTRAL") or "NEUTRAL").upper()
    materiality_score, materiality = score_materiality(title, event_type, sentiment_score)
    impact, reason = infer_impact(ticker, title, sentiment_label, event_type)
    return {
        "ticker": ticker.upper(),
        "title": title,
        "publisher": item.get("publisher", "Unknown"),
        "link": item.get("link", ""),
        "pub_time": item.get("pub_time", 0),
        "event_type": event_type,
        "materiality": materiality,
        "materiality_score": materiality_score,
        "sentiment_label": sentiment_label,
        "sentiment_score": sentiment_score,
        "impact": impact,
        "reason": reason,
    }


def summarize_ticker_news(ticker: str, items: Iterable[dict]) -> dict:
    analyzed = [analyze_news_item(ticker, item) for item in items]
    if not analyzed:
        return {
            "ticker": ticker.upper(),
            "news_count": 0,
            "net_news_score": 0,
            "verdict": "NO_NEWS",
            "summary": "No fresh news found.",
            "top_events": [],
        }

    impact_points = {"POSITIVE": 1, "NEGATIVE": -1, "CAUTION": -0.35, "NEUTRAL": 0}
    weighted = sum(impact_points.get(item["impact"], 0) * item["materiality_score"] for item in analyzed)
    net_score = round(weighted / max(len(analyzed), 1), 2)
    top_events = sorted(analyzed, key=lambda item: item["materiality_score"], reverse=True)[:3]
    event_counts = Counter(item["event_type"] for item in analyzed)

    if net_score >= 25:
        verdict = "NEWS_SUPPORTIVE"
        summary = "News flow is supportive for this stock today."
    elif net_score <= -25:
        verdict = "NEWS_RISK"
        summary = "News flow is risky enough to avoid blind long entries."
    elif any(item["materiality"] in {"HIGH", "CRITICAL"} and item["impact"] == "CAUTION" for item in top_events):
        verdict = "EVENT_CAUTION"
        summary = "Important news exists, but direction is not clean. Treat as watch-only."
    else:
        verdict = "NEWS_NEUTRAL"
        summary = "No strong news edge detected."

    return {
        "ticker": ticker.upper(),
        "news_count": len(analyzed),
        "net_news_score": net_score,
        "verdict": verdict,
        "summary": summary,
        "event_mix": dict(event_counts),
        "top_events": top_events,
    }


def build_daily_analyst_report(force_refresh: bool = False, limit: int = 12) -> dict:
    database.init_db()
    settings = database.get_capital_settings()
    gemini_key = settings.get("gemini_api_key", "")
    tickers = [t for t in database.get_watchlist_tickers() if t.upper() not in INDEX_SYMBOLS]
    tickers = tickers[:limit]

    stock_reports = []
    all_events = []
    for ticker in tickers:
        items = fetch_stock_news(ticker, gemini_api_key=gemini_key, force_refresh=force_refresh)
        report = summarize_ticker_news(ticker, items)
        stock_reports.append(report)
        all_events.extend(report.get("top_events", []))

    risky = [r for r in stock_reports if r["verdict"] in {"NEWS_RISK", "EVENT_CAUTION"}]
    supportive = [r for r in stock_reports if r["verdict"] == "NEWS_SUPPORTIVE"]
    neutral = [r for r in stock_reports if r["verdict"] in {"NEWS_NEUTRAL", "NO_NEWS"}]
    top_events = sorted(all_events, key=lambda item: item["materiality_score"], reverse=True)[:8]

    if risky:
        desk_command = "CAUTION"
        desk_reason = f"{len(risky)} tracked stocks have risky or unclear high-impact news. Do not force trades."
    elif supportive:
        desk_command = "SELECTIVE_WATCH"
        desk_reason = f"{len(supportive)} stocks have supportive news. Trade only if technical setup also agrees."
    else:
        desk_command = "NEWS_NEUTRAL"
        desk_reason = "No strong news edge detected from current free sources."

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_cost": "INR 0 - free Yahoo Finance/Google-style cached news and local rules",
        "desk_command": desk_command,
        "desk_reason": desk_reason,
        "counts": {
            "tracked": len(stock_reports),
            "supportive": len(supportive),
            "risky": len(risky),
            "neutral": len(neutral),
        },
        "supportive_stocks": supportive[:5],
        "risk_stocks": risky[:5],
        "top_events": top_events,
        "stock_reports": sorted(stock_reports, key=lambda item: item["net_news_score"], reverse=True),
    }
