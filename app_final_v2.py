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

@handler.add(FollowEvent)
def handle_follow(event):
    welcome_text = "很高興在 RAYA 與您相遇。\n\n請告訴我您的居住城市（例如：「我在台北」），我們將於每日早晨送上「RAYA 迷你肌膚日報」。"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome_text))

@handler.add(MessageEvent, message=TextMessage)
def handle_msg(event):
    uid = event.source.user_id
    txt = event.message.text.strip()
    
    if "我在" in txt:
        found_loc = next((city for city in SUPPORTED_CITIES if city in txt), None)
        if found_loc:
            update_subscription(uid, True, found_loc)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"已為您記錄城市：{found_loc} ✓\n\n從明天起，每天早晨為您送上專屬日報。"))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="目前支援台灣各縣市，請輸入如：我在台北。"))
    elif txt == "取消推播":
        update_subscription(uid, False)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="已為妳停止每日推播。"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
