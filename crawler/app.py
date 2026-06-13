from playwright.async_api import async_playwright
from flask import Flask, request, jsonify
import os
import asyncio
import aiohttp
import CaptchaCracker as cc
import re
import traceback
import logging
from flask_cors import CORS
from datetime import datetime, timedelta
from urllib.parse import urljoin

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ------------------ 設定 ------------------
URL = "https://ltcpap.mohw.gov.tw/molc/eg999/index"
SCORE_API = "https://ltcpap.mohw.gov.tw/molc/eg999/viewEg_score"

SCORE_TYPES = [
    "cp05L9I1E", "cp05L9I1N",    # 專業課程 實體/網路
    "cp10L9I1E", "cp10L9I1N",    # 專業品質 實體/網路
    "cp15L9I1E", "cp15L9I1N",    # 專業倫理 實體/網路
    "cp20L9I1E", "cp20L9I1N",    # 專業法規 實體/網路
    "ct05L9I2Total",              # 消防安全
    "ct10L9I2Total",              # 緊急應變
    "ct15L9I2Total",              # 感染管制
    "ct20L9I2Total",              # 性別敏感度
    "ctL9I2TotalAll",             # 必修累積總分
    "ct30L9I2Total",              # 原住民族與多元族群
    "ct35L9I2Total",              # 原住民族文化敏感度
    "ct40L9I2Total",              # 多元族群文化感度
    "cpL11I3E",                   # 實體課程總計
    "cpL11I3NB20231012",          # 網路課程 112.10.12以前
    "cpL11I3NA20231013",          # 網路課程 112.10.13以後
]

# ------------------ 模型載入 ------------------
def load_model():
    img_width = 150
    img_height = 45
    max_length = 6
    characters = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    weights_path = os.path.join(base_dir, "weights.h5")
    return cc.ApplyModel(weights_path, img_width, img_height, max_length, characters)

MODEL = load_model()

# ------------------ Browser 設定 ------------------
async def get_browser(p):
    return await p.chromium.launch(
        headless=True,
        args=[
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox'
        ]
    )

# ------------------ 登入流程 ------------------
async def login(username, password, login_url, max_retry, browser):
    last_exc = None
    last_trace = None

    for attempt in range(1, max_retry + 1):
        success = False
        page = await browser.new_page()
        try:
            logger.info(f"登入嘗試 {attempt}/{max_retry}")
            await page.goto(login_url, timeout=30000, wait_until="domcontentloaded")
            await page.wait_for_selector('input[name="idno"]', timeout=30000)

            await page.fill('input[name="idno"]', username)
            await page.evaluate(f"document.querySelector('input[name=\"brDt\"]').value = '{password}'")

            captcha_code = await download_and_recognize_captcha(page, MODEL)
            if not captcha_code:
                logger.warning("驗證碼辨識失敗，重試...")
                continue

            logger.info(f"驗證碼辨識結果: {captcha_code}")
            await fill_and_submit_captcha(page, captcha_code)
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            page_content = await page.content()
            if "查詢積分數" in page_content:
                logger.info("登入成功")
                success = True
                return page, None

            if "驗證碼錯誤" in page_content or "驗證碼" in page_content:
                logger.warning("驗證碼可能錯誤，重試...")
            elif "身分證" in page_content or "出生日期" in page_content:
                logger.warning("帳號或密碼錯誤，停止重試")
                return None, "帳號或密碼錯誤"
            else:
                logger.warning("登入失敗，原因不明")

        except Exception as e:
            last_exc = e
            last_trace = traceback.format_exc()
        finally:
            if not success:
                await page.close()

    error_msg = f"登入失敗。最後錯誤: {last_exc}\n{last_trace}" if last_exc else "登入失敗"
    return None, error_msg

