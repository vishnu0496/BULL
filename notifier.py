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

def send_morning_brief():
    """Compiles and transmits a daily market intelligence brief to Telegram."""
    if TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE" or CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("[Notifier] Telegram tokens not configured. Skipping morning brief.")
        return False
        
    from src.fii_tracker import get_fii_signal
    from src.earnings_calendar import get_earnings_this_week
    from src.sector_rotation import get_sector_rankings
    from src.premarket_signals import get_premarket_score
    from src.promoter_tracker import get_recent_promoter_activity
    
    try:
        # 1. Premarket details
        pm = get_premarket_score()
        pm_score = pm.get("pre_market_score", 50.0)
        pm_class = pm.get("classification", "NEUTRAL_OPEN")
        pm_rec = pm.get("recommendation", "No recommendation")
        
        # 2. FII details
        fii = get_fii_signal()
        fii_net = fii.get("fii_net", 0.0)
        dii_net = fii.get("dii_net", 0.0)
        fii_streak = f"{fii.get('streak_days', 0)} days {fii.get('streak_type', 'NEUTRAL')}"
        
        # 3. Sector Leaders (top 3)
        sectors = get_sector_rankings()
        top_sectors = sectors[:3]
        sectors_str = ", ".join([f"{s['sector']} (#{s['rank']}, {s['weekly_return']:+.1f}%)" for s in top_sectors]) if top_sectors else "None"
        
        # 4. Earnings this week
        earnings = get_earnings_this_week()
        earnings_str = ", ".join([f"{e['ticker'].replace('.NS','')}" for e in earnings[:5]]) if earnings else "None"
        
        # 5. Promoter activity
        promoters = get_recent_promoter_activity(days=1)
        prom_str = ""
        if promoters:
            for p in promoters[:3]:
                ticker = p['ticker'].replace('.NS','')
                action = p['transaction_type']
                val = p['value_crore']
                prom_str += f"\n• {ticker}: {action} (₹{val:.1f} Cr)"
        else:
            prom_str = "\nNo major promoter trades logged today."
            
        message = (
            f"☀️ *BULL Morning Market Brief* ☀️\n\n"
            f"📊 *Pre-Market Outlook:* {pm_class.replace('_', ' ')} (Score: {pm_score:.0f})\n"
            f"📝 _Rec:_ {pm_rec}\n\n"
            f"👥 *Institutional Flows (FII/DII):*\n"
            f"• FII Net: {fii_net:+.1f} Cr (Streak: {fii_streak})\n"
            f"• DII Net: {dii_net:+.1f} Cr\n\n"
            f"🔥 *Top Sector Leaders:* {sectors_str}\n"
            f"📅 *Earnings This Week:* {earnings_str}\n"
            f"💼 *Promoter Activity (Last 24h):*{prom_str}\n\n"
            f"🤖 _BULL Intelligence Layer v2_"
        )
        
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload, timeout=8)
        print("[Notifier] Morning brief transmitted successfully.")
        return True
    except Exception as e:
        print(f"Failed to transmit Telegram morning brief: {e}")
        return False
