from datetime import date, datetime
import os
import sys
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Add project root directory to path to allow importing from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.database import (
    add_paper_trade,
    get_db_health,
    get_latest_price,
    get_paper_trades,
    get_portfolio_holdings,
    get_prices,
    get_watchlist,
    get_watchlist_tickers,
    init_db,
    remove_from_watchlist,
    get_capital_settings,
    update_capital_settings,
    add_to_watchlist
)
from src.fetcher import sync_ticker
from src.utils import format_inr, format_percentage, get_color_class, get_pnl_indicator
from src.engine import get_all_trade_ideas, generate_trade_idea, get_mentor_suggestions
from src.market import get_market_regime
from src.backtest import run_backtest, get_all_stock_verdicts
from src.news import fetch_stock_news, get_aggregated_sentiment

init_db()

st.set_page_config(
    page_title="BULL Research Desk",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

INDEX_SYMBOLS = {"^NSEI", "NIFTY", "^BSESN", "SENSEX"}

# Caching strategy: Cache the backtest verdicts of watchlist stocks
@st.cache_data
def get_cached_stock_verdicts(tickers_tuple):
    return get_all_stock_verdicts(list(tickers_tuple))

# Caching strategy: Cache the stock news items
@st.cache_data
def get_cached_stock_news(ticker, gemini_api_key=None, force_refresh=False):
    return fetch_stock_news(ticker, gemini_api_key, force_refresh)

# Apply Premium Dark/Glassmorphism Styles
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
    
    /* 1. Global Reset & Body Background */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .stApp {
        background-color: #06090e !important;
        background-image: 
            radial-gradient(at 0% 0%, rgba(20, 30, 48, 0.4) 0px, transparent 50%), 
            radial-gradient(at 100% 0%, rgba(10, 15, 30, 0.8) 0px, transparent 50%),
            radial-gradient(at 50% 100%, rgba(15, 23, 42, 0.9) 0px, transparent 70%) !important;
        background-attachment: fixed !important;
    }
    
    /* Hide default Streamlit visual headers & footer watermarks */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 2.5rem !important;
    }
    
    /* 2. Sidebar Navigation Panel Styling */
    [data-testid="stSidebar"] {
        background-color: #080c14 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.04) !important;
    }
    
    /* Sidebar text colors and headings */
    [data-testid="stSidebar"] h2 {
        font-weight: 800 !important;
        letter-spacing: 0.05em !important;
    }
    
    /* radio navigation controls */
    [data-testid="stSidebar"] .stRadio > div {
        background-color: transparent !important;
    }
    
    [data-testid="stSidebar"] .stRadio label {
        font-size: 0.9rem !important;
        font-weight: 500 !important;
        color: #94a3b8 !important;
        padding: 0.6rem 0.8rem !important;
        border-radius: 8px !important;
        margin-bottom: 0.3rem !important;
        transition: all 0.2s ease !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        border: 1px solid transparent !important;
    }
    
    [data-testid="stSidebar"] .stRadio label:hover {
        background-color: rgba(255, 255, 255, 0.03) !important;
        color: #f8fafc !important;
        border-color: rgba(255, 255, 255, 0.02) !important;
    }
    
    /* Active indicator for navigation */
    [data-testid="stSidebar"] div[role="radiogroup"] > div[data-checked="true"] > label {
        background-color: rgba(56, 189, 248, 0.08) !important;
        color: #38bdf8 !important;
        border-left: 3px solid #38bdf8 !important;
        border-color: rgba(56, 189, 248, 0.15) !important;
        font-weight: 600 !important;
    }
    
    /* 3. Custom Glassmorphic Card Blocks */
    .card {
        background: linear-gradient(135deg, rgba(17, 24, 39, 0.7) 0%, rgba(15, 23, 42, 0.85) 100%);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.04);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }
    
    .card:hover {
        transform: translateY(-2px);
        border-color: rgba(56, 189, 248, 0.15);
        box-shadow: 0 12px 40px rgba(56, 189, 248, 0.06);
    }
    
    /* Glassmorphic Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, rgba(15, 23, 42, 0.5) 0%, rgba(30, 41, 59, 0.3) 100%) !important;
        backdrop-filter: blur(10px) !important;
        border: 1px solid rgba(255, 255, 255, 0.03) !important;
        border-radius: 12px !important;
        padding: 1.1rem !important;
        margin-bottom: 0.75rem !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2) !important;
        transition: all 0.25s ease !important;
    }
    
    .metric-card:hover {
        transform: translateY(-2px) !important;
        border-color: rgba(255, 255, 255, 0.08) !important;
        box-shadow: 0 6px 25px rgba(0,0,0,0.3) !important;
    }
    
    .metric-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        color: #64748b;
        margin-bottom: 0.4rem;
        font-weight: 700;
    }
    
    .metric-value {
        font-size: 1.5rem;
        font-weight: 700;
        color: #f1f5f9;
        letter-spacing: -0.01em;
    }
    
    .metric-note {
        font-size: 0.8rem;
        color: #94a3b8;
        margin-top: 0.3rem;
    }
    
    /* 4. Breathing Pulsate Glow Animations for Today's Command Desk */
    @keyframes pulse-green {
        0% { box-shadow: 0 0 12px rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.25); }
        50% { box-shadow: 0 0 25px rgba(16, 185, 129, 0.28); border-color: rgba(16, 185, 129, 0.45); }
        100% { box-shadow: 0 0 12px rgba(16, 185, 129, 0.12); border-color: rgba(16, 185, 129, 0.25); }
    }
    @keyframes pulse-amber {
        0% { box-shadow: 0 0 12px rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.2); }
        50% { box-shadow: 0 0 25px rgba(245, 158, 11, 0.28); border-color: rgba(245, 158, 11, 0.4); }
        100% { box-shadow: 0 0 12px rgba(245, 158, 11, 0.12); border-color: rgba(245, 158, 11, 0.2); }
    }
    @keyframes pulse-red {
        0% { box-shadow: 0 0 12px rgba(244, 63, 94, 0.12); border-color: rgba(244, 63, 94, 0.25); }
        50% { box-shadow: 0 0 25px rgba(244, 63, 94, 0.28); border-color: rgba(244, 63, 94, 0.45); }
        100% { box-shadow: 0 0 12px rgba(244, 63, 94, 0.12); border-color: rgba(244, 63, 94, 0.25); }
    }
    
    .command-panel-trade {
        background: linear-gradient(135deg, rgba(6, 78, 59, 0.2) 0%, rgba(15, 23, 42, 0.95) 100%) !important;
        border: 1px solid rgba(16, 185, 129, 0.25) !important;
        border-radius: 16px !important;
        padding: 1.6rem !important;
        text-align: center !important;
        margin-bottom: 1.5rem !important;
        animation: pulse-green 3s infinite ease-in-out !important;
    }
    
    .command-panel-wait {
        background: linear-gradient(135deg, rgba(120, 53, 4, 0.15) 0%, rgba(15, 23, 42, 0.95) 100%) !important;
        border: 1px solid rgba(245, 158, 11, 0.2) !important;
        border-radius: 16px !important;
        padding: 1.6rem !important;
        text-align: center !important;
        margin-bottom: 1.5rem !important;
        animation: pulse-amber 3s infinite ease-in-out !important;
    }
    
    .command-panel-avoid {
        background: linear-gradient(135deg, rgba(127, 29, 29, 0.2) 0%, rgba(15, 23, 42, 0.95) 100%) !important;
        border: 1px solid rgba(244, 63, 94, 0.25) !important;
        border-radius: 16px !important;
        padding: 1.6rem !important;
        text-align: center !important;
        margin-bottom: 1.5rem !important;
        animation: pulse-red 3s infinite ease-in-out !important;
    }
    
    /* Title Stylings */
    .main-title {
        font-size: 2.4rem;
        font-weight: 800;
        background: linear-gradient(135deg, #ffffff 0%, #94a3b8 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.3rem;
        letter-spacing: -0.02em;
    }
    
    .section-subtitle {
        font-size: 0.95rem;
        color: #64748b;
        margin-bottom: 1.5rem;
        font-weight: 500;
    }
    
    /* 5. Custom Form Controls, Buttons, Selectors */
    div[data-testid="stForm"] {
        background: rgba(15, 23, 42, 0.45) !important;
        border: 1px solid rgba(255, 255, 255, 0.04) !important;
        border-radius: 12px !important;
        padding: 1.5rem !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.15) !important;
    }
    
    /* Button Custom styling */
    div.stButton > button, stSubmitButton > button {
        background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.05) !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.2rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 12px rgba(5, 150, 105, 0.15) !important;
    }
    
    div.stButton > button:hover, stSubmitButton > button:hover {
        transform: translateY(-1px) !important;
        box-shadow: 0 6px 18px rgba(5, 150, 105, 0.25) !important;
        background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    }
    
    /* Form input box overrides */
    div.stTextInput input, div.stNumberInput input, select, .stSelectbox div[role="combobox"] {
        background-color: #090e17 !important;
        color: #f1f5f9 !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 8px !important;
        transition: all 0.2s ease !important;
    }
    
    div.stTextInput input:focus, div.stNumberInput input:focus, .stSelectbox div[role="combobox"]:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.12) !important;
    }
    
    /* 6. Market School Learning Cards */
    .school-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.18) 0%, rgba(15, 23, 42, 0.6) 100%) !important;
        border-left: 4px solid #10b981 !important;
        border-top: 1px solid rgba(255,255,255,0.03) !important;
        border-right: 1px solid rgba(255,255,255,0.03) !important;
        border-bottom: 1px solid rgba(255,255,255,0.03) !important;
        border-radius: 8px !important;
        padding: 1.2rem !important;
        margin-bottom: 1.25rem !important;
        transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1) !important;
    }
    
    .school-card:hover {
        transform: translateX(4px) !important;
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.28) 0%, rgba(15, 23, 42, 0.75) 100%) !important;
        box-shadow: 0 6px 20px rgba(0,0,0,0.15) !important;
    }
    
    .school-term {
        font-size: 1.15rem !important;
        font-weight: 700 !important;
        color: #F8FAFC !important;
        margin-bottom: 0.35rem !important;
        letter-spacing: -0.01em;
    }
    
    .school-definition {
        font-size: 0.95rem !important;
        color: #cbd5e1 !important;
        margin-bottom: 0.5rem !important;
        line-height: 1.5 !important;
    }
    
    .school-example {
        font-size: 0.9rem !important;
        color: #38bdf8 !important;
        font-style: italic !important;
        border-top: 1px dashed rgba(255,255,255,0.08) !important;
        padding-top: 8px !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sidebar Navigation
st.sidebar.markdown("<h2 style='text-align: center; color: #FF4B4B;'>BULL RESEARCH</h2>", unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; color: #8892B0; font-size: 0.8rem;'>Private Local Stock Dashboard</p>", unsafe_allow_html=True)
st.sidebar.write("---")

page = st.sidebar.radio(
    "Navigation Menu",
    [
        "🎓 Daily Stock Mentor (Top Picks)",
        "📊 Pre-Market Research Desk",
        "🎫 Futures & Options (F&O) Desk",
        "🏆 Strategy Ranking Report",
        "📖 Paper Journal",
        "🎓 Market School",
        "⚙️ Capital Settings",
        "🧪 Backtest Lab",
        "🔍 Data Health"
    ]
)

# HELPER FUNCTIONS
def normalize_ticker(raw_ticker: str) -> str:
    ticker = raw_ticker.strip().upper()
    if ticker and "." not in ticker and not ticker.startswith("^"):
        ticker = f"{ticker}.NS"
    return ticker

def clean_ticker(ticker: str) -> str:
    """Friendly ticker representation for retail investors (stripping yfinance suffixes like .NS)."""
    if ticker.startswith("^"):
        return ticker
    return ticker.split('.')[0]

def get_data_freshness(tickers) -> str:
    dates = []
    for t in tickers:
        _, latest_date = get_latest_price(t)
        if latest_date:
            dates.append(str(latest_date))
    return max(dates) if dates else "No cached prices"


# ----------------------------------------
# PAGE 1: PRE-MARKET RESEARCH DESK
# ----------------------------------------
# ----------------------------------------
# PAGE 0: DAILY STOCK MENTOR (TOP PICKS)
# ----------------------------------------
if page == "🎓 Daily Stock Mentor (Top Picks)":
    st.markdown("<h1 class='main-title'>Daily Stock Mentor</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Your trading teacher. Every morning, I scan India's top 20 sector leaders and suggest 2 or 3 high-probability swings.</p>", unsafe_allow_html=True)
    
    settings = get_capital_settings()
    max_risk = float(settings.get('max_risk_per_trade', 100.0))
    total_capital = float(settings.get('total_capital', 5000.0))
    
    # Simple risk management lesson
    st.markdown(f"""
        <div class="card" style="background: linear-gradient(135deg, rgba(56, 189, 248, 0.08) 0%, rgba(15, 23, 42, 0.85) 100%); border-color: rgba(56, 189, 248, 0.2); padding: 1.3rem;">
            <h4 style="margin:0; color:#38bdf8; font-weight:700; font-size:1.15rem;">📚 Today's Teacher Lesson: The Risk Rule</h4>
            <p style="margin:8px 0 0 0; color:#cbd5e1; font-size:0.92rem; line-height:1.5;">
                With your current capital of <strong>{format_inr(total_capital)}</strong> and risk budget of <strong>{format_inr(max_risk)} per trade</strong>, 
                we strictly buy <em>Equity shares</em> (normal stocks). We do not touch high-leverage F&O because it is too risky for a learning account. 
                If a suggested trade hits the safety stop-loss, you will lose a maximum of <strong>{format_inr(max_risk)}</strong>. This is how we play safe!
            </p>
        </div>
    """, unsafe_allow_html=True)
    
    st.write("")
    
    with st.spinner("Teacher is analyzing Nifty market leaders and reading news..."):
        mentor_picks = get_mentor_suggestions()
        
    if not mentor_picks:
        st.info("The broader market is currently rangebound or bearish. For safety, I suggest waiting today. Patience is a trader's best friend!")
    else:
        st.subheader("🎯 Teacher's Picks of the Day")
        
        # Display 2-3 picks in columns
        cols = st.columns(len(mentor_picks))
        for idx, idea in enumerate(mentor_picks):
            with cols[idx]:
                import html as html_mod
                ticker = idea['ticker']
                dec_val = idea['decision']
                conf_val = idea['confidence_score']
                win_rate = idea.get('backtest_win_rate', 0.0)
                clean_sym = clean_ticker(ticker)
                
                dec_color = "#10b981" if dec_val == "TRADE" else "#f59e0b"
                dec_bg = "rgba(16,185,129,0.15)" if dec_val == "TRADE" else "rgba(245,158,11,0.15)"
                status_text = "Ready to Buy (Trigger Zone)" if dec_val == "TRADE" else "Watch Triggers"
                status_dot = "🟢" if dec_val == "TRADE" else "🟡"
                
                risk_per_share = idea['risk_per_share']
                qty = idea['suggested_quantity']
                
                # Safely escape reason text
                reason_text = idea['reasons'][-1] if idea['reasons'] else "Setup is technically solid with positive backing."
                reason_text = html_mod.escape(str(reason_text))
                
                entry_str = format_inr(idea['entry_trigger'])
                stop_str = format_inr(idea['stop_loss'])
                target_str = format_inr(idea['target_1'])
                wr_str = f"{win_rate*100:.1f}%"
                sent_label = idea.get('sentiment_label', 'NEUTRAL')
                sent_color = "#10b981" if sent_label == "BULLISH" else "#f43f5e" if sent_label == "BEARISH" else "#94a3b8"
                
                card_html = f"""
                <div style="
                    background: linear-gradient(135deg, rgba(17,24,39,0.75) 0%, rgba(15,23,42,0.9) 100%);
                    border: 1px solid rgba(255,255,255,0.05);
                    border-radius: 14px;
                    padding: 1.4rem 1.3rem;
                    margin-bottom: 1rem;
                    min-height: 460px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.35);
                    font-family: 'Inter', sans-serif;
                ">
                    <!-- Header: Ticker + Badge -->
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
                        <span style="color:#F8FAFC; font-size:1.5rem; font-weight:800; letter-spacing:-0.01em;">{html_mod.escape(clean_sym)}</span>
                        <span style="
                            background: {dec_bg};
                            color: {dec_color};
                            font-weight: 800;
                            padding: 4px 14px;
                            border-radius: 6px;
                            font-size: 0.75rem;
                            letter-spacing: 0.06em;
                            border: 1px solid {dec_color}33;
                            text-transform: uppercase;
                        ">{html_mod.escape(dec_val)}</span>
                    </div>
                    
                    <!-- Status -->
                    <div style="color:{dec_color}; font-size:0.92rem; font-weight:600; margin-bottom:16px;">
                        {status_dot} {html_mod.escape(status_text)}
                    </div>
                    
                    <!-- Justification Box -->
                    <div style="
                        background: rgba(15,23,42,0.5);
                        border-radius: 10px;
                        padding: 12px 14px;
                        margin-bottom: 18px;
                        border: 1px solid rgba(255,255,255,0.03);
                    ">
                        <div style="color:#64748b; font-size:0.7rem; text-transform:uppercase; font-weight:700; letter-spacing:0.05em; margin-bottom:4px;">Mentor's Justification</div>
                        <div style="color:#cbd5e1; font-size:0.85rem; line-height:1.5;">{reason_text}</div>
                    </div>
                    
                    <!-- Data Table -->
                    <table style="width:100%; border-collapse:collapse; font-size:0.88rem; margin-bottom:14px;">
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:9px 0; color:#94a3b8;">Buy Trigger</td>
                            <td style="text-align:right; padding:9px 0; color:#F8FAFC; font-weight:700;">{html_mod.escape(entry_str)}</td>
                        </tr>
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:9px 0; color:#94a3b8;">Safety Exit</td>
                            <td style="text-align:right; padding:9px 0; color:#f43f5e; font-weight:700;">{html_mod.escape(stop_str)}</td>
                        </tr>
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:9px 0; color:#94a3b8;">Profit Goal</td>
                            <td style="text-align:right; padding:9px 0; color:#10b981; font-weight:700;">{html_mod.escape(target_str)}</td>
                        </tr>
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:9px 0; color:#94a3b8;">Shares to Buy</td>
                            <td style="text-align:right; padding:9px 0; color:#F8FAFC; font-weight:700;">{qty}</td>
                        </tr>
                        <tr style="border-bottom:1px solid rgba(255,255,255,0.04);">
                            <td style="padding:9px 0; color:#94a3b8;">Win Rate</td>
                            <td style="text-align:right; padding:9px 0; color:#38bdf8; font-weight:700;">{html_mod.escape(wr_str)}</td>
                        </tr>
                        <tr>
                            <td style="padding:9px 0; color:#94a3b8;">AI Sentiment</td>
                            <td style="text-align:right; padding:9px 0; color:{sent_color}; font-weight:700;">{html_mod.escape(sent_label)}</td>
                        </tr>
                    </table>
                    
                    <!-- Confidence bar -->
                    <div style="margin-top:6px;">
                        <div style="color:#64748b; font-size:0.7rem; text-transform:uppercase; font-weight:700; letter-spacing:0.05em; margin-bottom:6px;">Confidence {conf_val}/100</div>
                        <div style="width:100%; background:rgba(255,255,255,0.05); border-radius:6px; height:8px; overflow:hidden;">
                            <div style="width:{conf_val}%; height:100%; background:linear-gradient(90deg, {dec_color} 0%, #38bdf8 100%); border-radius:6px;"></div>
                        </div>
                    </div>
                </div>
                """
                st.html(card_html)
                
                # Clean streamlit button to log paper trade
                if st.button(f"📥 Log Practice Trade: {clean_sym}", key=f"log_mentor_{ticker}", use_container_width=True):
                    if qty <= 0:
                        st.error("Cannot log trade. Position size is 0 shares. Check capital settings.")
                    else:
                        add_paper_trade(
                            ticker=ticker,
                            trade_date=date.today().strftime('%Y-%m-%d'),
                            action="BUY",
                            quantity=qty,
                            price=idea['entry_trigger'],
                            notes=f"Logged automatically from Daily Mentor Pick. Target Goal: {format_inr(idea['target_1'])}, Safety Stop: {format_inr(idea['stop_loss'])}."
                        )
                        st.toast(f"✓ Added {qty} shares of {clean_sym} to your practice journal!")
                        st.success(f"Log Successful: Check the '📖 Paper Journal' tab to view this position.")

elif page == "📊 Pre-Market Research Desk":
    st.markdown("<h1 class='main-title'>Pre-Market Research Desk</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Evaluate watchlist stocks, generate technical buy triggers, and inspect charts offline.</p>", unsafe_allow_html=True)
    
    tickers = get_watchlist_tickers()
    settings = get_capital_settings()
    
    # Load all trade ideas (excluding index symbols)
    ideas = get_all_trade_ideas()
    
    # Load and cache strategy verdicts
    tickers_tuple = tuple(sorted(tickers))
    verdicts = get_cached_stock_verdicts(tickers_tuple)
    verdicts_dict = {v['ticker']: v for v in verdicts}
    
    # Load Gemini API key from settings
    gemini_key = settings.get('gemini_api_key', '')
    
    # Load pre-market news and sentiment ratings for watchlist using ThreadPoolExecutor for parallel performance
    import concurrent.futures
    
    sentiment_dict = {}
    news_dict = {}
    stocks_to_fetch = [t for t in tickers if t not in INDEX_SYMBOLS]
    
    def fetch_single_ticker_sentiment(t):
        try:
            ticker_news = get_cached_stock_news(t, gemini_api_key=gemini_key)
            avg_score, avg_label = get_aggregated_sentiment(ticker_news)
            return t, ticker_news, {
                'score': avg_score,
                'label': avg_label,
                'news_count': len(ticker_news)
            }
        except Exception:
            return t, [], {
                'score': 0.0,
                'label': 'NEUTRAL',
                'news_count': 0
            }
            
    with st.spinner("Scanning pre-market news and AI sentiment in parallel..."):
        if stocks_to_fetch:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(stocks_to_fetch), 8)) as executor:
                results = list(executor.map(fetch_single_ticker_sentiment, stocks_to_fetch))
            for t, ticker_news, sent_info in results:
                news_dict[t] = ticker_news
                sentiment_dict[t] = sent_info
        else:
            sentiment_dict = {}
            news_dict = {}
                
    # Apply Command overrides to technical ideas
    valid_trade_setups_count = 0
    for idea in ideas:
        t = idea['ticker']
        v_info = verdicts_dict.get(t, {
            'verdict': 'WEAK',
            'reason': 'Not enough historical sample.',
            'win_rate': 0.0,
            'total_trades': 0,
            'net_profit': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'expectancy': 0.0
        })
        
        # Attach sentiment stats to idea
        sent_info = sentiment_dict.get(t, {'score': 0.0, 'label': 'NEUTRAL', 'news_count': 0})
        idea['sentiment_score'] = sent_info['score']
        idea['sentiment_label'] = sent_info['label']
        idea['news_count'] = sent_info['news_count']
        
        if idea['decision'] == 'TRADE':
            # Check historical backtest verdict
            if v_info['verdict'] in ['WEAK', 'BAD']:
                idea['decision'] = 'WAIT'
                idea['overridden'] = True
                idea['override_reason'] = f"historical backtest verdict is {v_info['verdict']}"
                idea['reasons'].append(f"⚠️ Command Center Override: Downgraded from TRADE to WAIT because historical backtest verdict is {v_info['verdict']}. Reason: {v_info['reason']}")
            # Check AI pre-market news sentiment override
            elif sent_info['label'] == 'BEARISH':
                idea['decision'] = 'WAIT'
                idea['overridden'] = True
                idea['override_reason'] = f"AI news sentiment is BEARISH ({sent_info['score']})"
                idea['reasons'].append(f"⚠️ AI Sentiment Filter: Downgraded from TRADE to WAIT because overall pre-market news sentiment is BEARISH (Score: {sent_info['score']}).")
            else:
                idea['overridden'] = False
                valid_trade_setups_count += 1
        else:
            idea['overridden'] = False
                
    # Get Market Index Regime
    regime = get_market_regime()
    bias_color = "#22c55e" if regime['market_bias'] == "BULLISH" else ("#ef4444" if regime['market_bias'] == "BEARISH" else "#94a3b8")
    
    # Calculate Today's Command (Central Decision Override logic)
    if regime['market_bias'] == "BEARISH":
        todays_command = "NO TRADE"
        command_reason = "Broader market bias is BEARISH. Cash stock buy triggers are locked for safety."
        command_color = "#ef4444"
        command_border = "#ef4444"
    elif regime['market_bias'] == "NEUTRAL":
        todays_command = "WAIT"
        command_reason = "Broader market bias is NEUTRAL. Index is rangebound. Wait for consolidation breakout."
        command_color = "#f59e0b"
        command_border = "#26345f"
    else:  # BULLISH
        # Rule: Today's Command should only become TRADE if index is BULLISH and we have at least one stock setup in TRADE with a GOOD historical verdict
        if valid_trade_setups_count > 0:
            todays_command = "TRADE"
            command_reason = "Broader market bias is BULLISH and high-confidence breakouts with proven historical edge are active."
            command_color = "#22c55e"
            command_border = "#22c55e"
        else:
            todays_command = "WAIT"
            command_reason = "Broader market bias is BULLISH, but no stocks trigger a TRADE setup with a verified historical edge."
            command_color = "#f59e0b"
            command_border = "#26345f"
            
    # Command Center Block Panel
    panel_class = "command-panel-trade" if todays_command == "TRADE" else ("command-panel-wait" if todays_command == "WAIT" else "command-panel-avoid")
    
    st.markdown(f"""
        <div class="{panel_class}">
            <h3 style="margin:0; color:#64748b; text-transform:uppercase; font-size:0.85rem; letter-spacing:0.08em; font-weight:700;">Today's Command</h3>
            <h1 style="margin:10px 0; color:{command_color}; font-size:3.8rem; font-weight:800; letter-spacing:0.04em;">{todays_command}</h1>
            <p style="margin:0; color:#e2e8f0; font-size:1.1rem; font-weight:500; line-height:1.4;">{command_reason}</p>
        </div>
    """, unsafe_allow_html=True)
    
    # 4 metrics cards below command
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Market Bias</div>
                <div class='metric-value' style='color:{bias_color};'>{regime['market_bias']}</div>
                <div class='metric-note'>Trend: {regime['trend_score']}/100 | Vol: {regime['volatility_score']}/100</div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Total Capital</div>
                <div class='metric-value'>{format_inr(settings['total_capital'])}</div>
                <div class='metric-note'>Max risk: {format_inr(settings['max_risk_per_trade'])}</div>
            </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Data Freshness</div>
                <div class='metric-value'>{get_data_freshness(tickers)}</div>
                <div class='metric-note'>Cached EOD daily prices</div>
            </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-label'>Active Trade Setups</div>
                <div class='metric-value'>{valid_trade_setups_count}</div>
                <div class='metric-note'>TRADE setups with GOOD history</div>
            </div>
        """, unsafe_allow_html=True)
        
    # Expander for market regime reasons
    with st.expander("🔍 Show Market Regime Analysis Details", expanded=False):
        for reason in regime['reasons']:
            st.markdown(f"- {reason}")
            
    st.write("")
    
    # --- Best Opportunity & Ranked Opportunities Layout ---
    col_left_main, col_right_main = st.columns([1.6, 1])
    
    with col_left_main:
        st.subheader("⭐ Best Opportunity")
        if not ideas:
            st.info("Watchlist has no stock symbols. Add symbols below.")
        else:
            best_idea = ideas[0]
            best_ticker = best_idea['ticker']
            
            # Fetch Cached Verdict
            best_verdict = verdicts_dict.get(best_ticker, {
                'verdict': 'WEAK',
                'total_trades': 0,
                'win_rate': 0.0,
                'net_profit': 0.0,
                'avg_win': 0.0,
                'avg_loss': 0.0,
                'expectancy': 0.0,
                'reason': 'Not enough historical sample.'
            })
            
            # Apply Override Decision Logic
            is_overridden = best_idea.get('overridden', False)
            final_decision = best_idea['decision']
            
            # If overridden, print warning box
            if is_overridden:
                override_text = best_idea.get('override_reason', f"historically this engine is {best_verdict['verdict']} on {best_ticker}")
                st.warning(f"⚠️ **Command Center Override**: **{best_ticker}** has the highest technical score today, but is downgraded to **WAIT** because {override_text}.")
                
            best_dec_color = "#22c55e" if final_decision == "TRADE" else ("#f59e0b" if final_decision == "WAIT" else "#ef4444")
            
            # Simple Status Label
            if final_decision == "TRADE":
                simple_status = "🟢 Ready to Buy! (Technical triggers active)"
            elif final_decision == "WAIT":
                if best_idea.get('overridden', False):
                    simple_status = "🟡 Wait! (Downgraded due to historical risk or bad news)"
                else:
                    simple_status = "🟡 Wait! (Not in a buy zone yet)"
            else:
                simple_status = "🔴 Avoid! (High risk or stale data)"
                
            # History explanation
            if best_verdict['verdict'] == "GOOD":
                history_text = "🟢 Safe: This setup historically makes money on this stock."
            elif best_verdict['verdict'] == "BAD":
                history_text = "🔴 Danger: This setup historically loses money on this stock."
            else:
                history_text = "🟡 Caution: Low sample size or average historical performance."
                
            # News explanation
            sent_label = best_idea.get('sentiment_label', 'NEUTRAL')
            sent_score = best_idea.get('sentiment_score', 0.0)
            if sent_label == "BULLISH":
                news_text = "🟢 Bullish: AI scan shows positive pre-market news sentiment."
            elif sent_label == "BEARISH":
                news_text = "🔴 Bearish: AI scan shows negative pre-market news sentiment."
            else:
                news_text = "⚪ Neutral: AI scan shows quiet/neutral pre-market news."
            
            # Render left-aligned HTML to prevent markdown parser from treating leading spaces as code blocks
            st.markdown(f"""<div class="card" style="margin-bottom:1rem;">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
