import streamlit as st
import streamlit.components.v1 as st_components
import yfinance as yf
import feedparser
from groq import Groq
import pandas as pd
from datetime import datetime, date, timedelta
import random
import requests
import json
import time
import os
import re
import hashlib
from collections import defaultdict
from streamlit_autorefresh import st_autorefresh

# ─── CONFIG FILE ──────────────────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "quant_config.json")

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "qwen/qwen3-32b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
    "groq/compound",
    "groq/compound-mini",
    "allam-2-7b",
]

FJ_DEFAULT_TOKEN = "%22EAAAAOz2wRurEvNgh5zYAhZQ9oLlm4S%2F6c7OBYGy3rW6RoYe%2FW55Koc8xFLoASWom6Tyr%2FrY%2BNNM%2BLwHz0rXTdlQVv7Po1wouMl7Gt0DfQ12yIS5JKj%2FB3zitZRdoHr5uEUWMcaCcFJJxQptMf6aWwnYWvhO%2FtrMIZbHpvLN%2Bw5nceHpLgVOMUxRLzSRQHJI7ito%2BMoik0CVQBAuburnNF5wmdNGr1ib%2BzyY30WQ9cd08%2F1cKCj2kZxhXqIg8Xw4dNW6%2FXQFWZ5scTnsp7dFp3VfsJR2YZ2lPA06EpRbC5Smo%2BPJlMftvKwmGQZR5Gw3QuQjJQ%3D%3D%22"

PRIORITY_COUNTRIES = {
    "US": "🇺🇸 EUA", "EU": "🇪🇺 ZONA EURO", "DE": "🇩🇪 ALEMANHA",
    "GB": "🇬🇧 REINO UNIDO", "UK": "🇬🇧 REINO UNIDO", "JP": "🇯🇵 JAPÃO",
    "CN": "🇨🇳 CHINA", "FR": "🇫🇷 FRANÇA", "CA": "🇨🇦 CANADÁ",
    "IT": "🇮🇹 ITÁLIA", "BR": "🇧🇷 BRASIL", "AU": "🇦🇺 AUSTRÁLIA",
    "CH": "🇨🇭 SUÍÇA", "NZ": "🇳🇿 NOVA ZELÂNDIA", "GLOBAL": "🌐 GLOBAL",
}

def _cfg_defaults():
    return {
        "groq_keys": ["", "", "", "", ""],
        "rss_urls": (
            "https://www.financialjuice.com/feed.ashx?xy=rss\n"
            "https://feeds.a.dj.com/rss/RSSMarketsMain.xml\n"
            "https://feeds.bloomberg.com/markets/news.rss"
        ),
        "ticker_bar_symbols": "^GSPC, ^IXIC, ^DJI, ^VIX, CL=F, BZ=F, DX-Y.NYB, GC=F",
        "gamma_instruments": [],
        "main_t_val": "",
        "sofr_val": 4.305,
        "effr_val": 4.330,
        "rrp_val": 485.2,
        "ai_model": "llama-3.3-70b-versatile",
        "fj_token": FJ_DEFAULT_TOKEN,
    }

def load_config():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults = _cfg_defaults()
            defaults.update(saved)
            return defaults
    except Exception:
        pass
    defaults = _cfg_defaults()
    try:
        keys_from_secrets = [st.secrets.get(f"groq_key_{i+1}", "") for i in range(5)]
        if any(k.strip() for k in keys_from_secrets):
            defaults["groq_keys"] = keys_from_secrets
        if st.secrets.get("fj_token", "").strip():
            defaults["fj_token"] = st.secrets["fj_token"]
    except Exception:
        pass
    return defaults

def save_config():
    keys_to_save = ["groq_keys","rss_urls","ticker_bar_symbols","gamma_instruments",
                    "main_t_val","sofr_val","effr_val","rrp_val","ai_model","fj_token"]
    data = {k: st.session_state.get(k, _cfg_defaults().get(k)) for k in keys_to_save}
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

# ─── PAGE CONFIG ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="QUANT TERMINAL v10",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── AUTENTICAÇÃO ─────────────────────────────────────────────────────────────
def _check_password():
    try:
        senha_correta = st.secrets.get("app_password", "")
    except Exception:
        senha_correta = ""
    if not senha_correta:
        return True  # sem senha configurada, libera acesso
    if st.session_state.get("_autenticado"):
        return True
    st.markdown("""
    <style>
    .auth-wrap{display:flex;align-items:center;justify-content:center;min-height:80vh;}
    .auth-box{background:#161B22;border:1px solid #30363D;border-top:3px solid #EFA500;padding:40px 48px;border-radius:8px;width:100%;max-width:380px;text-align:center;}
    .auth-title{font-family:'Barlow Condensed',sans-serif;font-size:28px;font-weight:800;color:#EFA500;letter-spacing:2px;margin-bottom:4px;}
    .auth-sub{font-family:'JetBrains Mono',monospace;font-size:11px;color:#A8B3BD;margin-bottom:28px;}
    </style>
    <div class="auth-wrap"><div class="auth-box">
    <div class="auth-title">⚡ QUANT TERMINAL</div>
    <div class="auth-sub">v10.0 · Acesso restrito</div>
    </div></div>
    """, unsafe_allow_html=True)
    pwd = st.text_input("Senha de acesso", type="password", label_visibility="collapsed",
                        placeholder="🔒 Digite a senha...")
    if st.button("ENTRAR", use_container_width=True):
        if pwd == senha_correta:
            st.session_state._autenticado = True
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()

_check_password()

AI_REFRESH_INTERVAL     = 3600
NEWS_REFRESH_INTERVAL   = 60
TICKER_REFRESH_INTERVAL = 60
AUTOREFRESH_INTERVAL    = 60
FJ_REFRESH_INTERVAL     = 60

_ss_defaults = {
    "news_history": [],
    "macro_ai_cache": "",
    "last_ai_run": 0,
    "last_ai_auto": 0,
    "gamma_ai_cache": {},
    "last_autorefresh": time.time(),
    "last_news_fetch": 0,
    "last_ticker_fetch": 0,
    "ticker_store": {},
    "ai_running": False,
    "factors_cache": "",
    "last_factors_run": 0,
    "hvl_alerts": [],
    "hvl_alert_history": [],
    "sentiment_cache": {},
    "last_sentiment_run": 0,
    "translation_cache": {},
    "last_translation_run": 0,
    "translate_news": True,
    "ai_model": "llama-3.3-70b-versatile",
    "agenda_cache_global": "",
    "last_agenda_run": 0,
    "summary_cache_global": "",
    "last_summary_run": 0,
    "blocked_keys": {},
    "blocked_models": {},
    "ai_call_log": [],
    "fj_data": {},
    "fj_last_fetch": 0,
    "fj_token": FJ_DEFAULT_TOKEN,
    "orderflow_ai_cache": "",
    "last_orderflow_ai": 0,
    "calendar_ai_cache": "",
    "last_calendar_ai": 0,
    # v10 additions
    "intermarket_ai_cache": "",
    "last_intermarket_ai": 0,
    "risk_scan_cache": "",
    "last_risk_scan": 0,
    "news_sentiment_cache": "",
    "last_news_sentiment": 0,
    "market_context_cache": {},
    "last_market_context": 0,
}
for k, v in _ss_defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if 'cfg_loaded' not in st.session_state:
    cfg = load_config()
    for k, v in cfg.items():
        st.session_state[k] = v
    st.session_state.cfg_loaded = True

