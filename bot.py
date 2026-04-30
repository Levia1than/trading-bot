import telebot
import time
import random
import os
import threading
import requests
import json
import sqlite3
from datetime import datetime, timedelta
from telebot import types

TOKEN = 'BOT_TOKEN'
bot = telebot.TeleBot(TOKEN)

DB_FILE = "bot_database.db"
STATS_FILE = "statistics.json"
ADMIN_ID = 1008459439  # Твой Telegram ID

# ==================== SQLITE DATABASE ====================
class BotDB:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_table()

    def _create_table(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                chat_id INTEGER PRIMARY KEY,
                notif_freq REAL DEFAULT 0,
                last_notif REAL DEFAULT 0,
                balance REAL DEFAULT 0,
                risk REAL DEFAULT 0,
                max_trades INTEGER DEFAULT 0,
                trading_mode TEXT DEFAULT 'all',
                trial_start TEXT,
                subscription_end TEXT,
                is_approved INTEGER DEFAULT 1
            )
        ''')
        self.conn.commit()

    def get_user(self, chat_id):
        self.cursor.execute("SELECT * FROM users WHERE chat_id = ?", (chat_id,))
        row = self.cursor.fetchone()
        if row:
            return {
                "notif_freq": row[1], "last_notif": row[2], "balance": row[3],
                "risk": row[4], "max_trades": row[5], "trading_mode": row[6],
                "trial_start": row[7], "subscription_end": row[8],
                "is_approved": bool(row[9])
            }
        return None

    def save_user(self, chat_id, data):
        self.cursor.execute('''
            INSERT OR REPLACE INTO users (
                chat_id, notif_freq, last_notif, balance, risk, max_trades, 
                trading_mode, trial_start, subscription_end, is_approved
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            chat_id, data["notif_freq"], data["last_notif"], data["balance"],
            data["risk"], data["max_trades"], data["trading_mode"],
            data["trial_start"], data["subscription_end"], 1 if data["is_approved"] else 0
        ))
        self.conn.commit()

    def get_all_users(self):
        self.cursor.execute("SELECT * FROM users")
        rows = self.cursor.fetchall()
        users = {}
        for row in rows:
            users[row[0]] = {
                "notif_freq": row[1], "last_notif": row[2], "balance": row[3],
                "risk": row[4], "max_trades": row[5], "trading_mode": row[6],
                "trial_start": row[7], "subscription_end": row[8],
                "is_approved": bool(row[9])
            }
        return users

db = BotDB()

# ==================== HELPERS ====================
def load_stats():
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_stats(data):
    with open(STATS_FILE + ".tmp", 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(STATS_FILE + ".tmp", STATS_FILE)

stats_data = load_stats()

def get_live_price(symbol_name):
    if "OTC" in symbol_name.upper():
        return None
    crypto_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "UNIUSDT", "DOTUSDT", "MATICUSDT"]
    clean_symbol = symbol_name.replace("/", "").replace("-", "").upper().replace("(OTC)", "")
    if clean_symbol in crypto_symbols:
        try:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={clean_symbol}"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                price = float(response.json()['price'])
                return f"${price:,.2f}" if price > 1000 else f"${price:.4f}"
        except Exception:
            pass
    return None

def check_access(chat_id):
    user = db.get_user(chat_id) or {}
    today = datetime.now()
    sub_end = user.get("subscription_end")
    if sub_end:
        try:
            if datetime.strptime(sub_end, "%Y-%m-%d") >= today:
                return True
        except ValueError: pass
    trial_start = user.get("trial_start")
    if trial_start:
        try:
            start_date = datetime.strptime(trial_start, "%Y-%m-%d")
            if today - start_date <= timedelta(days=1):  # 🔹 ТРИАЛ 1 ДЕНЬ
                return True
        except ValueError: pass
    return False

def get_paywall_message():
    return (
        "⏰ Access Expired\n\n"
        "Your trial period has ended. To continue receiving institutional-grade setups:\n\n"
        "💳 Subscription Plans:\n"
        "• 1 Month — $49\n"
        "• 3 Month — $99\n\n"
        "💸 Pay USDT (TRC20): `ВСТАВЬ_СЮДА_СВОЙ_КОШЕЛЕК`\n\n"
        "📩 After payment, send your Transaction Hash to @YourSupport.\n"
        "Access is usually activated within 1 hour."
    )

# ==================== MARKUPS ====================
def get_mode_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📱 Pocket Option (OTC)", callback_data="mode_pocket"),
        types.InlineKeyboardButton("🪙 Crypto Only", callback_data="mode_crypto"),
        types.InlineKeyboardButton("💱 Forex Only", callback_data="mode_forex"),
        types.InlineKeyboardButton("🥇 Metals Only", callback_data="mode_metals"),
        types.InlineKeyboardButton("🔀 All Signals", callback_data="mode_all"),
        types.InlineKeyboardButton("📋 Main Menu", callback_data="back_to_main")
    )
    return markup