<h2 style="margin:0; color:#F8FAFC; font-size:1.6rem; font-weight:700;">{clean_ticker(best_ticker)}</h2>
<span style="background:linear-gradient(135deg, {best_dec_color} 0%, rgba(15,23,42,0.8) 100%); color:#ffffff; font-weight:800; padding:0.3rem 0.8rem; border-radius:6px; font-size:0.85rem; border: 1px solid {best_dec_color}44;">{final_decision}</span>
</div>
<p style="margin:0 0 15px 0; font-size:1.1rem; color:#E2E8F0; font-weight:600; display:flex; align-items:center;">
<span style="margin-right:8px;">{simple_status}</span>
</p>
<div style="background-color:rgba(15, 23, 42, 0.4); border-radius:8px; padding:0.9rem 1.1rem; margin-bottom:1.5rem; border: 1px solid rgba(255,255,255,0.03);">
<div style="margin-bottom:10px;">
<span style="color:#64748b; font-size:0.75rem; text-transform:uppercase; font-weight:700; display:block; margin-bottom:3px; letter-spacing:0.04em;">Historical Performance</span>
<span style="color:#F1F5F9; font-size:0.92rem; font-weight:500;">{history_text}</span>
</div>
<div>
<span style="color:#64748b; font-size:0.75rem; text-transform:uppercase; font-weight:700; display:block; margin-bottom:3px; letter-spacing:0.04em;">AI News Scan</span>
<span style="color:#F1F5F9; font-size:0.92rem; font-weight:500;">{news_text}</span>
</div>
</div>
<table style="width:100%; font-size:0.98rem; border-collapse:collapse; color:#E2E8F0;">
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:10px 0; color:#94a3b8;">Buy only if price rises to:</td><td style="text-align:right; font-weight:700; padding:10px 0; color:#F8FAFC;">{format_inr(best_idea['entry_trigger'])}</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:10px 0; color:#94a3b8;">Safety Exit (Stop-Loss):</td><td style="text-align:right; font-weight:700; color:#f43f5e; padding:10px 0;">{format_inr(best_idea['stop_loss'])}</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:10px 0; color:#94a3b8;">Goal (Target Profit):</td><td style="text-align:right; font-weight:700; color:#10b981; padding:10px 0;">{format_inr(best_idea['target_1'])}</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:10px 0; color:#94a3b8;">How many shares to buy:</td><td style="text-align:right; font-weight:700; padding:10px 0; color:#F8FAFC;">{best_idea['suggested_quantity']} shares</td></tr>
<tr><td style="padding:10px 0; color:#94a3b8;">Maximum possible loss:</td><td style="text-align:right; font-weight:700; color:#f43f5e; padding:10px 0;">{format_inr(best_idea['max_loss'])}</td></tr>
</table>
</div>""", unsafe_allow_html=True)
            
            with st.expander("⚙️ Advanced Setup Details (For Experts)", expanded=False):
                st.write(f"**Direction**: {best_idea['direction']}")
                st.write(f"**Technical Confidence Score**: {best_idea['confidence_score']}%")
                st.write(f"**Target 2**: {format_inr(best_idea['target_2'])}")
                st.write(f"**Backtest Win Rate**: {best_verdict['win_rate']*100:.1f}%")
                st.write(f"**Backtest Profit/Loss**: {format_inr(best_verdict['net_profit'])}")
                st.write(f"**Trade Expectancy**: {format_inr(best_verdict['expectancy'])} per trade")
                st.write(f"**News Sentiment Score**: {sent_score:+.2f}")
                st.write("**Technical Setup Reasons**:")
                for reason in best_idea['reasons']:
                    st.markdown(f"- {reason}")
                    
            with st.expander("📰 Live Pre-Market News & AI Sentiment Feed", expanded=False):
                best_news = news_dict.get(best_ticker, [])
                if not best_news:
                    st.info(f"No recent news articles found for {best_ticker} in the last 48 hours.")
                else:
                    for item in best_news:
                        item_label = item['sentiment_label']
                        item_score = item['sentiment_score']
                        badge_color = "🟢" if item_label == "BULLISH" else ("🔴" if item_label == "BEARISH" else "⚪")
                        
                        # Left-aligned HTML snippet to prevent code block parsing inside loop
                        st.markdown(f"""<div style="background-color:#0F172A; border-radius:6px; padding:0.6rem; margin-bottom:0.5rem; border:1px solid #1E293B;">
