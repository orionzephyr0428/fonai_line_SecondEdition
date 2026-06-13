from db import get_connection
import json

# ------------------ 檢查使用者是否存在 ------------------
def user_exists(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM user_state WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None

# ------------------ 建立新使用者 ------------------
def create_user_state(user_id, mode="AI"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_state (user_id, mode) VALUES (%s, %s)", (user_id, mode))
    conn.commit()
    cursor.close()
    conn.close()

# ------------------ 確保使用者存在 ------------------
def ensure_user_state(user_id):
    if not user_exists(user_id):
        create_user_state(user_id)

# ------------------ 抓取使用者資料 ------------------
def get_user_state(user_id):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM user_state WHERE user_id = %s", (user_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result

# ------------------ 更改使用模式 ------------------
def update_user_mode(user_id, mode):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE user_state SET mode = %s WHERE user_id = %s", (mode, user_id))
    conn.commit()
    cursor.close()
    conn.close()

# ------------------ 更新使用者子狀態 ------------------
def update_user_state(user_id, mode=None, sub_mode=None, temp_data=None):
    conn = get_connection()
    cursor = conn.cursor()
    
    fields = []
    values = []
    if mode is not None:
        fields.append("mode=%s")
        values.append(mode)
    if sub_mode is not None:
        fields.append("sub_mode=%s")
        values.append(sub_mode)
    if temp_data is not None:
        fields.append("temp_data=%s")
        values.append(json.dumps(temp_data))
    
    values.append(user_id)
    if fields:
        sql = f"UPDATE user_state SET {', '.join(fields)} WHERE user_id=%s"
        cursor.execute(sql, values)
        conn.commit()
    
    cursor.close()
    conn.close()