def get_main_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔥 READY FOR SIGNAL", callback_data="ready_signal"),
        types.InlineKeyboardButton("💰 Risk Calculator", callback_data="open_risk"),
        types.InlineKeyboardButton("⚙️ Trading Mode", callback_data="menu_cmd"),
        types.InlineKeyboardButton("📊 My Stats", callback_data="stats_btn"),
        types.InlineKeyboardButton("📘 Guide", callback_data="guide_cmd"),
        types.InlineKeyboardButton(" Notifications", callback_data="notif_settings")
    )
    return markup

def get_vote_markup():
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("✅ Win", callback_data="vote_win"),
        types.InlineKeyboardButton("❌ Loss", callback_data="vote_loss"),
        types.InlineKeyboardButton("⏭ Skip", callback_data="vote_skip")
    )
    return markup

def get_post_vote_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➡️ Next Signal", callback_data="ready_signal"),
        types.InlineKeyboardButton("📊 My Stats", callback_data="stats_btn")
    )
    return markup

# ==================== MESSAGES & SIGNALS ====================
WELCOME_MSG = (
    "Welcome. I'm Benjamin Edevane.\n"
    "This bot delivers institutional-grade setups filtered for precision, not hype. "
    "No lag. No guesswork. Just clean entries, defined risk, and real-time execution windows.\n\n"
    "🔹 How it works:\n"
    "• Signals drop with exact entry zone + expiry/direction.\n"
    "• Always risk 1–2% max. Never double down.\n"
    "• Wait for confirmation. Missed signal? Skip it.\n"
    "• Track every trade. Discipline compounds.\n\n"
    " Pro tip: Use /risk before trading to calculate safe position size.\n"
    "📊 Track your progress: /stats\n"
    " Live data enabled for crypto assets.\n"
    "You're not here to gamble. You're here to execute a process.\n"
    "Trade with structure. I'll handle the edge. 🤍"
)

