#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-

"""
RAYA 迷你肌膚日報 - LINE Webhook 互動引擎 v2
支持用戶地區設定和修改
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, Optional

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FollowEvent, UnfollowEvent
)

# ============================================================================
# Flask 應用初始化
# ============================================================================

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ============================================================================
# 用戶數據庫（簡化版，實際應使用 MySQL / MongoDB）
# ============================================================================
# 同樣使用自動獲取路徑的方法
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

def load_user_db() -> Dict:
    """加載用戶地區數據庫"""
    if not os.path.exists(USER_DB_FILE):
        return {}
    try:
        with open(USER_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def save_user_db(db: Dict):
    """保存用戶地區數據庫"""
    with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user_location(user_id: str) -> Optional[str]:
    """獲取用戶設定的地區"""
    db = load_user_db()
    return db.get(user_id, {}).get("location")

def set_user_location(user_id: str, location: str):
    """設定用戶地區"""
    db = load_user_db()
    if user_id not in db:
        db[user_id] = {}
    db[user_id]["location"] = location
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

# ============================================================================
# 地區映射和驗證
# ============================================================================

LOCATION_MAP = {
    "台北": {"code": "taipei", "name": "台北"},
    "新北": {"code": "newtaipei", "name": "新北"},
    "桃園": {"code": "taoyuan", "name": "桃園"},
    "新竹": {"code": "hsinchu", "name": "新竹"},
    "苗栗": {"code": "miaoli", "name": "苗栗"},
    "台中": {"code": "taichung", "name": "台中"},
    "彰化": {"code": "changhua", "name": "彰化"},
    "南投": {"code": "nantou", "name": "南投"},
    "雲林": {"code": "yunlin", "name": "雲林"},
    "嘉義": {"code": "chiayi", "name": "嘉義"},
    "台南": {"code": "tainan", "name": "台南"},
    "高雄": {"code": "kaohsiung", "name": "高雄"},
    "屏東": {"code": "pingtung", "name": "屏東"},
    "宜蘭": {"code": "yilan", "name": "宜蘭"},
    "花蓮": {"code": "hualien", "name": "花蓮"},
    "台東": {"code": "taitung", "name": "台東"},
}

def normalize_location(text: str) -> Optional[str]:
    """規範化地區名稱，返回標準地區名稱"""
    text = text.strip()
    
    # 直接匹配
    if text in LOCATION_MAP:
        return text
    
    # 模糊匹配（例如「新竹市」→「新竹」）
    for location_name in LOCATION_MAP.keys():
        if location_name in text:
            return location_name
    
    return None

# ============================================================================
# 訊息處理邏輯
# ============================================================================

def handle_location_change(user_id: str, text: str) -> Optional[str]:
    """
    處理地區修改請求
    
    觸發詞語：
    - 「我在 [地區]」
    - 「改變地區 [地區]」
    - 「設定地區 [地區]」
    - 「我要改」
    - 「查詢地區」
    """
    
    # 模式 1：「我在 [地區]」
    match = re.search(r'我在(.+)', text)
    if match:
        location_text = match.group(1)
        location = normalize_location(location_text)
        if location:
            set_user_location(user_id, location)
            return f"✅ 已更新！您的地區現在是『{location}』。\n從明天開始，我會為您推送{location}的肌膚日報喔 💚"
        else:
            return f"抱歉，我沒有找到『{location_text}』。\n請確認地區名稱是否正確，或從以下清單中選擇：\n台北、新北、桃園、新竹、苗栗、台中、彰化、南投、雲林、嘉義、台南、高雄、屏東、宜蘭、花蓮、台東"
    
    # 模式 2：「改變地區 [地區]」
    match = re.search(r'改變地區\s*(.+)', text)
    if match:
        location_text = match.group(1)
        location = normalize_location(location_text)
        if location:
            set_user_location(user_id, location)
            return f"✅ 已更新！您的地區現在是『{location}』。\n從明天開始，我會為您推送{location}的肌膚日報喔 💚"
        else:
            return f"抱歉，我沒有找到『{location_text}』。\n請確認地區名稱是否正確，或從以下清單中選擇：\n台北、新北、桃園、新竹、苗栗、台中、彰化、南投、雲林、嘉義、台南、高雄、屏東、宜蘭、花蓮、台東"
    
    # 模式 3：「設定地區 [地區]」
    match = re.search(r'設定地區\s*(.+)', text)
    if match:
        location_text = match.group(1)
        location = normalize_location(location_text)
        if location:
            set_user_location(user_id, location)
            return f"✅ 已更新！您的地區現在是『{location}』。\n從明天開始，我會為您推送{location}的肌膚日報喔 💚"
        else:
            return f"抱歉，我沒有找到『{location_text}』。\n請確認地區名稱是否正確，或從以下清單中選擇：\n台北、新北、桃園、新竹、苗栗、台中、彰化、南投、雲林、嘉義、台南、高雄、屏東、宜蘭、花蓮、台東"
    
    # 模式 4：「查詢地區」
    if any(keyword in text for keyword in ["查詢地區", "我的地區", "目前地區", "現在地區", "我在哪"]):
        current_location = get_user_location(user_id)
        if current_location:
            return f"✅ 您目前的地區設定是『{current_location}』。\n如果需要改變，隨時告訴我喔 💚"
        else:
            return "您還沒有設定地區。請告訴我您在哪裡呢？（例如：台中、高雄、台南...）"
    
    # 模式 5：「我要改」（當詢問時）
    if any(keyword in text for keyword in ["我要改", "改地區", "改變", "不對", "不是", "重新選擇"]):
        return "沒問題！請告訴我您現在在哪裡呢？（例如：台中、高雄、台南...）"
    
    return None

# ============================================================================
# Webhook 路由
# ============================================================================

@app.route("/callback", methods=["POST"])
def callback():
    """LINE Webhook 回調"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    
    return "OK"

