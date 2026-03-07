import os
import json
import requests
import random
from datetime import datetime
from typing import Dict
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, 
    FollowEvent
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

BASE_DIR = "/app/data" if os.path.exists("/app/data") else os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

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
# 2. 數據庫處理
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

def update_subscription(user_id: str, status: bool, location: str = None):
    db = load_user_db()
    if user_id not in db:
        db[user_id] = {"location": location or "未設定", "subscribed": False}
    
    db[user_id]["subscribed"] = status
    if location:
        db[user_id]["location"] = location
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

# ============================================================================
# 3. 推播引擎
# ============================================================================

def get_weather_data(lat, lon, location):
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=zh_tw"
    try:
        res = requests.get(url, timeout=10).json()
        return {
            "temp": res['main']['temp'],
            "humidity": res['main']['humidity'],
            "desc": res['weather'][0]['description']
        }
    except:
        return {"temp": 25, "humidity": 60, "desc": "資料讀取中"}

def run_push_job():
    print(f"⏰ RAYA 推播任務啟動：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        content_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core_strategies_v2.json")
        with open(content_path, 'r', encoding='utf-8') as f:
            strategies = json.load(f)
    except Exception as e:
        print(f"❌ 內容庫讀取失敗: {e}")
        return

    user_db = load_user_db()
    success_count = 0
    
    for user_id, info in user_db.items():
        if not info.get("subscribed", False) or info.get("location") == "未設定":
            continue

        try:
            location = info.get("location")
            coords = LOCATION_COORDINATES.get(location, LOCATION_COORDINATES["台北"])
            weather = get_weather_data(coords["lat"], coords["lon"], location)
            
            # 智慧場景判斷
            temp, humi = weather['temp'], weather['humidity']
            if temp >= 28:
                scenario = "wet_heat" if humi > 60 else "dry_heat"
            elif temp < 15:
                scenario = "wet_cold" if humi > 60 else "dry_cold"
            else:
                scenario = "seasonal"
            
            selected_tip = random.choice(strategies[scenario])
            
            msg = (
                f"🌸 RAYA 迷你肌膚日報｜{location}\n\n"
                f"🌡️ 氣溫 {temp}°C / 💧 濕度 {humi}%\n"
                f"☁️ 天氣狀況：{weather['desc']}\n\n"
                f"｜核心肌膚對策｜\n"
                f"• {selected_tip['content']}\n\n"
                f"｜建議動作｜\n"
                f"{' / '.join(selected_tip['actions'])}\n\n"
                f"讓肌膚與天氣和諧共處 💚"
            )
            
            line_bot_api.push_message(user_id, TextSendMessage(text=msg))
            success_count += 1
        except Exception as e:
            print(f"❌ {user_id} 發送失敗: {e}")

    print(f"🎉 任務完成，成功推播人數：{success_count}")

# ============================================================================
# 4. 訊息處理器
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
    # 初始化資料，預設不主動訂閱，等待地區設定
    update_subscription(user_id, False) 
    welcome_text = (
        "您好，我是 RAYA 專屬肌膚管家 💚\n\n"
        "為了每天早上為您精準推送「迷你肌膚日報」，請告訴我您所在的地區。\n\n"
        "👉 請回覆：我在台北、我在台中..."
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    
    if text == "測試推播":
        run_push_job()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚀 RAYA 測試指令已發出！"))
        return

    if "我在" in text or "地區" in text:
        new_loc = text.replace("我在", "").replace("地區", "").strip()[:2]
        if new_loc in LOCATION_COORDINATES:
            update_subscription(user_id, True, new_loc)
            response = f"✅ 歡迎訂閱 RAYA 迷你肌膚日報！\n已記錄地區：{new_loc}。\n明天 08:00 我們準時見 💚"
        else:
            response = "目前僅支援台灣主要縣市，請輸入正確地名（如：台北、桃園）。"
            
    elif text == "取消推播":
        update_subscription(user_id, False)
        response = "已暫停 RAYA 每日推播，隨時歡迎您再次回來 💚"
        
    else:
        response = "想修改地區或訂閱日報嗎？請輸入「我在台北」或「我在台中」！"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=response))

# ============================================================================
# 5. 啟動入口
# ============================================================================

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(run_push_job, 'cron', hour=8, minute=0)
    scheduler.start()
    
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
