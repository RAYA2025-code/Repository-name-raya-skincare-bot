import os
import json
import requests
import random
from datetime import datetime
from typing import Dict, Optional
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, FollowEvent
)
from apscheduler.schedulers.background import BackgroundScheduler
from filelock import FileLock

app = Flask(__name__)

# ============================================================================
# 1. 配置與路徑
# ============================================================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

BASE_DIR = "/app/data" if os.path.exists("/app/data") else os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

LOCATION_COORDINATES = {
    "台北": {"lat": 25.03, "lon": 121.56}, "新北": {"lat": 25.01, "lon": 121.46},
    "桃園": {"lat": 24.99, "lon": 121.31}, "台中": {"lat": 24.14, "lon": 120.67},
    "台南": {"lat": 22.99, "lon": 120.21}, "高雄": {"lat": 22.62, "lon": 120.31},
    "新竹": {"lat": 24.81, "lon": 120.96}, "彰化": {"lat": 24.08, "lon": 120.54},
    "宜蘭": {"lat": 24.75, "lon": 121.75}, "花蓮": {"lat": 23.97, "lon": 121.60}
}

# ============================================================================
# 2. 資料庫操作
# ============================================================================
def load_user_db():
    if not os.path.exists(USER_DB_FILE): return {}
    try:
        with open(USER_DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_user_db(db):
    lock = FileLock(f"{USER_DB_FILE}.lock")
    with lock:
        with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

def update_subscription(user_id, status, location=None):
    db = load_user_db()
    if user_id not in db:
        db[user_id] = {"location": location or "未設定", "subscribed": False}
    db[user_id]["subscribed"] = status
    if location: db[user_id]["location"] = location
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

# ============================================================================
# 3. 內容生成器 (200+ 種組合)
# ============================================================================
def get_daily_content(scenario, location, temp, humi, weather_desc):
    root = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(root, "core_strategies_v2.json"), 'r', encoding='utf-8') as f: strategies = json.load(f)
        with open(os.path.join(root, "greetings_v2.json"), 'r', encoding='utf-8') as f: greetings = json.load(f)
        with open(os.path.join(root, "philosophy_quotes_100_v2.json"), 'r', encoding='utf-8') as f: quotes = json.load(f)["quotes"]
        with open(os.path.join(root, "third_modules_v2.json"), 'r', encoding='utf-8') as f: modules = json.load(f)

        greet = random.choice(greetings.get(scenario, greetings["general"]))
        strat = random.choice(strategies[scenario])
        quote = random.choice(quotes["original_healing_quotes"]["quotes"])
        module = random.choice(modules["skincare_science"])

        return (
            f"{greet}\n"
            f"RAYA | {location} {datetime.now().strftime('%m/%d')} 肌膚日報\n\n"
            f"🌡️ {temp}°C | 💧 {humi}% | ☁️ {weather_desc}\n\n"
            f"｜核心肌膚對策｜\n• {strat['content']}\n\n"
            f"｜建議動作｜\n{ ' / '.join(strat['actions']) }\n\n"
            f"｜皮膚科學快訊｜\n{module['content']}\n\n"
            f"「{quote}」\n"
            f"RAYA—有感的肌膚進化 💚"
        )
    except Exception as e:
        return f"RAYA 提醒您：今日也要好好愛護肌膚喔！(內容讀取錯誤: {str(e)})"

def run_push_job():
    """定時推播任務：確保每天 08:00 只執行一次"""
    print(f"⏰ [RAYA] 定時任務執行中: {datetime.now()}")
    user_db = load_user_db()
    for user_id, info in user_db.items():
        if not info.get("subscribed") or info.get("location") == "未設定": continue
        try:
            loc = info["location"]
            coord = LOCATION_COORDINATES.get(loc, LOCATION_COORDINATES["台北"])
            w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={coord['lat']}&lon={coord['lon']}&appid={WEATHER_API_KEY}&units=metric&lang=zh_tw"
            w = requests.get(w_url, timeout=10).json()
            temp, humi = w['main']['temp'], w['main']['humidity']
            
            # 簡化的場景判斷
            if temp >= 28: scenario = "wet_heat" if humi > 60 else "dry_heat"
            elif temp < 15: scenario = "wet_cold" if humi > 60 else "dry_cold"
            else: scenario = "seasonal"

            msg = get_daily_content(scenario, loc, temp, humi, w['weather'][0]['description'])
            line_bot_api.push_message(user_id, TextSendMessage(text=msg))
        except Exception as e:
            print(f"❌ 推播失敗 {user_id}: {e}")

# ============================================================================
# 4. 訊息處理 (含總編測試模式)
# ============================================================================
@app.route("/callback", methods=['POST'])
def callback
