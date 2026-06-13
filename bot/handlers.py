from db import get_connection
from message_builders import build_message, build_credit_flex_message
from state_service import update_user_state
from config import CRAWLER_BASE_URL, REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ
from RAG import main as RAG
import json
import requests
import re
from linebot.models import TextSendMessage, ImageSendMessage
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

# ------------------ 處理 積分查詢 ------------------
def handle_query(user_id, user_state, msg, platform):
    # 取得暫存資料
    temp_data = json.loads(user_state["temp_data"]) if user_state["temp_data"] else {}

    # 根據 sub_mode 判斷要做什麼
    sub_mode = user_state["sub_mode"]

    if sub_mode is None or msg == "積分查詢":
        temp_data.clear()

        update_user_state(user_id, mode="query", sub_mode="select_period", temp_data=temp_data)
        
        options = [
            {"label": "當年積分", "text": "當年積分"},
            {"label": "六年積分", "text": "六年積分"}
        ]
        reply_message = build_message(platform, "請問要查詢當年積分還是六年積分？", options)
        return reply_message
    
    # Step 2: 選擇查詢期間 → 顯示填寫身分證
    elif sub_mode == "select_period":
        if msg == "當年積分":
            temp_data["time_period"] = 1
        elif msg == "六年積分":
            temp_data["time_period"] = 6
        else:
            temp_data["time_period"] = 1  # 預設當年
        
        update_user_state(user_id, mode="query", sub_mode="idno", temp_data=temp_data)
        if platform == "LINE":
            reply_message = TextSendMessage(
                text="請輸入您的身分證字號:(英文須大寫)"
            )
        elif platform == "web":
            reply_message = {
                "messages": [
                    { "type": "text", "content": "請輸入您的身分證字號:(英文須大寫)" }
                ]
            }
        return reply_message
           
    # Step 3: 已填 idno → 顯示填寫 brDt
    elif sub_mode == "idno":
        temp_data["idno"] = msg
        update_user_state(user_id, mode="query", sub_mode="brDt", temp_data=temp_data)
        if platform == "LINE":
            reply_message = TextSendMessage(
                text="請問您的民國出生日期是?\n(請依此格式填寫:099/01/01)"
            )
        elif platform == "web":
            reply_message = {
                "messages": [
                    { "type": "text", "content": "請問您的民國出生日期是?\n(請依此格式填寫:099/01/01)" }
                ]
            }
        return reply_message
        
    # Step 4: 已填 brDt → 顯示積分
    elif sub_mode == "brDt":
        logger.info("開始查詢")
        # 驗證並轉換日期格式
        brDt = msg.strip()
        
        # 民國年格式: 099/01/01 或 99/01/01
        roc_pattern = r'^(\d{2,3})/(\d{2})/(\d{2})$'
        # 西元年格式: 2010/01/01 或 2010-01-01
        ad_pattern = r'^(\d{4})[/-](\d{2})[/-](\d{2})$'
        
        roc_match = re.match(roc_pattern, brDt)
        ad_match = re.match(ad_pattern, brDt)
        
        if roc_match:
            # 已是民國年格式，確保年份為3位數
            year = roc_match.group(1)
            month = roc_match.group(2)
            day = roc_match.group(3)
            # 補足3位數年份
            if len(year) == 2:
                year = '0' + year
            brDt = f"{year}/{month}/{day}"
        elif ad_match:
            # 西元年轉民國年
            ad_year = int(ad_match.group(1))
            month = ad_match.group(2)
            day = ad_match.group(3)
            roc_year = ad_year - 1911
            if roc_year < 0:
                # 無效的西元年
                err_text = "日期格式錯誤，請輸入民國年格式 (例如: 099/01/01)"
                if platform == "LINE":
                    return TextSendMessage(text=err_text)
                else:
                    return {"messages": [{"type": "text", "content": err_text}]}
            brDt = f"{roc_year:03d}/{month}/{day}"
        else:
            # 格式不符
            err_text = "日期格式錯誤，請輸入民國年格式 (例如: 099/01/01) 或西元年格式 (例如: 2010/01/01)"
            if platform == "LINE":
                return TextSendMessage(text=err_text)
            else:
                return {"messages": [{"type": "text", "content": err_text}]}
        
        temp_data["brDt"] = brDt
        update_user_state(user_id, mode="human", sub_mode="", temp_data=temp_data)

        # 取得查詢參數
        idno = temp_data.get("idno")
        brDt = temp_data.get("brDt")
        time_period = temp_data.get("time_period", 1)
        logger.info("取得查詢參數 idno=%s, brDt=%s, time_period=%s", idno, brDt, time_period)
        # 根據 time_period 選擇 API URL
        if time_period == 6:
            url = f"{CRAWLER_BASE_URL}/run_one_6year"
        else:
            url = f"{CRAWLER_BASE_URL}/run_one_1year"

        # 呼叫外部服務並處理可能的網路/HTTP 錯誤
        try:
            logger.info("呼叫 API %s", url)
            resp = requests.post(url, json={"idno": idno, "brDt": brDt}, timeout=(REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ))
            resp.raise_for_status()
            logger.info("呼叫成功")
        except requests.RequestException as e:
            err_text = "查詢失敗，請稍後再試。"
            # err_text = f"查詢失敗，請稍後再試。錯誤：{str(e)}"
            if platform == "LINE":
                return TextSendMessage(text=err_text)
            else:
                return {"messages": [{ "type": "text", "content": err_text }]}
        
        # 解析 JSON 回應
        response_data = resp.json()
        
        # 判斷回傳結果
        if not response_data.get("success"):
            err_text = response_data.get("error", "查詢失敗，請稍後再試。")
            if platform == "LINE":
                return TextSendMessage(text=err_text)
            else:
                return {"messages": [{"type": "text", "content": err_text}]}
        
        # 使用 Flex Message 回傳積分結果
        if platform == "LINE":
            reply_message = build_credit_flex_message(response_data["data"], time_period)
            logger.info("回傳 Flex Message（altText: %s）", reply_message.alt_text)
        elif platform == "web":
            # Web 平台使用文字格式
            data_list = response_data.get("data", [])
            table_lines = []
            for item in data_list:
                if isinstance(item, list):
                    table_lines.append("\t".join(str(x) for x in item).strip())
                elif isinstance(item, dict):
                    table_lines.append("\t".join(f"{k}:{v}" for k, v in item.items()))
            table_output = "\n".join(table_lines)
            reply_message = {
                "messages": [
                    { "type": "text", "content": table_output }
                ]
            }
        return reply_message        