async def download_and_recognize_captcha(page, MODEL, max_attempts=3):
    captcha_elem = await page.wait_for_selector('#simpleCaptcha_image', state="visible", timeout=10000)
    captcha_url = await captcha_elem.get_attribute('src')
    captcha_path = "captcha.jpg"

    full_url = urljoin(page.url, captcha_url)
    response = await page.request.get(full_url)
    if response.status == 200:
        image_bytes = await response.body()
        with open("captcha.jpg", "wb") as f:
            f.write(image_bytes)
        logger.info("原始驗證碼下載成功")
    else:
        raise Exception("無法從伺服器獲取原始驗證碼圖片")

    try:
        captcha_code = MODEL.predict(captcha_path)
        if len(captcha_code) == 6 and captcha_code.isalnum():
            logger.info("驗證碼辨識成功")
            return captcha_code
        else:
            logger.warning(f"驗證碼格式錯誤: '{captcha_code}'")
            return None
    except Exception as e:
        logger.error(f"模型辨識失敗: {e}")
        return None

async def fill_and_submit_captcha(page, captcha_code):
    try:
        await page.wait_for_selector('input[name="captcha"]', timeout=15000)
        await page.fill('input[name="captcha"]', captcha_code)
        login_btn = page.locator("button", has_text="查詢")
        logger.info("按下查詢")
        await login_btn.wait_for(state="visible", timeout=15000)
        await login_btn.click()
    except Exception as e:
        logger.warning(f"正常點擊失敗，嘗試 JS Submit: {e}")
        try:
            await page.evaluate('document.querySelector("form").submit()')
        except Exception as final_error:
            raise Exception(f"這回合登入徹底沒救了: {final_error}")

# ------------------ 抓頁面資訊 ------------------
async def extract_valid_period(page):
    id_period_el = await page.query_selector("div.course-start p:last-child")
    if not id_period_el:
        logger.error("找不到有效期間元素")
        return "", ""

    id_period = (await id_period_el.inner_text()).strip()
    pattern = r"(\d+/\d+/\d+)\s*-\s*(\d+/\d+/\d+)"
    match = re.search(pattern, id_period)
    if not match:
        logger.error(f"無法解析有效期間: {id_period}")
        return "", ""

    return match.group(1), match.group(2)

# ------------------ 日期計算（純 Python）------------------
def calculate_date_range(valid_start_str, valid_end_str):
    def parse_roc(s):
        parts = s.split('/')
        return datetime(int(parts[0]) + 1911, int(parts[1]), int(parts[2]))

    def to_roc_str(d):
        return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"

    start_date = parse_roc(valid_start_str)
    end_date = parse_roc(valid_end_str)

    now = datetime.now()
    start_month = start_date.month
    start_day = start_date.day

    this_year_anniversary = datetime(now.year, start_month, start_day)

    if now < this_year_anniversary:
        ideal_start = datetime(now.year - 1, start_month, start_day)
    else:
        ideal_start = this_year_anniversary

    actual_query_start = max(ideal_start, start_date)

    try:
        actual_query_end = datetime(actual_query_start.year + 1, start_month, start_day) - timedelta(days=1)
    except ValueError:
        actual_query_end = datetime(actual_query_start.year + 1, 2, 28)

    actual_query_end = min(actual_query_end, end_date)

    return to_roc_str(actual_query_start), to_roc_str(actual_query_end)

# ------------------ 直接打 API ------------------
async def fetch_all_scores(cookies, selected_op, cert_sdt, cert_edt):
    async with aiohttp.ClientSession(cookies=cookies) as session:
        tasks = [
            session.post(SCORE_API, data={
                "selectedOp": selected_op,
                "certSdt": cert_sdt,
                "certEdt": cert_edt,
                "type": t,
            })
            for t in SCORE_TYPES
        ]
        responses = await asyncio.gather(*tasks)

        results = {}
        for t, resp in zip(SCORE_TYPES, responses):
            try:
                data = await resp.json(content_type=None)
                results[t] = str(data.get("score", 0))
            except Exception as e:
                logger.error(f"解析 {t} 失敗: {e}")
                results[t] = "0"

    logger.info(f"fetch_all_scores 完成: {results}")
    return results