# ============================================================================
# 事件處理器
# ============================================================================

@handler.add(FollowEvent)
def handle_follow(event):
    """用戶加入好友時的處理"""
    user_id = event.source.user_id
    
    # 發送歡迎訊息和地區詢問
    welcome_message = """嗨親愛的，歡迎加入 RAYA！💚

我是您的肌膚日報助手，每天都會根據您所在地區的天氣，為您推送個人化的肌膚護理建議。

請告訴我您現在在哪裡呢？
（例如：台北、台中、高雄、台南...）

支持的地區：
台北、新北、桃園、新竹、苗栗、台中、彰化、南投、雲林、嘉義、台南、高雄、屏東、宜蘭、花蓮、台東

設定完成後，您可以隨時發送以下指令修改地區：
✓ 「我在 [地區]」
✓ 「改變地區 [地區]」
✓ 「查詢地區」

讓我們一起照顧肌膚，也照顧自己吧！"""
    
    line_bot_api.push_message(
        user_id,
        TextSendMessage(text=welcome_message)
    )

@handler.add(UnfollowEvent)
def handle_unfollow(event):
    """用戶取消追蹤時的處理"""
    user_id = event.source.user_id
    db = load_user_db()
    if user_id in db:
        del db[user_id]
        save_user_db(db)
    print(f"用戶 {user_id} 已取消追蹤")

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理用戶訊息"""
    user_id = event.source.user_id
    text = event.message.text
    
    # 嘗試處理地區修改
    location_response = handle_location_change(user_id, text)
    
    if location_response:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=location_response)
        )
    else:
        # 其他訊息的處理（可擴展）
        default_response = """感謝您的訊息！

如果您想修改地區，可以發送：
✓ 「我在 [地區]」
✓ 「改變地區 [地區]」
✓ 「查詢地區」

更多詳細資訊，請查看『地區修改指南』。

RAYA—有感的肌膚進化 💚"""
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=default_response)
        )

# ============================================================================
# 主程序
# ============================================================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

