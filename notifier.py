# notifier.py
import os
import requests

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def load_env_file():
    """Manually parse .env file to load current environment configurations without external libraries."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        key_val = line.split("=", 1)
                        if len(key_val) == 2:
                            key = key_val[0].strip()
                            val = key_val[1].strip()
                            # Strip outer quotes if present
                            if val.startswith('"') and val.endswith('"'):
                                val = val[1:-1]
                            elif val.startswith("'") and val.endswith("'"):
                                val = val[1:-1]
                            os.environ[key] = val
        except Exception as e:
            print(f"[Notifier] Error loading .env file: {e}")

# Initial load on import
load_env_file()

def get_telegram_config():
    """Reload the environment file and get latest Telegram config parameters."""
    load_env_file()
    token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN") or "YOUR_BOT_TOKEN_HERE"
    chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID") or "YOUR_CHAT_ID_HERE"
    return token, chat_id

def send_telegram_alert(ticker: str, price: float, ml_score: float, rsi: float, rvol: float):
    token, chat_id = get_telegram_config()
    if token == "YOUR_BOT_TOKEN_HERE" or chat_id == "YOUR_CHAT_ID_HERE":
        print("[Notifier] Telegram alerts not configured. Skipping alert.")
        return False

    message = (
        f"🚨 *BULL Breakout Alert* 🚨\n\n"
        f"📈 *Ticker:* {ticker}\n"
        f"💰 *Trigger Price:* ₹{price:.2f}\n"
        f"🎯 *ML Confidence:* {ml_score:.1%}\n"
        f"📊 *Relative Volume (RVOL):* {rvol:.2f}x\n"
        f"⚡ *RSI:* {rsi:.1f}\n\n"
        f"👉 _Review risk size using the KELLY calculator before taking action._"
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
        return True
    except Exception as e:
        print(f"Failed to transmit Telegram alert: {e}")
        return False

def send_morning_brief():
    """Compiles and transmits the daily market intelligence brief to Telegram."""
    token, chat_id = get_telegram_config()
    if token == "YOUR_BOT_TOKEN_HERE" or chat_id == "YOUR_CHAT_ID_HERE":
        print("[Notifier] Telegram tokens not configured. Skipping morning brief.")
        return False
        
    try:
        from src.daily_brief import build_daily_brief, format_telegram_brief
        message = format_telegram_brief(build_daily_brief())
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
        }
        resp = requests.post(url, json=payload, timeout=8)
        resp.raise_for_status()
        print("[Notifier] Morning brief transmitted successfully.")
        return True
    except Exception as e:
        print(f"Failed to transmit Telegram morning brief: {e}")
        return False
