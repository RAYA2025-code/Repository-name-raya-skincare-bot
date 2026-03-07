import os
import json
import requests
from datetime import datetime
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
# 👇 這是新加入的排程工具
from apscheduler.schedulers.background import BackgroundScheduler
from filelock import FileLock

app = Flask(__name__)

# --- 設定區 ---
USER_DB_FILE = 'user_locations.json'
LOG_FILE = 'usage_log.json'
# 請確保這裡的路徑與你 GitHub 上的資料夾名稱一致
CONTENT_DIR = 'content_libraries'
# ============================================================================
# 用戶數據庫配置
# ============================================================================
# 優先使用 Railway Volume 掛載路徑，確保資料持久化；若無則使用目前資料夾
if os.path.exists("/app/data"):
    BASE_DIR = "/app/data"
else:
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
    """保存用戶地區數據庫 (加入檔案鎖防護)"""
    lock = FileLock(f"{USER_DB_FILE}.lock")
    with lock:
        with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

def get_user_location(user_id: str) -> Optional[str]:
    """獲取用戶設定的地區"""
    db = load_user_db()
    return db.get(user_id, {}).get("location")

def set_user_location(user_id: str, location: str):
    """設定用戶地區，並預設開啟訂閱"""
    db = load_user_db()
    if user_id not in db:
        db[user_id] = {}
    db[user_id]["location"] = location
    db[user_id]["subscribed"] = True  # ⭐ 新增：設定地區時自動視為已訂閱
    db[user_id]["updated_at"] = datetime.now().isoformat()
    save_user_db(db)

def update_subscription(user_id: str, status: bool):
    """⭐ 新增：更新用戶的推播訂閱狀態"""
    db = load_user_db()
    if user_id not in db:
        db[user_id] = {"location": "台北"} # 預設地區
    db[user_id]["subscribed"] = status
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
    if text in LOCATION_MAP:
        return text
    for location_name in LOCATION_MAP.keys():
        if location_name in text:
            return location_name
    return None

# ============================================================================
# 訊息處理邏輯
# ============================================================================

def handle_location_change(user_id: str, text: str) -> Optional[str]:
    """處理地區修改請求"""
    # 模式 1-3：「我在 [地區]」、「改變地區 [地區]」、「設定地區 [地區]」
    for pattern in [r'我在(.+)', r'改變地區\s*(.+)', r'設定地區\s*(.+)']:
        match = re.search(pattern, text)
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
            # 順便檢查訂閱狀態
            db = load_user_db()
            is_sub = db.get(user_id, {}).get("subscribed", True)
            status_text = "🟢 接收推播中" if is_sub else "⏸️ 推播已暫停"
            return f"✅ 您目前的地區設定是『{current_location}』。\n目前的推播狀態：{status_text}\n如果需要改變，隨時告訴我喔 💚"
        else:
            return "您還沒有設定地區。請告訴我您在哪裡呢？（例如：台中、高雄、台南...）"
    
    # 模式 5：「我要改」（當詢問時）
    if any(keyword in text for keyword in ["我要改", "改地區", "改變", "不對", "不是", "重新選擇"]):
        return "沒問題！請告訴我您現在在哪裡呢？（例如：台中、高雄、台南...）"
    
    return None

# ============================================================================
# Webhook 路由
# ============================================================================

@app.route("/callback", methods=['POST'])
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
    
    # ⭐ 新增：用戶一加入，預設將其存入資料庫並開啟訂閱
    update_subscription(user_id, True)
    
    welcome_message = """嗨親愛的，歡迎加入 RAYA！💚

我是您的肌膚日報助手，每天都會根據您所在地區的天氣，為您推送個人化的肌膚護理建議。

請告訴我您現在在哪裡呢？
（例如：台北、台中、高雄、台南...）

支持的地區：
台北、新北、桃園、新竹、苗栗、台中、彰化、南投...等台灣縣市。

👉 您可以隨時發送以下指令與我互動：
✓ 「我在 [地區]」：修改您的所在地區
✓ 「查詢地區」：查看目前設定
✓ 「取消推播」：暫停接收每日日報
✓ 「恢復推播」：重新開啟日報接收

讓我們一起照顧肌膚，也照顧自己吧！"""
    
    line_bot_api.push_message(
        user_id,
        TextSendMessage(text=welcome_message)
    )

@handler.add(UnfollowEvent)
def handle_unfollow(event):
    """用戶取消追蹤（封鎖）時的處理"""
    user_id = event.source.user_id
    db = load_user_db()
    if user_id in db:
        # 不一定要刪除，可以標記為未訂閱就好
        db[user_id]["subscribed"] = False
        save_user_db(db)
    print(f"用戶 {user_id} 已取消追蹤/封鎖")

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理用戶訊息"""
    user_id = event.source.user_id
    text = event.message.text.strip()
    
    # ⭐ 新增：優先處理訂閱/取消訂閱的指令
    if text in ["取消推播", "取消訂閱", "停止推播", "暫停推播"]:
        update_subscription(user_id, False)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="⏸️ 已為您暫停每日肌膚日報推播。\n若想恢復，請隨時發送「恢復推播」喔 💚")
        )
        return

    if text in ["恢復推播", "恢復訂閱", "重新推播", "開啟推播"]:
        update_subscription(user_id, True)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="▶️ 已為您恢復每日肌膚日報推播！\n明天早上見 💚")
        )
        return
    
    # 嘗試處理地區修改
    location_response = handle_location_change(user_id, text)
    
    if location_response:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=location_response)
        )
    else:
        # 其他訊息的預設回覆
        default_response = """感謝您的訊息！

如果您想修改地區，可以發送：
✓ 「我在 [地區]」
✓ 「查詢地區」

若想管理推播狀態，可以發送：
✓ 「取消推播」
✓ 「恢復推播」

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
