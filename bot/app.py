from flask import Flask, request, abort, jsonify
from flask_cors import CORS
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN
from state_service import ensure_user_state, get_user_state, update_user_mode
from handlers import handle_faq, handle_query, handle_human, handle_AI
import threading
import requests
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s %(message)s'
)
logger = logging.getLogger(__name__)

# ── 初始化 ────────────────────────────────
app = Flask(__name__)
CORS(app)  # 啟用 CORS
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ── Loading 動畫 ──────────────────────────
def send_loading_animation(user_id, seconds=60):
    """發送 loading 動畫，seconds 預設 60 秒，設為 5 可快速停止"""
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    data = {
        "chatId": user_id,
        "loadingSeconds": seconds
    }
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 202:
        logger.info(f"Loading animation: {seconds}s")
    else:
        logger.error(f"Loading error: {response.status_code}, {response.text}")
        
# ── Web 路由 ──────────────────────────────
@app.route("/api/chat", methods=['POST'])
def chat():
    platform = "web"
    data = request.json
    # 檢查 user_id 是否存在於 user_state 資料表
    user_id = data.get("user_id")
    user_state = get_user_state(user_id)

    ensure_user_state(user_id)

    if data.get("message_type") == "init":
        return jsonify({
            "messages": [
                {"type": "text", "content": "嗨，請選擇要進行的功能："},
                {
                    "type": "options",
                    "id": "welcome_menu",
                    "title": "功能選單",
                    "options": [
                        {"label": "常見問題"},
                        {"label": "AI客服"},
                        {"label": "積分查詢"}
                    ]
                }
            ]
        })
    elif data.get("message_type") == "text":
        msg = data.get("message", "")

        if msg == "常見問題":
            update_user_mode(user_id, "faq")
        elif msg == "AI客服":
            update_user_mode(user_id, "AI")
        elif msg == "積分查詢":
            update_user_mode(user_id, "query")

        # 處理使用者選擇的選項
        user_state = get_user_state(user_id)
        mode = user_state["mode"]
        
        if mode == "faq":
            reply_message = handle_faq(user_id, user_state, msg, platform)
            return jsonify(reply_message)
        elif mode == "AI":
            reply_message = handle_AI(user_id, user_state, msg, platform)
            return jsonify(reply_message)
        elif mode == "query":
            reply_message = handle_query(user_id, user_state, msg, platform)
            return jsonify(reply_message)
        elif mode == "human":
            reply_message = handle_human(user_id, user_state, msg, platform)
            return jsonify(reply_message)
        else:
            return jsonify({
                "messages": [
                    {"type": "text", "content": "未知的選項"}
                ]
            })
    
    # 預設回應（若都不符合）
    return jsonify({
        "messages": [
            {"type": "text", "content": "抱歉，我不太明白您的意思"}
        ]
    })
    
# ── LINE Webhook ──────────────────────────
@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭
    signature = request.headers.get('X-Line-Signature')
    # 取得 POST 資料
    body = request.get_data(as_text=True)
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text
    reply_token = event.reply_token
    thread = threading.Thread(target=process_user_request, args=(user_id, msg, reply_token))
    thread.start()
    
def process_user_request(user_id, msg, reply_token):
    platform = "LINE"
    # 檢查 user_id 是否存在於 user_state 資料表
    user_state = get_user_state(user_id)

    ensure_user_state(user_id)

    if msg == "常見問題":
        update_user_mode(user_id, "faq")
    elif msg == "AI客服":
        update_user_mode(user_id, "AI")
    elif msg == "積分查詢":
        update_user_mode(user_id, "query")
    elif msg == "真人客服" or msg == "帳號申請":
        update_user_mode(user_id, "human")

    user_state = get_user_state(user_id)
    mode = user_state["mode"]

    # 先顯示 loading 動畫
    send_loading_animation(user_id)

    try:
        if mode == "faq":
            reply_content = handle_faq(user_id, user_state, msg, platform)
        elif mode == "query":
            reply_content = handle_query(user_id, user_state, msg, platform)
        elif mode == "AI":
            reply_content = handle_AI(user_id, user_state, msg, platform)
        else: # human
            reply_content = handle_human(user_id, user_state, msg, platform)

        # 因為在背景執行緒，使用 reply_message 搭配 reply_token
        # 注意：reply_content 必須是 TextSendMessage 或 TemplateSendMessage 等物件
        # 如果回傳 None，發送提示訊息（這也會停止 loading 動畫）
        if reply_content is not None:
            line_bot_api.reply_message(reply_token, reply_content)
        else:
            # 設為最小值 5 秒後停止動畫
            send_loading_animation(user_id, 5)

    except Exception as e:
        logger.error(f"處理失敗: {e}")
        line_bot_api.reply_message(reply_token, TextSendMessage(text="抱歉，請稍後再試。"))
        
# ── 啟動 ──────────────────────────────────
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)