# ------------------ 組資料 ------------------
def build_data_list(valid_start, valid_end, cert_sdt, cert_edt, scores):
    return [
        ['有效期間', valid_start, valid_end],
        ['查詢區間', cert_sdt, cert_edt],
        ['課程屬性', '登錄積分(實體)', '登錄積分(網路)'],
        ['專業課程',  scores['cp05L9I1E'], scores['cp05L9I1N']],
        ['專業品質',  scores['cp10L9I1E'], scores['cp10L9I1N']],
        ['專業倫理',  scores['cp15L9I1E'], scores['cp15L9I1N']],
        ['專業法規',  scores['cp20L9I1E'], scores['cp20L9I1N']],
        ['課程類別', '系統登錄積分'],
        ['消防安全',  scores['ct05L9I2Total']],
        ['緊急應變',  scores['ct10L9I2Total']],
        ['感染管制',  scores['ct15L9I2Total']],
        ['性別敏感度', scores['ct20L9I2Total']],
        ['課程類別', '累積積分'],
        ['原住民族與多元族群文化敏感度及能力 (原名稱：多元文化族群)', scores['ct30L9I2Total']],
        ['原住民族文化敏感度及能力', scores['ct35L9I2Total']],
        ['多元族群文化感度及能力',   scores['ct40L9I2Total']],
        ['課程類別', '累積積分'],
        ['實體課程', scores['cpL11I3E']],
        ['網路課程112.10.12以前至多60點', scores['cpL11I3NB20231012']],
        ['網路課程112.10.13以後至多40點', scores['cpL11I3NA20231013']],
    ]

# ------------------ 主流程 ------------------
async def scrape_single(idno, brDt, time_range):
    async with async_playwright() as p:
        browser = await get_browser(p)
        try:
            page, error = await login(idno, brDt, URL, 5, browser)
            if error:
                return {"success": False, "error": error}

            selected_op = await page.eval_on_selector("#selectedOp", "el => el.value")
            valid_start, valid_end = await extract_valid_period(page)
            cookies = {c['name']: c['value'] for c in await page.context.cookies()}

            await page.close()
        finally:
            await browser.close()

    # 計算查詢區間
    if time_range == 1:
        cert_sdt, cert_edt = calculate_date_range(valid_start, valid_end)
    else:
        cert_sdt, cert_edt = valid_start, valid_end

    logger.info(f"查詢區間: {cert_sdt} ~ {cert_edt}")

    # 同時打 19 個 API
    scores = await fetch_all_scores(cookies, selected_op, cert_sdt, cert_edt)
    data = build_data_list(valid_start, valid_end, cert_sdt, cert_edt, scores)

    return {"success": True, "data": data}

def main(idno, brDt, time_range):
    result = asyncio.run(scrape_single(idno, brDt, time_range))
    if not result.get("success"):
        return {"success": False, "error": result.get("error", "Unknown error")}
    logger.info(f"爬取完成，共 {len(result.get('data', []))} 筆")
    return {"success": True, "data": result.get("data", [])}

# ------------------ Flask API ------------------
@app.route("/run_one_6year", methods=["POST"])
def run_one_6year():
    data = request.get_json() or {}
    idno = data.get("idno")
    brDt = data.get("brDt")
    if not idno or not brDt:
        return jsonify({"success": False, "error": "missing idno or brDt"}), 400
    return jsonify(main(idno, brDt, 6))

@app.route("/run_one_1year", methods=["POST"])
def run_one_1year():
    data = request.get_json() or {}
    idno = data.get("idno")
    brDt = data.get("brDt")
    if not idno or not brDt:
        return jsonify({"success": False, "error": "missing idno or brDt"}), 400
    return jsonify(main(idno, brDt, 1))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=6000, debug=True)
