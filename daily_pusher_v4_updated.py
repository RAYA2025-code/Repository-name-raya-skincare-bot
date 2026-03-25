import os, json, requests, random, time
from datetime import datetime, timedelta
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
    "基隆": {"lat": 25.12, "lon": 121.73}, "新竹": {"lat": 24.81, "lon": 120.96},
    "苗栗": {"lat": 24.56, "lon": 120.81}, "彰化": {"lat": 24.05, "lon": 120.51},
    "南投": {"lat": 23.91, "lon": 120.68}, "雲林": {"lat": 23.70, "lon": 120.43},
    "嘉義": {"lat": 23.48, "lon": 120.44}, "屏東": {"lat": 22.66, "lon": 120.48},
    "宜蘭": {"lat": 24.75, "lon": 121.75}, "花蓮": {"lat": 23.97, "lon": 121.60},
    "台東": {"lat": 22.75, "lon": 121.14}, "澎湖": {"lat": 23.56, "lon": 119.57},
    "金門": {"lat": 24.43, "lon": 118.32}, "馬祖": {"lat": 26.15, "lon": 119.92},
    "三重": {"lat": 25.06, "lon": 121.49}
}

def load_json(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path): return {}
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)

def run_push_job():
    if not os.path.exists(USER_DB_FILE): return
    with open(USER_DB_FILE, 'r', encoding='utf-8') as f: db = json.load(f)
    
    strategies = load_json("strategies_v3.json")
    quotes_data = load_json("philosophy_quotes_100_v2.json")
    weekly_themes = load_json("weekly_themes.json")

    # 取得今天星期幾 (英文小寫)
    weekday_key = datetime.now().strftime('%A').lower()

    for uid, info in db.items():
        if info.get("subscribed") and info.get("location") in LOCATION_COORDINATES:
            try:
                city = info["location"]
                coord = LOCATION_COORDINATES[city]
                
                # 1. 抓取天氣
                w_url = f"https://api.openweathermap.org/data/2.5/weather?lat={coord['lat']}&lon={coord['lon']}&appid={WEATHER_API_KEY}&units=metric"
                w_res = requests.get(w_url).json()
                temp = w_res['main']['temp']
                humi = w_res['main']['humidity']
                
                # 2. 判斷情境 (簡化邏輯)
                scen = "wet_heat" if humi > 70 and temp > 28 else "seasonal"
                if temp < 15: scen = "dry_cold"

                # 3. 組合內容 (全面使用「您」)
                strat = random.choice(strategies.get(scen, [{"content":"維持基礎保養。", "insight":"穩定修護您的肌膚。"}]))
                
                theme_list = weekly_themes.get(weekday_key, ["讓肌膚自在呼吸。"])
                selected_theme = random.choice(theme_list)

                quote_list = []
                for cat in quotes_data.get("quotes", {}).values():
                    quote_list.extend(cat.get("quotes", []))
                quote = random.choice(quote_list) if quote_list else "溫柔對待您自己。"

                msg = (
                    f"您好，親愛的，晨光已經抵達 ☀️\n"
                    f"{city} {datetime.now().strftime('%m/%d')} RAYA 迷你肌膚日報\n\n"
                    f"🌡 氣溫 {int(temp)}°C  💧 濕度 {humi}%\n\n"
                    f"｜核心肌膚對策｜\n• {strat['content']} {strat['insight']}\n\n"
                    f"｜本週節奏｜\n• {selected_theme}\n\n"
                    f"{quote}\n\n"
                    f"RAYA—有感的肌膚進化"
                )
                line_bot_api.push_message(uid, TextSendMessage(text=msg))
                time.sleep(1) 
            except Exception as e:
                print(f"Push failed for {uid}: {e}")

if __name__ == "__main__":
    while True:
        # 強制校準台灣時間 (Railway 伺服器通常是 UTC)
        now_utc = datetime.utcnow()
        now_taiwan = now_utc + timedelta(hours=8)
        
        # 每天早上 8:00 執行
        if now_taiwan.hour == 8 and now_taiwan.minute == 0:
            print(f"[{now_taiwan}] Starting daily push...")
            run_push_job()
            time.sleep(65) # 避開重複執行
        time.sleep(30)
