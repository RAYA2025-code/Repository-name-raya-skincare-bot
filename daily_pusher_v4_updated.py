import os, json, requests, random, time
from datetime import datetime
from linebot import LineBotApi
from linebot.models import TextSendMessage

# 配置
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

LOCATION_COORDINATES = {
    "台北": {"lat": 25.03, "lon": 121.56}, "新北": {"lat": 25.01, "lon": 121.46},
    "桃園": {"lat": 24.99, "lon": 121.31}, "台中": {"lat": 24.14, "lon": 120.67},
    "台南": {"lat": 22.99, "lon": 120.21}, "高雄": {"lat": 22.62, "lon": 120.31},
    "三重": {"lat": 25.06, "lon": 121.49} # 這裡可依需求補齊其他縣市
}

def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def run_push_job():
    if not os.path.exists(USER_DB_FILE): return
    with open(USER_DB_FILE, 'r', encoding='utf-8') as f: db = json.load(f)
    
    strategies = load_json("strategies_v3.json")
    mapping = load_json("climate_content_mapping.json")
    quotes_data = load_json("philosophy_quotes_100_v2.json")

    for uid, info in db.items():
        if info.get("subscribed") and info.get("location") in LOCATION_COORDINATES:
            try:
                city = info["location"]
                coord = LOCATION_COORDINATES[city]
                # 1. 抓天氣
                w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={coord['lat']}&lon={coord['lon']}&appid={WEATHER_API_KEY}&units=metric"
                w_res = requests.get(w_url).json()
                temp, humi = w_res['main']['temp'], w_res['main']['humidity']
                
                # 2. 判斷情境
                scen = "wet_heat" if humi > 70 and temp > 28 else "seasonal"
                
                # 3. 組合內容
                strat = random.choice(strategies.get(scen, [{"content":"基礎保養", "insight":"穩定修護"}]))
                quote_list = []
                for cat in quotes_data.get("quotes", {}).values(): quote_list.extend(cat.get("quotes", []))
                quote = random.choice(quote_list) if quote_list else "溫柔對待自己。"

                msg = (
                    f"嗨，晨光已經抵達 ☀️\n{city} {datetime.now().strftime('%m/%d')} RAYA 迷你肌膚日報\n\n"
                    f"🌡 氣溫 {int(temp)}°C  💧 濕度 {humi}%\n\n"
                    f"｜核心肌膚對策｜\n• {strat['content']} {strat['insight']}\n\n"
                    f"{quote}\n\n"
                    f"RAYA—有感的肌膚進化"
                )
                line_bot_api.push_message(uid, TextSendMessage(text=msg))
                time.sleep(1) 
            except Exception as e: print(f"Push failed for {uid}: {e}")

if __name__ == "__main__":
    while True:
        now = datetime.now()
        if now.hour == 8 and now.minute == 0:
            run_push_job()
            time.sleep(65)
        time.sleep(30)
