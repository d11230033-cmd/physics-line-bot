# --- 「神殿」：AI 宗師的核心 (藍圖三 + 最終・藍圖一) ---
#
# 版本：已植入 Neon 記憶 + 向量 RAG (pgvector)
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

# --- ★ 第四紀元：向量 RAG 工具 ★ ---
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

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

# --- ★ 第四紀元：載入「向量轉換」模型 (啟動時載入一次) ★ ---
# (這會佔用一些記憶體，但 100% 低於「整本 PDF」)
try:
    print("--- (AI) 正在載入向量模型 'all-MiniLM-L6-v2'... ---")
    vector_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
    print("--- (AI) 向量模型載入成功！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法載入 SentenceTransformer 模型。錯誤：{e}")
    vector_model = None

# --- 步驟四：AI 宗師的「靈魂」核心 (★ RAG + 蘇格拉底 ★) ---
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是 100% 的「蘇格拉底式教學法」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

# --- ★ 「第四紀元」RAG 指令 ★ ---
5.  在每次回答之前，你 **「必須」** 優先查閱我提供給你的「相關段落」。
6.  你的提問 **「必須」** 100% 基於這份「相關段落」。
7.  如果「相關段落」中**沒有**資訊 (顯示為 'N/A')，你可以禮貌地告知學生「這個問題超出了目前教材的範圍」，然後再嘗試用你的「基礎知識」提問。
8.  **「絕對禁止」** 提及「相關段落」這幾個字，你要假裝這些知識是你**自己**知道的。
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
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        return None

# 函數：初始化資料庫（★ 升級：同時註冊 vector ★）
def initialize_database():
    conn = get_db_connection()
    if conn:
        try:
            # ★ 註冊 pgvector (必須在建立游標「之前」)
            register_vector(conn)
            print("--- (SQL) `register_vector` 成功 ---")

            with conn.cursor() as cur:
                # 建立「聊天紀錄」表格
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        user_id TEXT PRIMARY KEY,
                        history JSONB
                    );
                """)
                print("--- (SQL) 表格 'chat_history' 確認/建立成功 ---")

                # 建立「向量索引」表格 (以防萬一)
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS physics_vectors (
                        id SERIAL PRIMARY KEY,
                        content TEXT,
                        embedding VECTOR(384)
                    );
                """)
                print("--- (SQL) 表格 'physics_vectors' 確認/建立成功 ---")

                conn.commit()
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
            history_to_save = []
            if chat_session.history: 
                for content in chat_session.history:
                    parts_text = []
                    if content.parts:
                        try:
                            parts_text = [part.text for part in content.parts if hasattr(part, 'text')]
                        except Exception as part_e:
                            print(f"!!! 警告：提取 history parts 時出錯: {part_e}。內容: {content}")

                    role = content.role if hasattr(content, 'role') else 'unknown' 
                    history_to_save.append({'role': role, 'parts': parts_text})

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_history (user_id, history)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save)))
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法儲存 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()

# --- ★ 第四紀元：向量 RAG 搜尋函數 ★ ---
def find_relevant_chunks(query_text, k=3):
    """搜尋最相關的 k 個教科書段落"""
    if not vector_model:
        print("!!! (RAG) 錯誤：向量模型未載入，無法執行搜尋。")
        return "N/A" # 返回 N/A

    conn = None
    try:
        print(f"--- (RAG) 正在為問題「{query_text[:20]}...」產生向量... ---")
        # 1. 將「學生的問題」轉換為向量
        query_embedding = vector_model.encode(query_text)

        print("--- (RAG) 正在連接資料庫以搜尋向量... ---")
        conn = get_db_connection()
        if not conn:
            return "N/A"

        # 2. 註冊 pgvector (每次連接都必須做)
        register_vector(conn)

        with conn.cursor() as cur:
            # 3. 執行「向量相似度搜尋」
            # (使用 <-> 運算子，即 L2 歐幾里得距離)
            cur.execute(
                "SELECT content FROM physics_vectors ORDER BY embedding <-> %s LIMIT %s",
                (query_embedding, k)
            )
            results = cur.fetchall()

        if not results:
            print("--- (RAG) 警告：在資料庫中找不到相關段落。 ---")
            return "N/A"

        # 4. 將「相關段落」組合成一個「上下文」
        context = "\n\n---\n\n".join([row[0] for row in results])
        print(f"--- (RAG) 成功找到 {len(results)} 個相關段落！ ---")
        return context

    except Exception as e:
        print(f"!!! (RAG) 嚴重錯誤：在 `find_relevant_chunks` 中失敗。錯誤：{e}")
        return "N/A"
    finally:
        if conn:
            conn.close()

# 在程式啟動時，只初始化資料庫 (模型已在頂層載入)
initialize_database()

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

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 最終 RAG + 記憶 ★) ---
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
    user_question = "" 

    try:
        if isinstance(event.message, ImageMessage):
            user_question = "老師，這張圖片上的物理問題（如下圖）要怎麼思考？"
            prompt_parts = [user_question] # 暫時禁用圖片
        else:
            user_question = event.message.text

            # ★ 執行「第四紀元」向量 RAG！ ★
            context = find_relevant_chunks(user_question)

            # 構建「RAG 提示詞」
            rag_prompt = f"""
            ---「相關段落」開始---
            {context}
            ---「相關段落」結束---

            學生問題：「{user_question}」

            (請你嚴格遵守 System Prompt 中的指令，100% 基於上述「相關段落」，用「蘇格拉底式提問」來回應學生的問題。)
            """
            prompt_parts = [rag_prompt]

        # 4. 呼叫 Gemini，進行「當前的對話」
        response = chat_session.send_message(prompt_parts)
        final_text = response.text

        # 5. 儲存「更新後的記憶」(藍圖三)
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫/RAG操作失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在檢索記憶/教科書或冥想中，請稍後再試。"

    # 6. 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)