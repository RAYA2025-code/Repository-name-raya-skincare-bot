import os
import json
import requests
import re
from datetime import datetime
from typing import Dict, Optional, List
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    FollowEvent, UnfollowEvent
)
from apscheduler.schedulers.background import BackgroundScheduler
from filelock import FileLock

app = Flask(__name__)

# ============================================================================
# 1. 環境變數與路徑設定
# ============================================================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 資料存儲路徑 (優先使用掛載路徑)
BASE_DIR = "/app/data" if os.path.exists("/app/data") else os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")
LOG_FILE = os.path.join(BASE_DIR, "usage_log.json")
CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "content_libraries")

# 地區座標對應 (推播天氣用)
LOCATION_COORDINATES = {
    "台北": {"lat": 25.03, "lon": 121.56}, "新北": {"lat": 25.01, "lon": 121.46},
    "桃園": {"lat": 24.99, "lon": 121.31}, "台中": {"lat": 24.14, "lon": 120.67},
    "台南": {"lat": 22.99, "lon": 120.21}, "高雄": {"lat": 22.62, "lon": 120.31},
    "基隆": {"lat": 25.12, "lon": 121.74}, "新竹": {"lat": 24.81, "lon": 120.96},
    "苗栗": {"lat": 24.56, "lon": 120.82}, "彰化": {"lat": 24.08, "lon": 120.54},
    "南投": {"lat": 23.91, "lon": 120.68}, "雲林": {"lat": 23.70, "lon": 120.43},
    "嘉義": {"lat": 23.48, "lon": 120.44}, "屏東": {"lat": 22.67, "lon": 120.48},
    "宜蘭": {"lat": 24.75, "lon": 121.75}, "花蓮": {"lat": 23.97, "lon": 121.60},
    "台東": {"lat": 22.75, "lon": 121.14}
}

# ============================================================================
# 2. 數據庫處理函數
# ============================================================================

def load_user_db() -> Dict:
    if not os.path.exists(USER_DB_FILE): return {}
    try:
        with open(USER_DB_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_user_db(db: Dict):
    lock = FileLock(f"{USER_DB_FILE}.lock")
    with lock:
        with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

def update_subscription(user_id: str, status: bool, location: str = "台北"):
    db = load_user_db()
    if user_id not in db: db[user_id] = {"location": location}
    db[user_id]["subscribed"] = status
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

# ============================================================================
# 3. 推播核心引擎 (原本在 daily_pusher 的功能)
# ============================================================================

def get_weather_data(lat, lon, location):
    """獲取天氣數據"""
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=zh_tw"
    try:
        res = requests.get(url, timeout=10).json()
        return {
            "temp": res['main']['temp'],
            "humidity": res['main']['humidity'],
            "desc": res['weather'][0]['description']
        }
    except:
        return {"temp": 25, "humidity": 60, "desc": "晴朗"}

def run_push_job():
    """定時任務：每天早上 08:00 執行"""
    print(f"⏰ 推播任務啟動：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    user_db = load_user_db()
    if not user_db: return

    success_count = 0
    for user_id, info in user_db.items():
        if not info.get("subscribed", True): continue

        try:
            location = info.get("location", "台北")
            coords = LOCATION_COORDINATES.get(location, LOCATION_COORDINATES["台北"])
            weather = get_weather_data(coords["lat"], coords["lon"], location)
            
            # 這裡可以根據 weather 數據判斷推送內容
            # 簡化版：直接發送保養提醒
            msg = f"🌸 芮亞(Rui Ya)肌膚日報\n\n早安！今天{location}的天氣為「{weather['desc']}」，氣溫約 {weather['temp']}°C。\n濕度為 {weather['humidity']}%，建議今日重點：{'加強控油' if weather['humidity'] > 70 else '加強保濕'} 💚"
            
            line_bot_api.push_message(user_id, TextSendMessage(text=msg))
            success_count += 1
        except Exception as e:
            print(f"❌ 推播失敗 {user_id}: {e}")

    print(f"🎉 任務完成，成功推播人數：{success_count}")

# ============================================================================
# 4. LINE 訊息處理器 (Web 回覆部分)
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

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    update_subscription(user_id, True)
    welcome_text = "歡迎加入 RAYA！💚\n請告訴我您所在的地區（例如：台北、台中），我將每天早上為您提供肌膚保養建議。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    
    # 簡易地區設定邏輯
    if "我在" in text or "地區" in text:
        # 簡單提取地名（這裡可優化為正則表達式）
        new_loc = text.replace("我在", "").replace("地區", "").strip()[:2]
        if new_loc in LOCATION_COORDINATES:
            update_subscription(user_id, True, new_loc)
            response = f"✅ 已記錄！您的地區是 {new_loc}。明天 08:00 見！"
        else:
            response = "目前僅支援台灣主要縣市，請輸入正確的地名（如：台北、台中）。"
    elif text == "取消推播":
        update_subscription(user_id, False)
        response = "已暫停每日推播，期待下次再為您服務 💚"
    else:
        response = "想修改地區嗎？請輸入「我在台北」或「我在台中」！"
    
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))

# ============================================================================
# 5. 啟動入口
# ============================================================================

if __name__ == "__main__":
    # 啟動背景排程 (BackgroundScheduler 不會卡住 Flask)
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    # 設定 08:00 定時任務
    scheduler.add_job(run_push_job, 'cron', hour=8, minute=0)
    scheduler.start()
    
    print("🚀 系統已全面啟動：LINE 回覆與 08:00 推播任務同時運行中")
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
