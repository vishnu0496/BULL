# notifier.py
import requests

TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"
CHAT_ID = "YOUR_CHAT_ID_HERE"

def send_telegram_alert(ticker: str, price: float, ml_score: float, rsi: float, rvol: float):
    message = (
        f"🚨 *BULL Breakout Alert* 🚨\n\n"
        f"📈 *Ticker:* {ticker}\n"
        f"💰 *Trigger Price:* ₹{price:.2f}\n"
        f"🎯 *ML Confidence:* {ml_score:.1%}\n"
        f"📊 *Relative Volume (RVOL):* {rvol:.2f}x\n"
        f"⚡ *RSI:* {rsi:.1f}\n\n"
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
