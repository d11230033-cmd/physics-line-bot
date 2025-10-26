# --- 「神殿」：AI 宗師的核心 (藍圖三 + 新・藍圖一) ---
#
# 版本：已植入 Neon 記憶 + 本地 RAG (PyMuPDF)
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
import fitz     # ★ 新・藍圖一：PDF 閱讀工具 (PyMuPDF) ★

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

# --- ★ 新・藍圖一：本地 RAG 函數 ★ ---

# 全局變量，用於緩存教科書內容，避免每次都讀取
RAG_CACHE = None

def load_corpus_from_local_folder():
    global RAG_CACHE
    # 如果緩存已存在，直接返回，提高效率
    if RAG_CACHE is not None:
        print("--- (RAG) 使用緩存的教科書內容 ---")
        return RAG_CACHE

    print("--- (RAG) 正在從 'corpus' 資料夾讀取所有 PDF 和 TXT... ---")
    corpus_text = ""
    corpus_dir = 'corpus'

    try:
        if not os.path.exists(corpus_dir):
            print(f"!!! (RAG) 警告：找不到 '{corpus_dir}' 資料夾。")
            return ""

        for filename in os.listdir(corpus_dir):
            filepath = os.path.join(corpus_dir, filename)

            if filename.endswith('.pdf'):
                print(f"  > (RAG) 正在讀取 PDF: {filename}")
                try:
                    with fitz.open(filepath) as doc:
                        for page in doc:
                            corpus_text += page.get_text() + "\n\n"
                except Exception as pdf_e:
                    print(f"!!! (RAG) 錯誤：讀取 PDF '{filename}' 失敗。錯誤：{pdf_e}")

            elif filename.endswith('.txt'):
                print(f"  > (RAG) 正在讀取 TXT: {filename}")
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        corpus_text += f.read() + "\n\n"
                except Exception as txt_e:
                    print(f"!!! (RAG) 錯誤：讀取 TXT '{filename}' 失敗。錯誤：{txt_e}")

        RAG_CACHE = corpus_text # 存入緩存
        print("--- (RAG) 教科書內容讀取並緩存完畢！ ---")
        return corpus_text

    except Exception as e:
        print(f"!!! (RAG) 嚴重錯誤：讀取 'corpus' 資料夾失敗。錯誤：{e}")
        return "" # 返回空內容

# --- 步驟四：AI 宗師的「靈魂」核心 (★ 重大修改 ★) ---
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是 100% 的「蘇格拉底式教學法」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

# --- ★ 「新・藍圖一」RAG 指令 ★ ---
5.  在每次回答之前，你 **「必須」** 優先查閱我提供給你的「教科書內容」。
6.  你的提問 **「必須」** 100% 基於這份「教科書內容」。
7.  如果「教科書內容」中**沒有**相關資訊，你可以禮貌地告知學生「這個問題超出了目前教材的範圍」，然後再嘗試用你的「基礎知識」提問。
8.  **「絕對禁止」** 提及「教科書內容」這幾個字，你要假裝這些知識是你**自己**知道的。

# --- 你的「教學流程」---
1.  **「確認問題」**：(同前)
2.  **「拆解問題」**：(同前, 但基於「教科書內容」)
3.  **「逐步引導」**：(同前, 但基於「教科書內容」)
4.  **「保持鼓勵」**：(同前)
"""

# --- 步驟五 & 六：AI 宗師的「大腦」設定 (★ 重大修改：使用 gemini-pro ★) ---
# (我們在「藍圖三」的偵錯中，已經知道 0.8.5 兼容的是 gemini-pro)
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro', # ★ 確保使用兼容的模型
    system_instruction=system_prompt,
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        # ... (其他安全設定同前) ...
    }
)

# --- 步驟七：連接「外部大腦」(Neon 資料庫) ---
# (這整段「藍圖三」的程式碼保持不變)
def get_db_connection():
    # ... (同前) ...
def initialize_database():
    # ... (同前) ...
def get_chat_history(user_id):
    # ... (同前) ...
def save_chat_history(user_id, chat_session):
    # ... (同前) ...

# --- (這段程式碼需要「貼回」您在「藍圖三」中已成功運作的版本) ---
# (為求完整，我先貼上「藍圖三」的最終修正版)

# 函數：建立資料庫連接
def get_db_connection():
    try:
        # ★ 確保 DATABASE_URL 中不含 'channel_binding'
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
    history_json = [] # 默認為空列表
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    history_json = result[0] # 這是 JSONB 讀取來的字典列表
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    # 0.8.5 版的 start_chat(history=...) 接受字典列表
    return history_json 

# 函數：儲存聊天紀錄 (兼容 0.8.5 的字典格式)
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            # 0.8.5 版的 .history 屬性就是字典列表
            history_to_save = chat_session.history 
            with conn.cursor() as cur:
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

# 在程式啟動時，嘗試初始化資料庫 和 讀取 RAG！
initialize_database()
load_corpus_from_local_folder() # ★ 啟動時就預先載入教科書！

# --- 步驟八：神殿的「入口」(Webhook) --- (保持不變)
@app.route("/callback", methods=['POST'])
def callback():
    # ... (同前) ...

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 重大修改：植入 RAG ★) ---
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
    user_question = "" # 用於 RAG

    try:
        if isinstance(event.message, ImageMessage):
            # (RAG 目前僅支援文字，圖片題暫時不使用 RAG)
            user_question = "老師，這張圖片上的物理問題（如下圖）要怎麼思考？"
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = io.BytesIO(message_content.content)
            img = Image.open(image_bytes)
            prompt_parts = [img, user_question] 
        else:
            user_question = event.message.text

            # ★ 執行「新・藍圖一」RAG！ ★
            # 1. 取得教科書內容
            context = load_corpus_from_local_folder() 

            # 2. 構建「RAG 提示詞」
            rag_prompt = f"""
            ---「教科書內容」開始---
            {context}
            ---「教科書內容」結束---

            學生問題：「{user_question}」

            (請你嚴格遵守 System Prompt 中的指令，100% 基於上述「教科書內容」，用「蘇格拉底式提問」來回應學生的問題。)
            """
            prompt_parts = [rag_prompt]

        # 4. 呼叫 Gemini，進行「當前的對話」
        response = chat_session.send_message(prompt_parts)
        final_text = response.text

        # 5. 儲存「更新後的記憶」(藍圖三)
        save_chat_history(user_id, chat_session)

    except Exception as e:
        # 這裡的 "冥想中" 錯誤，現在也可能是 RAG 讀取失敗
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫/RAG操作失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在檢索記憶/教科書或冥想中，請稍後再試。"

    # 6. 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 --- (保持不變)
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)