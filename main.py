# --- 「神殿」：AI 宗師的核心 (藍圖三：神諭的記憶) ---
#
# 版本：已植入 Neon 資料庫記憶功能
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, content_types #<-- 新增 import
from PIL import Image
import io
import psycopg2 #<-- 新增 import：資料庫連接工具
import json     #<-- 新增 import：處理 JSON 格式的歷史紀錄

# --- 步驟一：神殿的鑰匙 (從 Render.com 讀取) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL') #<-- 新增：讀取大腦連接線

# --- 步驟二：神殿的基礎建設 --- (保持不變)
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 步驟三：連接「神之鍛造廠」(Gemini) --- (保持不變)
try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    print(f"!!! 嚴重錯誤：無法設定 Google API Key。錯誤：{e}")

# --- 步驟四：AI 宗師的「靈魂」核心 (System Prompt) --- (保持不變)
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是 100% 的「蘇格拉底式教學法」。
# ... (省略之前的蘇格拉底提示詞，內容不變) ...
# --- 你的「工具使用」--- (已移除)
"""

# --- 步驟五 & 六：AI 宗師的「大腦」設定 (已移除 Tools) --- (保持不變)
model = genai.GenerativeModel(
    model_name='gemini-pro',
    system_instruction=system_prompt,
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# --- ★★★ 新增：步驟七：連接「外部大腦」(Neon 資料庫) ★★★ ---

# 函數：建立資料庫連接
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        return None

# 函數：初始化資料庫（如果表格不存在就建立）
def initialize_database():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        user_id TEXT PRIMARY KEY,
                        history JSONB
                    );
                """)
                conn.commit()
            print("--- 資料庫表格 'chat_history' 確認/建立成功 ---")
        except Exception as e:
            print(f"!!! 錯誤：無法初始化資料庫表格。錯誤：{e}")
        finally:
            conn.close()

# 函數：讀取聊天紀錄
def get_chat_history(user_id):
    conn = get_db_connection()
    history = []
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result:
                    # 從 JSONB 直接讀取 Python 列表/字典
                    history = result[0] 
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    # 確保返回的是 Gemini 能理解的 Content 列表
    # (舊語法 0.8.5 需要手動轉換)
    gemini_history = []
    if isinstance(history, list): # 確保 history 是列表
         for item in history:
             # 檢查每個 item 是否有 'role' 和 'parts'
             if isinstance(item, dict) and 'role' in item and 'parts' in item:
                 # 確保 parts 是列表
                 parts = item['parts'] if isinstance(item['parts'], list) else [item['parts']]
                 try:
                    # 嘗試創建 Content 物件
                    gemini_history.append(content_types.to_content({'role': item['role'], 'parts': parts}))
                 except Exception as convert_e:
                    print(f"!!! 警告：轉換歷史紀錄項目失敗: {item}。錯誤: {convert_e}")
             else:
                 print(f"!!! 警告：歷史紀錄項目格式不符: {item}")

    return gemini_history

# 函數：儲存聊天紀錄
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            # 將 Gemini 的 Content 列表轉換回簡單的字典列表以儲存為 JSONB
            history_to_save = []
            if chat_session.history: # 檢查 history 是否存在且非空
                for content in chat_session.history:
                     # 確保 content.parts 不是 None 且可迭代
                     parts_text = [part.text for part in content.parts if hasattr(part, 'text')] if content.parts else []
                     history_to_save.append({'role': content.role, 'parts': parts_text})

            with conn.cursor() as cur:
                # 使用 UPSERT 語法：如果 user_id 已存在則更新，否則插入新紀錄
                cur.execute("""
                    INSERT INTO chat_history (user_id, history)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save))) # 將列表轉為 JSON 字串儲存
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法儲存 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()

# 在程式啟動時，嘗試初始化資料庫
initialize_database()

# --- 步驟八：神殿的「入口」(Webhook) --- (保持不變)
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 重大修改：讀寫記憶 ★) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):

    user_id = event.source.user_id

    # 1. ★ 讀取「過去的記憶」 ★
    past_history = get_chat_history(user_id)

    # 2. ★ 根據「記憶」開啟「對話」 ★
    #    (注意：我們每次都基於讀取的歷史紀錄開啟一個新的對話物件)
    #    (這與之前在記憶體中保留 chat_session 不同)
    try:
         # 使用兼容 0.8.5 的方式，history 參數可能不直接支持 Content 物件
         # 我們需要將其轉換回字典列表
         history_for_start = []
         for content in past_history:
             parts_text = [part.text for part in content.parts if hasattr(part, 'text')] if content.parts else []
             history_for_start.append({'role': content.role, 'parts': parts_text})

         chat_session = model.start_chat(history=history_for_start)
    except Exception as start_chat_e:
         print(f"!!! 警告：從歷史紀錄開啟對話失敗。使用空對話。錯誤：{start_chat_e}")
         # 如果載入歷史失敗，就開啟一個全新的對話
         chat_session = model.start_chat(history=[]) # 確保傳遞空列表

    # 3. 準備「當前的輸入」
    prompt_parts = [] # 先初始化
    try:
        if isinstance(event.message, ImageMessage):
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = io.BytesIO(message_content.content)
            img = Image.open(image_bytes)
            # Gemini 需要圖像數據在前，文字在後（或者明確指定）
            prompt_parts = [img, "老師，這張圖片上的物理問題（如下圖）要怎麼思考？"] 
        else:
            prompt_parts = [event.message.text]

        # 4. ★ 呼叫 Gemini，進行「當前的對話」 ★
        response = chat_session.send_message(prompt_parts)
        final_text = response.text

        # 5. ★ 儲存「更新後的記憶」 ★
        #    (注意：chat_session.history 現在包含了這次的問與答)
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫操作失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在檢索記憶或冥想中，請稍後再試。"

    # 6. 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 --- (保持不變)
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)