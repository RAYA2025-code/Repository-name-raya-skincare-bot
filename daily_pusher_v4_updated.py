#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-

"""
RAYA 迷你肌膚日報 v4.2 - 每日推播核心系統 (自動任務版)
支援：用戶分區推播、訂閱狀態過濾、內容不重複機制
"""

import json
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from linebot import LineBotApi
from linebot.models import TextSendMessage

# ============================================================================
# 全局配置
# ============================================================================
# 優先偵測 Railway Volume 持久化路徑，否則使用目前路徑
if os.path.exists("/app/data"):
    BASE_DIR = "/app/data"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOG_FILE = os.path.join(BASE_DIR, "usage_log.json")
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

# 初始化 LINE API
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)

# 地區座標映射
LOCATION_COORDINATES = {
    "台北": {"lat": 25.0330, "lon": 121.5654},
    "新北": {"lat": 25.0330, "lon": 121.4680},
    "桃園": {"lat": 24.9936, "lon": 121.3010},
    "新竹": {"lat": 24.8026, "lon": 120.9676},
    "苗栗": {"lat": 24.5590, "lon": 120.8157},
    "台中": {"lat": 24.1477, "lon": 120.6736},
    "彰化": {"lat": 24.0804, "lon": 120.5368},
    "南投": {"lat": 23.8103, "lon": 120.6625},
    "雲林": {"lat": 23.7145, "lon": 120.4519},
    "嘉義": {"lat": 23.4626, "lon": 120.4521},
    "台南": {"lat": 22.9937, "lon": 120.2153},
    "高雄": {"lat": 22.6428, "lon": 120.2997},
    "屏東": {"lat": 22.6799, "lon": 120.4870},
    "宜蘭": {"lat": 24.7595, "lon": 121.7453},
    "花蓮": {"lat": 23.9908, "lon": 121.6289},
    "台東": {"lat": 22.7696, "lon": 121.1450},
}

# ============================================================================
# 資料加載
# ============================================================================

def load_user_db() -> Dict:
    if not os.path.exists(USER_DB_FILE):
        return {}
    try:
        with open(USER_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def load_content_libraries() -> Optional[Dict]:
    try:
        # 內容文件通常跟隨程式碼部署，不一定在 Volume
        CODE_DIR = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(CODE_DIR, "core_strategies_v2.json"), 'r', encoding='utf-8') as f:
            core_strategies = json.load(f)
        with open(os.path.join(CODE_DIR, "philosophy_quotes_100_v2.json"), 'r', encoding='utf-8') as f:
            quotes = json.load(f)
        with open(os.path.join(CODE_DIR, "third_modules_v2.json"), 'r', encoding='utf-8') as f:
            third_modules = json.load(f)
        with open(os.path.join(CODE_DIR, "greetings_v2.json"), 'r', encoding='utf-8') as f:
            greetings = json.load(f)

        return {
            "core_strategies": core_strategies,
            "quotes": quotes["quotes"],
            "third_modules": third_modules,
            "greetings": greetings,
        }
    except Exception as e:
        print(f"❌ 加載內容庫失敗: {e}")
        return None

# ============================================================================
# 天氣與邏輯
# ============================================================================

def get_weather_data(latitude: float, longitude: float, city: str) -> Dict:
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return {"temp_max": 25, "temp_min": 20, "feels_like": 23, "humidity": 60, "uvi": 5, "aqi": 40, "city": city}
    
    try:
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {'lat': latitude, 'lon': longitude, 'appid': api_key, 'units': 'metric'}
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        return {
            "temp_max": data['main']['temp_max'],
            "temp_min": data['main']['temp_min'],
            "feels_like": data['main']['feels_like'],
            "humidity": data['main']['humidity'],
            "uvi": data.get('uvi', 0),
            "aqi": data.get('aqi', 0),
            "city": city,
        }
    except:
        return {"temp_max": 25, "temp_min": 20, "feels_like": 23, "humidity": 60, "uvi": 5, "aqi": 40, "city": city}

def determine_weather_scenario(weather: Dict) -> str:
    if weather["aqi"] >= 100: return "pollution"
    if weather["temp_max"] >= 28: return "wet_heat" if weather["humidity"] > 60 else "dry_heat"
    if weather["temp_max"] < 15: return "wet_cold" if weather["humidity"] > 60 else "dry_cold"
    return "seasonal"