<div style="display:flex; justify-content:space-between; font-size:0.75rem; color:#8892B0; margin-bottom:4px;">
<span>{item.get('publisher', 'Yahoo Finance')}</span>
<span>{badge_color} {item_label} ({item_score})</span>
</div>
<a href="{item.get('link', '#')}" target="_blank" style="text-decoration:none; color:#F8FAFC; font-weight:600; font-size:0.88rem;">{item['title']}</a>
</div>""", unsafe_allow_html=True)
                    
    with col_right_main:
        st.subheader("Watchlist Opportunities List")
        if not ideas:
            st.info("Watchlist is empty.")
        else:
            for idea in ideas:
                ticker_val = idea['ticker']
                dec_val = idea['decision']
                conf_val = idea['confidence_score']
                
                # Get status emoji (Ready = Green, Wait = Yellow, Avoid = Red)
                status_emoji = "🟢" if dec_val == "TRADE" else ("🟡" if dec_val == "WAIT" else "🔴")
                
                dec_color = "#22c55e" if dec_val == "TRADE" else ("#f59e0b" if dec_val == "WAIT" else "#ef4444")
                
                st.markdown(f"""
                    <div class="card" style="padding: 0.8rem 1.1rem; margin-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center; background: linear-gradient(135deg, rgba(17, 24, 39, 0.4) 0%, rgba(15, 23, 42, 0.6) 100%);">
                        <div>
                            <strong style="font-size: 1.05rem; color: #F8FAFC; font-weight: 700;">{status_emoji} {clean_ticker(ticker_val)}</strong><br/>
                            <span style="font-size: 0.8rem; color: #94a3b8; margin-top: 4px; display: inline-block;">Buy Price: {format_inr(idea['entry_trigger'])} | Score: {conf_val}/100</span>
                        </div>
                        <span style="background: linear-gradient(135deg, {dec_color} 0%, rgba(15,23,42,0.8) 100%); color: #ffffff; font-weight: 800; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.7rem; border: 1px solid {dec_color}44;">{dec_val}</span>
                    </div>
                """, unsafe_allow_html=True)

    st.write("---")
    
    # Watchlist and chart layout
    left, right = st.columns([1, 2.2])
    
    with left:
        st.subheader("Watchlist Management")
        with st.form("add_ticker_form_p1", clear_on_submit=True):
            new_ticker = st.text_input("Stock Ticker Symbol", placeholder="TCS or TCS.NS")
            submitted = st.form_submit_button("Add and Sync")
            
        if submitted and new_ticker:
            ticker_normalized = normalize_ticker(new_ticker)
            with st.spinner(f"Syncing {ticker_normalized} metadata..."):
                res = sync_ticker(ticker_normalized)
                if res['success']:
                    st.cache_data.clear()  # Clear cache on changes
                    st.success(f"Added and synced {res['name']} ({ticker_normalized}) successfully!")
                    st.rerun()
                else:
                    st.error(f"Could not load data for {ticker_normalized}. Ensure it is listed correctly on NSE.")
                    
        if tickers:
            stocks_only = [t for t in tickers if t not in INDEX_SYMBOLS]
            remove_ticker = st.selectbox("Select symbol to remove", stocks_only)
            if st.button("Delete Selected Symbol", use_container_width=True):
                remove_from_watchlist(remove_ticker)
                st.cache_data.clear()  # Clear cache on changes
                st.warning(f"Deleted {remove_ticker} price records.")
                st.rerun()
                
            wl_df = get_watchlist()
            wl_df_stocks = wl_df[~wl_df['ticker'].isin(INDEX_SYMBOLS)]
            st.dataframe(wl_df_stocks[['ticker', 'name', 'industry']], hide_index=True, use_container_width=True)
        else:
            st.info("Watchlist is currently empty. Add a symbol above to start researching.")
            
        st.caption("Safety guideline: Do not place entry orders in the first 5 minutes of trade. Treat entries as triggers to watch after 9:20 AM, not automatic executions.")
        
    with right:
        st.subheader("Interactive Stock Chart")
        stocks_only_tickers = [t for t in tickers if t not in INDEX_SYMBOLS]
        if stocks_only_tickers:
            selected_ticker = st.selectbox("Select stock to chart", stocks_only_tickers)
            prices_df = get_prices(selected_ticker)
            
            if prices_df.empty:
                st.warning(f"No price history cached for {selected_ticker}.")
                st.info("Sync stock data in the Data Health tab.")
            else:
                plot_df = prices_df.iloc[-126:].copy()  # Last 6 months
                plot_df['sma_20'] = plot_df['close'].rolling(20).mean()
                plot_df['sma_50'] = plot_df['close'].rolling(50).mean()
                
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=plot_df['date'],
                    open=plot_df['open'],
                    high=plot_df['high'],
                    low=plot_df['low'],
                    close=plot_df['close'],
                    name="Candlestick",
                    increasing_line_color="#10b981",
                    decreasing_line_color="#f43f5e",
                ))
                fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['sma_20'], name="SMA 20", line=dict(color="#f59e0b", width=1.5)))
                fig.add_trace(go.Scatter(x=plot_df['date'], y=plot_df['sma_50'], name="SMA 50", line=dict(color="#3b82f6", width=1.5)))
                
                fig.update_xaxes(
                    gridcolor='rgba(255, 255, 255, 0.03)',
                    zerolinecolor='rgba(255, 255, 255, 0.05)',
                    linecolor='rgba(255, 255, 255, 0.05)'
                )
                fig.update_yaxes(
                    gridcolor='rgba(255, 255, 255, 0.03)',
                    zerolinecolor='rgba(255, 255, 255, 0.05)',
                    linecolor='rgba(255, 255, 255, 0.05)'
                )
                fig.update_layout(
                    template="plotly_dark",
                    height=450,
                    margin=dict(l=30, r=30, t=10, b=10),
                    xaxis_rangeslider_visible=False,
                    plot_bgcolor="rgba(15, 23, 42, 0.3)",
                    paper_bgcolor="rgba(0, 0, 0, 0)",
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Add stocks to watchlist to render historical pricing charts.")


# ----------------------------------------
# PAGE 1B: FUTURES & OPTIONS (F&O) DESK
# ----------------------------------------
elif page == "🎫 Futures & Options (F&O) Desk":
    st.markdown("<h1 class='main-title'>Futures & Options (F&O) Desk</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Learn and mock-trade derivative contracts. This desk is in Developer Mock Mode for your safety.</p>", unsafe_allow_html=True)
    
    st.warning("⚠️ **Safety Shield Active**: F&O contracts involve high leverage and time decay. Real-money options recommendation signals are currently offline to protect your capital. Practice with Equity shares first!")
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.markdown("""<div class="card" style="margin-bottom:1rem;">
<h3 style="margin:0; color:#F8FAFC; font-weight:700;">NIFTY 24000 CALL OPTION</h3>
<p style="margin:4px 0 12px 0; color:#38BDF8; font-size:0.88rem; font-weight:600;">Category: Index Call Option (Weekly)</p>
<table style="width:100%; font-size:0.95rem; border-collapse:collapse; color:#E2E8F0;">
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Contract Expiry:</td><td style="text-align:right; font-weight:700; color:#F8FAFC; padding:8px 0;">Next Thursday</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Buy Trigger Premium:</td><td style="text-align:right; font-weight:700; color:#10b981; padding:8px 0;">₹150.00</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Target Goal Premium:</td><td style="text-align:right; font-weight:700; color:#38bdf8; padding:8px 0;">₹210.00</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Safety Exit Premium:</td><td style="text-align:right; font-weight:700; color:#f43f5e; padding:8px 0;">₹120.00</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Lot Size (Minimum Block):</td><td style="text-align:right; font-weight:700; color:#F8FAFC; padding:8px 0;">25 shares</td></tr>
<tr><td style="padding:8px 0; color:#94a3b8;">Approx. Cost (Margin):</td><td style="text-align:right; font-weight:700; color:#f59e0b; padding:8px 0;">₹3,750.00</td></tr>
</table>
</div>""", unsafe_allow_html=True)
        
    with c2:
        st.markdown("""<div class="card" style="margin-bottom:1rem;">
