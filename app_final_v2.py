import os, json
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FollowEvent
from filelock import FileLock

app = Flask(__name__)

# 從環境變數讀取金鑰
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 檔案路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DB_FILE = os.path.join(BASE_DIR, "user_locations.json")

# 支援城市名單
SUPPORTED_CITIES = ["台北", "新北", "桃園", "台中", "台南", "高雄", "基隆", "新竹", "苗栗", "彰化", "南投", "雲林", "嘉義", "屏東", "宜蘭", "花蓮", "台東", "澎湖", "金門", "馬祖", "三重"]

def update_subscription(user_id, status, location=None):
    db = {}
    if os.path.exists(USER_DB_FILE):
        try:
            with open(USER_DB_FILE, 'r', encoding='utf-8') as f: db = json.load(f)
        except: db = {}
    
    if user_id not in db:
        db[user_id] = {"location": location or "未設定", "subscribed": False}
    db[user_id]["subscribed"] = status
    if location: db[user_id]["location"] = location
    
    lock = FileLock(f"{USER_DB_FILE}.lock")
    with lock.acquire(timeout=5):
        with open(USER_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get("X-Line-Signature","")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"

# --- 第 67 行 ---
@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = "很高興在 RAYA 與您相遇。\n\n請告訴我您的居住城市（例如：「我在台北」），我們將於每日早晨送上「RAYA 迷你肌膚日報」。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))

# 處理取消邏輯
    if txt == "取消推播":
        update_subscription(uid, False)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已為您停止每日推播，RAYA 隨時歡迎您回來。"))
        return

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