def get_ai_model():
    return st.session_state.get('ai_model', 'llama-3.3-70b-versatile')

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Barlow+Condensed:wght@400;600;700;800&family=Barlow:wght@300;400;500;600&display=swap');
:root{--bg:#0D1117;--bg2:#161B22;--bg3:#1C2128;--amber:#EFA500;--text:#E6EDF3;--dim:#A8B3BD;--green:#3FB950;--red:#F85149;--yellow:#F0B429;--cyan:#58A6FF;--border:#30363D;--dim2:#C5CDD6;}
.stApp{background:var(--bg)!important;color:var(--text);font-family:'Barlow',sans-serif;}
.stApp>header{background:transparent!important;}
section[data-testid="stSidebar"]{background:var(--bg2)!important;border-right:1px solid var(--border);}
.block-container{padding:0.5rem 1rem 2rem 1rem!important;max-width:100%!important;}
#MainMenu{visibility:hidden;}footer{visibility:hidden;}
header[data-testid="stHeader"]{background:transparent!important;height:auto!important;visibility:visible!important;z-index:999998!important;}
div.stButton>button,section[data-testid="stSidebar"] .stButton button{background:#1C2128!important;border:1px solid #30363D!important;color:#E6EDF3!important;font-family:'Barlow Condensed',sans-serif!important;font-weight:700!important;font-size:13px!important;letter-spacing:0.5px!important;padding:8px 12px!important;border-radius:4px!important;transition:all 0.15s ease!important;}
div.stButton>button:hover,section[data-testid="stSidebar"] .stButton button:hover{background:#EFA500!important;color:#000!important;border-color:#EFA500!important;}
div.stButton>button:focus,div.stButton>button:active{background:#1C2128!important;color:#E6EDF3!important;border-color:#EFA500!important;box-shadow:0 0 0 2px rgba(239,165,0,0.3)!important;}
div[data-testid="stExpander"]{background:#1C2128!important;border:1px solid #30363D!important;border-radius:4px!important;}
div[data-testid="stExpander"] summary{background:#1C2128!important;color:#E6EDF3!important;}
div[data-testid="stExpander"]:hover summary{border-color:#EFA500!important;}
div.stNumberInput>div{background:#0D1117!important;border:1px solid #30363D!important;border-radius:4px!important;}
div.stNumberInput button{background:#1C2128!important;border:none!important;color:#E6EDF3!important;}
div.stNumberInput button:hover{background:#EFA500!important;color:#000!important;}
.ticker-bar{display:grid;grid-template-columns:repeat(8,1fr);background:var(--bg2);border-bottom:2px solid var(--amber);border-top:1px solid var(--border);margin-bottom:4px;}
.tc{padding:8px 10px;text-align:center;border-right:1px solid var(--border);}
.tc:last-child{border-right:none;}
.tl{font-size:10px;color:var(--dim2);font-family:'JetBrains Mono';margin-bottom:2px;font-weight:600;}
.tp{font-family:'Barlow Condensed';font-size:20px;font-weight:700;color:#fff;line-height:1;}
.tv{font-family:'JetBrains Mono';font-size:11px;font-weight:600;margin-top:2px;}
.news-ticker{background:var(--amber);color:var(--bg);font-family:'JetBrains Mono';font-size:10.5px;font-weight:700;padding:5px 12px;margin-bottom:12px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}
.sh{background:var(--bg2);border-bottom:2px solid var(--amber);border-left:4px solid var(--amber);padding:6px 10px;font-family:'Barlow Condensed';font-size:13px;font-weight:700;color:var(--amber);letter-spacing:.8px;text-transform:uppercase;margin-bottom:6px;margin-top:8px;}
.gamma-levels-wrap{overflow-x:auto;margin-bottom:8px;}
.gamma-levels{display:flex;gap:0;min-width:max-content;border:1px solid var(--border);}
.gl-item{flex:0 0 auto;min-width:140px;background:var(--bg3);border-right:1px solid var(--border);padding:10px 14px;text-align:center;}
.gl-item:last-child{border-right:none;}
.gl-item.hvl{background:#1A1208;border-top:3px solid var(--amber);}
.gl-item.cw{background:#0D1A14;border-top:3px solid var(--green);}
.gl-item.pw{background:#1A0D0D;border-top:3px solid var(--red);}
.gl-item.spot{background:#0D1520;border-top:3px solid var(--cyan);}
.gl-lbl{font-size:10px;color:var(--dim2);font-family:'JetBrains Mono';text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px;display:block;white-space:nowrap;font-weight:600;}
.gl-val{font-family:'Barlow Condensed';font-size:22px;font-weight:700;color:#fff;display:block;line-height:1;}
.gl-sub{font-size:10px;color:var(--dim2);font-family:'JetBrains Mono';margin-top:4px;display:block;white-space:nowrap;font-weight:500;}
.inst-table{width:100%;border-collapse:collapse;font-size:12px;}
.inst-table thead td{background:var(--bg3);color:var(--amber);font-family:'Barlow Condensed';font-size:11px;font-weight:700;padding:5px 8px;border-bottom:1px solid var(--amber);}
.inst-table tbody tr:nth-child(odd) td{background:var(--bg);}
.inst-table tbody tr:nth-child(even) td{background:var(--bg2);}
.inst-table tbody tr td{padding:6px 8px;border-bottom:1px solid var(--border);vertical-align:middle;font-family:'JetBrains Mono';font-size:11px;color:var(--text);}
.inst-table tbody tr:hover td{background:#1f2937;}
.badge{display:inline-block;padding:2px 8px;border-radius:2px;font-family:'Barlow Condensed';font-size:11px;font-weight:700;white-space:nowrap;}
.bp{background:#1a4a1a;color:#3FB950;border:1px solid #3FB950;}
.bn{background:#4a1a1a;color:#F85149;border:1px solid #F85149;}
.bnt{background:#2a2a2a;color:var(--dim2);border:1px solid #4a525c;}
.bft{background:#4a3200;color:#EFA500;border:1px solid #EFA500;}
.bbl{background:#0d2a4a;color:#58A6FF;border:1px solid #58A6FF;}
.ai-box{background:var(--bg2);border:1px solid var(--border);border-left:4px solid var(--amber);padding:14px 16px;font-size:13px;line-height:1.75;margin-bottom:10px;color:var(--text);}
.ai-box-blue{background:var(--bg2);border:1px solid var(--border);border-left:4px solid var(--cyan);padding:14px 16px;font-size:13px;line-height:1.75;margin-bottom:10px;color:var(--text);}
.ai-box-green{background:#071510;border:1px solid #1a4a1a;border-left:4px solid var(--green);padding:14px 16px;font-size:13px;line-height:1.75;margin-bottom:10px;color:var(--text);}
.ai-box-red{background:#150707;border:1px solid #4a1a1a;border-left:4px solid var(--red);padding:14px 16px;font-size:13px;line-height:1.75;margin-bottom:10px;color:var(--text);}
.fg{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0;}
.fpos{background:#071510;border:1px solid #1a4a1a;border-left:4px solid var(--green);padding:12px 14px;}
.fneg{background:#150707;border:1px solid #4a1a1a;border-left:4px solid var(--red);padding:12px 14px;}
.ftit{font-family:'Barlow Condensed';font-size:13px;font-weight:700;margin-bottom:8px;}
.fi{font-size:12px;line-height:1.6;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.08);color:var(--text);}
.fi:last-child{border-bottom:none;}
.fi::before{content:"▸ ";color:var(--amber);}
.news-item{padding:7px 8px;border-bottom:1px solid var(--border);line-height:1.4;}
.news-time{color:var(--dim2);font-size:10px;font-family:'JetBrains Mono';font-weight:600;}
.news-link{color:var(--cyan);text-decoration:none;font-size:12px;}
.news-link:hover{color:var(--amber);}
.rate-box{background:var(--bg2);padding:12px 14px;border:1px solid var(--border);margin-bottom:4px;border-top:2px solid var(--amber);}
.rate-lbl{font-size:11px;color:var(--dim2);font-family:'JetBrains Mono';font-weight:600;}
.rate-val{font-family:'Barlow Condensed';font-size:28px;font-weight:700;color:#fff;line-height:1;margin:4px 0 2px 0;}
.rate-sub{font-size:10px;color:var(--dim2);font-family:'JetBrains Mono';font-weight:500;}
.quant-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:3px;}
.quant-item{background:var(--bg3);padding:7px 9px;border:1px solid var(--border);text-align:center;}
.q-lbl{font-size:10px;color:var(--dim2);display:block;text-transform:uppercase;margin-bottom:3px;font-family:'JetBrains Mono';font-weight:600;}
.q-val{font-size:13px;font-weight:700;display:block;}
.q-chg{font-size:11px;font-weight:600;display:block;font-family:'JetBrains Mono';}
.stTabs [data-baseweb="tab-list"]{gap:6px;background:transparent;}
.stTabs [data-baseweb="tab"]{background:var(--bg2)!important;border:1px solid var(--border)!important;color:var(--dim2)!important;padding:8px 18px!important;border-radius:4px 4px 0 0!important;font-family:'Barlow Condensed'!important;font-weight:700!important;font-size:13px!important;}
.stTabs [aria-selected="true"]{color:var(--amber)!important;border-bottom:2px solid var(--amber)!important;background:var(--bg3)!important;}
.main-header{display:flex;justify-content:space-between;align-items:center;padding:10px 0 8px 0;border-bottom:2px solid var(--amber);margin-bottom:4px;}
.main-title{font-family:'Barlow Condensed';font-size:28px;font-weight:800;color:#fff;letter-spacing:1px;}
.main-date{font-size:11px;color:var(--dim2);margin-top:2px;font-family:'JetBrains Mono';font-weight:500;}
.regime-box{padding:12px 16px;border-radius:2px;margin-bottom:8px;}
.regime-pos{background:#071510;border:1px solid #3FB950;border-left:5px solid #3FB950;}
.regime-neg{background:#150707;border:1px solid #F85149;border-left:5px solid #F85149;}
.regime-title{font-family:'Barlow Condensed';font-size:16px;font-weight:700;margin-bottom:4px;}
.regime-desc{font-size:12.5px;color:var(--text);line-height:1.6;}
.scroll-box{max-height:68vh;overflow-y:auto;}
.empty-state{background:var(--bg2);border:1px dashed var(--border);padding:40px 20px;text-align:center;border-radius:4px;margin:10px 0;}
.empty-title{font-family:'Barlow Condensed';font-size:18px;font-weight:700;color:var(--dim2);margin-bottom:8px;}
.empty-sub{font-size:12.5px;color:var(--dim2);font-family:'JetBrains Mono';line-height:1.6;}
.live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--green);margin-right:5px;animation:pulse 1.5s infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.4;}}
.alert-hvl{animation:alertpulse 2s infinite;}
@keyframes alertpulse{0%,100%{opacity:1;}50%{opacity:.7;}}
.of-card{background:var(--bg2);border:1px solid var(--border);padding:12px;border-radius:4px;text-align:center;transition:all 0.2s;}
.of-card.pos{border-top:4px solid var(--green);}
.of-card.neg{border-top:4px solid var(--red);}
.of-card.alert{animation:alertpulse 1.5s infinite;border:2px solid var(--red);box-shadow:0 0 15px rgba(248,81,73,0.4);}
.of-card.bigwin{animation:alertpulse 1.5s infinite;border:2px solid var(--green);box-shadow:0 0 15px rgba(63,185,80,0.4);}
.of-name{font-family:'Barlow Condensed';font-size:16px;font-weight:800;color:var(--amber);text-transform:uppercase;margin-bottom:4px;}
.of-total{font-family:'Barlow Condensed';font-size:28px;font-weight:800;line-height:1;margin:6px 0;}
.of-bs{display:flex;justify-content:space-between;margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-family:'JetBrains Mono';font-size:11px;}
.of-buy{color:var(--green);font-weight:700;}
.of-sell{color:var(--red);font-weight:700;}
.of-ticker-row{display:grid;grid-template-columns:60px 1fr 90px;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border);font-family:'JetBrains Mono';font-size:11px;align-items:center;}
.of-ticker-row:nth-child(odd){background:var(--bg);}
.of-ticker-row:nth-child(even){background:var(--bg2);}
.of-ticker-sym{font-family:'Barlow Condensed';font-size:13px;font-weight:700;color:var(--amber);}
.of-ticker-bar{height:14px;background:var(--bg3);border-radius:2px;position:relative;overflow:hidden;}
.of-ticker-fill{height:100%;border-radius:2px;}
.of-ticker-fill.buy{background:linear-gradient(90deg,var(--green),#2ea043);}
.of-ticker-fill.sell{background:linear-gradient(90deg,var(--red),#da3633);}
.of-ticker-val{text-align:right;font-weight:600;}
.of-mag7{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin:8px 0;}
.of-mag-item{background:var(--bg2);border:1px solid var(--border);padding:8px;text-align:center;border-radius:4px;}
.of-mag-item.up{border-top:3px solid var(--green);}
.of-mag-item.down{border-top:3px solid var(--red);}
.of-mag-tk{font-family:'Barlow Condensed';font-size:13px;font-weight:700;color:var(--amber);}
.of-mag-val{font-family:'JetBrains Mono';font-size:12px;font-weight:700;margin-top:4px;}
.of-mag-arrow{font-size:14px;margin-top:2px;}
.cal-row{display:grid;grid-template-columns:60px 50px 1fr 60px 70px 70px 70px;gap:8px;padding:7px 10px;border-bottom:1px solid var(--border);align-items:center;font-family:'JetBrains Mono';font-size:11.5px;transition:background 0.15s;}
.cal-row:nth-child(odd){background:var(--bg);}
.cal-row:nth-child(even){background:var(--bg2);}
.cal-row:hover{background:#1f2937;}
.cal-row.high{border-left:3px solid var(--red);}
.cal-row.med{border-left:3px solid var(--yellow);}
.cal-row.low{border-left:3px solid var(--dim2);}
.cal-row.past{opacity:0.55;}
.cal-row.now{background:rgba(239,165,0,0.12);border-left:3px solid var(--amber);}
.cal-time{font-weight:700;color:var(--amber);font-size:12px;}
.cal-country{font-weight:700;color:#fff;text-align:center;}
.cal-event{color:var(--text);font-weight:500;}
.cal-imp{text-align:center;font-size:13px;}
.cal-num{text-align:right;color:var(--dim2);}
.cal-num.actual{color:#fff;font-weight:700;}
.cal-num.beat{color:var(--green);font-weight:700;}
.cal-num.miss{color:var(--red);font-weight:700;}
.cal-header{display:grid;grid-template-columns:60px 50px 1fr 60px 70px 70px 70px;gap:8px;padding:8px 10px;background:var(--bg3);border-bottom:2px solid var(--amber);font-family:'Barlow Condensed';font-size:11px;font-weight:700;color:var(--amber);text-transform:uppercase;letter-spacing:0.5px;}
.cal-day-header{background:linear-gradient(90deg,var(--bg3),transparent);padding:8px 12px;margin-top:12px;border-left:4px solid var(--amber);font-family:'Barlow Condensed';font-size:14px;font-weight:700;color:var(--amber);}
.ai-log-row{display:grid;grid-template-columns:60px 1fr 80px 80px 1fr;gap:6px;padding:5px 8px;border-bottom:1px solid var(--border);font-family:'JetBrains Mono';font-size:10px;align-items:center;}
.ai-log-row:nth-child(odd){background:var(--bg);}
.ai-log-row:nth-child(even){background:var(--bg2);}
.fv-wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px;margin:8px 0;}
.fv-sector{background:var(--bg2);border:1px solid var(--border);border-top:3px solid var(--amber);padding:8px;border-radius:2px;}
.fv-sector-header{display:flex;justify-content:space-between;align-items:center;padding:4px 6px 8px 6px;border-bottom:1px solid var(--border);margin-bottom:6px;}
.fv-sector-name{font-family:'Barlow Condensed';font-size:13px;font-weight:700;color:var(--amber);text-transform:uppercase;}
.fv-sector-perf{font-family:'JetBrains Mono';font-size:12px;font-weight:700;padding:2px 8px;border-radius:2px;}
.fv-stocks{display:grid;grid-template-columns:repeat(auto-fill,minmax(60px,1fr));gap:2px;}
.fv-stock{padding:4px 3px;border-radius:2px;text-align:center;cursor:pointer;transition:transform .1s;overflow:hidden;}
.fv-stock:hover{transform:scale(1.08);z-index:10;position:relative;box-shadow:0 2px 8px rgba(0,0,0,.5);}
.fv-tk{font-family:'Barlow Condensed';font-size:11px;font-weight:700;line-height:1;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.fv-pf{font-family:'JetBrains Mono';font-size:9px;font-weight:600;line-height:1;margin-top:2px;display:block;}
.fut-cat{background:var(--bg2);border:1px solid var(--border);border-top:3px solid var(--amber);padding:8px 10px;margin-bottom:8px;}
.fut-cat-name{font-family:'Barlow Condensed';font-size:13px;font-weight:700;color:var(--amber);text-transform:uppercase;margin-bottom:6px;padding-bottom:4px;border-bottom:1px solid var(--border);}
.fut-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(110px,1fr));gap:4px;}
.fut-item{background:var(--bg3);border:1px solid var(--border);padding:6px 8px;text-align:center;border-radius:2px;transition:transform .1s;}
.fut-item:hover{transform:scale(1.04);border-color:var(--amber);}
.fut-item.up{border-left:3px solid var(--green);}
.fut-item.down{border-left:3px solid var(--red);}
.fut-item.flat{border-left:3px solid var(--dim2);}
.fut-tk{font-family:'Barlow Condensed';font-size:11px;font-weight:700;color:var(--amber);display:block;line-height:1;}
.fut-nm{font-size:10px;color:var(--dim2);font-family:'JetBrains Mono';display:block;margin:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500;}
.fut-pr{font-family:'JetBrains Mono';font-size:12px;font-weight:700;color:#fff;display:block;line-height:1.2;}
.fut-pc{font-family:'JetBrains Mono';font-size:11px;font-weight:600;display:block;line-height:1;}
small{color:var(--dim2)!important;}p{color:var(--text);}
.stTextInput label,.stSelectbox label,.stCheckbox label,.stTextArea label,.stNumberInput label{color:var(--text)!important;font-family:'Barlow',sans-serif!important;font-weight:500!important;}
input[type="text"],input[type="number"],input[type="password"],input[type="email"],textarea,.stTextInput input,.stNumberInput input,.stTextArea textarea{color:#FFFFFF!important;opacity:1!important;-webkit-text-fill-color:#FFFFFF!important;background:var(--bg)!important;}
[data-testid="stStatusWidget"],[data-testid="stDecoration"],[data-testid="stToolbar"],div[data-baseweb="notification"],.stStatusWidget{display:none!important;visibility:hidden!important;opacity:0!important;}
.stApp,section.main,.block-container,[data-testid="stMain"]{opacity:1!important;background:var(--bg)!important;}
body,html{opacity:1!important;background:var(--bg)!important;}
.sentiment-bar{height:20px;border-radius:3px;position:relative;overflow:hidden;background:linear-gradient(90deg,#F85149,#F0B429,#3FB950);margin:8px 0;}
.sentiment-needle{position:absolute;top:0;width:3px;height:100%;background:#fff;box-shadow:0 0 6px rgba(255,255,255,.8);transform:translateX(-50%);}
.risk-card{background:var(--bg2);border:1px solid var(--border);padding:10px 14px;border-radius:4px;margin-bottom:6px;}
.risk-card.high{border-left:4px solid var(--red);}
.risk-card.med{border-left:4px solid var(--yellow);}
.risk-card.low{border-left:4px solid var(--green);}
@media(max-width:768px){.ticker-bar{grid-template-columns:repeat(2,1fr)!important;}.of-mag7{grid-template-columns:repeat(4,1fr)!important;}.cal-header,.cal-row{grid-template-columns:50px 35px 1fr 50px!important;}.fg{grid-template-columns:1fr!important;}}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<script>
(function(){let v=document.querySelector('meta[name="viewport"]');if(!v){v=document.createElement('meta');v.name='viewport';document.head.appendChild(v);}v.content='width=device-width,initial-scale=1.0,maximum-scale=5.0,user-scalable=yes';})();
</script>
""", unsafe_allow_html=True)

# ── COMPONENTE PERSISTENTE: sidebar btn + tab restore + anti-escurecimento ────
st_components.html("""
<script>
(function(){
  var p=window.parent;
  var d=p.document;

  /* ── 1. ANTI-ESCURECIMENTO ── */
  var styleId='qt-no-fade';
  if(!d.getElementById(styleId)){
    var s=d.createElement('style');
    s.id=styleId;
    s.textContent=[
      '.stApp,[data-testid="stMain"],section.main,.block-container{opacity:1!important;transition:none!important;}',
      'div[class*="overlayContainer"],div[class*="overlay"],div[class*="stSpinner"]{display:none!important;opacity:0!important;}',
      '.stApp::before,.stApp::after{display:none!important;}',
      '[data-testid="stStatusWidget"],[data-testid="stDecoration"],[data-testid="stToolbar"]{display:none!important;}'
    ].join('');
    d.head.appendChild(s);
  }

  /* ── 2. BOTÃO SIDEBAR ── */
  var CSS='position:fixed;top:10px;left:10px;z-index:2147483647;background:linear-gradient(135deg,#EFA500,#FFB800);color:#000;font-family:"Barlow Condensed",sans-serif;font-weight:800;font-size:13px;letter-spacing:1px;border:none;border-radius:6px;padding:7px 15px;cursor:pointer;box-shadow:0 4px 12px rgba(239,165,0,0.5);line-height:1.2;';
  function sbOpen(){var sb=d.querySelector('section[data-testid="stSidebar"]');return sb?sb.getBoundingClientRect().width>80:false;}
  function doToggle(){
    var tries=['.stSidebarCollapseButton button','.stSidebarHeader button','section[data-testid="stSidebar"] button','[data-testid="collapsedControl"]'];
    for(var i=0;i<tries.length;i++){var el=d.querySelector(tries[i]);if(el&&el.offsetParent!==null){el.click();return;}}
  }
  function ensureBtn(){
    var b=d.getElementById('qt-sb-btn');
    if(!b){
      b=d.createElement('button');b.id='qt-sb-btn';b.style.cssText=CSS;
      b.addEventListener('mouseenter',function(){b.style.opacity='0.85';b.style.transform='scale(1.05)';});
      b.addEventListener('mouseleave',function(){b.style.opacity='1';b.style.transform='';});
      b.addEventListener('click',function(){doToggle();setTimeout(function(){b.textContent=sbOpen()?'✕ FECHAR':'☰ MENU';},450);});
      d.body.appendChild(b);
    }
    b.textContent=sbOpen()?'✕ FECHAR':'☰ MENU';
    b.style.display='block';
    ['.stSidebarCollapseButton','[data-testid="collapsedControl"]'].forEach(function(s){
      d.querySelectorAll(s).forEach(function(el){el.style.opacity='0';el.style.pointerEvents='none';});
    });
  }

  /* ── 3. TAB RESTORE ── */
  var isR=false;
  function saveTab(){
    try{
      var tabs=Array.from(d.querySelectorAll('button[data-testid="stTab"]'));
      var active=tabs.findIndex(function(t){return t.getAttribute('aria-selected')==='true';});
      if(active>=0)sessionStorage.setItem('qt_tab_idx',String(active));
    }catch(e){}
  }
  function restoreTab(){
    if(isR)return;
    try{
      var si=parseInt(sessionStorage.getItem('qt_tab_idx')||'0');
      if(si<=0)return;
      var tabs=d.querySelectorAll('button[data-testid="stTab"]');
      if(tabs.length<=si)return;
      var tt=tabs[si];
      if(tt.getAttribute('aria-selected')==='true')return;
      isR=true;tt.click();setTimeout(function(){isR=false;},400);
    }catch(e){isR=false;}
  }
  /* Escutar cliques nas tabs para salvar */
  d.addEventListener('click',function(e){
    var t=e.target.closest('button[data-testid="stTab"]');
    if(t)setTimeout(saveTab,100);
  },true);
  /* Observar DOM para restaurar tab após rerun */
  new MutationObserver(function(muts){
    for(var i=0;i<muts.length;i++){
      for(var j=0;j<muts[i].addedNodes.length;j++){
        var n=muts[i].addedNodes[j];
        if(n.nodeType!==1)continue;
        if((n.matches&&n.matches('div[data-baseweb="tab-list"]'))||(n.querySelector&&n.querySelector('div[data-baseweb="tab-list"]'))){
          setTimeout(restoreTab,200);return;
        }
      }
    }
  }).observe(d.body,{childList:true,subtree:true});

  /* ── TICK GERAL ── */
  function tick(){ensureBtn();}
  setTimeout(tick,600);
  setInterval(tick,800);
})();
</script>
""", height=0)

# ══════════════════════════════════════════════════════════════════════════════
# GAMMA LEVEL DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════
GAMMA_LEVEL_INFO = {
    "HVL":        {"name":"High Vol Level","short":"Flip Gamma","color":"#EFA500","class":"hvl","desc":"Ponto de inflexão do regime. Acima = dealers compram quedas. Abaixo = dealers vendem quedas."},
    "CW":         {"name":"Call Wall","short":"Teto curto prazo","color":"#3FB950","class":"cw","desc":"Maior concentração de gamma de calls. Resistência magnética."},
    "CW 0DTE":    {"name":"Call Wall 0DTE","short":"Teto intraday","color":"#3FB950","class":"cw","desc":"Call Wall para opções que expiram hoje."},
    "PW":         {"name":"Put Wall","short":"Suporte curto prazo","color":"#F85149","class":"pw","desc":"Maior concentração de gamma de puts. Rompimento = aceleração de queda."},
    "PW 0DTE":    {"name":"Put Wall 0DTE","short":"Suporte intraday","color":"#F85149","class":"pw","desc":"Put Wall para opções com expiração hoje."},
    "KL":         {"name":"Key Level","short":"Nível estrutural","color":"#58A6FF","class":"","desc":"Strike com grande concentração de OI."},
    "KL 0DTE":    {"name":"Key Level 0DTE","short":"Pivô intraday","color":"#58A6FF","class":"","desc":"Key Level para opções de expiração hoje."},
    "GEX 1":      {"name":"GEX Strike #1","short":"Maior GEX","color":"#A8B3BD","class":"","desc":"Strike com maior Gamma Exposure absoluto."},
    "GEX 2":      {"name":"GEX Strike #2","short":"2º maior GEX","color":"#A8B3BD","class":"","desc":"Segundo maior strike de GEX."},
    "GEX 3":      {"name":"GEX Strike #3","short":"3º maior GEX","color":"#A8B3BD","class":"","desc":"Terceiro maior strike de GEX."},
    "1D Exp Min": {"name":"1-Day Expected Min","short":"Mínimo esperado","color":"#F85149","class":"pw","desc":"Limite inferior do range esperado pelo mercado de opções."},
    "1D Exp Max": {"name":"1-Day Expected Max","short":"Máximo esperado","color":"#3FB950","class":"cw","desc":"Limite superior do range esperado."},
}

# ══════════════════════════════════════════════════════════════════════════════
# TICKER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_ticker_live(symbol: str) -> dict:
    try:
        t    = yf.Ticker(symbol)
        hist = t.history(period="2d")
        if len(hist) < 2:
            return {}
        price  = float(hist['Close'].iloc[-1])
        prev   = float(hist['Close'].iloc[-2])
        change = ((price - prev) / prev) * 100
        clean  = (symbol.replace("^","").replace("=X","").replace("-Y.NYB","")
                        .replace("=F","").replace(".AX","").replace(".MI","")
                        .replace(".SS","").replace(".BO",""))
        return {"sym":symbol,"n":clean,"p":price,"c":change,"ts":time.time(),"price":price,"change":change}
    except:
        return {}

def update_ticker_store(symbols: list, force: bool = False):
    now = time.time()
    for sym in symbols:
        existing = st.session_state.ticker_store.get(sym, {})
        age = now - existing.get("ts", 0)
        if force or age > TICKER_REFRESH_INTERVAL:
            d = _fetch_ticker_live(sym)
            if d:
                st.session_state.ticker_store[sym] = d
    st.session_state.last_ticker_fetch = time.time()

def get_cached_tickers(symbols: list) -> list:
    now = time.time()
    missing = [s for s in symbols if s not in st.session_state.ticker_store
               or (now - st.session_state.ticker_store[s].get("ts", 0)) > TICKER_REFRESH_INTERVAL]
    if missing:
        update_ticker_store(missing)
    return [st.session_state.ticker_store[s] for s in symbols
            if s in st.session_state.ticker_store and st.session_state.ticker_store[s]]

def get_full_ticker_live(symbol: str) -> dict:
    stored = st.session_state.ticker_store.get(symbol, {})
    if stored and (time.time() - stored.get("ts", 0)) < TICKER_REFRESH_INTERVAL:
        return stored
    d = _fetch_ticker_live(symbol)
    if d:
        try:
            hist = yf.Ticker(symbol).history(period="2d")
            d["high"]  = float(hist['High'].iloc[-1])
            d["low"]   = float(hist['Low'].iloc[-1])
            d["vol"]   = float(hist['Volume'].iloc[-1])
            d["open"]  = float(hist['Open'].iloc[-1])
        except:
            pass
        st.session_state.ticker_store[symbol] = d
    return d

# ══════════════════════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════════════════════
def fetch_news_background():
    now = time.time()
    if (now - st.session_state.last_news_fetch) < NEWS_REFRESH_INTERVAL:
        return [item['t'] for item in st.session_state.news_history[:30]]
    new_titles = []
    for url in st.session_state.rss_urls.split('\n'):
        if not url.strip():
            continue
        try:
            feed = feedparser.parse(url.strip())
            for entry in feed.entries[:20]:
                title = getattr(entry, 'title', '')
                link  = getattr(entry, 'link', '#')
                if title and not any(n['t'] == title for n in st.session_state.news_history):
                    st.session_state.news_history.insert(0, {
                        't': title, 'l': link,
                        'h': datetime.now().strftime("%H:%M"),
                    })
                if title:
                    new_titles.append(title)
        except:
            continue
    st.session_state.news_history = st.session_state.news_history[:150]
    st.session_state.last_news_fetch = now
    return new_titles or [item['t'] for item in st.session_state.news_history[:30]]

def _parse_levels(levels_str: str) -> dict:
    parts = [p.strip() for p in levels_str.split(',')]
    d = {}
    for i in range(0, len(parts) - 1, 2):
        try:
            d[parts[i]] = float(parts[i+1])
        except:
            pass
    return d

def _get_inst(label: str):
    for inst in st.session_state.get("gamma_instruments", []):
        if inst.get('label','').upper() == label.upper():
            return inst
    return None

# ══════════════════════════════════════════════════════════════════════════════
# AI ROTATION SYSTEM
# ══════════════════════════════════════════════════════════════════════════════
def _key_hash(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()[:8] if key else "none"

def _is_key_blocked(key: str) -> bool:
    blocked = st.session_state.get('blocked_keys', {})
    h = _key_hash(key)
    if h in blocked:
        if time.time() < blocked[h]:
            return True
        else:
            del blocked[h]
            st.session_state.blocked_keys = blocked
    return False

def _is_model_blocked(model: str) -> bool:
    blocked = st.session_state.get('blocked_models', {})
    if model in blocked:
        if time.time() < blocked[model]:
            return True
        else:
            del blocked[model]
            st.session_state.blocked_models = blocked
    return False

def _block_key(key: str, seconds: int = 60):
    blocked = st.session_state.get('blocked_keys', {})
    blocked[_key_hash(key)] = time.time() + seconds
    st.session_state.blocked_keys = blocked

def _block_model(model: str, seconds: int = 300):
    blocked = st.session_state.get('blocked_models', {})
    blocked[model] = time.time() + seconds
    st.session_state.blocked_models = blocked

def _log_ai_call(model: str, key_hash: str, status: str, error: str = ""):
    log = st.session_state.get('ai_call_log', [])
    log.insert(0, {"ts":time.time(),"time":datetime.now().strftime("%H:%M:%S"),"model":model,"key":key_hash,"status":status,"error":error[:120] if error else ""})
    st.session_state.ai_call_log = log[:50]

def get_available_model() -> str:
    selected = st.session_state.get('ai_model', 'llama-3.3-70b-versatile')
    if not _is_model_blocked(selected):
        return selected
    for m in GROQ_MODELS:
        if m != selected and not _is_model_blocked(m):
            return m
    return selected

def call_groq_with_fallback(messages: list, max_tokens: int = 800,
                             temperature: float = 0.5, max_attempts: int = 5) -> str:
    valid_keys = [k for k in st.session_state.get('groq_keys', []) if k.strip()]
    if not valid_keys:
        return "⚠️ Nenhuma GROQ API Key configurada."
    last_error = ""
    tried_models = set()
    for attempt in range(max_attempts):
        available_keys = [k for k in valid_keys if not _is_key_blocked(k)]
        if not available_keys:
            available_keys = valid_keys
        key = random.choice(available_keys)
        model = get_available_model()
        kh = _key_hash(key)
        if model in tried_models and len(tried_models) < len(GROQ_MODELS):
            for m in GROQ_MODELS:
                if m not in tried_models and not _is_model_blocked(m):
                    model = m
                    break
        tried_models.add(model)
        try:
            client = Groq(api_key=key)
            res = client.chat.completions.create(
                messages=messages, model=model,
                max_tokens=max_tokens, temperature=temperature
            ).choices[0].message.content
            _log_ai_call(model, kh, "✅ OK")
            return res
        except Exception as e:
            err_str = str(e).lower()
            last_error = str(e)
            if "429" in err_str or "rate_limit" in err_str or "rate limit" in err_str:
                _block_key(key, seconds=60)
                if "tpd" in err_str or "rpd" in err_str or "daily" in err_str:
                    _block_model(model, seconds=3600)
                    _log_ai_call(model, kh, "⚠️ DAILY LIMIT", str(e))
                else:
                    _log_ai_call(model, kh, "⚠️ RATE LIMIT", str(e))
            elif "decommissioned" in err_str or ("model" in err_str and "not found" in err_str):
                _block_model(model, seconds=86400)
                _log_ai_call(model, kh, "❌ MODEL DEAD", str(e))
            elif any(code in err_str for code in ["500","502","503","504"]):
                _block_model(model, seconds=120)
                _log_ai_call(model, kh, "❌ SERVER ERR", str(e))
            elif "401" in err_str or "unauthorized" in err_str or ("invalid" in err_str and "key" in err_str):
                _block_key(key, seconds=3600)
                _log_ai_call(model, kh, "🔒 AUTH ERR", str(e))
            elif "context" in err_str or "too long" in err_str or "max_tokens" in err_str:
                _log_ai_call(model, kh, "📏 CTX TOO LONG", str(e))
                max_tokens = max(200, max_tokens // 2)
            else:
                _log_ai_call(model, kh, "❌ ERRO", str(e))
    return f"⚠️ Falha após {max_attempts} tentativas. Último erro: {last_error[:200]}"

def get_groq_client():
    valid = [k for k in st.session_state.get('groq_keys', []) if k.strip()]
    if not valid:
        return None
    available = [k for k in valid if not _is_key_blocked(k)]
    if not available:
        blocked = st.session_state.get('blocked_keys', {})
        best = min(valid, key=lambda k: blocked.get(_key_hash(k), 0))
        return Groq(api_key=best)
    return Groq(api_key=random.choice(available))

# ══════════════════════════════════════════════════════════════════════════════
# TRANSLATION
# ══════════════════════════════════════════════════════════════════════════════
def translate_news_batch(news_items: list, client_obj=None):
    if not news_items:
        return
    if 'translation_cache' not in st.session_state:
        st.session_state.translation_cache = {}
    to_translate = [item.get('t','') for item in news_items
                    if item.get('t','') and item.get('t','') not in st.session_state.translation_cache]
    if not to_translate:
        return
    for i in range(0, len(to_translate), 15):
        batch = to_translate[i:i+15]
        try:
            numbered = "\n".join(f"{idx+1}. {t}" for idx, t in enumerate(batch))
            prompt = f"""Traduza os títulos de notícias financeiras para português brasileiro.
REGRAS: Mantenha tickers/siglas em maiúsculo (AAPL, FED, S&P 500). Mantenha valores (US$100B, 5%). Tradução natural. Retorne APENAS as traduções numeradas.
TÍTULOS:\n{numbered}\nTRADUÇÕES:"""
            res = call_groq_with_fallback([{"role":"user","content":prompt}], max_tokens=1500, temperature=0.3, max_attempts=2)
            if res.startswith("⚠️"):
                for o in batch:
                    st.session_state.translation_cache.setdefault(o, o)
                continue
            for line in res.split('\n'):
                line = line.strip()
                if not line or '. ' not in line[:5]:
                    continue
                try:
                    num_str, translation = line.split('. ', 1)
                    idx = int(num_str.strip()) - 1
                    if 0 <= idx < len(batch):
                        st.session_state.translation_cache[batch[idx]] = translation.strip()
                except:
                    continue
        except Exception:
            for o in batch:
                st.session_state.translation_cache.setdefault(o, o)
    if len(st.session_state.translation_cache) > 500:
        items = list(st.session_state.translation_cache.items())
        st.session_state.translation_cache = dict(items[-400:])

def get_translated_title(original_title: str) -> str:
    return st.session_state.get('translation_cache', {}).get(original_title, original_title)

# ══════════════════════════════════════════════════════════════════════════════
# HVL ALERTS
# ══════════════════════════════════════════════════════════════════════════════
def check_hvl_alerts(gamma_instruments: list, ticker_store: dict) -> list:
    alerts = []
    prev_alerts = {a['label']: a for a in st.session_state.hvl_alerts}
    for inst in gamma_instruments:
        label  = inst.get('label','')
        ticker = inst.get('ticker','')
        levels = _parse_levels(inst.get('levels',''))
        hvl    = levels.get('HVL', 0)
        if not hvl or not ticker:
            continue
        td = ticker_store.get(ticker, {})
        if not td:
            continue
        spot = td.get('p', 0)
        if not spot:
            continue
        above = spot >= hvl
        prev  = prev_alerts.get(label, {})
        prev_above = prev.get('above', above)
        if above != prev_above:
            direction = "ACIMA" if above else "ABAIXO"
            alert = {'label':label,'ticker':ticker,'hvl':hvl,'spot':spot,
                     'above':above,'direction':direction,
                     'diff':spot-hvl,'regime':"POSITIVO" if above else "NEGATIVO",
                     'time':datetime.now().strftime("%H:%M:%S"),'ts':time.time()}
            alerts.append(alert)
            history = st.session_state.hvl_alert_history
            history.insert(0, alert)
            st.session_state.hvl_alert_history = history[:50]
        else:
            if prev:
                alerts.append(prev)
            else:
                alerts.append({'label':label,'ticker':ticker,'hvl':hvl,'spot':spot,
                               'above':above,'direction':"ACIMA" if above else "ABAIXO",
                               'diff':spot-hvl,'regime':"POSITIVO" if above else "NEGATIVO",
                               'time':datetime.now().strftime("%H:%M:%S"),'ts':time.time()})
    st.session_state.hvl_alerts = alerts
    return [a for a in alerts if
            any(a['label'] == b['label'] and a.get('above') != b.get('above')
                for b in prev_alerts.values())]

# ══════════════════════════════════════════════════════════════════════════════
# MARKET CONTEXT — yFinance additional data for AI
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300)
def fetch_market_context() -> dict:
    """Busca contexto adicional de mercado para enriquecer análise AI."""
    ctx = {}
    try:
        # VIX
        vix = yf.Ticker("^VIX").history(period="5d")
        if len(vix) >= 2:
            ctx['vix'] = float(vix['Close'].iloc[-1])
            ctx['vix_prev'] = float(vix['Close'].iloc[-2])
            ctx['vix_chg'] = ctx['vix'] - ctx['vix_prev']
    except:
        pass
    try:
        # 10-Year yield
        tnx = yf.Ticker("^TNX").history(period="5d")
        if len(tnx) >= 2:
            ctx['yield_10y'] = float(tnx['Close'].iloc[-1])
            ctx['yield_10y_prev'] = float(tnx['Close'].iloc[-2])
            ctx['yield_10y_chg'] = ctx['yield_10y'] - ctx['yield_10y_prev']
    except:
        pass
    try:
        # 2-Year yield
        twoyr = yf.Ticker("^IRX").history(period="5d")
        if len(twoyr) >= 2:
            ctx['yield_2y'] = float(twoyr['Close'].iloc[-1]) / 10
    except:
        pass
    try:
        # DXY
        dxy = yf.Ticker("DX-Y.NYB").history(period="5d")
        if len(dxy) >= 2:
            ctx['dxy'] = float(dxy['Close'].iloc[-1])
            ctx['dxy_chg'] = float(dxy['Close'].iloc[-1]) - float(dxy['Close'].iloc[-2])
    except:
        pass
    try:
        # Gold
        gc = yf.Ticker("GC=F").history(period="5d")
        if len(gc) >= 2:
            ctx['gold'] = float(gc['Close'].iloc[-1])
            ctx['gold_chg_pct'] = ((ctx['gold'] - float(gc['Close'].iloc[-2])) / float(gc['Close'].iloc[-2])) * 100
    except:
        pass
    try:
        # WTI Oil
        cl = yf.Ticker("CL=F").history(period="5d")
        if len(cl) >= 2:
            ctx['oil'] = float(cl['Close'].iloc[-1])
            ctx['oil_chg_pct'] = ((ctx['oil'] - float(cl['Close'].iloc[-2])) / float(cl['Close'].iloc[-2])) * 100
    except:
        pass
    try:
        # SPY for 5d return
        spy = yf.Ticker("SPY").history(period="10d")
        if len(spy) >= 5:
            ctx['spy_5d_ret'] = ((float(spy['Close'].iloc[-1]) - float(spy['Close'].iloc[-5])) / float(spy['Close'].iloc[-5])) * 100
    except:
        pass
    return ctx

# ══════════════════════════════════════════════════════════════════════════════
# EARNINGS FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════
def _get_week_range():
    today = date.today()
    wd = today.weekday()
    if wd > 4:
        monday = today + timedelta(days=(7 - wd))
    else:
        monday = today - timedelta(days=wd)
    friday = monday + timedelta(days=4)
    return monday, friday

def _get_previous_business_day():
    d = date.today() - timedelta(days=1)
    while d.weekday() > 4:
        d -= timedelta(days=1)
    return d

@st.cache_data(ttl=3600)
def fetch_earnings_week():
    monday, friday = _get_week_range()
    url = (f"https://api.savvytrader.com/pricing/assets/earnings/calendar"
           f"?start={monday.strftime('%Y-%m-%d')}&end={friday.strftime('%Y-%m-%d')}")
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                return data
    except:
        pass
    return []

@st.cache_data(ttl=600)
def fetch_yesterday_earnings_results(min_mcap: float = 500e6):
    yesterday = _get_previous_business_day()
    yesterday_str = yesterday.strftime('%Y-%m-%d')
    start = yesterday - timedelta(days=1)
    end   = yesterday + timedelta(days=1)
    url = (f"https://api.savvytrader.com/pricing/assets/earnings/calendar"
           f"?start={start.strftime('%Y-%m-%d')}&end={end.strftime('%Y-%m-%d')}")
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return [], yesterday
        data = r.json()
        if not isinstance(data, list):
            return [], yesterday
        reported = []
        for e in data:
            mcap  = e.get("marketCap", 0) or 0
            edate = e.get("earningsDate", "")
            if edate != yesterday_str or mcap < min_mcap:
                continue
            has_actual  = e.get("epsActual") is not None or e.get("eps") is not None
            has_revenue = e.get("revenueActual") is not None
            if has_actual or has_revenue:
                reported.append(e)
        reported.sort(key=lambda x: x.get("marketCap", 0) or 0, reverse=True)
        return reported[:50], yesterday
    except Exception:
        return [], yesterday

def get_earnings_actual(e: dict) -> float:
    return e.get("epsActual") if e.get("epsActual") is not None else e.get("eps")

def get_revenue_actual(e: dict) -> float:
    rev_a = e.get("revenueActual")
    if rev_a is not None and rev_a != 0:
        return rev_a
    rev = e.get("revenue")
    if rev is not None and rev != 0:
        return rev
    return 0

def filter_important_earnings(earnings_list: list, min_market_cap: float = 0,
                               min_importance: int = 0, show_all: bool = False) -> list:
    if show_all:
        filtered = list(earnings_list)
    else:
        filtered = [e for e in earnings_list
                    if (e.get("marketCap",0) or 0) >= min_market_cap
                    or (e.get("importance",0) or 0) >= min_importance]
    filtered.sort(key=lambda x: (x.get("marketCap",0) or 0), reverse=True)
    return filtered

def format_market_cap(val):
    if not val or val == 0: return "—"
    if val >= 1e12: return f"${val/1e12:.1f}T"
    if val >= 1e9:  return f"${val/1e9:.1f}B"
    if val >= 1e6:  return f"${val/1e6:.0f}M"
    return f"${val:,.0f}"

def earnings_time_label(e):
    t = e.get("earningsTime","")
    if not t: return "—"
    try:
        hour = int(t.split(":")[0])
        return "BMO" if hour < 12 else "AMC"
    except:
        return "—"

def calc_surprise(actual, estimate):
    if actual is None or estimate is None or estimate == 0:
        return None
    return ((actual - estimate) / abs(estimate)) * 100

# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL JUICE
# ══════════════════════════════════════════════════════════════════════════════
def _format_money(val: float, short: bool = True) -> str:
    if val is None: return "—"
    try:
        val = float(val)
    except:
        return "—"
    abs_val = abs(val)
    sign = "-" if val < 0 else ""
    if abs_val >= 1e9:   return f"{sign}${abs_val/1e9:.2f}B"
    elif abs_val >= 1e6: return f"{sign}${abs_val/1e6:.1f}M"
    elif abs_val >= 1e3: return f"{sign}${abs_val/1e3:.1f}K"
    else:                return f"{sign}${abs_val:,.0f}"

@st.cache_data(ttl=FJ_REFRESH_INTERVAL)
def fetch_fj_data(token: str = None) -> dict:
    if not token:
        token = st.session_state.get('fj_token', FJ_DEFAULT_TOKEN)
    time_offset = -3
    url = (f"https://live.financialjuice.com/FJService.asmx/Startup"
           f"?info={token}&TimeOffset={time_offset}&tabID=0&oldID=0&TickerID=0&FeedCompanyID=0&strSearch=&extraNID=0")
    headers = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
               "Accept":"application/json, text/javascript, */*; q=0.01",
               "Referer":"https://www.financialjuice.com/",
               "X-Requested-With":"XMLHttpRequest"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return {}
        text = r.text.strip()
        if text.startswith("<?xml") or "<string" in text:
            m = re.search(r'<string[^>]*>(.*?)</string>', text, re.DOTALL)
            if m:
                text = m.group(1).strip()
                text = text.replace("&quot;",'"').replace("&amp;","&").replace("&lt;","<").replace("&gt;",">")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = json.loads(text.replace("\r","").replace("\n",""))
        return data if isinstance(data, dict) else {}
    except Exception as e:
        return {}

def parse_fj_orderflow(fj_data: dict) -> dict:
    if not fj_data:
        return {}
    market_data = fj_data.get("MarketData", {})
    if not market_data:
        return {}
    indices_raw = market_data.get("MarketData", [])
    chart_data  = market_data.get("ChartData", {})
    graph_data  = market_data.get("GraphData", {})
    is_moc      = market_data.get("IsMOC", False)
    indices = []
    for idx in indices_raw:
        try:
            indices.append({
                "name":      idx.get("Sheet_Name","?"),
                "moo_buys":  float(idx.get("MOO_Buys",0) or 0),
                "moo_sells": float(idx.get("MOO_Sells",0) or 0),
                "moo_total": float(idx.get("MOO_Total",0) or 0),
                "moc_buys":  float(idx.get("MOC_Buys",0) or 0),
                "moc_sells": float(idx.get("MOC_Sells",0) or 0),
                "moc_total": float(idx.get("MOC_Total",0) or 0),
            })
        except:
            continue
    def parse_tickers(lst):
        result = []
        if isinstance(lst, list):
            for t in lst:
                try:
                    sym = (t.get("Ticker","") or "").strip()
                    val = float(t.get("Value",0) or 0)
                    if sym:
                        result.append({"ticker":sym,"value":val})
                except:
                    continue
        return result
    return {
        "indices":      indices,
        "top_buy_moo":  parse_tickers(chart_data.get("MOOBuyTickers",[])),
        "top_sell_moo": parse_tickers(chart_data.get("MOOSellTickers",[])),
        "top_buy_moc":  parse_tickers(chart_data.get("MOCBuyTickers",[])),
        "top_sell_moc": parse_tickers(chart_data.get("MOCSellTickers",[])),
        "mag7_moo":     parse_tickers(graph_data.get("MOO",[])),
        "mag7_moc":     parse_tickers(graph_data.get("MOC",[])),
        "is_moc":       is_moc,
    }

def parse_fj_calendar(fj_data: dict, only_today: bool = True, min_impact: int = 1,
                       priority_only: bool = True, include_global: bool = True) -> list:
    if not fj_data:
        return []
    cal_raw = fj_data.get("Cal", [])
    if not isinstance(cal_raw, list):
        return []
    today_str = date.today().strftime("%Y-%m-%d")
    now_dt    = datetime.now()
    events    = []
    for e in cal_raw:
        try:
            country = (e.get("CountryCode","") or "").upper().strip()
            if priority_only:
                if country == "" and not include_global:
                    continue
                elif country and country not in PRIORITY_COUNTRIES:
                    continue
            try:
                api_imp = int(e.get("ImpID","3") or "3")
            except:
                api_imp = 3
            imp = 3 if api_imp == 1 else (2 if api_imp == 2 else 1)
            if imp < min_impact:
                continue
            real_date_str = e.get("RealDate", e.get("Date",""))
            if not real_date_str:
                continue
            try:
                if "T" in real_date_str:
                    event_dt = datetime.fromisoformat(real_date_str.replace("Z",""))
                else:
                    event_dt = datetime.strptime(real_date_str.split("T")[0], "%Y-%m-%d")
            except:
                continue
            event_date_str = event_dt.strftime("%Y-%m-%d")
            if only_today and event_date_str != today_str:
                continue
            is_past = False
            is_now  = False
            if event_date_str == today_str:
                time_diff = (event_dt - now_dt).total_seconds()
                is_past = time_diff < -300
                is_now  = -300 <= time_diff <= 1800
            country_name = PRIORITY_COUNTRIES.get(country, country) if country else "🌐 GLOBAL"
            country_emoji = country_name.split(" ")[0] if " " in country_name else (country if country else "🌐")
            events.append({
                "id":           e.get("ID",""),
                "date":         event_date_str,
                "time":         e.get("Time","??:??"),
                "datetime":     event_dt,
                "country":      country if country else "GLOBAL",
                "country_name": country_name,
                "country_emoji":country_emoji,
                "title":        e.get("Title",""),
                "forecast":     e.get("Forecast","-") or "-",
                "previous":     e.get("Previous","-") or "-",
                "actual":       e.get("Actual","-") or "-",
                "impact":       imp,
                "api_impact":   api_imp,
                "is_past":      is_past,
                "is_now":       is_now,
                "speaker":      e.get("Speaker","") or "",
            })
        except Exception:
            continue
    events.sort(key=lambda x: x["datetime"])
    return events

def detect_orderflow_alerts(parsed: dict) -> list:
    alerts = []
    if not parsed or not parsed.get("indices"):
        return alerts
    for idx in parsed["indices"]:
        name      = idx["name"]
        moo_total = idx["moo_total"]
        moc_total = idx["moc_total"]
        if moc_total < -50_000_000:
            alerts.append({"type":"MOC_SELL","index":name,"value":moc_total,
                           "msg":f"⚠️ {name}: MOC dominante de VENDA ({_format_money(moc_total)})","color":"red"})
        if moo_total > 300_000_000:
            alerts.append({"type":"MOO_BUY","index":name,"value":moo_total,
                           "msg":f"🟢 {name}: MOO forte de COMPRA ({_format_money(moo_total)})","color":"green"})
        if moo_total < -300_000_000:
            alerts.append({"type":"MOO_SELL","index":name,"value":moo_total,
                           "msg":f"🔴 {name}: MOO forte de VENDA ({_format_money(moo_total)})","color":"red"})
    return alerts

def get_fj_cached_data() -> tuple:
    raw = fetch_fj_data()
    if not raw:
        return ({}, [], [])
    orderflow = parse_fj_orderflow(raw)
    cal_today = parse_fj_calendar(raw, only_today=True, min_impact=2, priority_only=True, include_global=True)
    alerts    = detect_orderflow_alerts(orderflow)
    return (orderflow, cal_today, alerts)

# ══════════════════════════════════════════════════════════════════════════════
# AI TRIGGER HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def should_run_macro_ai(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.macro_ai_cache: return True
    if (time.time() - st.session_state.last_ai_auto) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_factors(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.factors_cache: return True
    if (time.time() - st.session_state.last_factors_run) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_summary(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.get('summary_cache_global',''): return True
    if (time.time() - st.session_state.get('last_summary_run',0)) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_orderflow_ai(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.get('orderflow_ai_cache',''): return True
    if (time.time() - st.session_state.get('last_orderflow_ai',0)) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_calendar_ai(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.get('calendar_ai_cache',''): return True
    if (time.time() - st.session_state.get('last_calendar_ai',0)) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_intermarket_ai(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.get('intermarket_ai_cache',''): return True
    if (time.time() - st.session_state.get('last_intermarket_ai',0)) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_risk_scan(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.get('risk_scan_cache',''): return True
    if (time.time() - st.session_state.get('last_risk_scan',0)) >= AI_REFRESH_INTERVAL: return True
    return False

def should_run_news_sentiment(btn_clicked: bool) -> bool:
    if btn_clicked: return True
    if not st.session_state.get('news_sentiment_cache',''): return True
    if (time.time() - st.session_state.get('last_news_sentiment',0)) >= 1800: return True
    return False

# ══════════════════════════════════════════════════════════════════════════════
# FINVIZ
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60)
def fetch_finviz_bubbles():
    url = "https://finviz.com/api/bubbles?x=sector&y=lastChange&size=marketCap&color=sector&idx=sp500&rangeX=&rangeY=&sec=&ind=&cap=&sh_avgvol=&tickers=&excludeTickers="
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []

def render_finviz_bubbles():
    import plotly.express as px
    data = fetch_finviz_bubbles()
    if not data:
        st.error("⚠️ Erro ao carregar dados do Finviz.")
        return

    total = len(data)
    up = sum(1 for x in data if x.get('y', 0) > 0)
    down = sum(1 for x in data if x.get('y', 0) < 0)
    avg_val = sum(x.get('y', 0) for x in data) / total if total > 0 else 0
    
    color_red = "#F85149"
    color_green = "#3FB950"
    avg_color = color_green if avg_val >= 0 else color_red

    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; gap: 10px; margin-bottom: 20px;">
            <div style="flex: 1; background: #0d1117; border: 1px solid #30363d; padding: 10px; border-radius: 4px; text-align: center;">
                <div style="color: #C5CDD6; font-size: 11px; font-family: 'JetBrains Mono'; font-weight:600;">TOTAL</div>
                <div style="color: #ffffff; font-size: 22px; font-weight: bold;">{total}</div>
            </div>
            <div style="flex: 1; background: #0d1117; border: 1px solid {color_green}; padding: 10px; border-radius: 4px; text-align: center;">
                <div style="color: #C5CDD6; font-size: 11px; font-family: 'JetBrains Mono'; font-weight:600;">SUBINDO</div>
                <div style="color: {color_green}; font-size: 22px; font-weight: bold;">{up}</div>
            </div>
            <div style="flex: 1; background: #0d1117; border: 1px solid {color_red}; padding: 10px; border-radius: 4px; text-align: center;">
                <div style="color: #C5CDD6; font-size: 11px; font-family: 'JetBrains Mono'; font-weight:600;">CAINDO</div>
                <div style="color: {color_red}; font-size: 22px; font-weight: bold;">{down}</div>
            </div>
            <div style="flex: 1; background: #0d1117; border: 1px solid {avg_color}; padding: 10px; border-radius: 4px; text-align: center;">
                <div style="color: #C5CDD6; font-size: 11px; font-family: 'JetBrains Mono'; font-weight:600;">MÉDIA GLOBAL</div>
                <div style="color: {avg_color}; font-size: 22px; font-weight: bold;">{avg_val:+.2f}%</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    df = pd.DataFrame(data)

    color_map = {
        "Technology": "#636EFA", "Healthcare": "#EF553B", "Financial": "#00CC96",
        "Consumer Cyclical": "#AB63FA", "Communication Services": "#FFA15A",
        "Industrials": "#19D3F3", "Consumer Defensive": "#FF6692", 
        "Energy": "#B6E880", "Utilities": "#FF97FF", "Real Estate": "#FECB52",
        "Basic Materials": "#17BECF"
    }

    fig = px.scatter(
        df, x="x", y="y", size="size", 
        color="color",
        color_discrete_map=color_map,
        hover_name="ticker", 
        custom_data=["company", "y"],
        size_max=40,
        opacity=1.0
    )

    fig.update_traces(
        hovertemplate="<b>%{hovertext}</b><br>%{customdata[0]}<br>Var: %{customdata[1]:.2f}%<extra></extra>"
    )

    fig.update_layout(
        template="plotly_dark",
        margin=dict(l=0, r=0, t=10, b=0),
        height=600,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, title=""),
        yaxis=dict(
            showgrid=True, 
            gridcolor="#30363D", 
            title="Variação %",
            tickfont=dict(color="#FFFFFF", size=12)
        ),
        showlegend=True,
        legend=dict(
            font=dict(color="#FFFFFF", size=12),
            orientation="h", 
            yanchor="bottom", 
            y=1.02, 
            xanchor="right", 
            x=1
        )
    )

    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})

# ══════════════════════════════════════════════════════════════════════════════
# FUTURES
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60)
def fetch_finviz_futures():
    url = "https://finviz.com/api/futures_all?timeframe=NO"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://finviz.com/futures.ashx",
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict):
                futures_list = []
                for ticker_key, info in data.items():
                    if isinstance(info, dict):
                        info["ticker"] = info.get("ticker", ticker_key)
                        futures_list.append(info)
                return futures_list
            elif isinstance(data, list):
                return data
    except Exception as e:
        print(f"Erro ao buscar futuros Finviz: {e}")
    return []

FUTURES_CATEGORIES = {
    "📊 ÍNDICES": ["ES", "NQ", "YM", "RTY", "MES", "MNQ", "MYM", "M2K", "VX"],
    "🛢️ ENERGIA": ["CL", "BZ", "NG", "RB", "HO", "QM", "QG"],
    "🥇 METAIS":  ["GC", "SI", "HG", "PL", "PA", "MGC", "SIL"],
    "🌾 GRÃOS":   ["ZC", "ZS", "ZW", "ZL", "ZM", "ZO", "ZR"],
    "🐄 CARNES":  ["LE", "GF", "HE"],
    "💵 MOEDAS":  ["6E", "6J", "6B", "6A", "6C", "6S", "6N", "DX"],
    "📈 BONDS":   ["ZB", "ZN", "ZF", "ZT", "UB"],
    "☕ SOFTS":   ["KC", "CC", "SB", "CT", "OJ", "LB"],
}

FUTURES_LABELS = {
    "ES": "S&P 500", "NQ": "NASDAQ", "YM": "DOW", "RTY": "RUSSELL", "VX": "VIX",
    "MES": "Micro S&P", "MNQ": "Micro NQ", "MYM": "Micro DOW", "M2K": "Micro RTY",
    "NKD": "Nikkei", "SPI": "S&P/ASX 200", "FDAX": "DAX", "FESX": "Eurostoxx",
    "CL": "WTI Oil", "BZ": "Brent", "NG": "Gás Natural", "RB": "Gasolina", "HO": "Heating Oil",
    "QM": "E-mini WTI", "QG": "E-mini Gás", "MCL": "Micro WTI",
    "GC": "Ouro", "SI": "Prata", "HG": "Cobre", "PL": "Platina", "PA": "Paládio",
    "MGC": "Micro Ouro", "SIL": "Micro Prata",
    "ZC": "Milho", "ZS": "Soja", "ZW": "Trigo", "ZL": "Óleo Soja", "ZM": "Farelo Soja",
    "ZO": "Aveia", "ZR": "Arroz", "KE": "Trigo KC",
    "LE": "Boi Gordo", "GF": "Bezerro", "HE": "Suíno",
    "6E": "EUR", "6J": "JPY", "6B": "GBP", "6A": "AUD",
    "6C": "CAD", "6S": "CHF", "6N": "NZD", "6M": "MXN", "6R": "RUB",
    "DX": "DXY (Dólar)",
    "ZB": "Bond 30Y", "ZN": "Note 10Y", "ZF": "Note 5Y", "ZT": "Note 2Y", "UB": "UltraBond",
    "TN": "Ultra 10Y",
    "KC": "Café", "CC": "Cacau", "SB": "Açúcar", "CT": "Algodão",
    "OJ": "Suco Laranja", "LB": "Madeira", "LBR": "Madeira",
    "BTC": "Bitcoin", "ETH": "Ethereum", "MBT": "Micro BTC", "MET": "Micro ETH",
}

def get_futures_by_category(all_futures: list) -> dict:
    if not all_futures:
        return {}
    
    valid_futures = [f for f in all_futures if isinstance(f, dict)]
    if not valid_futures:
        return {}
    
    futures_dict = {}
    for f in valid_futures:
        ticker = (f.get("ticker") or f.get("label") or "").upper()
        if ticker:
            futures_dict[ticker] = f
    
    organized = {}
    used_tickers = set()
    
    for cat_name, tickers in FUTURES_CATEGORIES.items():
        cat_futures = []
        for tk in tickers:
            if tk in futures_dict:
                f = futures_dict[tk]
                last_price = f.get("last", 0) or 0
                prev       = f.get("prevClose", 0) or 0
                chg_pct    = f.get("change", 0) or 0
                chg_abs    = last_price - prev if prev else 0
                
                cat_futures.append({
                    "ticker":    tk,
                    "name":      FUTURES_LABELS.get(tk, f.get("label", tk)),
                    "last":      last_price,
                    "change":    chg_abs,
                    "chgPct":    chg_pct,
                    "prevClose": prev,
                    "high":      f.get("high", 0) or 0,
                    "low":       f.get("low", 0) or 0,
                })
                used_tickers.add(tk)
        if cat_futures:
            organized[cat_name] = cat_futures
    
    others = []
    for ticker, f in futures_dict.items():
        if ticker not in used_tickers and ticker:
            last_price = f.get("last", 0) or 0
            prev       = f.get("prevClose", 0) or 0
            chg_pct    = f.get("change", 0) or 0
            chg_abs    = last_price - prev if prev else 0
            
            others.append({
                "ticker":    ticker,
                "name":      FUTURES_LABELS.get(ticker, f.get("label", ticker)),
                "last":      last_price,
                "change":    chg_abs,
                "chgPct":    chg_pct,
                "prevClose": prev,
                "high":      f.get("high", 0) or 0,
                "low":       f.get("low", 0) or 0,
            })
    if others:
        others.sort(key=lambda x: x["ticker"])
        organized["📦 OUTROS"] = others
    
    return organized

# ══════════════════════════════════════════════════════════════════════════════
# ORDER FLOW RENDER
# ══════════════════════════════════════════════════════════════════════════════
def render_orderflow_donuts(orderflow: dict):
    import plotly.graph_objects as go
    indices = orderflow.get("indices", [])
    if not indices:
        st.warning("⚠️ Sem dados de Order Flow.")
        return
    is_moc = orderflow.get("is_moc", False)
    label  = "MOC" if is_moc else "MOO"
    cols   = st.columns(min(4, len(indices)))
    for i, idx in enumerate(indices[:4]):
        with cols[i]:
            buys  = idx["moc_buys"]  if is_moc else idx["moo_buys"]
            sells = idx["moc_sells"] if is_moc else idx["moo_sells"]
            total = idx["moc_total"] if is_moc else idx["moo_total"]
            center_color = "#3FB950" if total >= 0 else "#F85149"
            buys_abs  = abs(buys)  if buys  else 0.01
            sells_abs = abs(sells) if sells else 0.01
            fig = go.Figure(data=[go.Pie(
                values=[buys_abs, sells_abs], labels=["Buy","Sell"], hole=0.72,
                marker=dict(colors=["#3FB950","#F85149"], line=dict(color='#0D1117',width=2)),
                textinfo='none', showlegend=False, rotation=90,
            )])
            fig.add_annotation(
                text=(f"<b style='font-size:14px;color:#A8B3BD;'>{label}</b><br>"
                      f"<b style='font-size:22px;color:{center_color};'>{_format_money(total)}</b><br>"
                      f"<span style='font-size:10px;color:#3FB950;'>↑ {_format_money(buys)}</span><br>"
                      f"<span style='font-size:10px;color:#F85149;'>↓ {_format_money(sells)}</span>"),
                x=0.5, y=0.5, showarrow=False,
                font=dict(family="Barlow Condensed",color="#FFFFFF"),
                xref="paper", yref="paper",
            )
            fig.update_layout(
                title=dict(text=f"<b style='color:#EFA500;font-family:Barlow Condensed;font-size:16px;'>{idx['name']}</b>",x=0.5,xanchor='center',y=0.95),
                template="plotly_dark", height=260,
                margin=dict(l=10,r=10,t=40,b=10),
                paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar':False})

def render_orderflow_cards(orderflow: dict, alerts: list):
    indices = orderflow.get("indices", [])
    if not indices:
        return
    is_moc       = orderflow.get("is_moc", False)
    alert_indices = {a["index"] for a in alerts}
    big_buy_indices = {a["index"] for a in alerts if a["type"] == "MOO_BUY"}
    sell_indices = {a["index"] for a in alerts if a["type"] in ["MOC_SELL","MOO_SELL"]}
    cols = st.columns(len(indices[:4]))
    for i, idx in enumerate(indices[:4]):
        with cols[i]:
            name  = idx["name"]
            moo_b = idx["moo_buys"];  moo_s = idx["moo_sells"]; moo_t = idx["moo_total"]
            moc_b = idx["moc_buys"];  moc_s = idx["moc_sells"]; moc_t = idx["moc_total"]
            card_class = "of-card"
            if name in sell_indices:       card_class += " alert"
            elif name in big_buy_indices:  card_class += " bigwin"
            elif (is_moc and moc_t >= 0) or (not is_moc and moo_t >= 0): card_class += " pos"
            else:                          card_class += " neg"
            main_total = moc_t if is_moc else moo_t
            main_label = "MOC" if is_moc else "MOO"
            total_color = "#3FB950" if main_total >= 0 else "#F85149"
            st.markdown(
                f'<div class="{card_class}">'
                f'<div class="of-name">{name}</div>'
                f'<div style="font-size:10px;color:#C5CDD6;font-family:JetBrains Mono;font-weight:600;">{main_label} TOTAL</div>'
                f'<div class="of-total" style="color:{total_color};">{_format_money(main_total)}</div>'
                f'<div class="of-bs"><span class="of-buy">▲ {_format_money(moo_b)}</span><span class="of-sell">▼ {_format_money(moo_s)}</span></div>'
                f'<div style="display:flex;justify-content:space-between;margin-top:6px;padding-top:6px;border-top:1px dashed #30363D;font-size:10px;font-family:JetBrains Mono;">'
                f'<span style="color:#C5CDD6;">MOO:<b style="color:{"#3FB950" if moo_t>=0 else "#F85149"};">{_format_money(moo_t)}</b></span>'
                f'<span style="color:#C5CDD6;">MOC:<b style="color:{"#3FB950" if moc_t>=0 else "#F85149"};">{_format_money(moc_t)}</b></span>'
                f'</div></div>', unsafe_allow_html=True)

def render_top_tickers(orderflow: dict):
    is_moc = orderflow.get("is_moc", False)
    buys   = orderflow.get("top_buy_moc",  []) if is_moc else orderflow.get("top_buy_moo",  [])
    sells  = orderflow.get("top_sell_moc", []) if is_moc else orderflow.get("top_sell_moo", [])
    label  = "MOC" if is_moc else "MOO"
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f'<div class="sh">🟢 TOP 5 BUY {label}</div>', unsafe_allow_html=True)
        if buys:
            max_val = max((t["value"] for t in buys), default=1)
            parts = []
            for t in buys[:5]:
                pct = (t["value"]/max_val*100) if max_val > 0 else 0
                parts.append(f'<div class="of-ticker-row"><span class="of-ticker-sym">{t["ticker"].strip()}</span><div class="of-ticker-bar"><div class="of-ticker-fill buy" style="width:{pct:.1f}%;"></div></div><span class="of-ticker-val" style="color:#3FB950;">{_format_money(t["value"])}</span></div>')
            st.markdown('<div>'+''.join(parts)+'</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#A8B3BD;">Sem dados</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(f'<div class="sh">🔴 TOP 5 SELL {label}</div>', unsafe_allow_html=True)
        if sells:
            max_val = max((t["value"] for t in sells), default=1)
            parts = []
            for t in sells[:5]:
                pct = (t["value"]/max_val*100) if max_val > 0 else 0
                parts.append(f'<div class="of-ticker-row"><span class="of-ticker-sym">{t["ticker"].strip()}</span><div class="of-ticker-bar"><div class="of-ticker-fill sell" style="width:{pct:.1f}%;"></div></div><span class="of-ticker-val" style="color:#F85149;">{_format_money(t["value"])}</span></div>')
            st.markdown('<div>'+''.join(parts)+'</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div style="padding:20px;text-align:center;color:#A8B3BD;">Sem dados</div>', unsafe_allow_html=True)

def render_mag7_individual(orderflow: dict):
    is_moc = orderflow.get("is_moc", False)
    mag7   = orderflow.get("mag7_moc",[]) if is_moc else orderflow.get("mag7_moo",[])
    if not mag7:
        return
    order    = ["AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA"]
    mag_dict = {t["ticker"].strip(): t["value"] for t in mag7}
    label    = "MOC" if is_moc else "MOO"
    st.markdown(f'<div class="sh">📈 MAG 7 INDIVIDUAL — {label} IMBALANCE</div>', unsafe_allow_html=True)
    items = []
    for sym in order:
        val = mag_dict.get(sym, 0)
        if val > 0:   cls="up";   arrow="▲"; color="#3FB950"
        elif val < 0: cls="down"; arrow="▼"; color="#F85149"
        else:         cls="";     arrow="—"; color="#A8B3BD"
        items.append(f'<div class="of-mag-item {cls}"><div class="of-mag-tk">{sym}</div><div class="of-mag-val" style="color:{color};">{_format_money(val)}</div><div class="of-mag-arrow" style="color:{color};">{arrow}</div></div>')
    st.markdown('<div class="of-mag7">'+''.join(items)+'</div>', unsafe_allow_html=True)

def render_orderflow_alerts(alerts: list):
    if not alerts:
        return
    for a in alerts[:5]:
        bg     = "#150707" if a["color"] == "red" else "#071510"
        border = "#F85149" if a["color"] == "red" else "#3FB950"
        st.markdown(f'<div class="alert-hvl" style="background:{bg};border:2px solid {border};border-left:6px solid {border};padding:10px 16px;margin-bottom:6px;"><span style="font-family:Barlow Condensed;font-size:18px;font-weight:800;color:{border};">{a["msg"]}</span><span style="font-family:JetBrains Mono;font-size:10px;color:#C5CDD6;margin-left:12px;">{datetime.now().strftime("%H:%M:%S")} BRT</span></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# CALENDAR RENDER
# ══════════════════════════════════════════════════════════════════════════════
def render_calendar_live(events: list, show_filters: bool = True):
    if not events:
        st.markdown('<div class="empty-state"><div class="empty-title">📅 Sem eventos hoje</div><div class="empty-sub">Nenhum evento de impacto médio/alto<br>nos países G7+China para hoje.</div></div>', unsafe_allow_html=True)
        return
    today_str   = date.today().strftime("%d/%m/%Y")
    weekday_name = ["SEGUNDA","TERÇA","QUARTA","QUINTA","SEXTA","SÁBADO","DOMINGO"][date.today().weekday()]
    st.markdown(f'<div class="cal-day-header">📅 HOJE — {weekday_name} {today_str} · {len(events)} eventos</div>', unsafe_allow_html=True)
    st.markdown('<div class="cal-header"><span>HORA</span><span>PAÍS</span><span>EVENTO</span><span>IMP.</span><span style="text-align:right;">PREV</span><span style="text-align:right;">FCST</span><span style="text-align:right;">ATUAL</span></div>', unsafe_allow_html=True)
    def parse_num(s):
        s = str(s).replace("%","").replace("K","").replace("M","").replace("B","").replace(",",".").strip()
        return float(s)
    rows = []
    for ev in events:
        row_class  = "cal-row"
        row_class += " high" if ev["impact"]==3 else (" med" if ev["impact"]==2 else " low")
        if ev["is_now"]:  row_class += " now"
        elif ev["is_past"]: row_class += " past"
        imp_str = '<span style="color:#F85149;">★★★</span>' if ev["impact"]==3 else ('<span style="color:#F0B429;">★★</span>' if ev["impact"]==2 else '<span style="color:#A8B3BD;">★</span>')
        country_emoji = ev.get("country_emoji", ev["country"])
        actual   = ev["actual"]
        forecast = ev["forecast"]
        actual_class = "cal-num"
        if actual and actual != "-" and forecast and forecast != "-":
            actual_class = "cal-num actual"
            try:
                act  = parse_num(actual)
                fcst = parse_num(forecast)
                if act > fcst:   actual_class = "cal-num beat"
                elif act < fcst: actual_class = "cal-num miss"
            except:
                pass
        title = ev["title"]
        if ev.get("speaker"):
            title += f' <small style="color:#A8B3BD;">({ev["speaker"]})</small>'
        if ev["is_now"]:
            title = f'🔴 <b>{title}</b>'
        rows.append(f'<div class="{row_class}"><span class="cal-time">{ev["time"]}</span><span class="cal-country" title="{ev["country_name"]}">{country_emoji}</span><span class="cal-event">{title}</span><span class="cal-imp">{imp_str}</span><span class="cal-num">{ev["previous"]}</span><span class="cal-num">{ev["forecast"]}</span><span class="{actual_class}">{ev["actual"]}</span></div>')
    st.markdown('<div>'+''.join(rows)+'</div>', unsafe_allow_html=True)

def render_calendar_legend():
    st.markdown('<div style="font-size:10px;color:#A8B3BD;padding:6px 10px;font-family:JetBrains Mono;background:var(--bg2);border-radius:3px;margin-top:6px;">★★★ <b style="color:#F85149;">ALTO IMPACTO</b> · ★★ <b style="color:#F0B429;">MÉDIO</b> · 🔴 <b>ACONTECENDO AGORA</b> · <span style="color:#3FB950;">VERDE</span> = Beat · <span style="color:#F85149;">VERMELHO</span> = Miss</div>', unsafe_allow_html=True)

def render_calendar_summary_cards(events: list):
    if not events:
        return
    high     = sum(1 for e in events if e["impact"] == 3)
    med      = sum(1 for e in events if e["impact"] == 2)
    past     = sum(1 for e in events if e["is_past"])
    upcoming = len(events) - past
    countries = set(e["country"] for e in events)
    st.markdown(
        f'<div style="display:flex;gap:8px;margin-bottom:8px;">'
        f'<div style="flex:1;background:#150707;border:1px solid #F85149;padding:8px;text-align:center;border-radius:4px;"><div style="font-size:9px;color:#C5CDD6;font-family:JetBrains Mono;font-weight:600;">ALTO IMPACTO</div><div style="font-family:Barlow Condensed;font-size:22px;font-weight:800;color:#F85149;">{high}</div></div>'
        f'<div style="flex:1;background:#1A1208;border:1px solid #F0B429;padding:8px;text-align:center;border-radius:4px;"><div style="font-size:9px;color:#C5CDD6;font-family:JetBrains Mono;font-weight:600;">MÉDIO</div><div style="font-family:Barlow Condensed;font-size:22px;font-weight:800;color:#F0B429;">{med}</div></div>'
        f'<div style="flex:1;background:var(--bg2);border:1px solid var(--border);padding:8px;text-align:center;border-radius:4px;"><div style="font-size:9px;color:#C5CDD6;font-family:JetBrains Mono;font-weight:600;">UPCOMING</div><div style="font-family:Barlow Condensed;font-size:22px;font-weight:800;color:#58A6FF;">{upcoming}</div></div>'
        f'<div style="flex:1;background:var(--bg3);border:1px solid var(--amber);padding:8px;text-align:center;border-radius:4px;"><div style="font-size:9px;color:#C5CDD6;font-family:JetBrains Mono;font-weight:600;">PAÍSES</div><div style="font-family:Barlow Condensed;font-size:22px;font-weight:800;color:#EFA500;">{len(countries)}</div></div>'
        f'</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# AI TEXT RENDERER
# ══════════════════════════════════════════════════════════════════════════════
def render_ai_text(text: str, box_class: str = "ai-box", header_color: str = "#EFA500") -> str:
    """Renderiza texto AI formatado com markdown básico."""
    rend = ""
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            rend += "<br>"
        elif (line.startswith("**") and line.endswith("**")) or line.startswith("###"):
            clean = line.replace("**","").replace("###","").strip()
            rend += (f'<div style="font-family:Barlow Condensed;font-size:13px;font-weight:700;'
                     f'color:{header_color};text-transform:uppercase;margin-top:12px;padding-bottom:3px;'
                     f'border-bottom:1px solid #30363D;">{clean}</div>')
        elif "**" in line:
            txt = line
            while "**" in txt:
                s = txt.find("**"); e = txt.find("**", s+2)
                if e == -1: break
                txt = txt[:s] + f'<b style="color:{header_color};">' + txt[s+2:e] + '</b>' + txt[e+2:]
            rend += f'<div style="font-size:13px;line-height:1.7;padding:2px 0;">{txt}</div>'
        elif line.startswith(("•","–","–","-","▸")):
            rend += f'<div style="padding:4px 0 4px 10px;font-size:12.5px;border-bottom:1px solid rgba(255,255,255,.04);line-height:1.65;">{line}</div>'
        elif line.startswith(("⏰","📌","└─","- ","→")):
            rend += f'<div style="font-size:12.5px;padding:3px 0 3px 16px;line-height:1.6;color:#C5CDD6;">{line}</div>'
        else:
            rend += f'<div style="font-size:13px;line-height:1.7;padding:2px 0;">{line}</div>'
    return rend

# ══════════════════════════════════════════════════════════════════════════════
# AUTO-REFRESH
# ══════════════════════════════════════════════════════════════════════════════
refresh_count = st_autorefresh(interval=AUTOREFRESH_INTERVAL * 1000, key="auto_refresh_main")
if refresh_count > 0:
    last_count = st.session_state.get("_last_refresh_count", -1)
    if refresh_count != last_count:
        st.session_state.last_autorefresh = time.time()
        st.session_state._last_refresh_count = refresh_count

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<div style="font-family:Barlow Condensed;font-size:22px;font-weight:800;color:#EFA500;padding:8px 0 2px 0;letter-spacing:1px;">⚡ QUANT TERMINAL</div>'
        '<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;padding-bottom:10px;border-bottom:1px solid #30363D;">v10.0 · AI Enhanced Edition</div>',
        unsafe_allow_html=True
    )
    elapsed   = time.time() - st.session_state.last_autorefresh
    remaining = max(0, AUTOREFRESH_INTERVAL - int(elapsed))
    pct       = min(100, int((elapsed / AUTOREFRESH_INTERVAL) * 100))
    st.markdown(
        f'<div style="margin:10px 0 6px 0;font-family:JetBrains Mono;font-size:10px;color:#A8B3BD;">'
        f'<span class="live-dot"></span>UI REFRESH: <span style="color:#EFA500;">{remaining}s</span> '
        f'<span style="color:#3FB950;">#{refresh_count}</span><br>'
        f'<div style="background:#30363D;height:3px;margin-top:5px;border-radius:2px;overflow:hidden;">'
        f'<div style="background:#EFA500;height:100%;width:{pct}%;transition:width .5s linear;"></div></div></div>',
        unsafe_allow_html=True
    )

    st.markdown("---")

    cfg = load_config() if 'groq_keys' not in st.session_state else {}
    groq_keys         = st.session_state.get('groq_keys', [])
    gamma_instruments = st.session_state.get('gamma_instruments', [])
    sofr_rate         = float(st.session_state.get('sofr_val', 4.305))
    effr_rate         = float(st.session_state.get('effr_val', 4.330))
    rrp_value         = float(st.session_state.get('rrp_val', 485.2))
    main_t            = st.session_state.get('main_t_val', '')
    client            = get_groq_client()

    btn_ai = st.button("🤖 AI MACRO", use_container_width=True, key="sb_ai_macro")
    if st.button("🔄 REFRESH DADOS", use_container_width=True, key="sb_refresh"):
        fetch_fj_data.clear()
        fetch_finviz_futures.clear()
        fetch_finviz_bubbles.clear()
        fetch_earnings_week.clear()
        fetch_market_context.clear()
        st.session_state.ticker_store = {}
        st.session_state.last_news_fetch = 0
        st.rerun()

    st.markdown("---")

    # Fetch data upfront
    news_titles = fetch_news_background()
    if st.session_state.get('translate_news', True) and client and news_titles:
        translate_news_batch(st.session_state.news_history[:30])

    tb_symbols = [s.strip() for s in st.session_state.get('ticker_bar_symbols','^GSPC,^IXIC,^DJI,^VIX,CL=F,BZ=F,DX-Y.NYB,GC=F').split(',') if s.strip()]
    tb_data = get_cached_tickers(tb_symbols)

    fj_orderflow, fj_calendar, fj_alerts = get_fj_cached_data()
    st.session_state.fj_last_fetch = time.time()

    hvl_alerts = check_hvl_alerts(gamma_instruments, st.session_state.ticker_store)

    # AI controls in sidebar
    st.markdown('<div style="font-size:11px;color:#A8B3BD;font-family:JetBrains Mono;font-weight:600;">ANÁLISES AI</div>', unsafe_allow_html=True)
    if st.button("🌐 Inter-Market AI", use_container_width=True, key="sb_intermarket"):
        st.session_state.intermarket_ai_cache = ""
    if st.button("🛡️ Risk Scanner AI", use_container_width=True, key="sb_riskscan"):
        st.session_state.risk_scan_cache = ""
    if st.button("📊 Sentimento News", use_container_width=True, key="sb_sentiment"):
        st.session_state.news_sentiment_cache = ""

    st.markdown("---")

    # Translate toggle
    st.session_state.translate_news = st.checkbox(
        "📰 Traduzir notícias", value=st.session_state.get('translate_news', True), key="sb_translate"
    )

    # Active keys indicator
    valid_keys = [k for k in groq_keys if k.strip()]
    col_k = "#3FB950" if valid_keys else "#F85149"
    msg_k = f"✅ {len(valid_keys)} key(s) ativa(s)" if valid_keys else "⚠️ Sem API Key"
    st.markdown(f'<div style="background:{"#0D1F14" if valid_keys else "#1F0D0D"};border-left:3px solid {col_k};padding:6px 10px;font-size:11px;font-family:JetBrains Mono;color:{col_k};margin-top:4px;">{msg_k} · {get_ai_model()[:20]}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN HEADER
# ══════════════════════════════════════════════════════════════════════════════
now_dt = datetime.now()
st.markdown(
    f'<div class="main-header">'
    f'<div><div class="main-title">⚡ QUANT TERMINAL v10</div>'
    f'<div class="main-date">{now_dt.strftime("%A, %d de %B de %Y · %H:%M:%S BRT").upper()} · AI ENHANCED</div></div>'
    f'<div style="text-align:right;font-family:JetBrains Mono;font-size:10px;color:#A8B3BD;">'
    f'<div><span class="live-dot"></span>LIVE DATA</div>'
    f'<div style="color:#EFA500;font-weight:700;">Financial Juice · Finviz · SavvyTrader</div></div>'
    f'</div>', unsafe_allow_html=True
)

# ── TICKER BAR ─────────────────────────────────────────────────────────────────
_tlabels = {
    "GSPC":"S&P 500","IXIC":"NASDAQ","DJI":"DOW JONES","VIX":"VIX",
    "CL":"WTI OIL","BZ":"BRENT","DXYNOB":"DXY","GC":"OURO","ES":"ES FUT","NQ":"NQ FUT",
}
ticker_html = '<div class="ticker-bar">'
for a in tb_data:
    col  = "#3FB950" if a['c'] >= 0 else "#F85149"
    sign = "+" if a['c'] >= 0 else ""
    name = _tlabels.get(a['n'].replace("-","").replace(".",""), a['n'])
    p_fmt = f"{a['p']:,.2f}" if a['p'] > 1 else f"{a['p']:.4f}"
    ticker_html += f'<div class="tc"><div class="tl">{name}</div><div class="tp">{p_fmt}</div><div class="tv" style="color:{col};">{sign}{a["c"]:.2f}%</div></div>'
ticker_html += '</div>'
st.markdown(ticker_html, unsafe_allow_html=True)

if fj_alerts:
    render_orderflow_alerts(fj_alerts)
if hvl_alerts:
    for alert in hvl_alerts:
        ac = "#3FB950" if "ACIMA" in alert['direction'] else "#F85149"
        bg = "#071510" if "ACIMA" in alert['direction'] else "#150707"
        st.markdown(f'<div class="alert-hvl" style="background:{bg};border:2px solid {ac};border-left:6px solid {ac};padding:10px 16px;margin-bottom:6px;"><span style="font-family:Barlow Condensed;font-size:20px;font-weight:800;color:{ac};">🚨 ALERTA HVL — {alert["label"]} CRUZOU {alert["direction"]}</span><span style="font-family:JetBrains Mono;font-size:11px;color:var(--text);margin-left:16px;">Spot {alert["spot"]:,.2f} | HVL {alert["hvl"]:,.2f} ({alert["diff"]:+.1f}pts) | Regime → {alert["regime"]} | {alert["time"]} BRT</span></div>', unsafe_allow_html=True)

if news_titles:
    translated_ticker = [get_translated_title(t) for t in news_titles[:10]]
    st.markdown(f'<div class="news-ticker">📡 LIVE: {" · ".join(translated_ticker)}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TABS
# ══════════════════════════════════════════════════════════════════════════════
tab1, tab_of, tab2, tab3, tab4, tab_earn, tab_im, tab5, tab_cfg = st.tabs([
    "📊 MACRO & AI",
    "🏦 ORDER FLOW",
    "🌍 MERCADOS GLOBAIS",
    "📈 GAMMA & ESTRUTURA",
    "📅 CALENDÁRIO LIVE",
    "💰 EARNINGS",
    "🌐 INTER-MARKET",
    "📰 NEWS FEED",
    "⚙️ CONFIGURAÇÕES",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — MACRO & AI (ENHANCED v10)
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    col_main, col_side = st.columns([1.65, 1])

    with col_main:
        st.markdown('<div class="sh">🤖 ANÁLISE MACRO AI — SENTIMENTO INSTITUCIONAL PROFUNDO</div>', unsafe_allow_html=True)

        should_run_ai = should_run_macro_ai(btn_ai)

        if should_run_ai and client and news_titles:
            with st.spinner("Processando análise macro profunda..."):
                # Build rich market context
                mkt_ctx = fetch_market_context()
                vix_val      = mkt_ctx.get('vix', 0)
                vix_chg      = mkt_ctx.get('vix_chg', 0)
                yield_10y    = mkt_ctx.get('yield_10y', 0)
                yield_10y_chg= mkt_ctx.get('yield_10y_chg', 0)
                yield_2y     = mkt_ctx.get('yield_2y', 0)
                dxy          = mkt_ctx.get('dxy', 0)
                dxy_chg      = mkt_ctx.get('dxy_chg', 0)
                gold         = mkt_ctx.get('gold', 0)
                gold_chg_pct = mkt_ctx.get('gold_chg_pct', 0)
                oil          = mkt_ctx.get('oil', 0)
                oil_chg_pct  = mkt_ctx.get('oil_chg_pct', 0)
                spy_5d       = mkt_ctx.get('spy_5d_ret', 0)

                vix_regime = ("BAIXO (<15 — complacência)") if vix_val < 15 else ("MODERADO (15-25)") if vix_val < 25 else ("ALTO (25-35 — medo institucional)") if vix_val < 35 else ("EXTREMO (>35 — crise/capitulação)")
                yield_curve = yield_10y - yield_2y if yield_10y and yield_2y else None
                curve_str   = f"INVERTIDA ({yield_curve:.2f}%)" if yield_curve and yield_curve < 0 else (f"NORMAL ({yield_curve:.2f}%)" if yield_curve else "N/A")

                gamma_ctx = ""
                for inst in gamma_instruments[:4]:
                    lvs = _parse_levels(inst.get('levels',''))
                    spot_d = st.session_state.ticker_store.get(inst.get('ticker',''), {})
                    spot_price = spot_d.get('p', 0)
                    regime_str = "ACIMA do HVL (Positivo)" if spot_price >= lvs.get('HVL',0) and lvs.get('HVL',0) else "ABAIXO do HVL (Negativo)" if lvs.get('HVL',0) else "N/A"
                    gamma_ctx += (f"\n  {inst['label']}: HVL={lvs.get('HVL',0):,.0f}, CW={lvs.get('CW',0):,.0f}, PW={lvs.get('PW',0):,.0f}, GEX=${inst.get('gex',0):+.3f}Bn, Spot={spot_price:,.2f} → {regime_str}")

                of_ctx = ""
                if fj_orderflow.get("indices"):
                    of_ctx = "\n\nORDER FLOW INSTITUCIONAL (Financial Juice):"
                    for idx in fj_orderflow["indices"][:4]:
                        imb_label = "COMPRA DOMINANTE" if idx['moo_total'] > 0 else "VENDA DOMINANTE"
                        of_ctx += (f"\n  {idx['name']}: MOO={_format_money(idx['moo_total'])} ({imb_label}), "
                                   f"MOC={_format_money(idx['moc_total'])}, Buys={_format_money(idx['moo_buys'])}, Sells={_format_money(idx['moo_sells'])}")

                snap_tickers = get_cached_tickers(["AAPL","MSFT","NVDA","META","AMZN","TSLA","GOOGL"])
                snap_str = " | ".join([f"{t['n']}: {t['p']:.1f} ({'+' if t['c']>=0 else ''}{t['c']:.1f}%)" for t in snap_tickers])

                prompt = f"""Você é o Head of Macro Research de um hedge fund multibillionário estilo Bridgewater/Citadel. Hoje: {datetime.now().strftime('%d/%b/%Y %H:%M BRT')}.

═══════════════════════════════════════════════
CONTEXTO DE MERCADO COMPLETO
═══════════════════════════════════════════════

VOLATILIDADE:
  VIX: {vix_val:.2f} ({'+' if vix_chg>=0 else ''}{vix_chg:.2f} pts) → Regime: {vix_regime}

TAXA DE JUROS & CURVA:
  10Y Yield: {yield_10y:.3f}% ({'+' if yield_10y_chg>=0 else ''}{yield_10y_chg:.3f}%)
  Curva 10Y-2Y: {curve_str}
  SOFR: {sofr_rate:.3f}% | EFFR: {effr_rate:.3f}% | RRP: ${rrp_value:.1f}Bn

CÂMBIO & COMMODITIES:
  DXY: {dxy:.2f} ({'+' if dxy_chg>=0 else ''}{dxy_chg:.2f})
  Ouro: ${gold:.1f} ({'+' if gold_chg_pct>=0 else ''}{gold_chg_pct:.2f}%)
  WTI: ${oil:.2f} ({'+' if oil_chg_pct>=0 else ''}{oil_chg_pct:.2f}%)
  SPY retorno 5 dias: {'+' if spy_5d>=0 else ''}{spy_5d:.2f}%

MAG 7 SNAPSHOT: {snap_str}

GAMMA STRUCTURE:{gamma_ctx if gamma_ctx else " Não configurado."}
{of_ctx}

NOTÍCIAS CRÍTICAS (últimas):
{chr(10).join(f'  [{i+1}] {n}' for i, n in enumerate(news_titles[:18]))}

ATIVO PRINCIPAL CONFIGURADO: {main_t if main_t else "Nenhum"}

═══════════════════════════════════════════════
ANÁLISE REQUERIDA
═══════════════════════════════════════════════

Produza análise institucional PROFUNDA em 6 seções. Seja específico com números. Evite generalidades.

**1. REGIME MACRO ATUAL**
Classifique o regime atual: Risk-On/Off? Qual tipo exato (reflexão/recuperação/recessão/expansão)? Conecte VIX ({vix_val:.1f}), curva ({curve_str}), DXY ({dxy:.2f}) e liquidez (RRP ${rrp_value:.1f}Bn) em argumento coeso. Máx 4 linhas.

**2. NARRATIVA DOMINANTE**
Qual é A narrativa que está movendo o mercado esta semana? Qual força entre Fed/crescimento/geopolítica/corporativa está no comando? Cite 2-3 notícias específicas da lista que confirmam. Máx 3 linhas.

**3. ESTRUTURA DE GAMMA & ORDER FLOW**
{'Analise posicionamento dos dealers nos HVL configurados. ' if gamma_ctx else 'Gamma não configurado — '}{'Integre com imbalance MOO/MOC: quem está comprando e quem está vendendo em bloco. Qual índice mostra divergência?' if of_ctx else 'Sem dados de Order Flow.'}

**4. INTER-MARKET SIGNALS**
Correlações que importam HOJE: Bonds vs Equities (convergindo ou divergindo?), DXY vs Risk Assets, Gold como sinal de estresse? Identifique 1 divergência suspeita que o mercado pode estar ignorando.

**5. ATIVO FOCO: {main_t if main_t else "N/A — configure na sidebar"}**
{'Viés direcional CLARO com suporte/resistência concretos. Qual catalão intraday pode mudar o viés? Onde invalidar a tese.' if main_t else 'Configure um ativo principal na aba CONFIGURAÇÕES para análise focada.'}

**6. VEREDICTO OPERACIONAL**
Resumo em 2 frases: (a) qual o maior risco não precificado hoje, (b) ação concreta para o pregão de amanhã.

Tom: Head of Research institucional. Direto, com dados. Português pt-BR. Máx 520 palavras."""

                res = call_groq_with_fallback(
                    messages=[{"role":"user","content":prompt}],
                    max_tokens=1100, temperature=0.35
                )
                if not res.startswith("⚠️"):
                    st.session_state.macro_ai_cache = res
                    st.session_state.last_ai_run  = time.time()
                    st.session_state.last_ai_auto = time.time()
                else:
                    st.session_state.macro_ai_cache = res

        elif should_run_ai and not client:
            st.session_state.macro_ai_cache = "⚠️ Configure a GROQ API Key na aba CONFIGURAÇÕES."

        if st.session_state.macro_ai_cache:
            rend = render_ai_text(st.session_state.macro_ai_cache)
            ai_age_s = int(time.time() - st.session_state.last_ai_run)
            next_ai  = max(0, AI_REFRESH_INTERVAL - int(time.time() - st.session_state.last_ai_auto))
            st.markdown(
                f'<div class="ai-box">{rend}'
                f'<div style="margin-top:10px;padding-top:8px;border-top:1px solid #30363D;font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;">'
                f'Gerado há {ai_age_s}s · Auto-refresh em {next_ai//60}min · {get_ai_model()}</div></div>',
                unsafe_allow_html=True
            )
        else:
            st.markdown('<div class="empty-state"><div class="empty-title">🤖 Análise AI Macro</div><div class="empty-sub">Clique "AI MACRO" na sidebar.<br>Requer GROQ Key + RSS feeds configurados.</div></div>', unsafe_allow_html=True)

        # SENTIMENTO NEWS (v10 new)
        st.markdown('<div class="sh">📊 SENTIMENTO DE MERCADO — ANÁLISE AI DAS NOTÍCIAS</div>', unsafe_allow_html=True)
        run_sent = should_run_news_sentiment(False)
        if run_sent and client and news_titles:
            with st.spinner("Analisando sentimento das notícias..."):
                sent_prompt = f"""Analise as notícias abaixo e retorne APENAS JSON válido:

NOTÍCIAS:
{chr(10).join(f'- {n}' for n in news_titles[:20])}

Retorne APENAS este JSON (sem texto adicional):
{{"score": <-10 a 10>, "label": "MUITO BEARISH|BEARISH|NEUTRO|BULLISH|MUITO BULLISH", "dominante": "<tema principal em 5 palavras>", "alertas": ["<alerta 1>","<alerta 2>"], "oportunidade": "<oportunidade em 8 palavras>"}}

score: -10=pânico extremo, 0=neutro, +10=euforia máxima"""

                sent_res = call_groq_with_fallback([{"role":"user","content":sent_prompt}], max_tokens=300, temperature=0.2, max_attempts=3)
                if not sent_res.startswith("⚠️"):
                    try:
                        s = sent_res.find('{'); e = sent_res.rfind('}') + 1
                        if s >= 0 and e > s:
                            st.session_state.news_sentiment_cache = sent_res[s:e]
                            st.session_state.last_news_sentiment = time.time()
                    except:
                        pass

        if st.session_state.get('news_sentiment_cache'):
            try:
                sent_data = json.loads(st.session_state.news_sentiment_cache)
                score     = sent_data.get('score', 0)
                label     = sent_data.get('label', 'NEUTRO')
                dominante = sent_data.get('dominante', '')
                alertas   = sent_data.get('alertas', [])
                oportun   = sent_data.get('oportunidade', '')

                score_pct = (score + 10) / 20 * 100
                score_color = "#3FB950" if score > 2 else ("#F85149" if score < -2 else "#F0B429")
                label_class = "bp" if score > 2 else ("bn" if score < -2 else "bnt")

                st.markdown(
                    f'<div style="background:var(--bg2);border:1px solid var(--border);padding:12px 16px;border-radius:4px;">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">'
                    f'<span class="badge {label_class}" style="font-size:13px;padding:4px 14px;">{label}</span>'
                    f'<span style="font-family:Barlow Condensed;font-size:24px;font-weight:800;color:{score_color};">{score:+.1f}/10</span>'
                    f'</div>'
                    f'<div style="height:16px;border-radius:4px;background:linear-gradient(90deg,#F85149 0%,#F0B429 50%,#3FB950 100%);margin:8px 0;position:relative;">'
                    f'<div style="position:absolute;top:0;left:{score_pct:.1f}%;width:4px;height:100%;background:#fff;transform:translateX(-50%);border-radius:2px;box-shadow:0 0 6px rgba(255,255,255,.9);"></div>'
                    f'</div>'
                    f'<div style="font-size:11px;color:#A8B3BD;font-family:JetBrains Mono;display:flex;justify-content:space-between;margin-bottom:10px;"><span>BEARISH</span><span>NEUTRO</span><span>BULLISH</span></div>'
                    f'{"<div style=\"font-size:12px;color:#EFA500;font-family:JetBrains Mono;margin-bottom:6px;\">🎯 Tema: " + dominante + "</div>" if dominante else ""}'
                    f'{"".join([f"<div class=\"risk-card med\" style=\"padding:6px 10px;margin:3px 0;\"><span style=\"font-size:11.5px;\">⚠️ {a}</span></div>" for a in alertas[:3]])}'
                    f'{"<div style=\"font-size:12px;color:#3FB950;margin-top:8px;padding:6px 10px;background:#071510;border-left:3px solid #3FB950;\">💡 " + oportun + "</div>" if oportun else ""}'
                    f'</div>',
                    unsafe_allow_html=True
                )
            except:
                pass

        # FATORES BULL/BEAR
        if client and news_titles and st.session_state.macro_ai_cache:
            st.markdown('<div class="sh">⚖️ FATORES DO PREGÃO — BULL vs BEAR</div>', unsafe_allow_html=True)
            run_factors = should_run_factors(btn_ai)
            if run_factors:
                mkt_ctx2 = fetch_market_context()
                vix2  = mkt_ctx2.get('vix', 0)
                spy5d = mkt_ctx2.get('spy_5d_ret', 0)
                p2 = f"""Analista quant de hedge fund. Analise e retorne APENAS JSON válido.

CONTEXTO: SOFR:{sofr_rate}% | RRP:${rrp_value}Bn | VIX:{vix2:.1f} | SPY 5d:{spy5d:+.2f}%
NOTÍCIAS: {news_titles[:15]}

JSON (sem texto extra):
{{"positivos":["fator concreto 1 com dado","fator 2","fator 3","fator 4"],"riscos":["risco específico 1","risco 2","risco 3","risco 4"],"vies":"COMPRA|VENDA|NEUTRO","confianca":"ALTA|MÉDIA|BAIXA","prazo":"INTRADAY|SWING|SEMANAL"}}"""
                r2 = call_groq_with_fallback([{"role":"user","content":p2}], max_tokens=450, temperature=0.3)
                if not r2.startswith("⚠️"):
                    if "```" in r2:
                        for part in r2.split("```"):
                            if "{" in part:
                                r2 = part.replace("json","").strip(); break
                    s = r2.find('{'); e = r2.rfind('}') + 1
                    if s >= 0 and e > s:
                        st.session_state.factors_cache    = r2[s:e]
                        st.session_state.last_factors_run = time.time()

            if st.session_state.factors_cache:
                try:
                    factors = json.loads(st.session_state.factors_cache)
                    pos    = factors.get("positivos",[])
                    neg    = factors.get("riscos",[])
                    vies   = factors.get("vies","NEUTRO")
                    conf   = factors.get("confianca","MÉDIA")
                    prazo  = factors.get("prazo","INTRADAY")
                    vc     = "#3FB950" if vies=="COMPRA" else ("#F85149" if vies=="VENDA" else "#EFA500")
                    st.markdown(
                        f'<div style="background:var(--bg2);border:1px solid var(--border);padding:8px 14px;margin-bottom:6px;display:flex;gap:16px;align-items:center;">'
                        f'<span style="font-family:Barlow Condensed;font-size:11px;color:#A8B3BD;">VIÉS AI:</span>'
                        f'<span style="font-family:Barlow Condensed;font-size:20px;font-weight:800;color:{vc};">{vies}</span>'
                        f'<span style="font-family:JetBrains Mono;font-size:10px;color:#A8B3BD;">Confiança: <b style="color:#fff;">{conf}</b></span>'
                        f'<span style="font-family:JetBrains Mono;font-size:10px;color:#A8B3BD;">Prazo: <b style="color:#58A6FF;">{prazo}</b></span>'
                        f'</div>', unsafe_allow_html=True
                    )
                    fg  = '<div class="fg">'
                    fg += '<div class="fpos"><div class="ftit" style="color:#3FB950;">✅ POSITIVOS</div>'
                    for p in pos: fg += f'<div class="fi">{p}</div>'
                    fg += '</div>'
                    fg += '<div class="fneg"><div class="ftit" style="color:#F85149;">⚠️ RISCOS</div>'
                    for r in neg: fg += f'<div class="fi">{r}</div>'
                    fg += '</div></div>'
                    st.markdown(fg, unsafe_allow_html=True)
                except:
                    pass

        # HVL HISTORY
        if st.session_state.hvl_alert_history:
            with st.expander(f"🚨 Histórico de Alertas HVL ({len(st.session_state.hvl_alert_history)})", expanded=False):
                hist_html = '<div style="max-height:200px;overflow-y:auto;">'
                for ah in st.session_state.hvl_alert_history[:20]:
                    ac  = "#3FB950" if "ACIMA" in ah.get('direction','') else "#F85149"
                    age = int((time.time() - ah.get('ts', time.time())) / 60)
                    hist_html += (f'<div style="padding:5px 8px;border-bottom:1px solid #30363D;font-size:11px;font-family:JetBrains Mono;">'
                                  f'<span style="color:#A8B3BD;">[{ah.get("time","?")}]</span> '
                                  f'<span style="color:#EFA500;font-weight:700;">{ah.get("label","?")}</span> '
                                  f'<span style="color:{ac};font-weight:700;">{ah.get("direction","?")}</span> '
                                  f'HVL:{ah.get("hvl",0):,.2f} Spot:{ah.get("spot",0):,.2f} '
                                  f'<span style="color:#A8B3BD;">({age}min atrás)</span></div>')
                hist_html += '</div>'
                st.markdown(hist_html, unsafe_allow_html=True)

    with col_side:
        st.markdown('<div class="sh">📡 LIVE NEWS</div>', unsafe_allow_html=True)
        n_html = '<div class="scroll-box" style="max-height:40vh;">'
        for item in st.session_state.news_history[:40]:
            translated = get_translated_title(item['t'])
            n_html += (f'<div class="news-item"><span class="news-time">[{item["h"]}]</span><br>'
                       f'<a href="{item["l"]}" target="_blank" class="news-link" title="{item["t"]}">{translated}</a></div>')
        if not st.session_state.news_history:
            n_html += '<div style="color:#A8B3BD;padding:20px;font-size:12px;text-align:center;">Configure RSS feeds.</div>'
        n_html += '</div>'
        st.markdown(n_html, unsafe_allow_html=True)

        st.markdown('<div class="sh" style="margin-top:12px;">💧 SOFR / EFFR / RRP</div>', unsafe_allow_html=True)
        r1, r2, r3 = st.columns(3)
        spread = effr_rate - sofr_rate
        with r1:
            st.markdown(f'<div class="rate-box"><div class="rate-lbl">SOFR</div><div class="rate-val">{sofr_rate:.3f}%</div><div class="rate-sub">Overnight</div></div>', unsafe_allow_html=True)
        with r2:
            st.markdown(f'<div class="rate-box"><div class="rate-lbl">EFFR</div><div class="rate-val">{effr_rate:.3f}%</div><div class="rate-sub">Spr:{spread:+.3f}%</div></div>', unsafe_allow_html=True)
        with r3:
            st.markdown(f'<div class="rate-box"><div class="rate-lbl">RRP $Bn</div><div class="rate-val">{rrp_value:.1f}</div><div class="rate-sub">Overnight</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="sh" style="margin-top:12px;">🚀 MEGA CAPS SNAPSHOT</div>', unsafe_allow_html=True)
        snap_data = get_cached_tickers(["AAPL","MSFT","NVDA","META","AMZN","TSLA","GOOGL","AMD"])
        mv_html = '<table class="inst-table"><thead><tr><td>TICKER</td><td>PREÇO</td><td>VAR.%</td></tr></thead><tbody>'
        for m in snap_data:
            col  = "#3FB950" if m['c'] >= 0 else "#F85149"
            sign = "+" if m['c'] >= 0 else ""
            mv_html += f'<tr><td style="color:#EFA500;font-weight:700;font-family:Barlow Condensed;font-size:13px;">{m["n"]}</td><td style="color:#fff;">${m["p"]:.2f}</td><td style="color:{col};font-weight:700;">{sign}{m["c"]:.2f}%</td></tr>'
        mv_html += "</tbody></table>"
        st.markdown(mv_html, unsafe_allow_html=True)

        # RISK SCANNER (v10 new)
        st.markdown('<div class="sh" style="margin-top:12px;">🛡️ RISK SCANNER AI</div>', unsafe_allow_html=True)
        run_risk = should_run_risk_scan(False)
        if run_risk and client and news_titles:
            with st.spinner("Escaneando riscos..."):
                mkt_rs = fetch_market_context()
                risk_prompt = f"""Você é o Chief Risk Officer de um hedge fund. Identifique os TOP 4 RISCOS do pregão de hoje.

DADOS: VIX={mkt_rs.get('vix',0):.1f} | 10Y={mkt_rs.get('yield_10y',0):.3f}% | DXY={mkt_rs.get('dxy',0):.2f} | RRP=${rrp_value:.1f}Bn
NOTÍCIAS RECENTES: {news_titles[:12]}

Retorne APENAS JSON válido:
{{"riscos":[{{"id":1,"nivel":"ALTO|MÉDIO|BAIXO","titulo":"titulo curto","desc":"1 frase","ativo_impactado":"ex: S&P, BRL, Oil"}},{{"id":2,"nivel":"...","titulo":"...","desc":"...","ativo_impactado":"..."}},...4 riscos total],"risco_macro":"1 frase sobre risco sistêmico maior"}}"""

                rr = call_groq_with_fallback([{"role":"user","content":risk_prompt}], max_tokens=600, temperature=0.3, max_attempts=3)
                if not rr.startswith("⚠️"):
                    try:
                        s = rr.find('{'); e = rr.rfind('}') + 1
                        if s >= 0 and e > s:
                            st.session_state.risk_scan_cache = rr[s:e]
                            st.session_state.last_risk_scan  = time.time()
                    except:
                        pass

        if st.session_state.get('risk_scan_cache'):
            try:
                rdata = json.loads(st.session_state.risk_scan_cache)
                riscos = rdata.get('riscos', [])
                risco_macro = rdata.get('risco_macro', '')
                for r in riscos[:4]:
                    nivel = r.get('nivel', 'MÉDIO')
                    nivel_cls = "high" if nivel=="ALTO" else ("med" if nivel=="MÉDIO" else "low")
                    nivel_color = "#F85149" if nivel=="ALTO" else ("#F0B429" if nivel=="MÉDIO" else "#3FB950")
                    st.markdown(
                        f'<div class="risk-card {nivel_cls}">'
                        f'<div style="display:flex;justify-content:space-between;">'
                        f'<span style="font-family:Barlow Condensed;font-size:13px;font-weight:700;">{r.get("titulo","")}</span>'
                        f'<span class="badge" style="background:{"#150707" if nivel=="ALTO" else "#1A1208"};color:{nivel_color};border:1px solid {nivel_color};">{nivel}</span>'
                        f'</div>'
                        f'<div style="font-size:11.5px;color:#C5CDD6;margin-top:3px;">{r.get("desc","")}</div>'
                        f'<div style="font-size:10px;color:#58A6FF;font-family:JetBrains Mono;margin-top:3px;">Ativo: {r.get("ativo_impactado","")}</div>'
                        f'</div>', unsafe_allow_html=True)
                if risco_macro:
                    st.markdown(f'<div style="background:#1A1208;border:1px solid #EFA500;border-left:3px solid #EFA500;padding:8px 12px;font-size:11.5px;color:#EFA500;margin-top:6px;">⚠️ Macro: {risco_macro}</div>', unsafe_allow_html=True)
            except:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# TAB ORDER FLOW (ENHANCED v10)
# ══════════════════════════════════════════════════════════════════════════════
with tab_of:
    st.markdown('<div class="sh">🏦 ORDER FLOW — IMBALANCE INSTITUCIONAL MOO/MOC (Financial Juice · 60s)</div>', unsafe_allow_html=True)

    if not fj_orderflow or not fj_orderflow.get("indices"):
        st.markdown('<div class="empty-state"><div class="empty-title">📡 Order Flow indisponível</div><div class="empty-sub">A API do Financial Juice pode estar offline ou o token expirou.<br>Verifique o token na aba CONFIGURAÇÕES.</div></div>', unsafe_allow_html=True)
    else:
        is_moc        = fj_orderflow.get("is_moc", False)
        session_label = "🌅 MOC (After Close)" if is_moc else "☀️ MOO (Pre-Market)"
        last_age      = int(time.time() - st.session_state.fj_last_fetch) if st.session_state.fj_last_fetch else 0

        st.markdown(
            f'<div style="background:var(--bg2);border:1px solid var(--border);padding:8px 14px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-family:Barlow Condensed;font-size:14px;font-weight:700;color:#EFA500;">{session_label}</span>'
            f'<span style="font-family:JetBrains Mono;font-size:10px;color:#A8B3BD;"><span class="live-dot"></span>LIVE · Atualizado há {last_age}s · Próximo refresh: ~60s</span>'
            f'</div>', unsafe_allow_html=True)

        st.markdown('<div class="sh">🍩 VISÃO GERAL — DONUTS</div>', unsafe_allow_html=True)
        render_orderflow_donuts(fj_orderflow)

        st.markdown('<div class="sh">📊 CARDS DETALHADOS — POR ÍNDICE</div>', unsafe_allow_html=True)
        render_orderflow_cards(fj_orderflow, fj_alerts)

        st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
        render_top_tickers(fj_orderflow)

        st.markdown('<div style="margin-top:14px;"></div>', unsafe_allow_html=True)
        render_mag7_individual(fj_orderflow)

        # AI ORDER FLOW (ENHANCED v10)
        st.markdown('<div class="sh" style="margin-top:14px;">🤖 ANÁLISE AI — MICROESTRUTURA INSTITUCIONAL PROFUNDA</div>', unsafe_allow_html=True)

        of_ai_col1, of_ai_col2 = st.columns([1, 5])
        with of_ai_col1:
            run_of_ai = st.button("🔄 Atualizar", key="btn_of_ai_refresh", use_container_width=True)
        with of_ai_col2:
            if st.session_state.get('orderflow_ai_cache',''):
                age_min = int((time.time() - st.session_state.get('last_orderflow_ai',0)) / 60)
                st.markdown(f'<div style="font-size:10px;color:#3FB950;font-family:JetBrains Mono;padding:7px 0;">✓ Análise carregada · {age_min}min atrás</div>', unsafe_allow_html=True)

        if should_run_orderflow_ai(run_of_ai) and client:
            with st.spinner("Analisando microestrutura do order flow..."):
                mkt_of = fetch_market_context()
                idx_summary = []
                for idx in fj_orderflow["indices"][:4]:
                    imb = idx['moo_total']
                    ratio = abs(idx['moo_buys']/idx['moo_sells']) if idx['moo_sells'] != 0 else 0
                    dominance = "BUY SIDE" if imb > 0 else "SELL SIDE"
                    idx_summary.append(
                        f"  {idx['name']}: MOO Total={_format_money(imb)} ({dominance}, ratio B/S={ratio:.2f}) | "
                        f"MOC Total={_format_money(idx['moc_total'])}"
                    )

                top_buys_key  = "top_buy_moc"  if is_moc else "top_buy_moo"
                top_sells_key = "top_sell_moc" if is_moc else "top_sell_moo"
                top_buys  = ", ".join([f"{t['ticker'].strip()}({_format_money(t['value'])})" for t in fj_orderflow.get(top_buys_key,  [])[:5]])
                top_sells = ", ".join([f"{t['ticker'].strip()}({_format_money(t['value'])})" for t in fj_orderflow.get(top_sells_key, [])[:5]])

                mag7_data = fj_orderflow.get("mag7_moc",[]) if is_moc else fj_orderflow.get("mag7_moo",[])
                mag7_str  = " | ".join([f"{t['ticker'].strip()}:{_format_money(t['value'])}" for t in mag7_data[:7]])

                of_prompt = f"""Você é Head of Order Flow Analysis de um prime brokerage (Goldman/Morgan Stanley). Sessão: {session_label}.

DADOS COMPLETOS DE ORDER FLOW:
{chr(10).join(idx_summary)}

TOP 5 COMPRADORES: {top_buys if top_buys else "N/A"}
TOP 5 VENDEDORES:  {top_sells if top_sells else "N/A"}
MAG 7 IMBALANCE: {mag7_str if mag7_str else "N/A"}

CONTEXTO MACRO:
VIX={mkt_of.get('vix',0):.1f} | 10Y Yield={mkt_of.get('yield_10y',0):.3f}% | DXY={mkt_of.get('dxy',0):.2f}
ALERTAS: {len(fj_alerts)} → {", ".join([a["msg"][:60] for a in fj_alerts[:2]]) if fj_alerts else "Nenhum"}

Produza análise DE MICROESTRUTURA (máx 220 palavras):

**📊 LEITURA DE FLUXO**
Qual é a narrativa do fluxo? Acumulação silenciosa, distribuição, or repositionamento? Identifique se os compradores/vendedores são momentum ou contrários. Conecte com VIX e yield.

**🔬 DESTAQUES SETORIAIS**
4 bullets: quais tickers/segmentos mostram fluxo anormal? Aponte divergências entre MAG7 e índice amplo se existirem.

**⚡ INTERPRETAÇÃO PARA O PREGÃO**
O imbalance atual sugere pressão de abertura/fechamento? Qual índice deve liderar? Em qual direção?

**🎯 AÇÃO CONCRETA**
1 frase: posicionamento preferencial baseado no fluxo atual (não recomendação financeira).

Tom: prime brokerage. Português pt-BR."""

                of_res = call_groq_with_fallback([{"role":"user","content":of_prompt}], max_tokens=600, temperature=0.35)
                if not of_res.startswith("⚠️"):
                    st.session_state.orderflow_ai_cache = of_res
                    st.session_state.last_orderflow_ai = time.time()
                else:
                    st.session_state.orderflow_ai_cache = of_res

        if st.session_state.get('orderflow_ai_cache',''):
            rend = render_ai_text(st.session_state.orderflow_ai_cache, "ai-box-blue", "#58A6FF")
            st.markdown(f'<div class="ai-box-blue">{rend}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — MERCADOS GLOBAIS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="sh">⚡ FUTUROS LIVE — TODOS OS MERCADOS (Finviz · 60s)</div>', unsafe_allow_html=True)
    
    with st.spinner("Carregando futuros..."):
        all_futures = fetch_finviz_futures()
    
    if all_futures:
        organized = get_futures_by_category(all_futures)
        all_pct = [f["chgPct"] for cat in organized.values() for f in cat]
        if all_pct:
            avg_pct = sum(all_pct) / len(all_pct)
            ups   = sum(1 for p in all_pct if p > 0)
            downs = sum(1 for p in all_pct if p < 0)
            avg_color = "#3FB950" if avg_pct >= 0 else "#F85149"
            
            st.markdown(
                f'<div style="display:flex;gap:8px;margin-bottom:8px;">'
                f'<div style="background:var(--bg2);border:1px solid var(--border);padding:6px 10px;flex:1;text-align:center;">'
                f'<div style="font-size:9px;color:#A8B3BD;font-family:JetBrains Mono;">MÉDIA GLOBAL</div>'
                f'<div style="font-family:Barlow Condensed;font-size:18px;font-weight:800;color:{avg_color};">{avg_pct:+.2f}%</div>'
                f'</div>'
                f'<div style="background:#071510;border:1px solid #3FB950;padding:6px 10px;flex:1;text-align:center;">'
                f'<div style="font-size:9px;color:#A8B3BD;font-family:JetBrains Mono;">SUBINDO</div>'
                f'<div style="font-family:Barlow Condensed;font-size:18px;font-weight:800;color:#3FB950;">{ups}</div>'
                f'</div>'
                f'<div style="background:#150707;border:1px solid #F85149;padding:6px 10px;flex:1;text-align:center;">'
                f'<div style="font-size:9px;color:#A8B3BD;font-family:JetBrains Mono;">CAINDO</div>'
                f'<div style="font-family:Barlow Condensed;font-size:18px;font-weight:800;color:#F85149;">{downs}</div>'
                f'</div>'
                f'<div style="background:var(--bg3);border:1px solid var(--amber);padding:6px 10px;flex:1;text-align:center;">'
                f'<div style="font-size:9px;color:#A8B3BD;font-family:JetBrains Mono;">TOTAL</div>'
                f'<div style="font-family:Barlow Condensed;font-size:18px;font-weight:800;color:var(--amber);">{len(all_pct)}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        
        cat_list = list(organized.items())
        col_f1, col_f2 = st.columns(2)
        for i, (cat_name, futs) in enumerate(cat_list):
            target_col = col_f1 if i % 2 == 0 else col_f2
            with target_col:
                fut_html = f'<div class="fut-cat"><div class="fut-cat-name">{cat_name}</div><div class="fut-grid">'
                for f in futs:
                    pct = f["chgPct"]
                    if pct > 0.05:
                        cls = "up"; col = "#3FB950"; sign = "+"
                    elif pct < -0.05:
                        cls = "down"; col = "#F85149"; sign = ""
                    else:
                        cls = "flat"; col = "#A8B3BD"; sign = "+" if pct >= 0 else ""
                    price = f["last"]
                    if price >= 10000:
                        p_fmt = f"{price:,.0f}"
                    elif price >= 100:
                        p_fmt = f"{price:,.2f}"
                    else:
                        p_fmt = f"{price:.4f}"
                    fut_html += (
                        f'<div class="fut-item {cls}" title="{f["name"]} ({f["ticker"]}): {f["last"]} | Δ {f["change"]:+.2f}">'
                        f'<span class="fut-tk">{f["ticker"]}</span>'
                        f'<span class="fut-nm">{f["name"]}</span>'
                        f'<span class="fut-pr">{p_fmt}</span>'
                        f'<span class="fut-pc" style="color:{col};">{sign}{pct:.2f}%</span>'
                        f'</div>'
                    )
                fut_html += '</div></div>'
                st.markdown(fut_html, unsafe_allow_html=True)
    
    st.markdown("---")
    
    regions = {
        "🌎 AMÉRICAS": ["^GSPC","^IXIC","^DJI","^BVSP","^MXX","^GSPTSE"],
        "🌍 EUROPA":   ["^GDAXI","^FTSE","^FCHI","^STOXX50E","^IBEX","FTSEMIB.MI"],
        "🌏 ÁSIA":     ["^N225","^HSI","000300.SS","^NSEI","^KS11","^STI"],
    }
    reg_labels = {
        "GSPC":"S&P 500","IXIC":"NASDAQ","DJI":"DOW","BVSP":"IBOV","MXX":"IPC MX","GSPTSE":"TSX CA",
        "GDAXI":"DAX","FTSE":"FTSE100","FCHI":"CAC40","STOXX50E":"STOXX50","IBEX":"IBEX35","FTSEMIBMI":"MIB IT",
        "N225":"NIKKEI","HSI":"HANG SENG","000300SS":"CSI300","NSEI":"NIFTY50","KS11":"KOSPI","STI":"STI SG",
    }
    r_c1, r_c2 = st.columns(2)
    for i, (rname, syms) in enumerate(regions.items()):
        col = r_c1 if i % 2 == 0 else r_c2
        with col:
            st.markdown(f'<div class="sh">{rname}</div>', unsafe_allow_html=True)
            rdata  = get_cached_tickers(syms)
            g_html = '<div class="quant-grid" style="margin-bottom:8px;">'
            for a in rdata:
                color = "#3FB950" if a['c'] >= 0 else "#F85149"
                sign  = "+" if a['c'] >= 0 else ""
                lbl   = reg_labels.get(a['n'].replace(".","").replace("-",""), a['n'])
                p_fmt = f"{a['p']:,.0f}" if a['p']>1000 else f"{a['p']:,.2f}"
                g_html += (
                    f'<div class="quant-item">'
                    f'<span class="q-lbl">{lbl}</span>'
                    f'<span class="q-val" style="color:#fff;">{p_fmt}</span>'
                    f'<span class="q-chg" style="color:{color};">{sign}{a["c"]:.2f}%</span>'
                    f'</div>'
                )
            g_html += '</div>'
            st.markdown(g_html, unsafe_allow_html=True)

    st.markdown("---")
    col_fx, col_yd = st.columns(2)

    with col_fx:
        st.markdown('<div class="sh">💱 FOREX MAJORS</div>', unsafe_allow_html=True)
        fx_data  = get_cached_tickers(["EURUSD=X","USDJPY=X","GBPUSD=X","AUDUSD=X","USDCAD=X","USDCHF=X","NZDUSD=X","USDBRL=X"])
        fx_names = {
            "EURUSDX":"EUR/USD","USDJPYX":"USD/JPY","GBPUSDX":"GBP/USD","AUDUSDX":"AUD/USD",
            "USDCADX":"USD/CAD","USDCHFX":"USD/CHF","NZDUSDX":"NZD/USD","USDBRLX":"USD/BRL",
        }
        fx_html = """<table class="inst-table"><thead><tr>
          <td>PAR</td><td>PREÇO</td><td>VAR.%</td><td>SINAL</td>
        </tr></thead><tbody>"""
        for f in fx_data:
            col   = "#3FB950" if f['c'] >= 0 else "#F85149"
            sign  = "+" if f['c'] >= 0 else ""
            name  = fx_names.get(f['n'], f['n'])
            badge = '<span class="badge bp">ALTA</span>' if f['c']>=0 else '<span class="badge bn">QUEDA</span>'
            fx_html += f"""<tr>
              <td style="color:#EFA500;font-weight:700;">{name}</td>
              <td style="color:#fff;font-weight:700;">{f['p']:.5f}</td>
              <td style="color:{col};font-weight:700;">{sign}{f['c']:.2f}%</td>
              <td>{badge}</td>
            </tr>"""
        fx_html += "</tbody></table>"
        st.markdown(fx_html, unsafe_allow_html=True)

    with col_yd:
        st.markdown('<div class="sh">📉 CURVA DE JUROS EUA</div>', unsafe_allow_html=True)
        yd_data   = get_cached_tickers(["^IRX","^FVX","^TNX","^TYX"])
        yd_labels = {"IRX":"3M T-Bill","FVX":"5Y T-Note","TNX":"10Y T-Note","TYX":"30Y T-Bond"}
        yd_html = """<table class="inst-table"><thead><tr>
          <td>PRAZO</td><td>YIELD</td><td>VAR.</td><td>SINAL</td>
        </tr></thead><tbody>"""
        for y in yd_data:
            col   = "#3FB950" if y['c'] >= 0 else "#F85149"
            sign  = "+" if y['c'] >= 0 else ""
            lbl   = yd_labels.get(y['n'], y['n'])
            yv    = y['p'] / 10
            badge = '<span class="badge bn">SUBINDO ⚠️</span>' if y['c']>0 else '<span class="badge bp">CAINDO ✓</span>'
            yd_html += f"""<tr>
              <td style="color:#EFA500;font-weight:700;">{lbl}</td>
              <td style="color:#fff;font-weight:700;">{yv:.3f}%</td>
              <td style="color:{col};">{sign}{y['c']:.1f}bps</td>
              <td>{badge}</td>
            </tr>"""
        yd_html += "</tbody></table>"
        st.markdown(yd_html, unsafe_allow_html=True)

    st.markdown('<div class="sh">🛢️ COMMODITIES & METAIS</div>', unsafe_allow_html=True)
    comm_data   = get_cached_tickers(["CL=F","BZ=F","NG=F","GC=F","SI=F","HG=F","ZC=F","ZS=F"])
    comm_labels = {"CL":"WTI OIL","BZ":"BRENT","NG":"GÁS NAT.","GC":"OURO","SI":"PRATA","HG":"COBRE","ZC":"MILHO","ZS":"SOJA"}
    comm_html   = '<div class="quant-grid">'
    for c in comm_data:
        color = "#3FB950" if c['c'] >= 0 else "#F85149"
        sign  = "+" if c['c'] >= 0 else ""
        lbl   = comm_labels.get(c['n'], c['n'])
        comm_html += (
            f'<div class="quant-item">'
            f'<span class="q-lbl">{lbl}</span>'
            f'<span class="q-val" style="color:#fff;">{c["p"]:,.2f}</span>'
            f'<span class="q-chg" style="color:{color};">{sign}{c["c"]:.2f}%</span>'
            f'</div>'
        )
    comm_html += '</div>'
    st.markdown(comm_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — GAMMA & ESTRUTURA (ENHANCED v10)
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    if not gamma_instruments:
        st.markdown('<div class="empty-state"><div class="empty-title">📈 Nenhum instrumento configurado</div><div class="empty-sub">Adicione instrumentos Gamma na aba CONFIGURAÇÕES.<br>Informe HVL, Call Wall, Put Wall e GEX de fontes como MenthorQ.</div></div>', unsafe_allow_html=True)
    else:
        for idx, inst in enumerate(gamma_instruments):
            label  = inst.get('label','?')
            ticker = inst.get('ticker','?')
            levels = _parse_levels(inst.get('levels',''))
            gex    = float(inst.get('gex', 0))

            spot_data = get_full_ticker_live(ticker)
            spot      = spot_data.get('p', 0)
            spot_chg  = spot_data.get('c', 0)

            hvl = levels.get('HVL', 0)
            cw  = levels.get('CW', 0)
            pw  = levels.get('PW', 0)
            regime_pos = (spot >= hvl) if hvl and spot else True

            st.markdown(
                f'<div class="sh">{label} — {ticker}'
                f'<span style="margin-left:10px;font-size:11px;color:{"#3FB950" if gex>=0 else "#F85149"};">GEX: {gex:+.3f}Bn</span>'
                f'<span style="margin-left:12px;font-size:11px;color:{"#3FB950" if regime_pos else "#F85149"};">{"✅ REGIME POSITIVO" if regime_pos else "⚠️ REGIME NEGATIVO"}</span>'
                f'</div>', unsafe_allow_html=True
            )

            display_keys = [k for k in levels if levels[k] and levels[k] != 0]
            if display_keys:
                gl_html = '<div class="gamma-levels-wrap"><div class="gamma-levels">'
                for key in display_keys:
                    val   = levels[key]
                    info  = GAMMA_LEVEL_INFO.get(key, {})
                    css_c = info.get("class","")
                    color = info.get("color","#A8B3BD")
                    short = info.get("short", key)
                    rel   = ""
                    if spot and val:
                        diff = spot - val
                        if abs(diff) < (val * 0.003):
                            rel = f'<span class="gl-sub" style="color:#EFA500;font-weight:700;">≈ SPOT ({diff:+.1f})</span>'
                        elif diff > 0:
                            rel = f'<span class="gl-sub" style="color:#3FB950;">+{diff:.1f}pts acima</span>'
                        else:
                            rel = f'<span class="gl-sub" style="color:#F85149;">{diff:.1f}pts abaixo</span>'
                    gl_html += (f'<div class="gl-item {css_c}"><span class="gl-lbl" style="color:{color};">{key}</span>'
                                f'<span class="gl-val">{val:,.2f}</span>'
                                f'<span class="gl-sub" style="color:#A8B3BD;">{short}</span>{rel}</div>')
                if spot:
                    sc = "#3FB950" if spot_chg >= 0 else "#F85149"
                    ss = "+" if spot_chg >= 0 else ""
                    gl_html += (f'<div class="gl-item spot" style="border-left:2px solid #58A6FF;">'
                                f'<span class="gl-lbl" style="color:#58A6FF;">▶ SPOT ATUAL</span>'
                                f'<span class="gl-val" style="color:#58A6FF;">{spot:,.2f}</span>'
                                f'<span class="gl-sub" style="color:{sc};">{ss}{spot_chg:.2f}%</span>'
                                f'<span class="gl-sub">tempo real</span></div>')
                gl_html += '</div></div>'
                st.markdown(gl_html, unsafe_allow_html=True)

            if hvl and spot:
                dist_hvl = spot - hvl
                pct_hvl  = (dist_hvl / hvl * 100) if hvl else 0
                exp_min  = levels.get('1D Exp Min', 0)
                exp_max  = levels.get('1D Exp Max', 0)
                if regime_pos:
                    title   = "✅ REGIME POSITIVO — Dealers amortecendo o mercado"
                    detail  = (f"Spot <b style='color:#3FB950;'>{spot:,.2f}</b> está <b style='color:#3FB950;'>{dist_hvl:+.1f}pts ({pct_hvl:+.2f}%)</b> ACIMA do HVL ({hvl:,.2f}). "
                               f"Dealers <b>compram nas quedas</b> para hedge de delta, criando suporte orgânico. "
                               + (f"Call Wall {cw:,.2f} = resistência. " if cw else "")
                               + (f"Range esperado: {exp_min:,.2f}–{exp_max:,.2f}." if exp_min and exp_max else ""))
                    box_class = "regime-pos"
                else:
                    title   = "⚠️ REGIME NEGATIVO — Dealers amplificando movimentos"
                    detail  = (f"Spot <b style='color:#F85149;'>{spot:,.2f}</b> está <b style='color:#F85149;'>{dist_hvl:+.1f}pts ({pct_hvl:+.2f}%)</b> ABAIXO do HVL ({hvl:,.2f}). "
                               f"Dealers <b>vendem nas quedas e compram nos ralis</b> — amplificando movimentos. "
                               + (f"Put Wall {pw:,.2f} = suporte crítico. " if pw else "")
                               + "Retorno acima do HVL = estabilização do regime.")
                    box_class = "regime-neg"
                st.markdown(f'<div class="regime-box {box_class}"><div class="regime-title">{title}</div><div class="regime-desc">{detail}</div></div>', unsafe_allow_html=True)

            # AI GAMMA ANALYSIS (ENHANCED v10)
            cache_key = f"gamma_{label}_{ticker}"
            ai_col1, ai_col2 = st.columns([1, 5])
            with ai_col1:
                run_inst_ai = st.button(f"🤖 AI {label}", key=f"ai_btn_{idx}_{label}")
            with ai_col2:
                if cache_key in st.session_state.gamma_ai_cache:
                    ts_c  = st.session_state.gamma_ai_cache[cache_key].get('ts', 0)
                    age_m = int((time.time() - ts_c) / 60)
                    st.markdown(f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;padding:7px 0;">✓ Análise {label} — {age_m}min atrás</div>', unsafe_allow_html=True)

            if run_inst_ai and client:
                with st.spinner(f"Analisando estrutura gamma de {label}..."):
                    lvl_str = " | ".join([f"{k}:{v:,.2f}" for k, v in levels.items() if v])
                    mkt_gamma = fetch_market_context()
                    vix_g = mkt_gamma.get('vix', 0)
                    exp_range = (exp_max - exp_min) if (exp_min and exp_max) else 0
                    exp_mid   = (exp_max + exp_min) / 2 if (exp_min and exp_max) else 0

                    ai_p = f"""Você é Head of Options Strategy especializado em Gamma Exposure e dealer positioning. Hoje: {datetime.now().strftime('%d/%b/%Y %H:%M')}.

INSTRUMENTO: {label} ({ticker})
SPOT: {spot:,.2f} ({spot_chg:+.2f}%) | GEX: ${gex:+.3f}Bn {'→ POSITIVO (amortecido)' if gex>=0 else '→ NEGATIVO (amplificado)'}
VIX: {vix_g:.1f}
REGIME: Spot {'ACIMA' if regime_pos else 'ABAIXO'} do HVL {hvl:,.2f} ({dist_hvl:+.1f}pts)
NÍVEIS: {lvl_str}
RANGE ESPERADO: {exp_min:,.2f}–{exp_max:,.2f} (largura: {exp_range:.2f}pts, mid: {exp_mid:,.2f})

**1. REGIME DE DEALER POSITIONING**
Explique o que GEX ${gex:+.3f}Bn + posição vs HVL {hvl:,.2f} significa OPERACIONALMENTE. Como os dealers estão se hedgeando agora? Que tipo de pressão eles criam?

**2. ZONAS DE ATRAÇÃO E REPULSÃO**
Identifique os 2-3 níveis mais magnéticos hoje. Por que o mercado tende a ser atraído/repelido por cada nível?

**3. CENÁRIOS DIRECIONAIS**
• ALTA: Para {cw:,.0f} (CW) — o que precisa acontecer? Qual catalisador?
• BAIXA: Rompimento de {pw:,.0f} (PW) — o que acelera? Qual target?
• PIN RISK: Existe risco de fixar próximo de {exp_mid:,.0f} no fechamento?

**4. ESTRATÉGIA CONCRETA**
Entrada, nível de invalidade, alvo primário e secundário. Máx 3 linhas.

Português pt-BR. Institucional. Máx 350 palavras."""

                    r = call_groq_with_fallback([{"role":"user","content":ai_p}], max_tokens=700, temperature=0.35)
                    st.session_state.gamma_ai_cache[cache_key] = {"text":r,"ts":time.time()}

            if cache_key in st.session_state.gamma_ai_cache:
                ai_txt = st.session_state.gamma_ai_cache[cache_key].get("text","")
                rend   = render_ai_text(ai_txt, "ai-box-blue", "#58A6FF")
                st.markdown(f'<div class="ai-box-blue">{rend}</div>', unsafe_allow_html=True)

            st.markdown('<hr style="border:none;border-top:1px solid #30363D;margin:14px 0;">', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — CALENDÁRIO LIVE (ENHANCED v10)
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="sh">📅 CALENDÁRIO ECONÔMICO LIVE — DADOS REAIS (Financial Juice · 60s)</div>', unsafe_allow_html=True)
    if not fj_calendar:
        st.markdown('<div class="empty-state"><div class="empty-title">📡 Sem eventos relevantes hoje</div><div class="empty-sub">Nenhum evento de impacto médio/alto nos países G7+China para hoje.</div></div>', unsafe_allow_html=True)
    else:
        render_calendar_summary_cards(fj_calendar)
        render_calendar_live(fj_calendar)
        render_calendar_legend()

        st.markdown('<div class="sh" style="margin-top:14px;">🤖 ANÁLISE AI — PLAYBOOK POR EVENTO (v10 Enhanced)</div>', unsafe_allow_html=True)
        cal_ai_col1, cal_ai_col2 = st.columns([1, 5])
        with cal_ai_col1:
            run_cal_ai = st.button("🔄 Atualizar", key="btn_cal_ai_refresh", use_container_width=True)
        with cal_ai_col2:
            if st.session_state.get('calendar_ai_cache',''):
                age_min = int((time.time() - st.session_state.get('last_calendar_ai',0)) / 60)
                st.markdown(f'<div style="font-size:10px;color:#3FB950;font-family:JetBrains Mono;padding:7px 0;">✓ Análise carregada · {age_min}min atrás</div>', unsafe_allow_html=True)

        if should_run_calendar_ai(run_cal_ai) and client:
            with st.spinner("Construindo playbook de eventos..."):
                events_text = []
                high_impact = []
                for ev in fj_calendar:
                    imp_str = "★★★ ALTO" if ev["impact"]==3 else ("★★ MÉDIO" if ev["impact"]==2 else "★ BAIXO")
                    actual_str = f" | ATUAL: {ev['actual']}" if ev['actual'] != "-" else ""
                    speaker_str = f" ({ev['speaker']})" if ev.get('speaker') else ""
                    ev_line = (f"• {ev['time']} BRT | {ev['country_name']} | {imp_str} | "
                               f"{ev['title']}{speaker_str} | Forecast: {ev['forecast']} · Previous: {ev['previous']}{actual_str}")
                    events_text.append(ev_line)
                    if ev["impact"] == 3:
                        high_impact.append(ev)

                mkt_cal = fetch_market_context()
                cal_prompt = f"""Você é Head of Macro Strategy de um macro hedge fund. Hoje: {date.today().strftime('%d/%m/%Y')}.

CALENDÁRIO ECONÔMICO COMPLETO DE HOJE:
{chr(10).join(events_text)}

CONTEXTO MACRO:
SOFR: {sofr_rate:.3f}% | EFFR: {effr_rate:.3f}% | RRP: ${rrp_value:.1f}Bn
VIX: {mkt_cal.get('vix',0):.1f} | 10Y Yield: {mkt_cal.get('yield_10y',0):.3f}% | DXY: {mkt_cal.get('dxy',0):.2f}
Gold: ${mkt_cal.get('gold',0):.0f} | WTI: ${mkt_cal.get('oil',0):.2f}

Produza um PLAYBOOK completo:

**🎯 EVENTO CRÍTICO DO DIA**
Em 2 frases: qual é O evento mais market-moving de hoje, por que e em qual janela de tempo opera.

**📋 PLAYBOOK POR EVENTO ALTO IMPACTO**
Para CADA evento ★★★ na lista, produza:
⏰ [HORA] EVENTO
• Consenso/Forecast vs Previous: o que o mercado espera
• Cenário BEAT (acima do forecast): impacto esperado em S&P, DXY, Yields, Gold
• Cenário MISS (abaixo do forecast): impacto esperado nos mesmos ativos
• Trade setup: como posicionar ANTES e como reação se trigger atingido

**📊 MATRIZ DE IMPACTO**
| Ativo | Direção Base | Trigger de Mudança |
(S&P 500, DXY, 10Y Yield, Ouro, BRL se relevante)

**⚡ POSICIONAMENTO PRÉ-EVENTO**
1 parágrafo: onde estar ANTES dos eventos críticos. Hedge recomendado.

REGRAS: Use APENAS eventos da lista. Máx 450 palavras. Português pt-BR institucional."""

                cal_res = call_groq_with_fallback([{"role":"user","content":cal_prompt}], max_tokens=900, temperature=0.35)
                if not cal_res.startswith("⚠️"):
                    st.session_state.calendar_ai_cache = cal_res
                    st.session_state.last_calendar_ai = time.time()
                else:
                    st.session_state.calendar_ai_cache = cal_res

        if st.session_state.get('calendar_ai_cache',''):
            rend = render_ai_text(st.session_state.calendar_ai_cache, "ai-box", "#EFA500")
            st.markdown(f'<div class="ai-box">{rend}</div>', unsafe_allow_html=True)

        st.markdown('<div class="sh" style="margin-top:14px;">📝 NOTAS DO DIA</div>', unsafe_allow_html=True)
        notes_key = f"cal_notes_{datetime.now().strftime('%Y%m%d')}"
        if notes_key not in st.session_state:
            st.session_state[notes_key] = ""
        cal_notes = st.text_area("Notas", value=st.session_state[notes_key], height=120,
                                  key="cal_notes_input", label_visibility="collapsed",
                                  placeholder="Ex: NFP veio acima do esperado...")
        st.session_state[notes_key] = cal_notes


# ══════════════════════════════════════════════════════════════════════════════
# TAB EARNINGS
# ══════════════════════════════════════════════════════════════════════════════
with tab_earn:
    earn_c1, earn_c2 = st.columns([1.4, 1])

    with earn_c1:
        st.markdown('<div class="sh">🗺️ S&P 500 BUBBLE MAP — DADOS LIVE (Finviz)</div>', unsafe_allow_html=True)
        render_finviz_bubbles()

    with earn_c2:
        monday, friday = _get_week_range()
        st.markdown(
            f'<div class="sh">💰 EARNINGS — {monday.strftime("%d/%m")} a {friday.strftime("%d/%m/%Y")}'
            f'{"  (PRÓXIMA SEMANA)" if date.today().weekday() > 4 else ""}</div>',
            unsafe_allow_html=True)

        f_c1, f_c2 = st.columns([1, 1])
        with f_c1:
            filter_mode = st.selectbox("Filtro", ["Importantes (>$5B)","Médias (>$1B)","TODAS as empresas"],
                                       key="earn_filter_mode", label_visibility="collapsed")
        with f_c2:
            show_only_today = st.checkbox("📅 Só hoje", key="earn_only_today", value=False)

        if filter_mode == "TODAS as empresas":
            filter_kwargs = {"show_all":True}; limit_per_day = 50
        elif filter_mode == "Médias (>$1B)":
            filter_kwargs = {"min_market_cap":1e9,"min_importance":3}; limit_per_day = 25
        else:
            filter_kwargs = {"min_market_cap":5e9,"min_importance":4}; limit_per_day = 15

        with st.spinner("Carregando earnings..."):
            raw_earnings = fetch_earnings_week()

        if raw_earnings:
            top_earnings = filter_important_earnings(raw_earnings, **filter_kwargs)
            if show_only_today:
                today_str_filter = date.today().strftime("%Y-%m-%d")
                top_earnings = [e for e in top_earnings if e.get("earningsDate","") == today_str_filter]

            if top_earnings:
                by_day = defaultdict(list)
                for e in top_earnings:
                    by_day[e.get("earningsDate","")].append(e)
                day_names = {0:"SEGUNDA",1:"TERÇA",2:"QUARTA",3:"QUINTA",4:"SEXTA",5:"SÁB",6:"DOM"}
                earn_html = '<div style="max-height:580px;overflow-y:auto;">'

                for day_str in sorted(by_day.keys()):
                    try:
                        day_date = datetime.strptime(day_str,"%Y-%m-%d").date()
                        day_name = day_names.get(day_date.weekday(),"")
                        is_today = day_date == date.today()
                    except:
                        day_name = ""; is_today = False

                    bg_day     = "#1A1208" if is_today else "#161B22"
                    border_day = "#EFA500" if is_today else "#30363D"
                    today_b    = ' <span class="badge bft">HOJE</span>' if is_today else ""
                    n_day      = len(by_day[day_str])
                    earn_html += (f'<div style="background:{bg_day};border-left:3px solid {border_day};padding:6px 10px;margin:4px 0 0 0;display:flex;justify-content:space-between;">'
                                  f'<span style="font-family:Barlow Condensed;font-size:13px;font-weight:700;color:#EFA500;">📅 {day_name} {day_str[8:10]}/{day_str[5:7]}</span>'
                                  f'<span style="font-family:JetBrains Mono;font-size:10px;color:#A8B3BD;">{n_day} empresas{today_b}</span></div>')

                    for e in sorted(by_day[day_str], key=lambda x: x.get("marketCap",0) or 0, reverse=True)[:limit_per_day]:
                        sym    = e.get("symbol","?")
                        name   = e.get("assetName", sym)
                        mcap   = format_market_cap(e.get("marketCap",0))
                        eps_e  = e.get("epsEstimate")
                        eps_p  = e.get("epsPrior")
                        eps_a  = get_earnings_actual(e)
                        rev_e  = e.get("revenueEstimate",0)
                        timing = earnings_time_label(e)
                        conf   = "✓" if e.get("isDateConfirmed",False) else "?"

                        if timing=="BMO":   tb = '<span class="badge bbl" style="font-size:9px;">BMO</span>'
                        elif timing=="AMC": tb = '<span class="badge bft" style="font-size:9px;">AMC</span>'
                        else:               tb = '<span class="badge bnt" style="font-size:9px;">TBD</span>'

                        mcap_raw = e.get("marketCap",0) or 0
                        if mcap_raw >= 200e9:   sym_c="#EFA500"; bdr="#EFA500"
                        elif mcap_raw >= 50e9:  sym_c="#58A6FF"; bdr="#58A6FF"
                        elif mcap_raw >= 10e9:  sym_c="#3FB950"; bdr="#30363D"
                        else:                    sym_c="#A8B3BD"; bdr="#30363D"

                        result_badge = ""
                        if eps_a is not None and eps_e is not None:
                            surprise = calc_surprise(eps_a, eps_e)
                            if surprise is not None:
                                if surprise > 5:    result_badge = f'<span class="badge bp" style="font-size:9px;">BEAT +{surprise:.1f}%</span>'
                                elif surprise < -5: result_badge = f'<span class="badge bn" style="font-size:9px;">MISS {surprise:.1f}%</span>'
                                else:               result_badge = f'<span class="badge bnt" style="font-size:9px;">INLINE</span>'
                                eps_str = f'<b style="color:#fff;">EPS:{eps_a:.2f}</b> est:{eps_e:.2f}'
                            else:
                                eps_str = f"EPS:{eps_e:.2f}" if eps_e is not None else "EPS:—"
                        else:
                            eps_str = f"EPS Est:{eps_e:.2f}" if eps_e is not None else "EPS:—"

                        ep_str = f" P:{eps_p:.2f}" if eps_p is not None else ""
                        rv_str = f" Rev:{format_market_cap(rev_e)}" if rev_e and rev_e>0 else ""

                        earn_html += (
                            f'<div style="display:grid;grid-template-columns:65px 1fr auto;gap:8px;padding:5px 10px;border-bottom:1px solid #30363D;border-left:2px solid {bdr};align-items:center;">'
                            f'<div><div style="font-family:Barlow Condensed;font-size:15px;font-weight:700;color:{sym_c};">{sym}</div><div style="font-size:9px;color:#A8B3BD;font-family:JetBrains Mono;">{mcap}</div></div>'
                            f'<div><div style="font-size:11px;color:#E6EDF3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;">{name}</div><div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;">{eps_str}{ep_str}{rv_str}</div></div>'
                            f'<div style="text-align:right;">{tb} {result_badge}<div style="font-size:9px;color:#A8B3BD;margin-top:2px;">{conf}</div></div>'
                            f'</div>')

                earn_html += '</div>'
                st.markdown(earn_html, unsafe_allow_html=True)

    # ── POST-MORTEM DO DIA ANTERIOR ──────────────────────────────────────
    st.markdown("---")
    yesterday = _get_previous_business_day()
    yesterday_label = yesterday.strftime("%A, %d/%m/%Y").upper()
    st.markdown(f'<div class="sh">📊 RESULTADOS DO DIA ANTERIOR — {yesterday_label} (BEAT vs MISS)</div>', unsafe_allow_html=True)

    pm_refresh_col1, pm_refresh_col2 = st.columns([1, 5])
    with pm_refresh_col1:
        if st.button("🔄 Recarregar", key="btn_pm_reload", use_container_width=True):
            fetch_yesterday_earnings_results.clear()
            st.rerun()
    
    recent_results, yesterday_dt = fetch_yesterday_earnings_results(min_mcap=500e6)
    
    with pm_refresh_col2:
        st.markdown(
            f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;padding:7px 0;">'
            f'🔍 {len(recent_results)} resultados encontrados em {yesterday_dt.strftime("%d/%m/%Y")} (MCap > $500M)</div>',
            unsafe_allow_html=True
        )

    if recent_results:
        with_results    = [e for e in recent_results if get_earnings_actual(e) is not None]
        without_results = [e for e in recent_results if get_earnings_actual(e) is None]
        
        n_beat = sum(1 for e in with_results 
                     if get_earnings_actual(e) is not None and e.get("epsEstimate") is not None
                     and get_earnings_actual(e) > e.get("epsEstimate"))
        n_miss = sum(1 for e in with_results 
                     if get_earnings_actual(e) is not None and e.get("epsEstimate") is not None
                     and get_earnings_actual(e) < e.get("epsEstimate"))
        n_inline = len(with_results) - n_beat - n_miss
        
        if with_results:
            beat_pct = (n_beat / len(with_results) * 100) if with_results else 0
            st.markdown(
                f'<div style="display:flex;gap:10px;margin-bottom:8px;">'
                f'<div style="background:#071510;border:1px solid #3FB950;padding:8px 14px;flex:1;text-align:center;">'
                f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;">BEAT</div>'
                f'<div style="font-family:Barlow Condensed;font-size:24px;font-weight:800;color:#3FB950;">{n_beat}</div>'
                f'<div style="font-size:10px;color:#3FB950;">{beat_pct:.0f}%</div>'
                f'</div>'
                f'<div style="background:#150707;border:1px solid #F85149;padding:8px 14px;flex:1;text-align:center;">'
                f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;">MISS</div>'
                f'<div style="font-family:Barlow Condensed;font-size:24px;font-weight:800;color:#F85149;">{n_miss}</div>'
                f'<div style="font-size:10px;color:#F85149;">{(n_miss/len(with_results)*100):.0f}%</div>'
                f'</div>'
                f'<div style="background:var(--bg2);border:1px solid var(--border);padding:8px 14px;flex:1;text-align:center;">'
                f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;">INLINE</div>'
                f'<div style="font-family:Barlow Condensed;font-size:24px;font-weight:800;color:#A8B3BD;">{n_inline}</div>'
                f'<div style="font-size:10px;color:#A8B3BD;">{(n_inline/len(with_results)*100):.0f}%</div>'
                f'</div>'
                f'<div style="background:var(--bg3);border:1px solid var(--amber);padding:8px 14px;flex:1;text-align:center;">'
                f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;">TOTAL</div>'
                f'<div style="font-family:Barlow Condensed;font-size:24px;font-weight:800;color:var(--amber);">{len(with_results)}</div>'
                f'<div style="font-size:10px;color:#A8B3BD;">reportados</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        
        pm_html = """<table class="inst-table"><thead><tr>
          <td>TICKER</td><td>EMPRESA</td><td>HORA</td>
          <td>EPS REAL</td><td>EPS EST.</td><td>SURPRESA</td>
          <td>REV REAL</td><td>MKTCAP</td><td>VEREDICTO</td>
        </tr></thead><tbody>"""
        ordered_results = with_results + without_results
        
        for e in ordered_results[:30]:
            sym   = e.get("symbol","?")
            name  = e.get("assetName", sym)
            timing = earnings_time_label(e)
            eps_e = e.get("epsEstimate")
            eps_a = get_earnings_actual(e)
            rev_a = get_revenue_actual(e)
            mcap  = format_market_cap(e.get("marketCap",0))
            
            surprise = calc_surprise(eps_a, eps_e)
            if eps_a is not None and eps_e is not None and surprise is not None:
                if surprise > 5:
                    verdict = '<span class="badge bp">BEAT ✓</span>'
                    surp_color = "#3FB950"
                    surp_str = f"+{surprise:.1f}%"
                elif surprise < -5:
                    verdict = '<span class="badge bn">MISS ✗</span>'
                    surp_color = "#F85149"
                    surp_str = f"{surprise:.1f}%"
                else:
                    verdict = '<span class="badge bnt">INLINE</span>'
                    surp_color = "#A8B3BD"
                    surp_str = f"{surprise:+.1f}%"
                eps_real_str = f'<b style="color:{surp_color};">{eps_a:.2f}</b>'
            else:
                verdict = '<span class="badge bnt">⏳ Aguardando</span>'
                surp_color = "#A8B3BD"
                surp_str = "—"
                eps_real_str = '<span style="color:#A8B3BD;">—</span>'
            
            rev_real_str = format_market_cap(rev_a) if rev_a and rev_a > 0 else "—"
            
            pm_html += f"""<tr>
              <td style="color:#EFA500;font-weight:700;font-family:Barlow Condensed;font-size:14px;">{sym}</td>
              <td style="font-size:11px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{name}</td>
              <td style="color:#A8B3BD;">{timing}</td>
              <td>{eps_real_str}</td>
              <td style="color:#58A6FF;">{f'{eps_e:.2f}' if eps_e is not None else '—'}</td>
              <td style="color:{surp_color};font-weight:700;">{surp_str}</td>
              <td style="color:#A8B3BD;">{rev_real_str}</td>
              <td style="color:#A8B3BD;">{mcap}</td>
              <td>{verdict}</td>
            </tr>"""
        pm_html += "</tbody></table>"
        st.markdown(pm_html, unsafe_allow_html=True)

        # AI Post-mortem
        pm_ai_key = f"postmortem_ai_{yesterday_dt.strftime('%Y%m%d')}"
        if pm_ai_key not in st.session_state:
            st.session_state[pm_ai_key] = ""

        pm_c1, pm_c2 = st.columns([1, 5])
        with pm_c1:
            run_pm_ai = st.button("🤖 ANÁLISE", key="btn_pm_ai_earn", use_container_width=True)

        if run_pm_ai and client and with_results:
            with st.spinner("Analisando resultados..."):
                pm_sum = []
                for e in with_results[:15]:
                    eps_a = get_earnings_actual(e)
                    eps_e = e.get('epsEstimate')
                    surp  = calc_surprise(eps_a, eps_e)
                    surp_str = f"{surp:+.1f}%" if surp is not None else "?"
                    verdict = "BEAT" if (surp and surp > 5) else ("MISS" if (surp and surp < -5) else "INLINE")
                    pm_sum.append(
                        f"{e.get('symbol','?')} ({e.get('assetName','?')}) — "
                        f"EPS Real:{eps_a} vs Est:{eps_e} = {verdict} ({surp_str}) — "
                        f"Rev:{format_market_cap(get_revenue_actual(e))} — "
                        f"MCap:{format_market_cap(e.get('marketCap',0))}"
                    )
                pm_prompt = f"""Analise os earnings de {yesterday_dt.strftime('%d/%m/%Y')}:

{chr(10).join(pm_sum)}

Stats: {n_beat} BEAT · {n_miss} MISS · {n_inline} INLINE

**SURPRESAS POSITIVAS** — Quais BEATs foram mais impressionantes
**SURPRESAS NEGATIVAS** — Quais MISSes mais decepcionaram
**LEITURA SETORIAL** — Setores fortes/fracos
**TENDÊNCIA** — O que esses números dizem
**TRADES HOJE** — 2-3 ideias baseadas nos resultados

Português pt-BR. Máx 350 palavras."""

                pm_res = call_groq_with_fallback(
                    messages=[{"role":"user","content":pm_prompt}],
                    max_tokens=550,
                    temperature=0.4
                )
                if not pm_res.startswith("⚠️"):
                    st.session_state[pm_ai_key] = pm_res

        if st.session_state[pm_ai_key]:
            rend = ""
            for line in st.session_state[pm_ai_key].split('\n'):
                line = line.strip()
                if not line: rend += "<br>"
                elif line.startswith("**"):
                    rend += f'<div style="font-family:Barlow Condensed;font-size:13px;font-weight:700;color:#EFA500;margin-top:10px;padding-bottom:3px;border-bottom:1px solid #30363D;">{line.replace("**","")}</div>'
                elif line.startswith("•") or line.startswith("-"):
                    rend += f'<div style="padding:3px 0 3px 10px;font-size:12px;line-height:1.6;">{line}</div>'
                else:
                    rend += f'<div style="font-size:12px;line-height:1.65;">{line}</div>'
            st.markdown(f'<div class="ai-box">{rend}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div style="background:var(--bg2);border:1px solid var(--border);padding:20px;'
            f'text-align:center;font-size:12px;color:#A8B3BD;">'
            f'Nenhum earnings encontrado em {yesterday_dt.strftime("%d/%m/%Y")}.<br>'
            f'<small>Pode ser feriado ou fim de semana</small></div>',
            unsafe_allow_html=True
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB INTER-MARKET (NEW v10)
# ══════════════════════════════════════════════════════════════════════════════
with tab_im:
    st.markdown('<div class="sh">🌐 ANÁLISE INTER-MARKET — CORRELAÇÕES & DIVERGÊNCIAS (v10 NEW)</div>', unsafe_allow_html=True)

    # Market context cards
    mkt_im = fetch_market_context()
    if mkt_im:
        cols_im = st.columns(6)
        metrics = [
            ("VIX", mkt_im.get('vix',0), mkt_im.get('vix_chg',0), "pts", False),
            ("10Y Yield", mkt_im.get('yield_10y',0), mkt_im.get('yield_10y_chg',0)*100, "bps", False),
            ("DXY", mkt_im.get('dxy',0), mkt_im.get('dxy_chg',0), "pts", False),
            ("Gold", mkt_im.get('gold',0), mkt_im.get('gold_chg_pct',0), "%", True),
            ("WTI Oil", mkt_im.get('oil',0), mkt_im.get('oil_chg_pct',0), "%", True),
            ("SPY 5d", 0, mkt_im.get('spy_5d_ret',0), "%", True),
        ]
        for i, (lbl, val, chg, unit, use_pct_color) in enumerate(metrics):
            with cols_im[i]:
                chg_color = "#3FB950" if chg >= 0 else "#F85149"
                sign = "+" if chg >= 0 else ""
                val_fmt = f"{val:.2f}" if val > 0 else "—"
                if lbl == "SPY 5d":
                    val_fmt = ""
                st.markdown(
                    f'<div style="background:var(--bg2);border:1px solid var(--border);border-top:2px solid #EFA500;padding:8px 10px;text-align:center;">'
                    f'<div style="font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;font-weight:600;">{lbl}</div>'
                    f'<div style="font-family:Barlow Condensed;font-size:22px;font-weight:800;color:#fff;">{val_fmt}</div>'
                    f'<div style="font-family:JetBrains Mono;font-size:11px;font-weight:600;color:{chg_color};">{sign}{chg:.2f}{unit}</div>'
                    f'</div>', unsafe_allow_html=True)

        # Yield curve display
        yield_2y = mkt_im.get('yield_2y', 0)
        yield_10y = mkt_im.get('yield_10y', 0)
        if yield_2y and yield_10y:
            spread = yield_10y - yield_2y
            curve_color = "#F85149" if spread < 0 else "#3FB950"
            curve_label = "🔴 INVERTIDA" if spread < 0 else "🟢 NORMAL"
            st.markdown(
                f'<div style="background:var(--bg2);border:1px solid var(--border);padding:10px 16px;margin:8px 0;display:flex;gap:20px;align-items:center;">'
                f'<span style="font-family:Barlow Condensed;font-size:13px;font-weight:700;color:#A8B3BD;">CURVA DE JUROS 2Y-10Y:</span>'
                f'<span style="font-family:Barlow Condensed;font-size:20px;font-weight:800;color:{curve_color};">{curve_label} ({spread:+.3f}%)</span>'
                f'<span style="font-family:JetBrains Mono;font-size:11px;color:#A8B3BD;">2Y: {yield_2y:.3f}% · 10Y: {yield_10y:.3f}%</span>'
                f'</div>', unsafe_allow_html=True)

    # AI INTER-MARKET ANALYSIS (NEW v10)
    st.markdown('<div class="sh">🤖 ANÁLISE AI — CORRELAÇÕES & DIVERGÊNCIAS INTER-MARKET</div>', unsafe_allow_html=True)

    im_col1, im_col2 = st.columns([1, 5])
    with im_col1:
        run_im_ai = st.button("🔄 Analisar", key="btn_im_ai", use_container_width=True)
    with im_col2:
        if st.session_state.get('intermarket_ai_cache',''):
            age_min = int((time.time() - st.session_state.get('last_intermarket_ai',0)) / 60)
            st.markdown(f'<div style="font-size:10px;color:#3FB950;font-family:JetBrains Mono;padding:7px 0;">✓ Análise carregada · {age_min}min atrás</div>', unsafe_allow_html=True)

    if should_run_intermarket_ai(run_im_ai) and client:
        with st.spinner("Analisando correlações inter-market..."):
            mkt_full = fetch_market_context()
            vix_im   = mkt_full.get('vix', 0)
            vix_chg_im = mkt_full.get('vix_chg', 0)
            y10  = mkt_full.get('yield_10y', 0)
            y2   = mkt_full.get('yield_2y', 0)
            dxy_im = mkt_full.get('dxy', 0)
            gold_im = mkt_full.get('gold', 0)
            gold_chg_im = mkt_full.get('gold_chg_pct', 0)
            oil_im = mkt_full.get('oil', 0)
            oil_chg_im = mkt_full.get('oil_chg_pct', 0)
            spy5d_im = mkt_full.get('spy_5d_ret', 0)
            spread_im = y10 - y2 if y10 and y2 else 0

            snap_im = get_cached_tickers(["^GSPC","^TNX","DX-Y.NYB","GC=F","CL=F"])
            snap_str_im = " | ".join([f"{t['n']}:{t['p']:.2f}({'+' if t['c']>=0 else ''}{t['c']:.2f}%)" for t in snap_im])

            # Order flow for context
            of_ctx_im = ""
            if fj_orderflow.get("indices"):
                of_ctx_im = "\nORDER FLOW: " + " | ".join([f"{i['name']}:MOO={_format_money(i['moo_total'])}" for i in fj_orderflow["indices"][:4]])

            im_prompt = f"""Você é o Chefe de Análise Inter-Market de um macro hedge fund global (estilo Ray Dalio / Stan Druckenmiller). Hoje: {datetime.now().strftime('%d/%b/%Y %H:%M')}.

SNAPSHOT COMPLETO:
Equities: SPY retorno 5d {spy5d_im:+.2f}%
Volatilidade: VIX {vix_im:.2f} ({'+' if vix_chg_im>=0 else ''}{vix_chg_im:.2f}pts)
Renda Fixa: 10Y Yield {y10:.3f}% | 2Y Yield {y2:.3f}% | Spread 10Y-2Y {spread_im:+.3f}% ({'INVERTIDA' if spread_im<0 else 'NORMAL'})
Câmbio: DXY {dxy_im:.2f}
Metais: Gold ${gold_im:.0f} ({gold_chg_im:+.2f}%)
Energia: WTI ${oil_im:.2f} ({oil_chg_im:+.2f}%)
{of_ctx_im}
SOFR {sofr_rate:.3f}% | RRP ${rrp_value:.1f}Bn

NOTÍCIAS-CHAVE: {news_titles[:10]}

Produza análise INTER-MARKET de alta qualidade:

**1. REGIME MACRO ATUAL**
Qual regime global? (Goldilocks/Reflação/Recessão-medo/Estagflação/Crise de crédito). Justifique com 3 indicadores concretos da lista acima.

**2. CORRELAÇÕES ATIVAS**
Identifique as 3 correlações mais importantes que estão FUNCIONANDO agora:
• Bonds vs Equities: convergindo (risk-on) ou divergindo (estresse)?
• DXY vs Commodities: qual relação domina?
• Gold como termômetro: o que está sinalizando (estresse real, hedge de inflação, ou apetite por risco)?

**3. DIVERGÊNCIAS SUSPEITAS**
Identifique 2 divergências que NÃO deveriam existir se o regime fosse coerente. Explique o que cada uma pode indicar sobre o próximo movimento.

**4. LIQUIDEZ & FUNDING**
SOFR {sofr_rate:.3f}% vs EFFR {effr_rate:.3f}% → spread de {effr_rate-sofr_rate:+.3f}%. RRP ${rrp_value:.1f}Bn. O que isso diz sobre liquidez do sistema? Existe risco de crise de funding a curto prazo?

**5. TRADE INTER-MARKET**
1 trade concreto baseado em correlação/divergência identificada. Par ou cesta de ativos, direção e racional.

Máx 420 palavras. Português pt-BR. Institucional."""

            im_res = call_groq_with_fallback([{"role":"user","content":im_prompt}], max_tokens=900, temperature=0.35)
            if not im_res.startswith("⚠️"):
                st.session_state.intermarket_ai_cache = im_res
                st.session_state.last_intermarket_ai = time.time()
            else:
                st.session_state.intermarket_ai_cache = im_res

    if st.session_state.get('intermarket_ai_cache',''):
        rend = render_ai_text(st.session_state.intermarket_ai_cache, "ai-box", "#EFA500")
        st.markdown(f'<div class="ai-box">{rend}</div>', unsafe_allow_html=True)
    elif not client:
        st.markdown('<div class="empty-state"><div class="empty-title">🌐 Análise Inter-Market</div><div class="empty-sub">Configure a GROQ API Key na aba CONFIGURAÇÕES<br>e clique "Analisar".</div></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB NEWS FEED
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="sh">📰 NEWS FEED COMPLETO</div>', unsafe_allow_html=True)

    nf_col1, nf_col2 = st.columns([3, 1])
    with nf_col2:
        st.session_state.translate_news = st.checkbox("Traduzir", value=st.session_state.get('translate_news',True), key="nf_translate")
        if st.button("🔄 Forçar atualização", use_container_width=True, key="nf_refresh"):
            st.session_state.last_news_fetch = 0
            st.rerun()

    with nf_col1:
        if st.session_state.news_history:
            items_per_page = 50
            total = len(st.session_state.news_history)
            pages = (total // items_per_page) + (1 if total % items_per_page else 0)
            page  = st.number_input("Página", min_value=1, max_value=max(1,pages), value=1, step=1, key="nf_page") - 1
            start = page * items_per_page
            end   = start + items_per_page

            feed_html = '<div style="max-height:75vh;overflow-y:auto;">'
            for item in st.session_state.news_history[start:end]:
                translated = get_translated_title(item['t']) if st.session_state.get('translate_news',True) else item['t']
                feed_html += (f'<div class="news-item">'
                              f'<span class="news-time">[{item["h"]}]</span><br>'
                              f'<a href="{item["l"]}" target="_blank" class="news-link">{translated}</a>'
                              f'{"<br><small>" + item["t"][:80] + "...</small>" if translated != item["t"] else ""}'
                              f'</div>')
            feed_html += '</div>'
            st.markdown(feed_html, unsafe_allow_html=True)
            st.caption(f"Mostrando {start+1}-{min(end,total)} de {total} notícias")
        else:
            st.markdown('<div class="empty-state"><div class="empty-title">📰 Sem notícias</div><div class="empty-sub">Configure os RSS feeds na aba CONFIGURAÇÕES.</div></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════════════════════════
with tab_cfg:
    st.markdown('<div class="sh">⚙️ CONFIGURAÇÕES — QUANT TERMINAL v10</div>', unsafe_allow_html=True)

    sv_c1, sv_c2 = st.columns([3, 1])
    cfg_status = sv_c1.empty()
    with sv_c2:
        if st.button("💾 SALVAR TUDO", use_container_width=True, key="cfg_save_top"):
            ok = save_config()
            mc = "#3FB950" if ok else "#F85149"
            mm = f"✅ Salvo: {CONFIG_FILE}" if ok else "⚠️ Erro ao salvar"
            cfg_status.markdown(f'<div style="background:{"#0D1F14" if ok else "#1F0D0D"};border-left:4px solid {mc};padding:8px 12px;font-size:11px;font-family:JetBrains Mono;color:{mc};">{mm}</div>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown('<div class="sh">🧠 MODELO DE IA (GROQ)</div>', unsafe_allow_html=True)
    model_c1, model_c2 = st.columns([3, 2])
    with model_c1:
        current_model = st.session_state.get('ai_model','llama-3.3-70b-versatile')
        if current_model not in GROQ_MODELS:
            GROQ_MODELS.insert(0, current_model)
        selected_model = st.selectbox("Modelo IA", options=GROQ_MODELS, index=GROQ_MODELS.index(current_model) if current_model in GROQ_MODELS else 0, key="cfg_ai_model_select", label_visibility="collapsed")
        st.session_state.ai_model = selected_model
    with model_c2:
        custom_model = st.text_input("Modelo customizado", value="", placeholder="ex: novo-modelo-groq", key="cfg_ai_model_custom", label_visibility="collapsed")
        if custom_model.strip():
            st.session_state.ai_model = custom_model.strip()
            selected_model = custom_model.strip()

    st.markdown(f'<div style="background:#0d2a4a;border:1px solid #58A6FF;border-left:4px solid #58A6FF;padding:10px 14px;font-size:12px;font-family:JetBrains Mono;color:#58A6FF;margin-top:6px;">🧠 Modelo ativo: <b>{selected_model}</b> · Fallback automático ativo · v10 Enhanced Prompts</div>', unsafe_allow_html=True)

    # Bloqueios
    blocked_keys   = st.session_state.get('blocked_keys', {})
    blocked_models = st.session_state.get('blocked_models', {})
    active_bk = {k:v for k,v in blocked_keys.items() if v > time.time()}
    active_bm = {k:v for k,v in blocked_models.items() if v > time.time()}
    if active_bk or active_bm:
        with st.expander(f"🔒 Bloqueios ativos ({len(active_bk)} keys + {len(active_bm)} modelos)", expanded=False):
            for kh, until in active_bk.items():
                st.markdown(f'<div style="font-size:10px;color:#F85149;font-family:JetBrains Mono;">🔒 Key {kh} → unlock em {int(until-time.time())}s</div>', unsafe_allow_html=True)
            for mdl, until in active_bm.items():
                st.markdown(f'<div style="font-size:10px;color:#F85149;font-family:JetBrains Mono;">🔒 {mdl} → unlock em {int(until-time.time())}s</div>', unsafe_allow_html=True)
            if st.button("🔓 Limpar bloqueios", key="btn_clear_blocks"):
                st.session_state.blocked_keys = {}
                st.session_state.blocked_models = {}
                st.success("Bloqueios limpos!")
                st.rerun()

    # AI Log
    if st.session_state.get('ai_call_log'):
        with st.expander(f"📋 Log de chamadas IA ({len(st.session_state.ai_call_log)})", expanded=False):
            log_html = ""
            for entry in st.session_state.ai_call_log[:30]:
                sc = "#3FB950" if "OK" in entry['status'] else ("#F0B429" if "RATE" in entry['status'] else "#F85149")
                log_html += (f'<div class="ai-log-row"><span style="color:#A8B3BD;">{entry["time"]}</span>'
                             f'<span style="color:#58A6FF;">{entry["model"][:30]}</span>'
                             f'<span style="color:#A8B3BD;">{entry["key"]}</span>'
                             f'<span style="color:{sc};">{entry["status"]}</span>'
                             f'<span style="color:#A8B3BD;font-size:9px;">{entry["error"]}</span></div>')
            st.markdown(log_html, unsafe_allow_html=True)
            if st.button("🗑️ Limpar log", key="btn_clear_log"):
                st.session_state.ai_call_log = []
                st.rerun()

    st.markdown("---")
    cc1, cc2 = st.columns(2)

    with cc1:
        st.markdown('<div class="sh">🔑 GROQ API KEYS</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:11px;color:#A8B3BD;font-family:JetBrains Mono;padding:6px 0 10px 0;">Até 5 chaves — rotação automática + fallback de modelo.<br><a href="https://console.groq.com" target="_blank" style="color:#58A6FF;">console.groq.com</a></div>', unsafe_allow_html=True)
        if not isinstance(st.session_state.get('groq_keys'), list):
            st.session_state.groq_keys = ["","","","",""]
        while len(st.session_state.groq_keys) < 5:
            st.session_state.groq_keys.append("")
        for i in range(5):
            v = st.text_input(f"API Key {i+1}", value=st.session_state.groq_keys[i], type="password", key=f"cfg_gk_{i}", placeholder="gsk_...")
            st.session_state.groq_keys[i] = v
        vk    = [k for k in st.session_state.groq_keys if k.strip()]
        col_k = "#3FB950" if vk else "#F85149"
        st.markdown(f'<div style="background:{"#0D1F14" if vk else "#1F0D0D"};border-left:4px solid {col_k};padding:8px 12px;font-size:12px;font-family:JetBrains Mono;color:{col_k};">{"✅ " + str(len(vk)) + " chave(s) ativa(s)" if vk else "⚠️ Sem chaves — AI desativado"}</div>', unsafe_allow_html=True)

    with cc2:
        st.markdown('<div class="sh">📡 RSS FEEDS</div>', unsafe_allow_html=True)
        rss_v = st.text_area("RSS", value=st.session_state.get('rss_urls',''), height=150, key="cfg_rss", label_visibility="collapsed")
        st.session_state.rss_urls = rss_v
        nf = len([u for u in rss_v.split('\n') if u.strip()])
        st.markdown(f'<div style="font-size:11px;color:#A8B3BD;font-family:JetBrains Mono;">{nf} feed(s)</div>', unsafe_allow_html=True)

        st.markdown('<div class="sh" style="margin-top:10px;">🏦 FINANCIAL JUICE TOKEN</div>', unsafe_allow_html=True)
        fj_token = st.text_input("FJ Token", value=st.session_state.get('fj_token',FJ_DEFAULT_TOKEN), type="password", key="cfg_fj_token", label_visibility="collapsed", placeholder="%22EAAA...")
        st.session_state.fj_token = fj_token if fj_token.strip() else FJ_DEFAULT_TOKEN
        if st.button("🔄 Limpar cache FJ", key="btn_fj_clear", use_container_width=True):
            fetch_fj_data.clear()
            st.success("Cache FJ limpo!")
            st.rerun()

    st.markdown("---")
    st.markdown('<div class="sh">📊 TICKER BAR</div>', unsafe_allow_html=True)
    tb_v = st.text_input("Ticker Bar (até 8, separados por vírgula)", value=st.session_state.get('ticker_bar_symbols','^GSPC,^IXIC,^DJI,^VIX,CL=F,BZ=F,DX-Y.NYB,GC=F'), key="cfg_tb")
    st.session_state.ticker_bar_symbols = tb_v

    st.markdown("---")
    st.markdown('<div class="sh">🎯 ATIVO PRINCIPAL</div>', unsafe_allow_html=True)
    mt_v = st.text_input("Ticker para análise AI foco (ex: IBIT, SPY, QQQ)", value=st.session_state.get('main_t_val',''), key="cfg_mt").upper()
    st.session_state.main_t_val = mt_v

    st.markdown("---")
    st.markdown('<div class="sh">📈 INSTRUMENTOS GAMMA (MenthorQ)</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:12px;color:#A8B3BD;font-family:Barlow;padding:6px 0 12px 0;line-height:1.8;">'
        '🔑 <b style="color:#EFA500;">Formato:</b> <code style="color:#58A6FF;font-size:11px;">LABEL, VALOR, LABEL, VALOR, ...</code><br>'
        '📌 Labels: <span style="color:#58A6FF;">HVL · CW · CW 0DTE · PW · PW 0DTE · KL · KL 0DTE · GEX 1 · GEX 2 · GEX 3 · 1D Exp Min · 1D Exp Max</span><br>'
        '📚 <a href="https://menthorq.com/academy/gamma-levels/" target="_blank" style="color:#58A6FF;">MenthorQ Academy</a>'
        '</div>', unsafe_allow_html=True)

    with st.expander("➕ ADICIONAR NOVO INSTRUMENTO", expanded=len(gamma_instruments)==0):
        na1, na2 = st.columns([1, 3])
        with na1:
            new_tk = st.text_input("Ticker yFinance", key="add_tk", placeholder="ES=F, SPY...").upper()
            new_lb = st.text_input("Label curto", key="add_lb", placeholder="ES, SPY...").upper()
            new_gx = st.number_input("GEX ($Bn)", value=0.0, format="%.3f", key="add_gx")
        with na2:
            default_lvl = "HVL, 0.00, CW, 0.00, CW 0DTE, 0.00, PW, 0.00, PW 0DTE, 0.00, KL, 0.00, KL 0DTE, 0.00, GEX 1, 0.00, GEX 2, 0.00, GEX 3, 0.00, 1D Exp Min, 0.00, 1D Exp Max, 0.00"
            new_lv = st.text_area("Níveis", value=default_lvl, height=110, key="add_lv")
        if st.button("➕ ADICIONAR", key="btn_add", use_container_width=True):
            if new_tk and new_lb:
                st.session_state.gamma_instruments.append({"ticker":new_tk,"label":new_lb,"levels":new_lv,"gex":new_gx})
                save_config()
                st.success(f"✅ {new_lb} ({new_tk}) adicionado!")
                st.rerun()
            else:
                st.warning("Preencha Ticker e Label.")

    for idx, inst in enumerate(list(st.session_state.gamma_instruments)):
        gex_v = float(inst.get('gex',0))
        with st.expander(f"✏️  {inst.get('label','?')}  ·  {inst.get('ticker','?')}  ·  GEX: {'+' if gex_v>=0 else ''}{gex_v:.3f}Bn", expanded=False):
            ei1, ei2 = st.columns([1, 3])
            with ei1:
                e_tk = st.text_input("Ticker", value=inst.get('ticker',''), key=f"e_tk_{idx}").upper()
                e_lb = st.text_input("Label",  value=inst.get('label',''),  key=f"e_lb_{idx}").upper()
                e_gx = st.number_input("GEX ($Bn)", value=gex_v, format="%.3f", key=f"e_gx_{idx}")
                bc1, bc2 = st.columns(2)
                with bc1:
                    if st.button("💾 Salvar", key=f"e_sv_{idx}", use_container_width=True):
                        new_levels = st.session_state.get(f"e_lv_{idx}", inst.get('levels',''))
                        st.session_state.gamma_instruments[idx] = {"ticker":e_tk,"label":e_lb,"levels":new_levels,"gex":e_gx}
                        if e_tk in st.session_state.ticker_store:
                            del st.session_state.ticker_store[e_tk]
                        ck = f"gamma_{e_lb}_{e_tk}"
                        if ck in st.session_state.gamma_ai_cache:
                            del st.session_state.gamma_ai_cache[ck]
                        save_config()
                        st.success(f"✅ {e_lb} salvo!")
                        st.rerun()
                with bc2:
                    if st.button("🗑️ Remover", key=f"e_rm_{idx}", use_container_width=True):
                        st.session_state.gamma_instruments.pop(idx)
                        save_config()
                        st.rerun()
            with ei2:
                st.text_area("Níveis", value=inst.get('levels',''), height=120, key=f"e_lv_{idx}", label_visibility="collapsed")

    st.markdown("---")
    st.markdown('<div class="sh">💧 SOFR / EFFR / RRP</div>', unsafe_allow_html=True)
    rt1, rt2, rt3 = st.columns(3)
    with rt1:
        sv_r = st.number_input("SOFR (%)", value=float(st.session_state.get('sofr_val',4.305)), format="%.3f", step=0.001, key="cfg_sofr")
        st.session_state.sofr_val = sv_r
    with rt2:
        ev_r = st.number_input("EFFR (%)", value=float(st.session_state.get('effr_val',4.330)), format="%.3f", step=0.001, key="cfg_effr")
        st.session_state.effr_val = ev_r
    with rt3:
        rv_r = st.number_input("RRP ($Bn)", value=float(st.session_state.get('rrp_val',485.2)), format="%.1f", key="cfg_rrp")
        st.session_state.rrp_val = rv_r

    st.markdown("---")
    st.markdown('<div class="sh">📦 BACKUP COMPLETO</div>', unsafe_allow_html=True)
    exp_c, imp_c = st.columns(2)
    with exp_c:
        full_export = {
            "groq_keys":st.session_state.get('groq_keys',[]),
            "rss_urls":st.session_state.get('rss_urls',''),
            "ticker_bar_symbols":st.session_state.get('ticker_bar_symbols',''),
            "gamma_instruments":st.session_state.gamma_instruments,
            "main_t_val":st.session_state.get('main_t_val',''),
            "sofr_val":st.session_state.get('sofr_val',4.305),
            "effr_val":st.session_state.get('effr_val',4.330),
            "rrp_val":st.session_state.get('rrp_val',485.2),
            "ai_model":st.session_state.get('ai_model','llama-3.3-70b-versatile'),
            "fj_token":st.session_state.get('fj_token',FJ_DEFAULT_TOKEN),
        }
        st.download_button("⬇️ Baixar quant_config.json", data=json.dumps(full_export,ensure_ascii=False,indent=2), file_name="quant_config.json", mime="application/json", use_container_width=True)
    with imp_c:
        imp_txt = st.text_area("JSON para importar", height=120, key="cfg_import", label_visibility="collapsed", placeholder='{"groq_keys":[...],"gamma_instruments":[...]}')
        if st.button("⬆️ IMPORTAR E APLICAR", use_container_width=True, key="btn_import"):
            try:
                imp = json.loads(imp_txt)
                allowed = ["groq_keys","rss_urls","ticker_bar_symbols","gamma_instruments","main_t_val","sofr_val","effr_val","rrp_val","ai_model","fj_token"]
                for k in allowed:
                    if k in imp:
                        st.session_state[k] = imp[k]
                st.session_state.ticker_store = {}
                st.session_state.gamma_ai_cache = {}
                save_config()
                st.success("✅ Importado com sucesso!")
                st.rerun()
            except Exception as e:
                st.error(f"JSON inválido: {e}")

    st.markdown("---")
    if st.button("💾 SALVAR TODAS AS CONFIGURAÇÕES", use_container_width=True, key="cfg_save_bottom"):
        ok = save_config()
        st.success(f"✅ Salvo em: {CONFIG_FILE}") if ok else st.error("⚠️ Erro ao salvar.")


# ─── FOOTER ──────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="border-top:1px solid #30363D;padding:8px 0;display:flex;justify-content:space-between;font-size:10px;color:#A8B3BD;font-family:JetBrains Mono;margin-top:20px;">
  <span>Order Flow: Financial Juice · Earnings: SavvyTrader · Bubble+Futures: Finviz · Gamma: MenthorQ · IA: <b style="color:#58A6FF;">{get_ai_model()}</b> · Não constitui recomendação</span>
  <span>QUANT TERMINAL v10.0 · {datetime.now().strftime("%d/%m/%Y %H:%M")} BRT · AI Enhanced Prompts · Todas as APIs mantidas</span>
</div>
""", unsafe_allow_html=True)