<h3 style="margin:0; color:#F8FAFC; font-weight:700;">TATAPOWER 450 CALL OPTION</h3>
<p style="margin:4px 0 12px 0; color:#38BDF8; font-size:0.88rem; font-weight:600;">Category: Stock Call Option (Monthly)</p>
<table style="width:100%; font-size:0.95rem; border-collapse:collapse; color:#E2E8F0;">
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Contract Expiry:</td><td style="text-align:right; font-weight:700; color:#F8FAFC; padding:8px 0;">Last Thursday of Month</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Buy Trigger Premium:</td><td style="text-align:right; font-weight:700; color:#10b981; padding:8px 0;">₹12.00</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Target Goal Premium:</td><td style="text-align:right; font-weight:700; color:#38bdf8; padding:8px 0;">₹18.00</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Safety Exit Premium:</td><td style="text-align:right; font-weight:700; color:#f43f5e; padding:8px 0;">₹8.00</td></tr>
<tr style="border-bottom:1px solid rgba(255,255,255,0.03);"><td style="padding:8px 0; color:#94a3b8;">Lot Size (Minimum Block):</td><td style="text-align:right; font-weight:700; color:#F8FAFC; padding:8px 0;">3,375 shares</td></tr>
<tr><td style="padding:8px 0; color:#94a3b8;">Approx. Cost (Margin):</td><td style="text-align:right; font-weight:700; color:#f59e0b; padding:8px 0;">₹40,500.00</td></tr>
</table>
</div>""", unsafe_allow_html=True)

    st.write("---")
    st.subheader("💡 Equity (Normal Stocks) vs F&O (Options) explained simply")
    
    col_eq, col_fo = st.columns(2)
    with col_eq:
        st.info("""
        **📦 Equity (Normal Shares)**:
        - **How it works**: You buy the actual share. If you buy 5 shares of Tata Power at ₹450, you own them.
        - **Risk**: Very low. Even if the price drops to ₹430, you only lose ₹20 per share. You can hold them for 10 years if you want.
        - **Cost**: You can buy as little as 1 share (₹450).
        """)
    with col_fo:
        st.warning("""
        **⚖️ F&O (Options Contracts)**:
        - **How it works**: You buy a time-limited contract representing a massive block of shares (e.g. 1 Lot = 3,375 shares).
        - **Risk**: Extremely high. If Tata Power stays below ₹450 by expiry, your contract value goes to **₹0 (Total Loss)**.
        - **Cost**: You cannot buy 1 share. You must buy at least 1 Lot (which costs ₹40,500+).
        """)


# ----------------------------------------
# PAGE 2: DATA HEALTH
# ----------------------------------------
elif page == "🔍 Data Health":
    st.markdown("<h1 class='main-title'>Data Health Diagnostic</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Inspect database storage capacity and refresh cached pricing data.</p>", unsafe_allow_html=True)
    
    health = get_db_health()
    tickers = get_watchlist_tickers()
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Watchlist Count", health['watchlist_count'])
    with c2:
        st.metric("Cached Price Rows", health['price_count'])
    with c3:
        st.metric("DB File Size", f"{health['file_size_mb']:.3f} MB")
        
    st.write(f"Database File Path: `{health['db_path']}`")
    st.write("---")
    
    col_l, col_r = st.columns([1, 1])
    
    with col_l:
        st.subheader("Bulk Data Sync Manager")
        if not tickers:
            st.warning("No tickers registered. Add tickers on the Pre-Market Research Desk.")
        else:
            st.write(f"Syncing daily prices (1 Year) for: {', '.join(clean_ticker(t) for t in tickers)}")
            if st.button("Sync All Watchlist Tickers", use_container_width=True):
                logs = []
                progress = st.progress(0)
                log_area = st.empty()
                for idx, t in enumerate(tickers):
                    res = sync_ticker(t)
                    if res['success']:
                        logs.append(f"✓ {t}: Successfully synced {res['rows_synced']} rows.")
                    else:
                        logs.append(f"✗ {t}: Sync failed.")
                    progress.progress((idx + 1) / len(tickers))
                    log_area.code("\n".join(logs))
                st.cache_data.clear()  # Clear cache on sync
                st.success("Synchronization process completed!")
                st.rerun()
                
    with col_r:
        st.subheader("Data Density Diagnostic")
        if tickers:
            rows = []
            for t in tickers:
                prices = get_prices(t)
                latest_p, latest_d = get_latest_price(t)
                rows.append({
                    "Ticker": clean_ticker(t),
                    "Total Days Cached": len(prices),
                    "Last Cache Date": latest_d or "N/A",
                    "Last Stored Close": format_inr(latest_p) if latest_p else "N/A",
                    "Density Status": "OK (>=60 rows)" if len(prices) >= 60 else "Insufficient (<60 rows)"
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("Watchlist is empty. No integrity check can be performed.")


# ----------------------------------------
# PAGE 3: PAPER JOURNAL
# ----------------------------------------
elif page == "📖 Paper Journal":
    st.markdown("<h1 class='main-title'>Simulated Trading Journal</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Test trade strategies without risking cash capital. Computations use latest stored price cache.</p>", unsafe_allow_html=True)
    
    tickers = get_watchlist_tickers()
    holdings, total_realized_pnl = get_portfolio_holdings()
    
    tab_new, tab_holdings, tab_history = st.tabs(["Log Paper Trade", "Open Paper Positions", "History"])
    
    # Exclude index symbols from paper trading dropdown
    valid_tickers = [t for t in tickers if t not in INDEX_SYMBOLS]
    
    with tab_new:
        if not valid_tickers:
            st.info("Watchlist is empty or only contains index symbols. Add stocks in the research desk to log mock trades.")
        else:
            selected_t = st.selectbox("Select Symbol", valid_tickers, format_func=clean_ticker, key="journal_symbol")
            latest_p, latest_d = get_latest_price(selected_t)
            st.caption(f"Latest stored close price in DB: {format_inr(latest_p)} (Cached: {latest_d})")
            
            col_a, col_b = st.columns(2)
            with col_a:
                action = st.radio("Action", ["BUY", "SELL"], horizontal=True)
                trade_date = st.date_input("Trade Execution Date", date.today())
            with col_b:
                quantity = st.number_input("Shares Quantity", min_value=1, value=10, step=1)
                execution_price = st.number_input("Paper execution price (₹)", min_value=0.0, value=float(latest_p or 0.0), format="%.2f")
                
            notes = st.text_area("Reason and post-trade notes")
            
            if st.button("Save simulated trade", use_container_width=True):
                # Verify selling shares
                shares_owned = 0
                for h in holdings:
                    if h['ticker'] == selected_t:
                        shares_owned = h['shares']
                        break
                
                if action == "SELL" and quantity > shares_owned:
                    st.error(f"Invalid transaction. You currently hold only {shares_owned} shares of {selected_t} in your journal.")
                elif execution_price <= 0:
                    st.error("Execution price must be greater than zero.")
                else:
                    add_paper_trade(
                        selected_t,
                        trade_date.strftime("%Y-%m-%d"),
                        action,
                        quantity,
                        execution_price,
                        notes
                    )
                    st.success("Simulated trade saved successfully!")
                    st.rerun()
                    
    with tab_holdings:
        if not holdings:
            st.info("No open mock positions. Log a BUY trade to get started.")
        else:
            rows = []
            for h in holdings:
                rows.append({
                    "Ticker": clean_ticker(h['ticker']),
                    "Shares": h['shares'],
                    "Avg Cost Basis": format_inr(h['avg_cost']),
                    "Latest Stored Price": format_inr(h['latest_price']),
                    "Total Cost": format_inr(h['total_cost']),
                    "Latest Stored Value": format_inr(h['current_value']),
                    "Unrealized PnL": format_inr(h['unrealized_pnl']),
                    "PnL %": format_percentage(h['unrealized_pnl_pct'])
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            st.metric("Total Closed Realized PnL", format_inr(total_realized_pnl))
            
    with tab_history:
        trades_df = get_paper_trades()
        if trades_df.empty:
            st.info("No trades saved in your local database ledger.")
        else:
            display_df = trades_df.copy()
            display_df['ticker'] = display_df['ticker'].apply(clean_ticker)
            display_df['price'] = display_df['price'].apply(format_inr)
            display_df['quantity'] = display_df['quantity'].apply(lambda x: f"{x:,}")
            display_df.columns = ['ID', 'Ticker', 'Trade Date', 'Action', 'Qty', 'Price', 'Notes', 'Logged At']
            
            st.dataframe(display_df[['Ticker', 'Trade Date', 'Action', 'Qty', 'Price', 'Notes']], hide_index=True, use_container_width=True)
            
            csv = trades_df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV Logs", csv, "bull_paper_trades.csv", "text/csv", use_container_width=True)


# ----------------------------------------
# PAGE 4: MARKET SCHOOL
# ----------------------------------------
elif page == "🎓 Market School":
    st.markdown("<h1 class='main-title'>Market School</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Learn core stock market and trading concepts using extremely simple language and real-world examples.</p>", unsafe_allow_html=True)
    
    tab_products, tab_execution, tab_options = st.tabs([
        "📦 Markets & Investment Products",
        "🎯 Technical Analysis & Execution",
        "⚖️ Options Trading Dictionary"
    ])
    
    with tab_products:
        st.subheader("Core Investment Vehicles")
        
        # Stock
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Stock</div>
                <div class='school-definition'>A tiny slice of ownership in a business. When you buy a stock, you become a shareholder.</div>
                <div class='school-example'><strong>Example:</strong> If you buy 1 share of Reliance Industries, you are a part-owner of the company. If Reliance grows and profits, your share value increases.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Nifty / Index
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Nifty / Index</div>
                <div class='school-definition'>A basket of top stocks grouped together to show the direction of the overall market.</div>
                <div class='school-example'><strong>Example:</strong> The Nifty 50 acts like a thermometer for the Indian stock market by tracking the 50 largest companies. If Nifty rises, the general economy is doing well.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # IPO
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>IPO (Initial Public Offering)</div>
                <div class='school-definition'>The first time a private company sells its shares on the exchange to raise money from public investors.</div>
                <div class='school-example'><strong>Example:</strong> A growing startup wants ₹100 crores to expand nationwide. They list their shares on the exchange through an IPO, letting you buy in early.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Mutual Fund
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Mutual Fund</div>
                <div class='school-definition'>A pooled fund collected from thousands of investors, managed by a professional who buys a diversified mix of stocks.</div>
                <div class='school-example'><strong>Example:</strong> If you only have ₹500 to invest, you cannot buy shares of 30 large companies. But by pooling your ₹500 in a Mutual Fund, you get fractional exposure to all of them.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # ETF
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>ETF (Exchange Traded Fund)</div>
                <div class='school-definition'>Like a mutual fund that tracks a specific basket of stocks, but you can buy and sell it instantly on the exchange just like a single share.</div>
                <div class='school-example'><strong>Example:</strong> Instead of buying 50 separate companies, you buy 1 share of "Nifty BeES" (an ETF tracking the Nifty 50 index) on your broker app.</div>
            </div>
        """, unsafe_allow_html=True)
        
    with tab_execution:
        st.subheader("Trade Setup Vocabulary")
        
        # Bullish / Bearish
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.markdown("""
                <div class='school-card'>
                    <div class='school-term'>Bullish</div>
                    <div class='school-definition'>Expecting prices to go up. Bulls strike upward with their horns.</div>
                    <div class='school-example'><strong>Example:</strong> Expecting auto sales to increase makes you bullish on Tata Motors.</div>
                </div>
            """, unsafe_allow_html=True)
        with col_b2:
            st.markdown("""
                <div class='school-card'>
                    <div class='school-term'>Bearish</div>
                    <div class='school-definition'>Expecting prices to fall. Bears swipe downward with their paws.</div>
                    <div class='school-example'><strong>Example:</strong> If a company faces a major lawsuit, you might be bearish on its stock.</div>
                </div>
            """, unsafe_allow_html=True)
            
        # Entry / Stop-loss / Target
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Entry (Trigger)</div>
                <div class='school-definition'>The specific price trigger level at which you decide to start a trade.</div>
                <div class='school-example'><strong>Example:</strong> "I will buy TCS if it breaks above ₹3,500." The entry trigger is ₹3,500.</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Stop-loss</div>
                <div class='school-definition'>Your safety net. A pre-set exit price to automatically sell and limit your loss if the trade goes wrong.</div>
                <div class='school-example'><strong>Example:</strong> You buy a stock at ₹100. You set a stop-loss at ₹90. If the stock falls to ₹90, you exit instantly, keeping your loss capped at ₹10.</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Target</div>
                <div class='school-definition'>Your profit goal price. The level where you sell your shares to lock in your gains.</div>
                <div class='school-example'><strong>Example:</strong> You buy at ₹100 and set target at ₹120. When the price hits ₹120, you sell and realize your ₹20 profit.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Risk / Capital
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Risk</div>
                <div class='school-definition'>The maximum money you could lose on a trade if your stop-loss gets hit.</div>
                <div class='school-example'><strong>Example:</strong> If you buy 10 shares of a stock at ₹100 with a stop-loss at ₹90, your risk is ₹10 per share, meaning a total of ₹100 risk.</div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Capital</div>
                <div class='school-definition'>Your trading bankroll. The total cash reserve you have allocated to trade.</div>
                <div class='school-example'><strong>Example:</strong> If you transfer ₹5,000 to your brokerage account to start trading, your capital is ₹5,000.</div>
            </div>
        """, unsafe_allow_html=True)
        
    with tab_options:
        st.subheader("Derivative Basics")
        st.info("ℹ️ Options trading is highly complex. Read these terms to understand the theory, though options recommendations are disabled in Phase 2.")
        
        # Call Option
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Call Option</div>
                <div class='school-definition'>A contract giving you the right (but not obligation) to BUY a stock at a fixed price before a specific date.</div>
                <div class='school-example'><strong>Example:</strong> Paying a non-refundable ₹5,000 token advance to lock in the purchase price of a ₹50 lakh flat for 3 months. If flat prices rise, you buy at the locked ₹50 lakh. If flat prices collapse, you walk away and lose only the ₹5,000 advance.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Put Option
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Put Option</div>
                <div class='school-definition'>A contract giving you the right (but not obligation) to SELL a stock at a fixed price before a specific date.</div>
                <div class='school-example'><strong>Example:</strong> Buying car insurance. If your ₹5 lakh car crashes, the insurer must pay you ₹5 lakh. If it doesn't crash, you only lose the insurance policy cost.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Underlying
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Underlying</div>
                <div class='school-definition'>The real asset (like physical shares) that the option contract represents.</div>
                <div class='school-example'><strong>Example:</strong> For a Nifty index call option, the underlying asset is the actual Nifty 50 index.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Premium
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Premium</div>
                <div class='school-definition'>The cost you pay to buy an option contract. This price fluctuates constantly.</div>
                <div class='school-example'><strong>Example:</strong> The ₹5,000 non-refundable advance or your yearly car insurance price. It is the cost of the contract.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Lot Size
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Lot Size</div>
                <div class='school-definition'>The fixed minimum block of shares you must purchase or trade in a single option contract.</div>
                <div class='school-example'><strong>Example:</strong> Reliance options have a lot size of 250. You cannot buy an option for 1 share; you must buy at least 1 lot of 250 shares.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # Expiry
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Expiry</div>
                <div class='school-definition'>The calendar date when an option contract becomes invalid and expires. In India, option contracts expire weekly or monthly.</div>
                <div class='school-example'><strong>Example:</strong> Like a milk carton expiry date. After this date, options contracts melt away and cease to exist.</div>
            </div>
        """, unsafe_allow_html=True)
        
        # ITM / ATM / OTM
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>ITM / ATM / OTM (Moneyness)</div>
                <div class='school-definition'>A categorization showing where the stock price is relative to the option's strike price:</div>
                <div style='color:#E2E8F0; font-size:0.9rem; padding:5px 0 10px 0;'>
                    • <strong>ITM (In the Money):</strong> Has real value. (E.g. Right to buy gold at ₹50,000 when market price is ₹60,000).<br>
                    • <strong>ATM (At the Money):</strong> Equal value. (E.g. Right to buy a share at ₹100 when it trades at exactly ₹100).<br>
                    • <strong>OTM (Out of the Money):</strong> No real value yet. (E.g. Right to buy gold at ₹70,000 when market price is only ₹60,000).
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # Time Decay
        st.markdown("""
            <div class='school-card'>
                <div class='school-term'>Time Decay (Theta)</div>
                <div class='school-definition'>The daily loss of an option contract's value as it gets closer to its expiry date.</div>
                <div class='school-example'><strong>Example:</strong> An option contract is like an ice cube left in the sun. Every day it sits without the stock price moving, a little bit of its value melts away until it reaches expiry.</div>
            </div>
        """, unsafe_allow_html=True)


