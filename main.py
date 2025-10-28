# --- 「神殿」：AI 宗師的核心 (藍圖三：穩定版) ---
#
# 版本：已移除「本地 RAG」以修復 OOM (Out of Memory) 錯誤
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, content_types
from PIL import Image
import io
import psycopg2 # 藍圖三：資料庫工具
import json     # 藍圖三：資料庫工具
# ★ 移除了 import fitz ★

# --- 步驟一：神殿的鑰匙 (從 Render.com 讀取) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- 步驟二：神殿的基礎建設 ---
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 步驟三：連接「神之鍛造廠」(Gemini) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    print(f"!!! 嚴重錯誤：無法設定 Google API Key。錯誤：{e}")

# --- ★ 移除了 load_corpus_from_local_folder() 函數 ★ ---

# --- 步驟四：AI 宗師的「靈魂」核心 (★ 恢復無 RAG 版 ★) ---
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是 100% 的「蘇格拉底式教學法」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

# --- ★ 移除了 RAG 相關指令 ★ ---

# --- 你的「教學流程」---
1.  **「確認問題」**：(同前)
2.  **「拆解問題」**：(同前)
3.  **「逐步引導」**：(同前)
4.  **「保持鼓勵」**：(同前)
"""

# --- 步驟五 & 六：AI 宗師的「大腦」設定 (★ 兼容版 ★) ---
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro', # ★ 確保使用兼容的 0.8.5 版本模型
    system_instruction=system_prompt,
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# --- 步驟七：連接「外部大腦」(Neon 資料庫) (★ 完整修正版 ★) ---

# 函數：建立資料庫連接
def get_db_connection():
    try:
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
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

# 函數：讀取聊天紀錄 (兼容 0.8.5 的字典格式)
def get_chat_history(user_id):
    conn = get_db_connection()
    history_json = [] 
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    history_json = result[0] 
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    return history_json 

# 函數：儲存聊天紀錄 (★ 修正 JSON 序列化錯誤 ★)
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            # ★★★ 新增：手動將 Content 物件轉換為字典列表 ★★★
            history_to_save = []
            if chat_session.history: # 確保 history 存在且非空
                for content in chat_session.history:
                    # 檢查 parts 是否存在且可迭代，並提取文字
                    parts_text = []
                    if content.parts:
                        try:
                            # 嘗試提取 text 屬性
                            parts_text = [part.text for part in content.parts if hasattr(part, 'text')]
                        except Exception as part_e:
                            print(f"!!! 警告：提取 history parts 時出錯: {part_e}。內容: {content}")
                            # 如果提取 text 失敗，可以考慮存儲其他信息或跳過
                            # parts_text = ["[無法提取的部分]"] # 或者其他標記

                    # 確保 role 存在
                    role = content.role if hasattr(content, 'role') else 'unknown' 

                    history_to_save.append({'role': role, 'parts': parts_text})
            # ★★★ 轉換完畢 ★★★

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_history (user_id, history)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save))) # ★ 現在存儲的是字典列表的 JSON 字串
                conn.commit()
        except Exception as e:
            # ★ 這裡的錯誤現在更可能是資料庫本身的錯誤
            print(f"!!! 錯誤：無法儲存 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()

# 在程式啟動時，只初始化資料庫
initialize_database()
# ★ 移除了 load_corpus_from_local_folder() ★

# --- 步驟八：神殿的「入口」(Webhook) ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 恢復「藍圖三」穩定版 ★) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):

    user_id = event.source.user_id

    # 1. 讀取「過去的記憶」(藍圖三)
    past_history = get_chat_history(user_id)

    # 2. 根據「記憶」開啟「對話」(藍圖三)
    try:
         chat_session = model.start_chat(history=past_history)
    except Exception as start_chat_e:
         print(f"!!! 警告：從歷史紀錄開啟對話失敗。使用空對話。錯誤：{start_chat_e}")
         chat_session = model.start_chat(history=[])

    # 3. 準備「當前的輸入」
    prompt_parts = []

    try:
        if isinstance(event.message, ImageMessage):
            user_question = "老師，這張圖片上的物理問題（如下圖）要怎麼思考？"
            prompt_parts = [user_question] # 暫時禁用圖片
        else:
            user_question = event.message.text
            prompt_parts = [user_question]

        # ★ 移除了 RAG 相關的所有程式碼 ★

        # 4. 呼叫 Gemini，進行「當前的對話」
        response = chat_session.send_message(prompt_parts)
        final_text = response.text

        # 5. 儲存「更新後的記憶」(藍圖三)
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫操作失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在檢索記憶或冥想中，請稍後再試。"

    # 6. 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)