signals = [
    {'pair': 'EUR/AUD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL  — EXECUTE WITHIN 1 MIN ️\n\nPair: EUR/AUD (OTC)\nDirection: DOWN 🔽\nExpiry: 2 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Bearish divergence on RSI. OTC algorithm usually trends for 3-4 candles. Avoid entering in the last 10s.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'USD/CHF (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: USD/CHF (OTC)\nDirection: UP ⬆️\nExpiry: 1 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Breakout of consolidation box. Volatility is high. Enter exactly at candle close. Fixed payout ~85%.\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'GBP/CHF (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL  — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: GBP/CHF (OTC)\nDirection: DOWN 🔽\nExpiry: 3 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Rejection from strong resistance. 3 min expiry allows noise to settle. Do not average down on OTC.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'CAD/JPY (OTC)', 'category': 'pocket', 'text': " SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: CAD/JPY (OTC)\nDirection: UP ⬆️\nExpiry: 5 min\n\n️ Enter within 60 seconds of this message\n💡 PO Tips: Swing trade on OTC. Wait for pullback to EMA21. Longer expiry reduces risk of false spikes.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'AUD/JPY (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: AUD/JPY (OTC)\nDirection: DOWN 🔽\nExpiry: 2 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Trend continuation. OTC respects support flips. Enter immediately. Risk management is key.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'NZD/CAD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: NZD/CAD (OTC)\nDirection: UP ⬆️\nExpiry: 1 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Scalping mode. Fast entry required. OTC liquidity is lower, so slippage can happen. Be ready.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'EUR/NZD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ️\n\nPair: EUR/NZD (OTC)\nDirection: DOWN 🔽\nExpiry: 2 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Double top pattern confirmed. OTC algorithms often repeat patterns. Target next liquidity zone.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'GBP/NZD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL  — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: GBP/NZD (OTC)\nDirection: UP ⬆️\nExpiry: 3 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Volatile pair. 3 min expiry gives room to breathe. Wait for green candle close before clicking.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'USD/CAD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ️\n\nPair: USD/CAD (OTC)\nDirection: DOWN 🔽\nExpiry: 1 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: News impact fading. OTC reversion to mean strategy. Enter fast, payout is stable ~88%.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'BTC/USD (OTC)', 'category': 'pocket', 'text': " SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: BTC/USD (OTC)\nDirection: UP ⬆️\nExpiry: 5 min\n\n️ Enter within 60 seconds of this message\n💡 PO Tips: Crypto OTC follows spot market momentum. Trend is strong. 5 min expiry catches the wave.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'ETH/USD (OTC)', 'category': 'pocket', 'text': " SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: ETH/USD (OTC)\nDirection: DOWN 🔽\nExpiry: 3 min\n\n⚠️ Enter within 60 seconds of this message\n PO Tips: Correction phase. OTC algorithm slows down. Patience with entry. Check correlation with BTC.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'AUD/USD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: AUD/USD (OTC)\nDirection: UP ⬆️\nExpiry: 2 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Support bounce. Classic OTC setup. Risk 1% max. Do not chase the trade.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'EUR/JPY (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: EUR/JPY (OTC)\nDirection: DOWN 🔽\nExpiry: 1 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Breakdown of ascending channel. High probability setup. OTC respects technicals well here.\n\n Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'GBP/JPY (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ️\n\nPair: GBP/JPY (OTC)\nDirection: UP ⬆️\nExpiry: 3 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: The Dragon pair. Volatile. 3 min expiry recommended to avoid whipsaws. Strong trend.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'NZD/JPY (OTC)', 'category': 'pocket', 'text': " SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: NZD/JPY (OTC)\nDirection: DOWN \nExpiry: 2 min\n\n️ Enter within 60 seconds of this message\n💡 PO Tips: Rejection at psychological level. OTC algorithm tends to reverse hard here. Execute with precision.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'CAD/CHF (OTC)', 'category': 'pocket', 'text': " SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: CAD/CHF (OTC)\nDirection: UP ⬆️\nExpiry: 5 min\n\n️ Enter within 60 seconds of this message\n💡 PO Tips: Slow mover. 5 min expiry captures the small moves. Low volatility but high accuracy.\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'AUD/NZD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: AUD/NZD (OTC)\nDirection: DOWN 🔽\nExpiry: 2 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Range bound strategy. Selling at resistance. OTC range is tight. Quick execution needed.\n\n Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'EUR/CAD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL  — EXECUTE WITHIN 1 MIN ️\n\nPair: EUR/CAD (OTC)\nDirection: UP ⬆️\nExpiry: 1 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Momentum spike. Enter on breakout candle close. 1 min expiry for quick profit taking.\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'GBP/CAD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL 🛑 — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: GBP/CAD (OTC)\nDirection: DOWN 🔽\nExpiry: 3 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Heavy pair. Moves slowly but surely. 3 min expiry allows trend to develop. Patience pays.\n\n🤍 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'USD/SGD (OTC)', 'category': 'pocket', 'text': "🛑 SIGNAL  — EXECUTE WITHIN 1 MIN ⏱️\n\nPair: USD/SGD (OTC)\nDirection: UP ⬆️\nExpiry: 2 min\n\n⚠️ Enter within 60 seconds of this message\n💡 PO Tips: Exotic pair on OTC. Often ignored by algorithms, creating predictable patterns. High payout potential.\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'BTC/USDT', 'category': 'crypto', 'text': "🤍 BTC/USDT — CALL (UP)\n📍 Entry Zone: 94,200 – 94,500\n⏱️ Expiry: 20 minutes\n💰 Payout: ~75%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for 15m MACD bullish crossover\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'EUR/USD', 'category': 'forex', 'text': "🖤 EUR/USD — PUT (DOWN)\n📍 Entry Zone: 1.0850 – 1.0865\n⏱️ Expiry: 5 minutes\n💰 Payout: ~82%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for 15m RSI divergence below 70\n\n Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'XAU/USD', 'category': 'metals', 'text': "🤍 XAU/USD — CALL (UP)\n📍 Entry Zone: 2325 – 2330\n⏱️ Expiry: 10 minutes\n💰 Payout: ~80%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for 1H candle close above 2330\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'ETH/USDT', 'category': 'crypto', 'text': "🖤 ETH/USDT — PUT (DOWN)\n📍 Entry Zone: 3,520 – 3,550\n⏱️ Expiry: 15 minutes\n💰 Payout: ~75%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for whale wallet movement\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'GBP/USD', 'category': 'forex', 'text': "🤍 GBP/USD — CALL (UP)\n📍 Entry Zone: 1.2710 – 1.2725\n⏱️ Expiry: 15 minutes\n💰 Payout: ~78%\n📐 Stake: $5-10 per trade (1% rule)\n Wait for bounce off 15m support level\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'XAG/USD', 'category': 'metals', 'text': "🖤 XAG/USD — PUT (DOWN)\n📍 Entry Zone: 28.50 – 28.80\n⏱️ Expiry: 15 minutes\n💰 Payout: ~77%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for industrial demand weakness\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'SOL/USDT', 'category': 'crypto', 'text': " SOL/USDT — CALL (UP)\n📍 Entry Zone: 178 – 182\n⏱️ Expiry: 20 minutes\n💰 Payout: ~72%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for altcoin season momentum\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'USD/JPY', 'category': 'forex', 'text': "🖤 USD/JPY — PUT (DOWN)\n📍 Entry Zone: 157.80 – 157.95\n️ Expiry: 10 minutes\n Payout: ~85%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for rejection at 1H resistance zone\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'GBP/JPY', 'category': 'forex', 'text': " GBP/JPY — CALL (UP)\n📍 Entry Zone: 199.50 – 199.80\n️ Expiry: 15 minutes\n Payout: ~83%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for London session breakout\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'BNB/USDT', 'category': 'crypto', 'text': "🖤 BNB/USDT — PUT (DOWN)\n📍 Entry Zone: 605 – 615\n⏱️ Expiry: 10 minutes\n💰 Payout: ~74%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for exchange volume drop\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'AUD/USD', 'category': 'forex', 'text': "🤍 AUD/USD — CALL (UP)\n📍 Entry Zone: 0.6580 – 0.6595\n⏱️ Expiry: 10 minutes\n💰 Payout: ~81%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for Australian data release\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'USD/CAD', 'category': 'forex', 'text': " USD/CAD — PUT (DOWN)\n Entry Zone: 1.3720 – 1.3735\n⏱️ Expiry: 5 minutes\n💰 Payout: ~78%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for oil price spike\n\n Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'ADA/USDT', 'category': 'crypto', 'text': "🤍 ADA/USDT — CALL (UP)\n📍 Entry Zone: 0.4520 – 0.4550\n⏱️ Expiry: 20 minutes\n💰 Payout: ~71%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for ecosystem upgrade news\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'EUR/GBP', 'category': 'forex', 'text': " EUR/GBP — PUT (DOWN)\n Entry Zone: 0.8550 – 0.8565\n️ Expiry: 5 minutes\n💰 Payout: ~73%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for UK data beat\n\n Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'XAU/USD', 'category': 'metals', 'text': "🖤 XAU/USD — PUT (DOWN)\n📍 Entry Zone: 2340 – 2345\n⏱️ Expiry: 10 minutes\n💰 Payout: ~81%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for Fed hawkish comments\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'DOGE/USDT', 'category': 'crypto', 'text': "🤍 DOGE/USDT — CALL (UP)\n Entry Zone: 0.1580 – 0.1600\n⏱️ Expiry: 15 minutes\n💰 Payout: ~70%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for social volume spike\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'NZD/USD', 'category': 'forex', 'text': "🖤 NZD/USD — PUT (DOWN)\n📍 Entry Zone: 0.6150 – 0.6165\n⏱️ Expiry: 10 minutes\n💰 Payout: ~77%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for RBNZ hawkish stance\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'AVAX/USDT', 'category': 'crypto', 'text': "🤍 AVAX/USDT — CALL (UP)\n📍 Entry Zone: 38.50 – 39.20\n⏱️ Expiry: 20 minutes\n💰 Payout: ~73%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for subnet activity surge\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'EUR/JPY', 'category': 'forex', 'text': "🖤 EUR/JPY — PUT (DOWN)\n📍 Entry Zone: 169.00 – 169.30\n⏱️ Expiry: 15 minutes\n💰 Payout: ~82%\n📐 Stake: $5-10 per trade (1% rule)\n Wait for BOJ intervention threat\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'XAG/USD', 'category': 'metals', 'text': "🤍 XAG/USD — CALL (UP)\n📍 Entry Zone: 27.80 – 28.10\n⏱️ Expiry: 15 minutes\n💰 Payout: ~78%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for gold/silver ratio compression\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'XRP/USDT', 'category': 'crypto', 'text': "🖤 XRP/USDT — PUT (DOWN)\n Entry Zone: 0.5420 – 0.5450\n⏱️ Expiry: 10 minutes\n💰 Payout: ~74%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for regulatory FUD wave\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'USD/CHF', 'category': 'forex', 'text': "🤍 USD/CHF — CALL (UP)\n📍 Entry Zone: 0.8920 – 0.8935\n⏱️ Expiry: 5 minutes\n💰 Payout: ~80%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for SNB intervention signals\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'LINK/USDT', 'category': 'crypto', 'text': "🤍 LINK/USDT — CALL (UP)\n Entry Zone: 18.20 – 18.50\n⏱️ Expiry: 20 minutes\n💰 Payout: ~72%\n📐 Stake: $5-10 per trade (1% rule)\n Wait for CCIP adoption news\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'GBP/CAD', 'category': 'forex', 'text': "🖤 GBP/CAD — PUT (DOWN)\n📍 Entry Zone: 1.7620 – 1.7640\n⏱️ Expiry: 15 minutes\n💰 Payout: ~76%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for CAD strength on oil\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'DOT/USDT', 'category': 'crypto', 'text': " DOT/USDT — CALL (UP)\n Entry Zone: 7.80 – 8.00\n⏱️ Expiry: 20 minutes\n💰 Payout: ~71%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for parachain auction hype\n\n Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'AUD/JPY', 'category': 'forex', 'text': "🖤 AUD/JPY — PUT (DOWN)\n📍 Entry Zone: 98.50 – 98.70\n⏱️ Expiry: 10 minutes\n💰 Payout: ~79%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for risk-off sentiment\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'UNI/USDT', 'category': 'crypto', 'text': " UNI/USDT — CALL (UP)\n📍 Entry Zone: 12.40 – 12.60\n⏱️ Expiry: 15 minutes\n💰 Payout: ~70%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for DeFi volume recovery\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'CAD/JPY', 'category': 'forex', 'text': "🤍 CAD/JPY — CALL (UP)\n📍 Entry Zone: 106.20 – 106.40\n⏱️ Expiry: 10 minutes\n💰 Payout: ~77%\n📐 Stake: $5-10 per trade (1% rule)\n Wait for commodity currency flow\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'},
    {'pair': 'MATIC/USDT', 'category': 'crypto', 'text': "🖤 MATIC/USDT — PUT (DOWN)\n📍 Entry Zone: 0.7100 – 0.7150\n⏱️ Expiry: 15 minutes\n💰 Payout: ~73%\n📐 Stake: $5-10 per trade (1% rule)\n🔁 Wait for L2 competition pressure\n\n🖤 Protect capital first. Profit follows.", 'image': 'usdjpy_down.png'},
    {'pair': 'NZD/JPY', 'category': 'forex', 'text': "🤍 NZD/JPY — CALL (UP)\n📍 Entry Zone: 91.80 – 92.00\n⏱️ Expiry: 10 minutes\n💰 Payout: ~75%\n Stake: $5-10 per trade (1% rule)\n🔁 Wait for carry trade momentum\n\n🤍 Protect capital first. Profit follows.", 'image': 'xau_up.png'}
]

# ==================== HANDLERS ====================
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    user = db.get_user(chat_id)
    if user is None:
        user = {
            "notif_freq": 0, "last_notif": 0, "balance": 0, "risk": 0, 
            "max_trades": 0, "trading_mode": None, "trial_start": datetime.now().strftime("%Y-%m-%d"),
            "subscription_end": None, "is_approved": True  # 🔒 TODO: WHITE LIST -> change to False later
        }
        db.save_user(chat_id, user)
        
        try:
            username = message.from_user.username or "нет"
            first_name = message.from_user.first_name or "User"
            admin_text = (
                f" **New Access Request**\n\n"
                f"👤 Name: `{first_name}`\n"
                f"🆔 ID: `{chat_id}`\n"
                f" Username: @{username}\n\n"
                f"Tap to approve:"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{chat_id}"))
            bot.send_message(ADMIN_ID, admin_text, reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass # Игнорируем, если админ ещё не запускал бота
    
    # 🔒 TODO: WHITE LIST -> раскомментируй эти 3 строки, когда будешь готов:
    # if not user.get("is_approved", False):
    #     bot.send_message(chat_id, "🔒 Access Restricted. Contact @YourSupport to get approved.")
    #     return

    mode = user.get("trading_mode")
    if mode is None:
        text = WELCOME_MSG + "\n\n👇 First, select your preferred market:"
        markup = get_mode_markup()
    else:
        text = "Welcome back. Ready to execute?"
        markup = get_main_markup()
        
    try:
        with open('welcome.png', 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    except FileNotFoundError:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("mode_"))
def set_mode(call):
    chat_id = call.message.chat.id
    mode = call.data.split("_")[1]
    bot.answer_callback_query(call.id, "Mode updated!")
    
    user = db.get_user(chat_id) or {}
    user["trading_mode"] = mode
    db.save_user(chat_id, user)
    
    bot.send_message(chat_id, f"✅ Trading mode: {mode.title()}\nYou can change it anytime via /menu")
    time.sleep(0.5)
    
    text = "📋 Main menu:"
    markup = get_main_markup()
    try:
        with open('menu.png', 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    except FileNotFoundError:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "menu_cmd")
def menu_callback(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    user = db.get_user(chat_id) or {}
    mode = user.get("trading_mode") or "all"
    text = f"⚙️ Trading Preferences\n\nCurrent Mode: {mode.title()}\n\nSelect to change:"
    bot.send_message(chat_id, text, reply_markup=get_mode_markup())

@bot.message_handler(commands=['menu'])
def show_menu(message):
    chat_id = message.chat.id
    text = "📋 Main menu:"
    markup = get_main_markup()
    try:
        with open('menu.png', 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    except FileNotFoundError:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "guide_cmd")
def show_guide(call):
    bot.answer_callback_query(call.id)
    guide_text = (
        "📘 Quick Start Guide\n\n"
        "1️⃣ Select your market: /menu\n"
        "2️⃣ Calculate risk: /risk\n"
        "3️⃣ Get signal: Tap READY\n"
        "4️⃣ Trade: Follow entry zone + expiry\n"
        "5️⃣ Track: Mark Win/Loss/Skip\n\n"
        "️ Rules:\n"
        "• Risk max 1-2% per trade\n"
        "• Never double down\n"
        "• Skip if you miss entry\n"
        "• Stop after 3 losses/day\n\n"
        " Support: @YourSupport"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_main"))
    try:
        with open('guide.png', 'rb') as photo:
            bot.send_photo(call.message.chat.id, photo, caption=guide_text, reply_markup=markup)
    except FileNotFoundError:
        bot.send_message(call.message.chat.id, guide_text, reply_markup=markup)

@bot.message_handler(commands=['guide'])
def guide_cmd(message):
    show_guide(message)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main_menu(call):
    bot.answer_callback_query(call.id)
    chat_id = call.message.chat.id
    text = " Main menu:"
    markup = get_main_markup()
    try:
        with open('menu.png', 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    except FileNotFoundError:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "notif_settings")
def show_notif_settings(call):
    bot.answer_callback_query(call.id)
    text = "🔔 Notification Settings\n\nChoose reminder frequency:"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⏱️ Every 2 hours", callback_data="notif_2h"),
        types.InlineKeyboardButton("⏱️ Every 4 hours", callback_data="notif_4h"),
        types.InlineKeyboardButton("🌍 Session alerts", callback_data="notif_session"),
        types.InlineKeyboardButton("🔕 Mute reminders", callback_data="notif_off")
    )
    bot.send_message(call.message.chat.id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("notif_"))
def setup_notif(call):
    chat_id = call.message.chat.id
    freq_map = {"notif_2h": 7200, "notif_4h": 14400, "notif_session": 14400, "notif_off": 0}
    freq = freq_map.get(call.data, 0)
    
    user = db.get_user(chat_id) or {}
    user["notif_freq"] = freq
    user["last_notif"] = time.time()
    db.save_user(chat_id, user)
    
    bot.answer_callback_query(call.id, "Settings saved!")
    text = "🔕 Notifications muted." if freq == 0 else f"✅ Notifications set to every {freq//3600} hour(s)."
    bot.send_message(chat_id, text)
    time.sleep(0.5)
    
    text = "📋 Main menu:"
    markup = get_main_markup()
    try:
        with open('menu.png', 'rb') as photo:
            bot.send_photo(chat_id, photo, caption=text, reply_markup=markup)
    except FileNotFoundError:
        bot.send_message(chat_id, text, reply_markup=markup)

# ==================== RISK CALCULATOR ====================
@bot.message_handler(commands=['risk'])
def risk_cmd(message):
    start_risk_flow(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "open_risk")
def risk_btn(call):
    bot.answer_callback_query(call.id)
    start_risk_flow(call.message.chat.id)

def start_risk_flow(chat_id):
    msg = bot.send_message(chat_id, "💰 Enter your current account balance ($):")
    bot.register_next_step_handler(msg, risk_step_balance)

def risk_step_balance(message):
    chat_id = message.chat.id
    try:
        bal = float(message.text.replace("$", "").replace(",", "").strip())
        if bal <= 0: raise ValueError
        user = db.get_user(chat_id) or {}
        user["balance"] = bal
        db.save_user(chat_id, user)
        msg = bot.send_message(chat_id, "️ Select risk per trade (reply with number):\n1️⃣ 1% (Conservative)\n2️⃣ 2% (Standard)\n3️⃣ 3% (Aggressive)")
        bot.register_next_step_handler(msg, lambda m: risk_step_percent(m, bal))
    except (ValueError, AttributeError):
        bot.send_message(chat_id, "❌ Invalid input. Please enter a valid number (e.g., 1000). Try again: /risk")

def risk_step_percent(message, balance):
    chat_id = message.chat.id
    txt = message.text.strip()
    if txt in ['1', '2', '3']:
        pct = int(txt)
        user = db.get_user(chat_id) or {}
        user["risk"] = pct
        db.save_user(chat_id, user)
        msg = bot.send_message(chat_id, " Max trades per day (reply with number):\n3️⃣ 3 trades\n5️ 5 trades")
        bot.register_next_step_handler(msg, lambda m: risk_step_trades(m, balance, pct))
    else:
        bot.send_message(chat_id, "❌ Please reply with 1, 2, or 3.")

def risk_step_trades(message, balance, risk_pct):
    chat_id = message.chat.id
    txt = message.text.strip()
    if txt in ['3', '5']:
        trades = int(txt)
        user = db.get_user(chat_id) or {}
        user["max_trades"] = trades
        db.save_user(chat_id, user)
        show_risk_result(chat_id, balance, risk_pct, trades)
    else:
        bot.send_message(chat_id, "❌ Please reply with 3 or 5.")
        msg = bot.send_message(chat_id, "📊 Max trades per day (reply with number):\n3️⃣ 3 trades\n5️⃣ 5 trades")
        bot.register_next_step_handler(msg, lambda m: risk_step_trades(m, balance, risk_pct))

def show_risk_result(chat_id, balance, risk_pct, max_trades):
    max_stake = balance * (risk_pct / 100)
    max_daily_loss = max_stake * max_trades
    daily_drawdown_pct = (max_daily_loss / balance) * 100
    text = (
        f"📊 Risk Management Profile\n\n"
        f"💵 Balance: ${balance:.2f}\n"
        f"🔹 Risk per trade: {risk_pct}% → Max Stake: ${max_stake:.2f}\n"
        f"📈 Max trades/day: {max_trades} → Max Daily Loss: ${max_daily_loss:.2f} ({daily_drawdown_pct:.1f}%)\n\n"
        f"📘 Discipline Rules:\n"
        f"• Never risk more than {risk_pct}% on a single setup.\n"
        f"• Stop trading if daily loss hits ${max_daily_loss:.2f}.\n"
        f"• Compounding requires consistency, not luck.\n\n"
        f"Trade safe. I'll handle the edge. 🤍\n\n Ready to execute? Tap below:"
    )
    bot.send_message(chat_id, text, reply_markup=get_main_markup())

# ==================== STATISTICS ====================
def record_result(chat_id, result):
    global stats_data
    if chat_id not in stats_data:
        stats_data[chat_id] = {"total":0, "wins":0, "losses":0, "skipped":0, "current_streak":0, "best_streak":0, "history":[]}
    s = stats_data[chat_id]
    s["total"] += 1
    if result == "win":
        s["wins"] += 1
        s["current_streak"] += 1
        if s["current_streak"] > s["best_streak"]: s["best_streak"] = s["current_streak"]
    elif result == "loss":
        s["losses"] += 1
        s["current_streak"] = 0
    elif result == "skip":
        s["skipped"] += 1
    s["history"].append({"res": result, "date": time.strftime("%Y-%m-%d")})
    save_stats(stats_data)

def get_stats_text(chat_id):
    if chat_id not in stats_data or stats_data[chat_id]["total"] == 0:
        return "📊 No trading data yet. Take some signals and record your results!"
    s = stats_data[chat_id]
    win_rate = (s["wins"] / s["total"]) * 100 if s["total"] > 0 else 0
    return (
        f"📊 Your Trading Statistics\n\n"
        f"🔹 Total Signals: {s['total']}\n"
        f"✅ Wins: {s['wins']} ({win_rate:.1f}%)\n"
        f" Losses: {s['losses']}\n"
        f"⏭ Skipped: {s['skipped']}\n\n"
        f"🔥 Current Win Streak: {s['current_streak']}\n"
        f" Best Win Streak: {s['best_streak']}\n\n"
        f" Consistency is key. Keep tracking!"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("vote_"))
def handle_vote(call):
    chat_id = call.message.chat.id
    result = call.data.split("_")[1]
    record_result(chat_id, result)
    try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=get_post_vote_markup())
    except: pass
    try: bot.answer_callback_query(call.id)
    except: pass

@bot.callback_query_handler(func=lambda call: call.data == "stats_btn")
def stats_btn_handler(call):
    bot.answer_callback_query(call.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➡️ Next Signal", callback_data="ready_signal"))
    bot.send_message(call.message.chat.id, get_stats_text(call.message.chat.id), reply_markup=markup)

@bot.message_handler(commands=['stats'])
def show_stats_cmd(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➡️ Next Signal", callback_data="ready_signal"))
    bot.send_message(message.chat.id, get_stats_text(message.chat.id), reply_markup=markup)

# ==================== SIGNALS ====================
@bot.callback_query_handler(func=lambda call: call.data == 'ready_signal')
def send_one_signal(call):
    chat_id = call.message.chat.id
    bot.answer_callback_query(call.id)
    
    if not check_access(chat_id):
        bot.send_message(chat_id, get_paywall_message())
        return

    user = db.get_user(chat_id) or {}
    mode = user.get("trading_mode") or "all"
    
    found_signal = None
    attempts = 0
    max_attempts = len(signals) * 2
    while attempts < max_attempts:
        idx = random.randint(0, len(signals) - 1)
        sig = signals[idx]
        if mode == "all" or sig["category"] == mode:
            found_signal = sig
            break
        attempts += 1

    if not found_signal:
        bot.send_message(chat_id, "⚠️ No signals available for your selected mode right now.")
        return

    temp_msg = bot.send_message(chat_id, "🔍 Market analysis in progress, please wait for signal...")
    time.sleep(2)

    final_text = found_signal['text']
    live_price = get_live_price(found_signal['pair'])
    
    if live_price:
        lines = final_text.split('\n')
        new_lines = []
        inserted = False
        for line in lines:
            if not inserted and ("Entry Zone" in line or "Expiry" in line):
                new_lines.append(f"💲 Current Price: {live_price} (Live)")
                inserted = True
            new_lines.append(line)
        final_text = '\n'.join(new_lines)
    else:
        if "OTC" in found_signal['pair'].upper():
            final_text = " OTC Algorithm Active\n" + final_text
        else:
            final_text = " Live Analysis Active\n" + final_text

    try:
        if os.path.exists(found_signal['image']):
            with open(found_signal['image'], 'rb') as img:
                bot.send_photo(chat_id, img, caption=final_text, reply_markup=get_vote_markup())
        else:
            bot.send_message(chat_id, final_text, reply_markup=get_vote_markup())
    except Exception as e:
        bot.send_message(chat_id, f"⚠️ Error: {e}")

    try: bot.delete_message(chat_id, temp_msg.message_id)
    except: pass
    
# ==================== ADMIN & STATUS ====================
@bot.message_handler(commands=['activate'])
def activate_premium(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "🚫 Admin only.")
        return
    args = message.text.split()
    if len(args) != 3:
        bot.send_message(message.chat.id, "❌ Format: /activate <chat_id> <days>")
        return
    try:
        target_id = int(args[1])
        days = int(args[2])
        target_user = db.get_user(target_id) or {}
        target_user["subscription_end"] = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        target_user["is_approved"] = True
        db.save_user(target_id, target_user)
        bot.send_message(message.chat.id, f"✅ Activated {days} days for user {target_id}.")
        try: bot.send_message(target_id, "🎉 Your premium access has been activated! Thank you.")
        except: pass
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")

@bot.message_handler(commands=['status'])
def check_status(message):
    chat_id = message.chat.id
    user = db.get_user(chat_id) or {}
    today = datetime.now()
    sub_end = user.get("subscription_end")
    trial_start = user.get("trial_start")
    
    if sub_end and datetime.strptime(sub_end, "%Y-%m-%d") >= today:
        days_left = (datetime.strptime(sub_end, "%Y-%m-%d") - today).days
        text = f"👑 Premium Active\n📅 Expires in: {days_left} days"
    elif trial_start and (today - datetime.strptime(trial_start, "%Y-%m-%d")).days < 1:
        days_left = 1 - (today - datetime.strptime(trial_start, "%Y-%m-%d")).days
        text = f"🆓 Trial Active\n📅 Days left: {days_left}"
    else:
        text = "❌ No active access. Contact @YourSupport"
    bot.send_message(chat_id, text)

# ==================== SCHEDULER ====================
def notification_scheduler():
    while True:
        now = time.time()
        all_users = db.get_all_users()
        for chat_id, data in all_users.items():
            freq = data.get("notif_freq", 0)
            last = data.get("last_notif", 0)
            if freq > 0 and (now - last) >= freq:
                try:
                    reminder = (
                        "🔔 Market Update\n\n"
                        "📊 Active setups forming in your selected market.\n"
                        "Don't miss the next opportunity.\n\n"
                        "🚀 Tap READY to get your signal now.\n"
                        "💡 Or check /stats to review your performance."
                    )
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("🔕 Mute reminders", callback_data="notif_off"))
                    bot.send_message(chat_id, reminder, reply_markup=markup)
                    
                    data["last_notif"] = now
                    db.save_user(chat_id, data)
                except Exception:
                    pass
        time.sleep(60)
        
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def quick_approve(call):
    if call.message.chat.id != ADMIN_ID: return
    target_id = int(call.data.split("_")[1])
    user = db.get_user(target_id)
    if user:
        user["is_approved"] = True
        user["trial_start"] = datetime.now().strftime("%Y-%m-%d")
        db.save_user(target_id, user)
        bot.answer_callback_query(call.id, "✅ Approved!")
        bot.edit_message_text("✅ User approved & access granted.", call.message.chat.id, call.message.message_id)
        try:
            bot.send_message(target_id, "🎉 Access granted! Type /start to begin.")
        except: pass        

if __name__ == '__main__':
    print("✅ Bot is running. Scheduler active.")
    print("🌐 Running on Render 24/7...")
    
    # Запускаем шедулер
    threading.Thread(target=notification_scheduler, daemon=True).start()
    
    # Запускаем бота с авто-перезапуском при ошибках
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            print(f"⚠️ Error: {e}")
            print("🔄 Restarting in 5 seconds...")
            time.sleep(5)
    
    