# ----------------------------------------
# PAGE 5: CAPITAL SETTINGS
# ----------------------------------------
elif page == "⚙️ Capital Settings":
    st.markdown("<h1 class='main-title'>Capital & Risk Settings</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Set your local trading boundaries. These figures dictate trade recommendations and calculate suggested share sizes.</p>", unsafe_allow_html=True)
    
    settings = get_capital_settings()
    
    with st.form("settings_form"):
        total_capital = st.number_input(
            "Total Trading Capital (₹)", 
            min_value=100.0, 
            max_value=10000000.0, 
            value=float(settings['total_capital']),
            step=500.0,
            help="Total fund allocated for trading cash stocks."
        )
        
        max_risk_per_trade = st.number_input(
            "Maximum Risk Per Trade (₹)", 
            min_value=10.0, 
            max_value=total_capital, 
            value=float(settings['max_risk_per_trade']),
            step=10.0,
            help="Maximum amount you are prepared to lose if a trade hits your stop-loss. Recommended is 1-2% of capital."
        )
        
        max_trades_per_day = st.slider(
            "Maximum Trades Per Day", 
            min_value=1, 
            max_value=10, 
            value=int(settings['max_trades_per_day']),
            help="Maximum setups to participate in concurrently in a single trading session."
        )
        
        allow_options = st.checkbox(
            "Allow Option Suggestions (F&O)",
            value=bool(settings['allow_options']),
            disabled=True,
            help="Disabled in Phase 2. F&O/Options recommendation models are currently offline."
        )
        
        experience_level = st.selectbox(
            "Experience Level",
            ["BEGINNER", "INTERMEDIATE", "ADVANCED"],
            index=["BEGINNER", "INTERMEDIATE", "ADVANCED"].index(settings['experience_level'])
        )
        
        st.markdown("<br/>", unsafe_allow_html=True)
        st.subheader("🤖 AI Core Configurations")
        gemini_api_key = st.text_input(
            "Gemini API Key (Google AI Studio)",
            value=settings.get('gemini_api_key', ''),
            type="password",
            help="Provide a free API key from Google AI Studio to upgrade pre-market scans to advanced semantic analysis."
        )
        
        st.markdown("<br/>", unsafe_allow_html=True)
        st.subheader("🔌 Broker Integration (Zerodha Kite Connect)")
        kite_api_key = st.text_input(
            "Kite Connect API Key",
            value=settings.get('kite_api_key', ''),
            help="Your Zerodha Kite Connect application API Key."
        )
        
        kite_api_secret = st.text_input(
            "Kite Connect API Secret",
            value=settings.get('kite_api_secret', ''),
            type="password",
            help="Your Zerodha Kite Connect application API Secret."
        )
        
        kite_request_token = st.text_input(
            "Kite Connect Request Token (Daily)",
            value=settings.get('kite_request_token', ''),
            help="Active daily session token. Enter the request token returned after authorization."
        )
        
        # Display Kite status badge
        if kite_api_key and kite_api_secret:
            st.markdown("""
                <div style='display:inline-block; background-color:#1e3a8a; color:#93c5fd; padding:0.25rem 0.5rem; border-radius:4px; font-size:0.75rem; font-weight:700; border: 1px solid #3b82f6;'>
                    🔌 Kite Configured (Mock Mode Active)
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div style='display:inline-block; background-color:#374151; color:#d1d5db; padding:0.25rem 0.5rem; border-radius:4px; font-size:0.75rem; font-weight:700; border: 1px solid #4b5563;'>
                    🔌 Kite Credentials Pending
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown("<br/>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Save Configuration Settings", use_container_width=True)
        
    if submitted:
        if max_risk_per_trade > total_capital:
            st.error("Max risk per trade cannot exceed total trading capital.")
        else:
            update_capital_settings(
                total_capital=total_capital,
                max_risk_per_trade=max_risk_per_trade,
                max_trades_per_day=max_trades_per_day,
                allow_options=1 if allow_options else 0,
                experience_level=experience_level,
                gemini_api_key=gemini_api_key,
                kite_api_key=kite_api_key,
                kite_api_secret=kite_api_secret,
                kite_request_token=kite_request_token
            )
            st.cache_data.clear()  # Clear cache on settings changes
            st.success("Configuration updated successfully!")
            st.rerun()
            
    # Risk advisory warnings based on settings (for beginner learning style)
    st.write("---")
    st.subheader("💡 Risk Management Advisory")
    
    risk_ratio = (max_risk_per_trade / total_capital) * 100
    
    if risk_ratio > 5.0:
        st.warning(f"⚠️ **High Risk Exposure ({risk_ratio:.1f}%)**: You are risking more than 5% of your total capital on a single trade. For a '{experience_level}' profile, we strongly recommend keeping risk under 2% (₹{total_capital * 0.02:.2f}) to avoid blowing up your account.")
    else:
        st.success(f"✓ **Safe Risk Profile ({risk_ratio:.1f}%)**: Your risk per trade is within the standard conservative boundary (<5% of capital). Excellent capital preservation structure!")
        
    st.info("ℹ️ Risk settings directly affect the Suggested Quantity in the Trade Idea Engine. Suggested Quantity = Max Risk Per Trade / Risk Per Share.")


# ----------------------------------------
# PAGE 6: BACKTEST LAB
# ----------------------------------------
elif page == "🧪 Backtest Lab":
    st.markdown("<h1 class='main-title'>Backtest Lab</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Evaluate the historical performance of the Trade Idea Engine v2 on your watchlist stocks using daily price cache.</p>", unsafe_allow_html=True)
    
    tickers = get_watchlist_tickers()
    if not tickers:
        st.info("Watchlist is empty. Add stocks on the Pre-Market Research Desk before running backtests.")
    else:
        # Filter index symbols from backtest selector
        valid_backtest_tickers = [t for t in tickers if t not in INDEX_SYMBOLS]
        if not valid_backtest_tickers:
            st.info("Please add at least one normal stock symbol to your watchlist (e.g. RELIANCE.NS) to backtest.")
        else:
            selected_t = st.selectbox("Select Stock to Backtest", valid_backtest_tickers, format_func=clean_ticker, key="backtest_ticker")
            
            col_btn = st.columns([1, 2])
            with col_btn[0]:
                run_btn = st.button("Run Backtest Simulation", use_container_width=True)
                
            if run_btn:
                with st.spinner(f"Running historical daily simulation on {selected_t}..."):
                    res = run_backtest(selected_t)
                    
                if res['total_trades'] == 0:
                    st.warning(f"No trades generated for {selected_t} during the historical period. Ensure this ticker has at least 60 daily candles synced in the database.")
                else:
                    # 4 KPI cards
                    k1, k2, k3, k4 = st.columns(4)
                    
                    net_p = res['net_profit']
                    net_color = "#22c55e" if net_p >= 0 else "#ef4444"
                    net_arrow = "▲" if net_p >= 0 else "▼"
                    
                    with k1:
                        st.markdown(f"""
                            <div class='metric-card'>
                                <div class='metric-label'>Net Profit / Loss</div>
                                <div class='metric-value' style='color:{net_color};'>{format_inr(net_p)}</div>
                                <div class='metric-note'>{net_arrow} Total PnL across all trades</div>
                            </div>
                        """, unsafe_allow_html=True)
                    with k2:
                        st.markdown(f"""
                            <div class='metric-card'>
                                <div class='metric-label'>Win Rate</div>
                                <div class='metric-value'>{res['win_rate'] * 100:.2f}%</div>
                                <div class='metric-note'>{res['wins']} Wins vs {res['losses']} Losses</div>
                            </div>
                        """, unsafe_allow_html=True)
                    with k3:
                        st.markdown(f"""
                            <div class='metric-card'>
                                <div class='metric-label'>Total Trades</div>
                                <div class='metric-value'>{res['total_trades']}</div>
                                <div class='metric-note'>Simulated execution count</div>
                            </div>
                        """, unsafe_allow_html=True)
                    with k4:
                        st.markdown(f"""
                            <div class='metric-card'>
                                <div class='metric-label'>Avg Win / Avg Loss</div>
                                <div class='metric-value' style='font-size:1.15rem; padding-top:4px;'>
                                    Win: <span style='color:#22c55e;'>{format_inr(res['avg_win'])}</span><br/>
                                    Loss: <span style='color:#ef4444;'>{format_inr(res['avg_loss'])}</span>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)
                        
                    st.write("")
                    
                    # Plot Cumulative PnL Curve
                    trades_list = res['trades_log']
                    df_trades = pd.DataFrame(trades_list)
                    df_trades['exit_date'] = pd.to_datetime(df_trades['exit_date'])
                    df_trades = df_trades.sort_values('exit_date').reset_index(drop=True)
                    df_trades['Cumulative Profit (₹)'] = df_trades['pnl'].cumsum()
                    
                    # Make a Plotly line chart
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=df_trades['exit_date'],
                        y=df_trades['Cumulative Profit (₹)'],
                        mode='lines+markers',
                        name='Cumulative PnL',
                        line=dict(color='#38BDF8', width=2),
                        marker=dict(size=6)
                    ))
                    fig.update_xaxes(
                        gridcolor='rgba(255, 255, 255, 0.03)',
                        zerolinecolor='rgba(255, 255, 255, 0.05)',
                        linecolor='rgba(255, 255, 255, 0.05)'
                    )
                    fig.update_yaxes(
                        gridcolor='rgba(255, 255, 255, 0.03)',
                        zerolinecolor='rgba(255, 255, 255, 0.05)',
                        linecolor='rgba(255, 255, 255, 0.05)'
                    )
                    fig.update_layout(
                        template="plotly_dark",
                        title="Cumulative Profit/Loss Curve (INR)",
                        xaxis_title="Exit Date",
                        yaxis_title="Profit/Loss in ₹",
                        height=350,
                        margin=dict(l=30, r=30, t=40, b=30),
                        plot_bgcolor="rgba(15, 23, 42, 0.3)",
                        paper_bgcolor="rgba(0, 0, 0, 0)",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Display Trade Log Table
                    st.subheader("Detailed Trade Logs")
                    display_trades = df_trades.copy()
                    display_trades['exit_date'] = display_trades['exit_date'].dt.strftime('%Y-%m-%d')
                    display_trades['pnl'] = display_trades['pnl'].apply(format_inr)
                    display_trades['entry_price'] = display_trades['entry_price'].apply(format_inr)
                    display_trades['exit_price'] = display_trades['exit_price'].apply(format_inr)
                    
                    # Rename columns
                    display_trades.columns = ['Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Exit Reason', 'Quantity', 'Trade PnL', 'Cumulative Profit']
                    st.dataframe(display_trades[['Entry Date', 'Exit Date', 'Entry Price', 'Exit Price', 'Exit Reason', 'Quantity', 'Trade PnL']], hide_index=True, use_container_width=True)
                    
                    # Download CSV
                    csv_data = df_trades.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Download Backtest Trade Logs (CSV)",
                        data=csv_data,
                        file_name=f"backtest_{selected_t.lower()}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )


# ----------------------------------------
# PAGE 7: STRATEGY RANKING REPORT
# ----------------------------------------
elif page == "🏆 Strategy Ranking Report":
    st.markdown("<h1 class='main-title'>Strategy Ranking Report</h1>", unsafe_allow_html=True)
    st.markdown("<p class='section-subtitle'>Examine historical backtests across all watchlist stocks to isolate symbols with a statistical edge.</p>", unsafe_allow_html=True)
    
    tickers = get_watchlist_tickers()
    if not tickers:
        st.info("Watchlist is empty. Add symbols to generate strategy ranks.")
    else:
        # Load and cache strategy verdicts
        tickers_tuple = tuple(sorted(tickers))
        
        # Provide a refresh button to manually clear Streamlit's data cache
        if st.sidebar.button("♻️ Refresh Strategy Ranks"):
            st.cache_data.clear()
            st.toast("Backtest statistics cache cleared!")
            st.rerun()
            
        with st.spinner("Backtesting all watchlist stocks..."):
            verdicts_list = get_cached_stock_verdicts(tickers_tuple)
            
        # Classify groups
        trusted_symbols = [v for v in verdicts_list if v['verdict'] == "GOOD"]
        dnt_symbols = [v for v in verdicts_list if v['verdict'] == "BAD"]
        
        # Display Trusted vs Avoid Panels
        col_t, col_d = st.columns(2)
        
        with col_t:
            st.markdown("""
                <div class="card" style="background: linear-gradient(135deg, rgba(6, 78, 59, 0.2) 0%, rgba(15, 23, 42, 0.8) 100%); border-color: rgba(16, 185, 129, 0.3); padding: 1.2rem; margin-bottom: 1rem;">
                    <h4 style="margin:0; color:#34d399; font-weight:700;">🟢 Trusted Symbols List</h4>
                    <p style="margin:6px 0 0 0; color:#94a3b8; font-size:0.88rem; line-height:1.4;">Stocks with a strong, proven historical backtest edge (GOOD). Setups are active on these symbols.</p>
                </div>
            """, unsafe_allow_html=True)
            
            if not trusted_symbols:
                st.info("No stocks currently meet the strict criteria for a GOOD verdict (Requires: >= 5 trades, >= 45% win rate, net positive profit).")
            else:
                for s in trusted_symbols:
                    st.markdown(f"**{clean_ticker(s['ticker'])}** | Win Rate: {s['win_rate']*100:.1f}% | Net Profit: {format_inr(s['net_profit'])}")
                    
        with col_d:
            st.markdown("""
                <div class="card" style="background: linear-gradient(135deg, rgba(127, 29, 29, 0.25) 0%, rgba(15, 23, 42, 0.8) 100%); border-color: rgba(239, 68, 68, 0.3); padding: 1.2rem; margin-bottom: 1rem;">
                    <h4 style="margin:0; color:#f87171; font-weight:700;">🔴 Do Not Trade List</h4>
                    <p style="margin:6px 0 0 0; color:#94a3b8; font-size:0.88rem; line-height:1.4;">Stocks with a negative edge in backtests (BAD). Technical trade signals are locked for safety.</p>
                </div>
            """, unsafe_allow_html=True)
            
            if not dnt_symbols:
                st.info("No stocks currently classified under the BAD verdict (Net loss, win rate < 35%, and >= 5 trades).")
            else:
                for s in dnt_symbols:
                    st.markdown(f"**{clean_ticker(s['ticker'])}** | Win Rate: {s['win_rate']*100:.1f}% | Net Loss: {format_inr(s['net_profit'])}")
                    
        st.write("")
        st.subheader("Watchlist Ranks & Historical Statistics")
        st.markdown("<p style='color:#8892B0; font-size:0.85rem; margin-top:-0.5rem;'>Ranked by Verdict (GOOD first, WEAK second, BAD last), Net Profit descending, Win Rate, and Trade counts.</p>", unsafe_allow_html=True)
        
        # Prepare table data
        table_rows = []
        for v in verdicts_list:
            table_rows.append({
                "Ticker": clean_ticker(v['ticker']),
                "Verdict": v['verdict'],
                "Net PnL": format_inr(v['net_profit']),
                "Win Rate": f"{v['win_rate']*100:.1f}%",
                "Total Trades": v['total_trades'],
                "Expectancy": format_inr(v['expectancy']),
                "Avg Win": format_inr(v['avg_win']),
                "Avg Loss": format_inr(v['avg_loss']),
                "Backtest Verdict Detail": v['reason']
            })
            
        st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)
