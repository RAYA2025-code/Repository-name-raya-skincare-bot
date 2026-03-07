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
# 2. 資料庫操作 (略，保持不變)
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
    if user_id not in db: db[user_id] = {"location": location or "未設定", "subscribed": False}
    db[user_id]["subscribed"] = status
    if location: db[user_id]["location"] = location
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

# ============================================================================
# 3. 內容生成器 - RAYA 旗艦格式
# ============================================================================
def get_daily_content(scenario, location, temp_max, temp_min, temp_feel, humi, uvi, aqi):
    root = os.path.dirname(os.path.abspath(__
