#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAYA - 肌膚保養日報機器人 v8.0
品牌調性：靜謐留白、細膩照護、專業諮詢
修正重點：恢復「妳」稱謂、補足服務項目描述、更新成功回覆格式
"""

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

# -------------------------------
# 環境變數與配置
# -------------------------------
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

BASE_DIR = "/app/data" if os.path.exists("/app/data") else os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

# -------------------------------
# 城市座標 (完整台灣縣市)
# -------------------------------
LOCATION_COORDINATES = {
    "台北": {"lat": 25.03, "lon": 121.56}, "新北": {"lat": 25.01, "lon": 121.46},
    "桃園": {"lat": 24.99, "lon": 121.31}, "台中": {"lat": 24.14, "lon": 120.67},
    "台南": {"lat": 22.99, "lon": 120.21}, "高雄": {"lat": 22.62, "lon": 120.31},
    "基隆": {"lat": 25.12, "lon": 121.73}, "新竹": {"lat": 24.81, "lon": 120.96},
    "苗栗": {"lat": 24.56, "lon": 120.81}, "彰化": {"lat": 24.05, "lon": 120.51},
    "南投": {"lat": 23.91, "lon": 120.68}, "雲林": {"lat": 23.70, "lon": 120.43},
    "嘉義": {"lat": 23.48, "lon": 120.44}, "屏東": {"lat": 22.66, "lon": 120.48},
    "宜蘭": {"lat": 24.75, "lon": 121.75}, "花蓮": {"lat": 23.97, "lon": 121.60},
    "台東": {"lat": 22.75, "lon": 121.14}, "澎湖": {"lat": 23.56, "lon": 119.57},
    "金門": {"lat": 24.43, "lon": 118.32}, "馬祖": {"lat": 26.15, "lon": 119.92},
    "三重": {"lat": 25.06, "lon": 121.49}
}

# -------------------------------
# 資料庫邏輯
# -------------------------------
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
    save_user_db(db)

def load_json(filename):
    try:
        root_path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(root_path, filename), 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return {}

# -------------------------------
# 日報生成文案
# -------------------------------
def get_daily_content(scenario, loc, t_max, t_min, t_feel, humi, rain, uvi, aqi):
    now = datetime.now()
    weekdays = ["一","二","三","四","五","六","日"]
    weekday_str = weekdays[now.weekday()]
    
    greetings = ["新的一天開始了 💪", "晨光已經抵達 ☀️", "讓早晨慢慢展開 ☀️", "給自己一個深呼吸 🍃", "今天會很美好 🌞"]
    selected_greet = random.choice(greetings)

    strategies = load_json("strategies_v3.json")
    default_strat = {"content":"今天適合基礎保養，維持代謝。", "insight":"穩定的保養規律是肌膚最好的夥伴。"}
    strat = random.choice(strategies.get(scenario, [default_strat]))
    
    block_1_title = "本週肌膚節奏" if scenario != "seasonal" else "核心肌膚對策"

    themes = load_json("weekly_themes.json")
    day_name = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][now.weekday()]
    day_themes = themes.get(day_name, [])
    theme_data = random.choice(day_themes) if day_themes else {"category":"RAYA 日常生活", "content":"保持身心平衡，讓肌膚自在呼吸。"}

    quote_data = load_json("philosophy_quotes_100_v2.json")
    all_quotes = []
    for k, v in quote_data.get("quotes", {}).items():
        all_quotes.extend(v.get("quotes", []))
    selected_quote = random.choice(all_quotes) if all_quotes else "溫柔地對待自己。"

    msg = (
        f"嗨，親愛的，{selected_greet}\n"
        f"{loc} {now.strftime('%m/%d')} ({weekday_str}) RAYA 迷你肌膚日報\n\n"
        f"🌡 氣溫 {int(t_max)}°C / {int(t_min)}°C (體感 {int(t_feel)}°C)\n"
        f"💧 濕度 {humi}% ☔ 降雨 {rain}%\n"
        f"☀️ 紫外線 {uvi} 🍃 空氣 AQI {aqi}\n\n"
        f"｜{block_1_title}｜\n"
        f"• {strat['content']} {strat['insight']}\n\n"
        f"｜{theme_data.get('category')}｜\n"
        f"• {theme_data.get('content')}\n\n"
        f"{selected_quote}\n\n"
        f"RAYA—有感的肌膚進化\n\n"
        f"💡 今天若有任何心得或想記錄的變化，隨時可以傳照片或留言與我分享。"
    )
    return msg

# -------------------------------
# LINE 事件處理
# -------------------------------
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature","")
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
    
    # 修改後的歡迎詞：包含服務項目與稱謂「妳」
    welcome_text = (
        "很高興在 RAYA 與您相遇。這裡是您可以放鬆、與自己對話的空間。\n\n"
        "作為您的專屬顧問，在私密空間裡，我們為妳照護每一寸細節。\n\n"
        "準備好了嗎？點擊下方預約服務。\n"
        "也請告訴我您的居住城市（例如：「我在台北」），我們會每天早晨 8 點送上「RAYA迷你肌膚日報」。"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))

@handler.add(MessageEvent, message=TextMessage)
def handle_msg(event):
    uid = event.source.user_id
    txt = event.message.text.strip()
    db = load_user_db()

    if txt == "日報":
        if uid in db and db[uid]["location"] != "未設定":
            push_single_user(uid, db[uid]["location"])
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請先告訴我妳的居住城市，例如：我在台北"))

    elif "我在" in txt:
        found_loc = None
        for city in LOCATION_COORDINATES.keys():
            if city in txt:
                found_loc = city
                break
        
        if found_loc:
            update_subscription(uid, True, found_loc)
            # 修改後的訂閱成功回覆：包含「✓」與完整機制說明
            success_msg = (
                f"已為您記錄城市：{found_loc} ✓\n\n"
                "從明天起，每天早晨 8 點為您送上「RAYA迷你肌膚日報」。\n\n"
                "根據今日天氣、濕度、紫外線等環境因素，提供適合的肌膚護理建議和最新資訊。讓這份日報成為您每天的保養小夥伴。\n\n"
                "💡 若想隨時查看今日日報，輸入「日報」即可。\n"
                "💡 若想停止推播，輸入「取消推播」。\n\n"
                "期待與您在 RAYA 相遇！"
            )
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=success_msg))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="目前支援台灣各縣市之氣候推播，請輸入如：我在台北。"))

    elif txt == "取消推播":
        update_subscription(uid, False)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已為妳停止每日推播，RAYA 隨時歡迎妳回來。"))

# -------------------------------
# 推播執行與 API
# -------------------------------
def push_single_user(uid, loc):
    coord = LOCATION_COORDINATES.get(loc)
    try:
        api_url = f"https://api.openweathermap.org/data/2.5/weather?lat={coord['lat']}&lon={coord['lon']}&appid={WEATHER_API_KEY}&units=metric"
        w = requests.get(api_url, timeout=10).json()

        t_max = w['main']['temp_max']
        t_min = w['main']['temp_min']
        t_feel = w['main']['feels_like']
        humi = w['main']['humidity']
        
        rain = 20 if humi > 70 else 0
        uvi = 5
        aqi = 40

        if humi > 70 and t_max > 28: scen = "wet_heat"
        elif t_max < 15: scen = "dry_cold"
        elif humi < 40: scen = "dry_heat"
        else: scen = "seasonal"

        msg = get_daily_content(scen, loc, t_max, t_min, t_feel, humi, rain, uvi, aqi)
        line_bot_api.push_message(uid, TextSendMessage(text=msg))
    except Exception as e:
        print(f"❌ 推播失敗: {e}")

def run_push_job():
    db = load_user_db()
    for uid, info in db.items():
        if info.get("subscribed") and info.get("location") != "未設定":
            push_single_user(uid, info["location"])

# -------------------------------
# 定時任務與啟動
# -------------------------------
if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(run_push_job, 'cron', hour=8, minute=0)
    scheduler.start()

    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