def select_content(today: datetime, weather: Dict, content_libs: Dict, used_ids: set) -> Optional[Dict]:
    scenario = determine_weather_scenario(weather)
    greeting = random.choice(content_libs["greetings"].get(scenario, []) + content_libs["greetings"]["general"])
    
    # 嘗試 50 次尋找不重複組合
    for _ in range(50):
        core = random.choice(content_libs["core_strategies"][scenario])
        weekday = today.weekday()
        if weekday == 0:
            tm_title, tm = "週肌膚儀表盤", random.choice(content_libs["third_modules"]["weekly_rhythm"]["monday"])
        elif weekday == 6:
            tm_title, tm = "週肌膚儀表盤", random.choice(content_libs["third_modules"]["weekly_rhythm"]["sunday"])
        else:
            tm_title, tm = ("皮膚科學快訊", random.choice(content_libs["third_modules"]["skincare_science"])) if random.random() < 0.5 \
                           else ("肌膚生活智庫", random.choice(content_libs["third_modules"]["skincare_lifestyle"]))
        
        quote_style = 'yang_mi_inspired' if tm_title == "皮膚科學快訊" else 'original_healing_quotes'
        quotes_list = content_libs["quotes"][quote_style]["quotes"]
        quote = random.choice(quotes_list)
        
        comp_id = f"{core['id']}-{tm['id']}-{quote_style}-{quotes_list.index(quote)}"
        if comp_id not in used_ids:
            return {"greeting": greeting, "weather": weather, "core_strategy": core, "third_module_title": tm_title, "third_module": tm, "quote": quote, "composite_id": comp_id}
    return None

def format_message(content: Dict) -> str:
    w = content["weather"]
    msg = f"{content['greeting']}\nRAYA | {w['city']} {datetime.now().strftime('%m/%d')} 肌膚日報\n\n"
    msg += f"🌡 {w['temp_max']}°C / {w['temp_min']}°C | 體感 {w['feels_like']}°C\n💧 濕度 {w['humidity']}% | ☀️ 紫外線 {w['uvi']}\n\n"
    msg += f"｜核心肌膚對策｜\n• {content['core_strategy']['content']}\n\n｜今日建議動作｜\n"
    msg += "\n".join([f"✓ {a}" for a in content['core_strategy']['actions']])
    msg += f"\n\n｜{content['third_module_title']}｜\n{content['third_module']['content']}\n\n"
    msg += f"{content['quote']}\nRAYA—有感的肌膚進化 💚"
    return msg

# ============================================================================
# 推播任務
# ============================================================================

def run_push_job():
    """核心推播任務：掃描用戶資料庫並過濾訂閱者"""
    print(f"⏰ 推播任務啟動：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    content_libs = load_content_libraries()
    user_db = load_user_db()
    
    if not content_libs or not user_db:
        print("❌ 失敗：內容庫或用戶資料庫為空")
        return

    # 加載日誌以確保不重複
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            usage_log = json.load(f)
    else:
        usage_log = {"usage_history": {}}
    
    used_ids = {f"{v['core_strategy_id']}-{v['third_module_id']}-{v['quote_id']}" for v in usage_log["usage_history"].values()}

    success_count = 0
    for user_id, info in user_db.items():
        # ⭐ 關鍵邏輯：檢查訂閱狀態
        is_subscribed = info.get("subscribed", True) # 沒寫的話預設 True 以相容舊資料
        
        if not is_subscribed:
            print(f"⏭️ 跳過用戶 {user_id} (已取消訂閱)")
            continue

        try:
            location = info.get("location", "台北")
            coords = LOCATION_COORDINATES.get(location, LOCATION_COORDINATES["台北"])
            weather = get_weather_data(coords["lat"], coords["lon"], location)
            
            selected = select_content(datetime.now(), weather, content_libs, used_ids)
            
            if selected:
                final_msg = format_message(selected)
                line_bot_api.push_message(user_id, TextSendMessage(text=final_msg))
                success_count += 1
                
                # 更新今日日誌 (以最後一個成功發送的為準或共用)
                today_str = datetime.now().strftime("%Y-%m-%d")
                cid = selected["composite_id"].split('-')
                usage_log["usage_history"][today_str] = {
                    "core_strategy_id": cid[0], "third_module_id": cid[1], "quote_id": f"{cid[2]}-{cid[3]}"
                }
                print(f"✅ 已發送給：{user_id} ({location})")
        except Exception as e:
            print(f"❌ 發送失敗 {user_id}: {e}")

    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(usage_log, f, ensure_ascii=False, indent=2)
    
    print(f"🎉 任務完成，成功推播人數：{success_count}")

if __name__ == "__main__":
    # 如果是手動執行此腳本，直接跑一次推播
    run_push_job()
