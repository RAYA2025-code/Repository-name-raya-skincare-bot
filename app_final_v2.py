#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import requests
import random
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
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

# 確保資料存放路徑正確
BASE_DIR = "/app/data" if os.path.exists("/app/data") else os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

LOCATION_COORDINATES = {
    "台北": {"lat": 25.03, "lon": 121.56}, "新北": {"lat": 25.01, "lon": 121.46},
    "桃園": {"lat": 24.99, "lon": 121.31}, "台中": {"lat": 24.14, "lon": 120.67},
    "台南": {"lat": 22.99, "lon": 120.21}, "高雄": {"lat": 22.62, "lon": 120.31},
    "新竹": {"lat": 24.81, "lon": 120.96}, "彰化": {"lat": 24.08, "lon": 120.54},
    "宜蘭": {"lat": 24.75, "lon": 121.75}, "花蓮": {"lat": 23.97, "lon": 121.60},
    "苗栗": {"lat": 24.56, "lon": 120.82}, "南投": {"lat": 23.91, "lon": 120.68},
    "雲林": {"lat": 23.70, "lon": 120.43}, "嘉義": {"lat": 23.48, "lon": 120.44},
    "屏東": {"lat": 22.67, "lon": 120.48}, "台東": {"lat": 22.75, "lon": 121.14},
    "基隆": {"lat": 25.12, "lon": 121.74}
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
    if location: 
        db[user_id]["location"] = location
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

# ============================================================================
# 3. 內容生成器
# ============================================================================
def get_daily_content(scenario, location, temp_max, temp_min, temp_feel, humi, uvi, aqi):
    root = os.path.dirname(os.path.abspath(__file__))
    now = datetime.now()
    weekday_idx = now.weekday()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    
    try:
        # 請確保資料夾下有這些 JSON 檔案
        with open(os.path.join(root, "strategies_v3.json"), 'r', encoding='utf-8') as f:
            strategies = json.load(f)
        
        # 模擬的主題與金句數據庫（若檔案不存在則使用預設值）
        theme_name = ["本週肌膚節奏", "肌膚科學教室", "中場修復儀式", "環境觀察指南", "戶外防護特輯", "生活保養美學", "週末深層修護"][weekday_idx]
        theme_msg = "每一次的堅持，都是在為未來的自己投資。"
        
        strat = random.choice(strategies.get(scenario, strategies["seasonal"]))

        msg = (
            f"嗨，親愛的，新的一天開始了 💪\n"
            f"{location} {now.strftime('%m/%d')} ({weekdays[weekday_idx]}) RAYA迷你肌膚日報\n"
            f"🌡 氣溫 {int(temp_max)}°C / {int(temp_min)}°C\n"
            f"🌤 體感 {int(temp_feel)}°C\n"
            f"💧 濕度 {humi}%\n"
            f"☀️ 紫外線 {uvi}\n"
            f"🍃 空氣 AQI {aqi}\n\n"
            f"｜核心肌膚對策｜\n"
            f"• {strat['content']}\n"
            f"{strat.get('insight', '你知道嗎？良好的作息是健康肌膚的基石。✨')}\n\n"
            f"｜今日建議動作｜\n"
        )
        
        for action in strat['actions']:
            msg += f"✓ {action}\n"
            
        msg += (
            f"\n｜{theme_name}｜(每天主題不同)\n"
            f"• {theme_msg}\n\n"
            f"RAYA—有感的肌膚進化"
        )
        return msg
    except Exception as e:
        return f"親愛的，今日也要好好愛護肌膚喔！💚\n(提示: 請確認 strategies_v3.json 檔案已上傳)"

# ============================================================================
# 4. Webhook 與 訊息處理
# ============================================================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    
    if text == "測試推播":
        run_push_job()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚀 測試推播已發送！"))
    elif "我在" in text:
        new_loc = text.replace("我在", "").strip()[:2]
        if new_loc in LOCATION_COORDINATES:
            update_subscription(user_id, True, new_loc)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已為您設定地區：{new_loc}，明天 08:00 見 💚"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 目前不支援此地區，請輸入正確縣市名稱（如：我在台北）。"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="👋 您好！我是 RAYA 芮亞肌膚助手。\n輸入「我在台北」即可訂閱每日保養日報！"))

def run_push_job():
    user_db = load_user_db()
    for user_id, info in user_db.items():
        if not info.get("subscribed") or info.get("location") == "未設定": continue
        try:
            loc = info["location"]
            coord = LOCATION_COORDINATES.get(loc, LOCATION_COORDINATES["台北"])
            w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={coord['lat']}&lon={coord['lon']}&appid={WEATHER_API_KEY}&units=metric&lang=zh_tw"
            w = requests.get(w_url).json()
            
            temp_max = w['main'].get('temp_max', w['main']['temp'])
            temp_min = w['main'].get('temp_min', w['main']['temp'])
            temp_feel = w['main'].get('feels_like', w['main']['temp'])
            humi = w['main']['humidity']
            
            # 場景判斷邏輯
            if temp_max >= 28: scenario = "wet_heat" if hum
