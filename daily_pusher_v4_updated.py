#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-

"""
RAYA 迷你肌膚日報 v4.1 - 每日推播核心系統
支持用戶自定義地區
"""

import json
import os
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests

# ============================================================================
# 全局配置
# ============================================================================
CONTENT_PATH = "/home/ubuntu/"
LOG_FILE = os.path.join(CONTENT_PATH, "usage_log.json")
USER_DB_FILE = os.path.join(CONTENT_PATH, "user_locations.json")

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
# 用戶數據庫操作
# ============================================================================

def load_user_db() -> Dict:
    """加載用戶地區數據庫"""
    if not os.path.exists(USER_DB_FILE):
        return {}
    try:
        with open(USER_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def get_user_location(user_id: str) -> str:
    """獲取用戶設定的地區，預設為台北"""
    db = load_user_db()
    return db.get(user_id, {}).get("location", "台北")

# ============================================================================
# 內容庫加載
# ============================================================================

def load_content_libraries() -> Optional[Dict]:
    """加載所有 V4 內容庫"""
    try:
        with open(os.path.join(CONTENT_PATH, "core_strategies_v2.json"), 'r', encoding='utf-8') as f:
            core_strategies = json.load(f)
        with open(os.path.join(CONTENT_PATH, "philosophy_quotes_100_v2.json"), 'r', encoding='utf-8') as f:
            quotes = json.load(f)
        with open(os.path.join(CONTENT_PATH, "third_modules_v2.json"), 'r', encoding='utf-8') as f:
            third_modules = json.load(f)
        with open(os.path.join(CONTENT_PATH, "greetings_v2.json"), 'r', encoding='utf-8') as f:
            greetings = json.load(f)

        return {
            "core_strategies": core_strategies,
            "quotes": quotes["quotes"],
            "third_modules": third_modules,
            "greetings": greetings,
        }
    except FileNotFoundError as e:
        print(f"❌ 內容庫文件未找到: {e}")
        return None
    except Exception as e:
        print(f"❌ 加載內容庫失敗: {e}")
        return None

# ============================================================================
# 天氣 API
# ============================================================================

def get_weather_data(latitude: float, longitude: float, city: str) -> Dict:
    """
    從 OpenWeather API 獲取天氣數據
    
    Args:
        latitude: 緯度
        longitude: 經度
        city: 城市名稱（用於顯示）
    
    Returns:
        天氣數據字典
    """
    try:
        api_key = os.getenv("WEATHER_API_KEY")
        if not api_key:
            print("⚠️ 未設定 WEATHER_API_KEY，使用模擬數據")
            return {
                "temp_max": 28,
                "temp_min": 22,
                "feels_like": 26,
                "humidity": 65,
                "uvi": 6,
                "aqi": 45,
                "city": city,
            }
        
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': api_key,
            'units': 'metric'
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
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
    except Exception as e:
        print(f"⚠️ 天氣 API 調用失敗: {e}，使用模擬數據")
        return {
            "temp_max": 28,
            "temp_min": 22,
            "feels_like": 26,
            "humidity": 65,
            "uvi": 6,
            "aqi": 45,
            "city": city,
        }

# ============================================================================
# 已使用內容追蹤
# ============================================================================

def load_usage_log() -> Dict:
    """加載已使用內容日誌"""
    if not os.path.exists(LOG_FILE):
        return {"usage_history": {}}
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            log = json.load(f)
            one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            log["usage_history"] = {
                date: ids
                for date, ids in log["usage_history"].items()
                if date >= one_year_ago
            }
            return log
    except (json.JSONDecodeError, FileNotFoundError):
        return {"usage_history": {}}

def save_usage_log(log: Dict):
    """保存已使用內容日誌"""
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

def get_used_ids(log: Dict) -> set:
    """獲取所有在一年內已使用的內容 ID"""
    used_ids = set()
    for date, ids in log["usage_history"].items():
        composite_id = f'{ids["core_strategy_id"]}-{ids["third_module_id"]}-{ids["quote_id"]}'
        used_ids.add(composite_id)
    return used_ids

# ============================================================================
# 內容選擇邏輯
# ============================================================================

def determine_weather_scenario(weather: Dict) -> str:
    """根據天氣數據判斷天氣情境"""
    if weather["aqi"] >= 100:
        return "pollution"
    if weather["temp_max"] >= 28:
        return "wet_heat" if weather["humidity"] > 60 else "dry_heat"
    if weather["temp_max"] < 15:
        return "wet_cold" if weather["humidity"] > 60 else "dry_cold"
    return "seasonal"

def select_third_module(today: datetime, weather_scenario: str, content_libs: Dict) -> Tuple[str, Dict]:
    """根據觸發邏輯選擇第三模組"""
    weekday = today.weekday()

    if weekday == 0:  # Monday
        return "週肌膚儀表盤", random.choice(content_libs["third_modules"]["weekly_rhythm"]["monday"])
    if weekday == 6:  # Sunday
        return "週肌膚儀表盤", random.choice(content_libs["third_modules"]["weekly_rhythm"]["sunday"])

    if random.random() < 0.5:
        return "皮膚科學快訊", random.choice(content_libs["third_modules"]["skincare_science"])
    else:
        return "肌膚生活智庫", random.choice(content_libs["third_modules"]["skincare_lifestyle"])

def select_content(today: datetime, weather: Dict, content_libs: Dict, used_composite_ids: set) -> Optional[Dict]:
    """選擇所有內容模組，確保組合是唯一的"""
    weather_scenario = determine_weather_scenario(weather)

    greeting_candidates = content_libs["greetings"].get(weather_scenario, []) + content_libs["greetings"]["general"]
    greeting = random.choice(greeting_candidates)

    for _ in range(100):
        core_strategy = random.choice(content_libs["core_strategies"][weather_scenario])
        third_module_title, third_module = select_third_module(today, weather_scenario, content_libs)
        
        if third_module_title == "肌膚SOS":
            quote_style = random.choice(['yang_mi_inspired', 'carina_lau_inspired'])
        elif third_module_title == "皮膚科學快訊":
            quote_style = 'yang_mi_inspired'
        else:
            quote_style = random.choice(['user_themes_inspired', 'original_healing_quotes'])
        
        quote_candidates = content_libs["quotes"][quote_style]["quotes"]
        quote = random.choice(quote_candidates)

        composite_id = f'{core_strategy["id"]}-{third_module["id"]}-{quote_style}-{quote_candidates.index(quote)}'

        if composite_id not in used_composite_ids:
            return {
                "greeting": greeting,
                "weather": weather,
                "core_strategy": core_strategy,
                "third_module_title": third_module_title,
                "third_module": third_module,
                "quote": quote,
                "composite_id": composite_id,
            }
    return None

# ============================================================================
# 訊息格式化
# ============================================================================

def format_message(content: Dict) -> str:
    """將選擇的內容格式化為最終的推播訊息"""
    weather = content["weather"]
    today_str = datetime.now().strftime("%m/%d")

    message = f'{content["greeting"]}\n'
    message += f'RAYA | {weather["city"]} {today_str} 肌膚日報\n\n'
    message += f'🌡 氣溫 {weather["temp_max"]}°C / {weather["temp_min"]}°C\n'
    message += f'🌤 體感 {weather["feels_like"]}°C\n'
    message += f'💧 濕度 {weather["humidity"]}%\n'
    message += f'☀️ 紫外線 {weather["uvi"]}\n'
    message += f'🍃 空氣 AQI {weather["aqi"]}\n\n'
    message += f'｜核心肌膚對策｜\n• {content["core_strategy"]["content"]}\n\n'
    message += f'｜今日建議動作｜\n'
    for action in content["core_strategy"]["actions"]:
        message += f'✓ {action}\n'
    message += f'\n｜{content["third_module_title"]}｜\n{content["third_module"]["content"]}\n\n'
    message += f'{content["quote"]}\n'
    message += "RAYA—有感的肌膚進化"

    return message

# ============================================================================
# 主執行函數
# ============================================================================

def generate_daily_message_for_user(user_id: str, content_libs: Dict) -> Optional[str]:
    """為特定用戶生成每日肌膚日報"""
    # 1. 獲取用戶設定的地區
    location = get_user_location(user_id)
    print(f"👤 用戶 {user_id} 的地區：{location}")
    
    # 2. 獲取地區座標
    if location not in LOCATION_COORDINATES:
        print(f"⚠️ 地區 {location} 不在支持列表中，使用台北座標")
        location = "台北"
    
    coords = LOCATION_COORDINATES[location]
    
    # 3. 獲取天氣數據
    weather_data = get_weather_data(coords["lat"], coords["lon"], location)
    print(f"🌤️ 獲取到 {location} 天氣：{weather_data['temp_max']}°C")
    
    # 4. 加載使用日誌
    usage_log = load_usage_log()
    used_composite_ids = get_used_ids(usage_log)
    
    # 5. 選擇獨特的內容組合
    today = datetime.now()
    selected_content = select_content(today, weather_data, content_libs, used_composite_ids)
    
    if not selected_content:
        print("❌ 無法生成獨特的內容組合")
        return None
    
    # 6. 格式化最終訊息
    final_message = format_message(selected_content)
    
    # 7. 更新使用日誌
    today_str = today.strftime("%Y-%m-%d")
    composite_id_parts = selected_content["composite_id"].split('-')
    usage_log["usage_history"][today_str] = {
        "core_strategy_id": composite_id_parts[0],
        "third_module_id": composite_id_parts[1],
        "quote_id": f'{composite_id_parts[2]}-{composite_id_parts[3]}'
    }
    save_usage_log(usage_log)
    
    return final_message

def main():
    """主執行函數"""
    print("🚀 開始生成 RAYA 每日肌膚日報 v4.1...")

    # 1. 加載內容庫
    content_libs = load_content_libraries()
    if not content_libs:
        print("❌ 程序終止：無法加載內容庫。")
        return
    print("✅ 內容庫加載成功。")

    # 2. 模擬用戶 ID（實際應從 LINE 用戶列表中獲取）
    test_user_id = "U1234567890"
    
    # 3. 為測試用戶生成訊息
    final_message = generate_daily_message_for_user(test_user_id, content_libs)
    
    if not final_message:
        print("❌ 無法生成訊息")
        return
    
    # 4. 打印最終訊息
    print("\n" + "="*40)
    print("📬 最終推播訊息：")
    print("="*40)
    print(final_message)
    print("="*40 + "\n")
    
    print("✅ RAYA 每日肌膚日報 v4.1 生成完畢！")

if __name__ == "__main__":
    main()
