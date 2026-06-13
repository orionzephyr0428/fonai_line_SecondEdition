# LINE Bot SDK
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    TextSendMessage, QuickReply, QuickReplyButton,
    FlexSendMessage, PostbackAction, ImageSendMessage
)

# ------------------ 處理 FAQ 請求版面 ------------------
def build_message(platform, title, options):
    if platform == "LINE":
        hero_url = None

        buttons = []
        for opt in options:
            button = {
                "type": "button",
                "action": {
                    "type": "message",
                    "label": opt["label"],
                    "text": opt["text"]
                },
                "style": "link",
                "margin": "sm"
            }
            buttons.append(button)


        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": hero_url if hero_url else "https://picsum.photos/seed/picsum/200/300",
                "size": "full",
                "aspectRatio": "20:9",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": title,
                        "weight": "bold",
                        "size": "lg",
                        "wrap": True
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": buttons
            }
        }

        return FlexSendMessage(
            alt_text=title,
            contents=bubble
        )
    elif platform == "web":
        # 文字區（標題 + 選擇性前言 + 選擇性圖片連結）
        msgs = []
    
        # 選項區（只保留 label，點擊後前端會把 label 當 message 回傳）
        normalized_options = []
        for opt in (options or []):
            if isinstance(opt, dict):
                label = opt.get("label") or opt.get("text") or ""
            else:
                label = str(opt)
            normalized_options.append({"label": label})

        msgs.append({
            "type": "options",
            "id": "menu_id",
            "title": title,
            "options": normalized_options
        })

        return {"messages": msgs}
    else:
        raise ValueError(f"Unknown platform: {platform}")
    

# ------------------ 積分版面 ------------------
def build_credit_flex_message(data_list, time_period):
    # --- 1. 工具函式：防呆提取資料 ---
    def g(row, col, default="0"):
        try:
            val = str(data_list[row][col]).strip()
            return val if val else default
        except:
            return default

    # --- 2. 核心數據處理 ---
    # 基礎資訊
    valid_range = f"{g(0, 1)} - {g(0, 2)}"
    query_range = f"{g(1, 1)} - {g(1, 2)}"
    
    # 實體與網路課程計算 (索引 17 為實體, 18+19 為網路加總)
    physical_val = g(17, 1)
    try:
        online_total = round(float(g(18, 1)) + float(g(19, 1)), 1)
        current_points = float(physical_val) + online_total
    except:
        online_total = 0.0
        current_points = float(physical_val) if physical_val.replace('.','',1).isdigit() else 0.0

    # --- 3. 根據 time_period 動態設定進度條參數 ---
    if time_period == 6:
        target_points = 120
        progress_title = "六年總計"
        progress_color = "#FFBB00"  # 橘黃色
    else:
        target_points = 20
        progress_title = "年度目標"
        progress_color = "#27ACB9"  # 藍綠色

    # 計算百分比
    percent = min(100, int((current_points / target_points) * 100)) if target_points > 0 else 0

    # --- 4. 組合 Flex Message ---
    bubble = {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "長照積分完整查詢結果", "weight": "bold", "color": "#FFFFFF", "size": "lg"},
                {"type": "box", "layout": "vertical", "margin": "md", "contents": [
                    {"type": "text", "text": f"🪪 證照效期：{valid_range}", "color": "#FFFFFF", "size": "xs", "margin": "xs"},
                    {"type": "text", "text": f"📅 查詢區間：{query_range}", "color": "#FFFFFF", "size": "xs"}
                ]}
            ],
            "backgroundColor": "#27ACB9"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "✨ 積分達成進度", "weight": "bold", "size": "md"},
                {"type": "box", "layout": "vertical", "margin": "md", "contents": [
                    # 這裡根據 time_period 僅顯示一條進度條
                    {"type": "text", "text": f"{progress_title} ({target_points}點)：目前 {current_points} 點", "size": "xs", "color": "#666666"},
                    {"type": "box", "layout": "horizontal", "margin": "xs", "contents": [
                        {"type": "box", "layout": "vertical", "contents": [], "width": f"{max(1, percent)}%", "backgroundColor": progress_color, "height": "8px"},
                        {"type": "box", "layout": "vertical", "contents": [], "width": f"{max(0, 100-percent)}%", "backgroundColor": "#DEDEDE", "height": "8px"}
                    ], "cornerRadius": "4px"}
                ]},
                {"type": "separator", "margin": "xl"},
                {"type": "text", "text": "📘 專業課程屬性", "weight": "bold", "size": "sm", "margin": "xl"},
                {"type": "box", "layout": "vertical", "margin": "md", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "專業課程 (實體/網路)", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": f"{g(3,1)} / {g(3,2)}", "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "專業品質", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": f"{g(4,1)} / {g(4,2)}", "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "專業倫理", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": f"{g(5,1)} / {g(5,2)}", "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "專業法規", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": f"{g(6,1)} / {g(6,2)}", "size": "xs", "align": "end", "flex": 2}]}
                ]},
                {"type": "text", "text": "🚨 系統登錄積分 (必修項目)", "weight": "bold", "size": "sm", "margin": "xl"},
                {"type": "box", "layout": "vertical", "margin": "md", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "消防安全", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(8, 1), "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "緊急應變", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(9, 1), "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "感染管制", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(10, 1), "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "性別敏感度", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(11, 1), "size": "xs", "align": "end", "flex": 2}]}
                ]},
                {"type": "text", "text": "🌍 族群文化感度", "weight": "bold", "size": "sm", "margin": "xl"},
                {"type": "box", "layout": "vertical", "margin": "md", "spacing": "sm", "contents": [
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "原住民族與多元族群", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(13, 1), "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "原住民族文化感度", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(14, 1), "size": "xs", "align": "end", "flex": 2}]},
                    {"type": "box", "layout": "horizontal", "contents": [{"type": "text", "text": "多元族群文化感度", "size": "xs", "color": "#555555", "flex": 4}, {"type": "text", "text": g(15, 1), "size": "xs", "align": "end", "flex": 2}]}
                ]},
                {"type": "separator", "margin": "xl"},
                {"type": "box", "layout": "horizontal", "margin": "lg", "contents": [
                    {"type": "text", "text": "實體課程總計", "size": "sm", "weight": "bold", "flex": 4},
                    {"type": "text", "text": f"{physical_val}", "size": "sm", "align": "end", "weight": "bold", "color": "#27ACB9", "flex": 2}
                ]},
                {"type": "box", "layout": "horizontal", "margin": "sm", "contents": [
                    {"type": "text", "text": "網路課程總計", "size": "sm", "weight": "bold", "flex": 4},
                    {"type": "text", "text": f"{online_total}", "size": "sm", "align": "end", "weight": "bold", "color": "#27ACB9", "flex": 2}
                ]}
            ]
        }
    }

    return FlexSendMessage(alt_text="長照積分查詢結果", contents=bubble)