# ------------------ 處理 AI 客服 ------------------
def handle_AI(user_id, user_state, msg, platform):
    # 取得使用者的暫存資料
    temp_data = json.loads(user_state["temp_data"]) if user_state["temp_data"] else {}

    sub_mode = user_state["sub_mode"]

    if sub_mode is None or msg == "AI客服":
        temp_data.clear()

        update_user_state(user_id, mode="AI", sub_mode="first", temp_data=temp_data)
        if platform == "LINE":
            reply_message = TextSendMessage(
                text="很高興為您服務！我是您的長照資訊小幫手，有什麼我可以幫助您的嗎？"
            )
        elif platform == "web":
            reply_message = {
                    "messages": [
                        { "type": "text", "content": "很高興為您服務！我是您的長照資訊小幫手，有什麼我可以幫助您的嗎？" }
                    ]
                }
        return reply_message
    elif sub_mode == "first":
        # 檢查是否超過 1 分鐘沒互動（使用 updated_at 欄位）
        updated_at = user_state.get("updated_at")
        if updated_at:
            elapsed = (datetime.now() - updated_at).total_seconds()
            if elapsed > 60:
                # 超時，靜默轉真人客服（不回傳訊息）
                update_user_state(user_id, mode="human", sub_mode="notified", temp_data=temp_data)
                return None
        
        # 更新 updated_at（觸發資料庫自動更新時間）
        update_user_state(user_id, sub_mode="first")
        
        result = RAG(msg, user_id)
        if result['success']:
            text = result['answer']
        else:
            text = "這題超出我們資料庫範圍，我已幫您請教專員，取得答案就回覆您。"
        if platform == "LINE":
            reply_message = TextSendMessage(text=text)
        elif platform == "web":
            reply_message = {
                    "messages": [
                        { "type": "text", "content": text }
                    ]
                }
        return reply_message

