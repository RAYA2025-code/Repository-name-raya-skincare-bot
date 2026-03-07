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

# 1. 配置
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

# 2. 資料庫邏輯
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
    save_user_db(db)

# 3. 內容生成
def get_daily_content(scenario, location, temp_max, temp_min, temp_feel, humi, uvi, aqi):
    now = datetime.now()
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    weekday_str = weekdays[now.weekday()]
    
    # 預設對策 (防止檔案讀取失敗時當機)
    default_strat = {"content": "今天適合基礎保養，多喝水維持代謝。", "insight": "你知道嗎？充足的睡眠能讓保養品吸收效率提高 20% ✨", "actions": ["基礎潔面", "保濕精華"]}
    
    try:
        root_path = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(root_path, "strategies_v3.json"), 'r', encoding='utf-8') as f:
            strategies = json.load(f)
        strat = random.choice(strategies.get(scenario, [default_strat]))
    except:
        strat = default_strat

    msg = (
        f"嗨，親愛的，新的一天開始了 💪\n"
        f"{location} {now.strftime('%m/%d')} ({weekday_str}) RAYA迷你肌膚日報\n"
        f"🌡 氣溫 {int(temp_max)}°C / {int(temp_min)}°C\n"
        f"🌤 體感 {int(temp_feel)}°C\n"
        f"💧 濕度 {humi}%\n"
        f"☀️ 紫外線 {uvi}\n"
        f"🍃 空氣 AQI {aqi}\n\n"
        f"｜核心肌膚對策｜\n"
        f"• {strat['content']}\n"
        f"{strat['insight']}\n\n"
        f"｜今日建議動作｜\n"
    )
    for a in strat['actions']: msg += f"✓ {a}\n"
    msg += f"\n每一次的堅持，都是在為未來的自己投資。\nRAYA—有感的肌膚進化"
    return msg

# 4. Webhook & 排程
@app.route("/callback", methods=['POST'])
def callback():
    sig = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try: handler.handle(body, sig)
    except: abort(400)
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_msg(event):
    uid = event.source.user_id
    txt = event.message.text.strip()
    if txt == "測試推播":
        run_push_job()
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚀 已手動觸發推播！"))
    elif "我在" in txt:
        loc = txt.replace("我在", "").strip()[:2]
        if loc in LOCATION_COORDINATES:
            update_subscription(uid, True, loc)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 已設定地區：{loc}，明天見！"))
    else:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="請輸入「我在台北」來訂閱日報 💚"))

def run_push_job():
    db = load_user_db()
    for uid, info in db.items():
        if not info.get("subscribed") or info.get("location") == "未設定": continue
        try:
            loc = info["location"]
            coord = LOCATION_COORDINATES[loc]
            w = requests.get(f"https://api.openweathermap.org/data/2.5/weather?lat={coord['lat']}&lon={coord['lon']}&appid={WEATHER_API_KEY}&units=metric").json()
            t_max = w['main']['temp_max']
            t_min = w['main']['temp_min']
            h = w['main']['humidity']
            scen = "wet_heat" if h > 70 and t_max > 25 else "seasonal"
            msg = get_daily_content(scen, loc, t_max, t_min, t_max, h, 6, 45)
            line_bot_api.push_message(uid, TextSendMessage(text=msg))
        except: pass

if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone="Asia/Taipei")
    scheduler.add_job(run_push_job, 'cron', hour=8, minute=0)
    scheduler.start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