# ------------------ 處理 FAQ 請求 ------------------
def handle_faq(user_id, user_state, msg, platform):
    # 取得暫存資料
    temp_data = json.loads(user_state["temp_data"]) if user_state["temp_data"] else {}

    # 根據 sub_mode 判斷要做什麼
    sub_mode = user_state["sub_mode"]

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if sub_mode is None or msg == "常見問題":
        temp_data.clear()
        cursor.execute("SELECT DISTINCT category1 FROM faq_questions")
        categories = cursor.fetchall()

        if not categories:
            update_user_state(user_id, mode="human", sub_mode=None, temp_data={})
            cursor.close()
            conn.close()
            return None

        update_user_state(user_id, mode="faq", sub_mode="category1", temp_data=temp_data)

        options = [{"label": row["category1"], "text": row["category1"]} for row in categories]
        reply_message = build_message(platform, "請選擇服務分類：", options)
        cursor.close()
        conn.close()
        return reply_message
    
    
    # Step 2: 已選 category1 → 顯示 category2
    elif sub_mode == "category1":
        cursor.execute("SELECT DISTINCT category2 FROM faq_questions WHERE category1=%s", (msg,))
        categories = cursor.fetchall()

        if not categories:
            update_user_state(user_id, mode="human", sub_mode=None, temp_data={})
            cursor.close()
            conn.close()
            return None

        temp_data["category1"] = msg

        update_user_state(user_id, mode="faq", sub_mode="category2", temp_data=temp_data)

        options = [{"label": row["category2"], "text": row["category2"]} for row in categories]
        reply_message = build_message(platform, "請選擇子分類：", options)

        cursor.close()
        conn.close()
        return reply_message
    
    # Step 3: 已選 category2 → 顯示問題
    elif sub_mode == "category2":
        cursor.execute("SELECT id, question FROM faq_questions WHERE category1=%s AND category2=%s",
                       (temp_data["category1"], msg))
        questions = cursor.fetchall()

        if not questions:
            update_user_state(user_id, mode="human", sub_mode=None, temp_data={})
            cursor.close()
            conn.close()
            return None

        temp_data["category2"] = msg

        update_user_state(user_id, mode="faq", sub_mode="question", temp_data=temp_data)

        options = [{"label": row["question"][:20], "text": row["question"]} for row in questions]
        reply_message = build_message(platform,"請選擇問題：", options)

        cursor.close()
        conn.close()
        return reply_message

    # Step 4: 已選 question → 顯示答案
    elif sub_mode == "question":
        cursor.execute("SELECT answer_json FROM faq_questions WHERE category1=%s AND category2=%s AND question=%s",
                       (temp_data["category1"], temp_data["category2"], msg))
        row = cursor.fetchone()

        if not row or not row.get("answer_json"):
            update_user_state(user_id, mode="human", sub_mode=None, temp_data={})
            cursor.close()
            conn.close()
            return None
        else:
            # 把 JSON 字串轉成 Python 物件
            answers = json.loads(row['answer_json'])
            
            messages = []
            for ans in answers:
                if ans["type"] == "text":
                    if platform == "LINE":
                        messages.append(TextSendMessage(text=ans["content"]))
                    elif platform == "web":
                        messages.append({"type": "text", "content": ans["content"]})
                elif ans["type"] == "url":
                    if platform == "LINE":
                        messages.append(ImageSendMessage(original_content_url=ans["content"],
                                                    preview_image_url=ans["content"]))
                    elif platform == "web":
                        messages.append({"type": "image", "url": ans["content"]})
                        
            if platform == "web":
                reply_message = {"messages": messages}
            else:
                reply_message = messages

        # 回到初始 FAQ 狀態
        update_user_state(user_id, mode="human", sub_mode=None, temp_data={})
        cursor.close()
        conn.close()
        return reply_message
    
# ------------------ 處理 真人客服 ------------------
def handle_human(user_id, user_state, msg, platform):
    # 取得使用者的暫存資料
    temp_data = json.loads(user_state["temp_data"]) if user_state["temp_data"] else {}

    sub_mode = user_state["sub_mode"]

    if sub_mode is None or msg == "真人客服":
        temp_data.clear()

        update_user_state(user_id, mode="human", sub_mode="notified", temp_data=temp_data)
        if platform == "LINE":
            reply_message = TextSendMessage(text="稍後由專員回覆")
        elif platform == "web":
            reply_message = {"messages": [{"type": "text", "content": "稍後由專員回覆"}]}
        return reply_message
