# --- 「神殿」：AI 宗師的核心 (第二十紀元：最終穩定版) ---
#
# SDK：★「還原」 google-genai (PS5 SDK) ★
# 修正：19. ★ (一致性修正) 將程式碼中所有 "AI 宗師" 替換為 "JYM助教" ★
# 修正：20. ★ (穩定性修正) 移除不相容的「繪圖」功能，修復所有 Bug ★
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
# ★ (還原) 移除 ImageSendMessage，因為我們不繪圖
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage

# --- ★ (還原) 第十四紀元：全新 SDK ★ ---
from google import genai
from google.genai import types
from google.genai.types import HarmCategory, HarmBlockThreshold

from PIL import Image
import io
import psycopg2 # 藍圖三：資料庫工具
import json     # 藍圖三：資料庫工具
import datetime # ★ 第七紀元：需要時間戳
import time     # ★ (新功能) 為了「自動重試」
# ★ (移除) import threading

# --- ★ (還原) 第八紀元：永恆檔案館工具 ★ ---
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- ★ 第五紀元：向量 RAG 工具 ★ ---
from pgvector.psycopg2 import register_vector

# --- ★ (新功能) Google Sheets 工具 ★ ---
import gspread
from google.oauth2.service_account import Credentials

# --- 步驟一：神殿的鑰匙 (從 Render.com 讀取) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get('DATABASE_URL')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# ★ (移除) Vertex AI 專案金鑰 ★
# GCP_PROJECT_ID = ...
# GCP_LOCATION = ...

# --- 步驟二：神殿的基礎建設 ---
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- ★ (還原) 第十四紀元：連接「神之鍛造廠」(Gemini PS5) ★ ---
try:
    client = genai.Client()
    print("--- (Gemini) ★ 第十四紀元：PS5 SDK (google-genai) 連接成功！ ★ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法設定 Google API Key (GEMINI_API_KEY)。錯誤：{e}")
    client = None

# --- ★ (還原) 第八紀元：連接「永恆檔案館」(Cloudinary) ★ ---
try:
    cloudinary.config( 
        cloud_name = CLOUDINARY_CLOUD_NAME, 
        api_key = CLOUDINARY_API_KEY, 
        api_secret = CLOUDINARY_API_SECRET 
    )
    print("--- (Cloudinary) 永恆檔案館連接成功！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法連接到 Cloudinary。錯誤：{e}")


# --- ★ (新功能) 連接 Google Sheets (★ 修正版：使用 KEY ★) ---
try:
    # 1. 定義 API 範圍
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file' # gspread 需要 drive.file 來「搜尋」檔案
    ]
    # 2. 讀取 Render 上的 Secret File ('service_account.json')
    CREDS = Credentials.from_service_account_file('service_account.json', scopes=SCOPES)
    gc = gspread.authorize(CREDS)
    
    # 3. ★★★ (新修正 + 請修改) 使用您試算表的「金鑰 (Key)」 ★★★
    # (請貼上您在「步驟一」從網址列複製的那串金鑰)
    SPREADSHEET_KEY = "1Evd8WACx_uDUl04c5x2jADFxgLl1A3jW2z0_RynTmhU" # ★★★ 在這裡貼上您的 KEY ★★★
    
    sh = gc.open_by_key(SPREADSHEET_KEY)
    
    # 4. 取得第一個工作表分頁 (名稱 "工作表1" 或 "Sheet1")
    worksheet = sh.get_worksheet(0) 
    
    print(f"--- (Google Sheets) 連接成功！已透過 KEY 開啟試算表 ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法連接到 Google Sheets。錯誤：{e}")
    print("    (★ 提醒：請再次確認您已將 'service_account.json' 中的 'client_email' 共用給此試算表，並設為「編輯者」 ★)")
    worksheet = None # 連接失敗

# ★ (移除) 連接 Google Text-to-Speech (TTS) ★
TTS_CLIENT = None
print("--- (TTS) 語音輸出功能已移除，確保系統穩定 ---")

# --- ★ (還原) 第十五紀元：定義「雙重專家」模型 (★ 移除繪圖 ★) ---
CHAT_MODEL = 'gemini-2.5-pro'           # ★ (還原) 使用 2.5-Pro (穩定版)
VISION_MODEL = 'gemini-2.5-flash-image'       # ★ (還原) 使用 2.5-flash-image (穩定版)
EMBEDDING_MODEL = 'models/text-embedding-004' # (保持不變，這是標準)
VECTOR_DIMENSION = 768 # ★ 向量維度 768

# --- 步驟四：AI 宗師的「靈魂」核心 (★ Persona 升級 ★) ---
system_prompt = """
你是一位頂尖大學的物理系博士，你對於高中物理教師甄試筆試與物理奧林匹亞競賽非常擅長而且是專家等級，你目前是頂尖台灣高中物理教師，你對於高中物理的知識與專業無庸置疑，更是頂尖台灣高中物理教學AI，叫做「JYM物理AI助教」。
你的教學風格是「蘇格拉底式評估法」(Socratic Evaluator)。
你「只會」收到三種輸入：
1.  學生的「純文字提問」。
2.  由「視覺專家」預先分析好的「圖片內容分析」。
3.  由「聽覺專家」預先分析好的「錄音內容分析」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。(★ 除非你正在執行「筆記整理 + 類題確認」★)
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。
5.  **「絕對必須」**：你「所有」的回應「必須」 100% 使用「繁體中文」(台灣用語)。「絕對禁止」使用「簡體中文」。

# --- ★ 「繪圖魔法」指令 (★ 已移除 ★) ---

# --- ★ 「第十二紀元：中文指令」核心邏輯 ★ ---
# 這是你最重要的思考流程！

* **【A. 如果學生的「輸入」是「一個指令」】:**
    * **如果輸入 100% 完全等於 `教我物理觀念`:**
        * 你的「唯一」回應「必須」是：「好的，你想學習什麼物理觀念呢？（例如：力矩、簡諧運動）」
        * (你「必須」忽略 RAG，並「停止」後續評估。)
    * **如果輸入 100% 完全等於 `教我解物理試題`:**
        * 你的「唯一」回應「必須」是：「沒問題！請你把『題目』用『文字』或『圖片』傳給我。」
        * (你「必須」忽略 RAG，並「停止」後續評估。)
    * **如果輸入 100% 完全等於 `我想知道這題哪裡算錯`:**
        * 你的「唯一」回應「必須」是：「我很樂意！請你把『你的手寫作答過程』用『圖片』傳給我。」
        * (你「必須」忽略 RAG，並「停止」後續評估。)
    # --- ★ (修改) 新的出題流程：先詢問，再出題 ★ ---
    * **如果輸入 100% 完全等於 `出物理題目檢測我`:**
        * 你的任務是：**「不要」** 立刻出題。
        * 你的回應「必須」是：「沒問題！為了出最適合你的題目，請告訴我：\n1. **年級** (例如：高二)\n2. **單元** (例如：2-1 動量)\n3. **難易度** (例如：中等)\n\n請直接回覆上述資訊即可！」
        * (你「必須」忽略 RAG，並「停止」後續評估。)

    * **如果輸入明顯是在指定「出題範圍」 (例如包含「年級」、「單元」、「難易度」的關鍵字):**
        * 你的任務是：
            1. 讀取學生指定的「年級」、「單元」與「難易度」。
            2. 你的「相關段落」是 [N/A] (不要去查資料庫，請運用你身為頂尖物理教師的知識庫)。
            3. **「產生題目」**：立刻設計一個符合該條件的「物理類題」(蘇格拉底式)。
            4. 直接提出這個問題，並等待學生回答。
        * (你「必須」忽略 RAG，並「停止」後續評估。)

* **【B. 如果學生的「輸入」**「不是」**上述指令 (★ 這代表他正在「正常對話」或「回答問題」★)】:**
    * 你才「啟動」你「正常」的「第十紀元：評估者核心邏輯」：

    1.  **【內心思考 - 步驟 1：自我解答】**
        * 「學生回答了『...』。在我回應之前，我必須先自己『在內心』計算或推導出我上一個問題的『正確答案』是什麼？」
        * (例如：「視覺專家」分析圖 11 說峰值在 t=1。所以「正確答案」是 t=1。)

    2.  **【內心思考 - 步驟 2：評估對錯】**
        * 「學生的答案『...』是否 100% 匹配我『內心』的正確答案？」

    3.  **【內心思考 - 步驟 3：分支應對 (★ 關鍵 ★)】**
        * **【B1. 如果學生「答對了」】:**
            * 「太棒了！學生答對了。我的回應『必須』：1. 肯d
ing他（例如：『完全正確！』、『沒錯！』）。 2. 總結我們剛剛的發現。 3. 提出『下一個』合乎邏輯的蘇格拉底式問題。」
        * **【B2. 如果學生「答錯了」】:**
            * 「啊，學生答錯了。他以為是『...』，但正確答案是『...』。」
            * 「我的回應『必須』是：1. 用『溫和、鼓勵』的方式，『委婉地指出』他的答案『可能需要重新思考』。」
            * 「例如：『嗯... 讓我們再檢查一下那個計算。』或『你離答案很近了，但我們來確認一下... (卡住的概念)』」
            * 「2. 接著，『立刻』提出一個『更簡單』、『更聚焦』的『引導性問題』，幫助他『自己』想通。」

# --- ★ 「第十紀元：教學策略」 (★ 升級版：加入筆記 ★) ★ ---
4.  **【RAG 策略】:** (僅在【B. 正常對話】模式下啟用) 在你「內心思考」或「提出問題」之前，你「必須」優先查閱「相關段落」。你的所有提問，都必須 100% 基於「相關段落」中的知識。
5.  **【學習診斷】:** (Point 4) 當一個完整的題目被引導完畢後, 你「必須」詢問學生：「經過剛剛的引導，你對於『...』(例如：力矩) 這個概念，是不是更清楚了呢？」
6.  **【★ 筆記整理 + 類題確認 ★】:** (Point 4) 如果學生在「學習診斷」中回答「是」或「學會了」：
    * **1. (給予肯定):** 你的回應「必須」以「太好了！很高興你學會了。」開頭。
    * **2. (提供筆記):** 接著，你「必須」立刻提供一份我們剛剛討論內容的「重點筆記整理」。(例如：「這裏是這題的「重點筆記整理」：\n - 步驟一：...\n - 步驟二：...\n - 關鍵公式：...」)
    * **3. (提供類題):** 在筆記之後，你「必須」接著說：「接下來，這裡有一題「類似題」，請你試著解解看：」
    * **4. (產生類題):** 你「必須」立刻「產生一個」與剛剛題目「概念相似，但數字或情境不同」的「新類題」。
"""

# --- ★ (還原) 第十四紀元：定義「PS5」的「設定」 ★ ---
generation_config = types.GenerateContentConfig(
    system_instruction=system_prompt,
    safety_settings=[
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]
)

# --- 步驟七：連接「外部大腦」(Neon 資料庫) (★ 無需變更 ★) ---
# (此區塊所有函式都無需變更)

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        return None

def initialize_database():
    conn = get_db_connection()
    if conn:
        try:
            register_vector(conn)
            print("--- (SQL) `register_vector` 成功 ---")
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT PRIMARY KEY, history JSONB);")
                print("--- (SQL) 表格 'chat_history' 確認/建立成功 ---")
                cur.execute(f"CREATE TABLE IF NOT EXISTS physics_vectors (id SERIAL PRIMARY KEY, content TEXT, embedding VECTOR({VECTOR_DIMENSION}));")
                print(f"--- (SQL) 表格 'physics_vectors' (維度 {VECTOR_DIMENSION}) 確認/建立成功 ---")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_log (
                        id SERIAL PRIMARY KEY, timestamp TIMESTZ DEFAULT CURRENT_TIMESTAMP, user_id TEXT,
                        user_message_type TEXT, user_content TEXT, image_url TEXT,
                        vision_analysis TEXT, rag_context TEXT, ai_response TEXT
                    );""")
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='research_log' AND column_name='image_url'
                        ) THEN ALTER TABLE research_log ADD COLUMN image_url TEXT; END IF;
                    END$$;""")
                print("--- (SQL) ★ 第八紀元：表格 'research_log' (含 image_url) 確認/建立/升級成功 ★ ---")
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法初始化資料庫表格。錯誤：{e}")
        finally:
            conn.close()

# --- ★ (還原) `google-genai` 版 `get_chat_history` ★ ---
def get_chat_history(user_id):
    conn = get_db_connection()
    history_list = [] 
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    history_json = result[0]
                    for item in history_json:
                        role = item.get('role', 'user')
                        parts_text = item.get('parts', [])
                        # ★ (移除) 繪圖標籤過濾
                        if role == 'user' or role == 'model':
                            history_list.append(types.Content(role=role, parts=[types.Part.from_text(text=text) for text in parts_text]))
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    return history_list 

# --- ★ (還原) `google-genai` 版 `save_chat_history` ★ ---
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            history_to_save = []
            history = chat_session.get_history() # ★ (還原)
            if history:
                for message in history:
                    if message.role == 'user' or message.role == 'model':
                        parts_text = [part.text for part in message.parts if hasattr(part, 'text')]
                        history_to_save.append({'role': message.role, 'parts': parts_text})
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_history (user_id, history) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save)))
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法儲存 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()

# --- ★ (還原) `google-genai` 版 `find_relevant_chunks` ★ ---
def find_relevant_chunks(query_text, k=3):
    conn = None
    if not client: return "N/A" # ★ (還原)
    try:
        cleaned_query_text = query_text.replace('\x00', '')
        print(f"--- (RAG) 正在為問題「{cleaned_query_text[:20]}...」向 Gemini 請求向量... ---")
        
        # ★ (還原)
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[cleaned_query_text] 
        )
        query_vector = result.embeddings[0].values 

        print("--- (RAG) 正在連接資料庫以搜尋向量... ---")
        conn = get_db_connection()
        if not conn: return "N/A"
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM physics_vectors ORDER BY embedding <-> %s::vector LIMIT %s",
                (query_vector, k)
            )
            results = cur.fetchall()
        if not results:
            print("--- (RAG) 警告：在資料庫中找不到相關段落。 ---")
            return "N/A"
        context = "\n\n---\n\n".join([row[0] for row in results])
        print(f"--- (RAG) 成功找到 {len(results)} 個相關段落！ ---")
        return context
    except Exception as e:
        print(f"!!! (RAG) 嚴重錯誤：在 `find_relevant_chunks` 中失敗。錯誤：{e}")
        return "N/A"
    finally:
        if conn: conn.close()

# --- ★ (新功能) 函數：儲存「研究日誌」(★ 升級版：同時寫入 Google Sheets ★) ---
def save_to_research_log(user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response):
    
    # --- 步驟 A：(不變) 儲存到 Neon 資料庫 ---
    conn = get_db_connection()
    if conn:
        try:
            print(f"--- (研究日誌) 正在儲存 user_id '{user_id}' 的完整互動 (to Neon)... ---")
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO research_log 
                    (user_id, user_message_type, user_content, image_url, vision_analysis, rag_context, ai_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response))
                conn.commit()
            print("--- (研究日誌) 儲存到 Neon 成功 ---")
        except Exception as e:
            print(f"!!! 錯誤：無法儲存「研究日誌」到 Neon。錯誤：{e}")
        finally:
            conn.close()

    # --- 步驟 B：(新功能) 儲存到 Google Sheets ---
    if worksheet: # 檢查 worksheet (在程式頂端) 是否在啟動時成功初始化
        try:
            print(f"--- (Google Sheets) 正在新增一列紀錄... ---")
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            row_data = [
                now_utc, user_id, user_msg_type, user_content,
                image_url, vision_analysis, rag_context, ai_response
            ]
            worksheet.append_row(row_data)
            print(f"--- (Google Sheets) 新增一列成功 ---")
        except Exception as e:
            print(f"!!! 嚴重錯誤：無法寫入 Google Sheets。錯誤：{e}")


# ★ (移除) 背景繪圖函式 ★

initialize_database()

# --- 步驟八：神殿的「入口」(Webhook) (★ 無需變更 ★) ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 還原版：移除繪圖 ★) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage)) # ★ 支援 AudioMessage ★
def handle_message(event):

    user_id = event.source.user_id

    if not client: # ★ (還原)
        print("!!! 嚴重錯誤：Gemini Client 未初始化！(金鑰可能錯誤)")
        # ★ (一致性修正)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="抱歉，JYM助教目前金鑰遺失，請檢查 Render 環境變數 `GEMINI_API_KEY`。"))
        return

    # --- ★ 第八紀元：初始化研究日誌變數 ★ ---
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = "" 
    vision_analysis = "" 
    rag_context = "" 
    final_response_text = "" # AI 的原始文字回應 (用於日誌)
    line_replies = []        # 準備傳送給 LINE 的訊息列表
    
    # 1. 讀取「過去的記憶」
    past_history = get_chat_history(user_id)

    # 2. 根據「過去的記憶」開啟「對話」
    try:
         # ★ (還原) `google-genai` 語法
         chat_session = client.chats.create(
             model=CHAT_MODEL, 
             history=past_history, 
             config=generation_config 
         )
    except Exception as start_chat_e:
         print(f"!!! 警告：從歷史紀錄開啟對話失敗。使用空對話。錯誤：{start_chat_e}")
         chat_session = client.chats.create(model=CHAT_MODEL, history=[], config=generation_config)

    # 3. 準備「當前的輸入」(★ 三位一體專家系統 ★)
    contents_to_send = []
    user_question = "" 

    try:
        if isinstance(event.message, ImageMessage):
            # --- ★ 專家一：「視覺專家」啟動 ★ ---
            user_message_type = "image"
            user_content = f"Image received (Message ID: {event.message.id})" 

            print(f"--- (Cloudinary) 收到來自 user_id '{user_id}' 的圖片，開始上傳... ---")
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = message_content.content 

            try:
                upload_result = cloudinary.uploader.upload(image_bytes)
                image_url_to_save = upload_result.get('secure_url')
                if image_url_to_save:
                    print(f"--- (Cloudinary) 圖片上傳成功！URL: {image_url_to_save} ---")
                else:
                    image_url_to_save = "upload_failed"
            except Exception as upload_e:
                print(f"!!! 嚴重錯誤：Cloudinary 圖片上傳失敗。錯誤：{upload_e}")
                image_url_to_save = f"upload_error: {upload_e}"

            print(f"--- (視覺專家) 正在分析圖片 (使用 {VISION_MODEL})... ---")
            img = PILImage.open(io.BytesIO(image_bytes)) # ★ (還原)

            vision_prompt = """
            你是一個「精準的」光學掃描儀 (OCR) 和「圖表分析」工具。
            你的「唯一」任務是「客觀地」、「逐字地」、「逐點地」描述圖片內容。
            **「絕對禁止」**：
            * 「絕對禁止」你「自己」去「解讀」物理意義或「計算」答案。
            你的「工作流程」是：
            1.  **「如果是「新問題」**：
                * 「1. 逐字」讀出「所有」的文字 (例如: "圖 10 為一發電機...")。
                * 「2. 描述」圖 10 (發電機) 的結構 (例如: "線圈甲、乙在N、S極間")。
                * 「3. 描述」圖 11 (a-t 圖)：
                    * 「a. 逐字」讀出 X 軸和 Y 軸的「標籤」(例如：`時間 t (s)`, `+N`, `-N`)。
                    * 「b. 逐字」讀出 X 軸上「所有」的「數字刻度」(例如：`0`, `4`, `8`, `12`)。
                    * 「c. 仔細觀察 0 和 4 之間」：這是一個「完整的」正弦波週期 (從 0 上升，到 4 回到 0)。
                    * 「d. 推論」：因此，波形在 `t=2` 時「必定」穿過零點。
                    * 「e. 推論」：因此，第一個「波峰 (Peak)」的「精確」t 座標「必定」是在 `t=0` 和 `t=2` 的正中間，也就是 **`t=1`**。
                    * 「f. 推論」：因此，第一個「波谷 (Trough)」的「精確」t 座標「必定」是在 `t=2` 和 `t=4` 的正中間，也就是 **`t=3`**。
            2.  **「如果是「學生作答」**：
                * 「1. 逐字」讀出學生的「所有」手寫文字和計算過程。
                * 「2. 客觀地」描述他的計算步驟，**「不要」**自己下判斷。
            請直接開始你的「客觀描述」。
            """
            
            # ★ (還原)
            vision_response = client.models.generate_content(
                model=VISION_MODEL, 
                contents=[img, vision_prompt] 
            )
            vision_analysis = vision_response.text 
            print(f"--- (視覺專家) 分析完畢：{vision_analysis[:70]}... ---")

            user_question = f"圖片內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"

        elif isinstance(event.message, AudioMessage):
            # --- ★ (新功能) 專家二：「聽覺專家」啟動 ★ ---
            user_message_type = "audio"
            user_content = f"Audio received (Message ID: {event.message.id})" 
            image_url_to_save = "N/A (Audio Message)" 

            print(f"--- (聽覺專家) 收到來自 user_id '{user_id}' 的錄音，開始分析... ---")
            message_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = message_content.content
            
            # ★ (還原) ★ 修正：使用 types.Blob 來封裝原始數據 ★
            audio_file = types.Part(inline_data=types.Blob(data=audio_bytes, mime_type='audio/m4a'))

            audio_prompt = """
            你是一個「精準的」聽打員和「語氣分析師」。
            你的「唯一」任務是「客觀地」分析這段學生的錄音。
            **「絕對禁止」**：
            * 「絕對禁止」你「自己」去「回答」錄音中的物理問題。
            你的「工作流程」是：
            1.  **「逐字稿」**：100% 精確地聽打出學生說的「每一句話」(使用繁體中文)。
            2.  **「語氣分析」**：客觀地描述學生的「情緒或語氣」(例如：聽起來很困惑、不確定、沮-喪、有自信等)。
            請「只」回傳這兩項分析，不要有多餘的對話。
            例如：
            「
            逐字稿：「老師，我... 我還是不懂為什麼這裡要用 F 等於 ma，力矩...」
            語氣分析：學生的語氣聽起來「非常困惑」而且「不確定」。
            」
            """
            
          # ★ (最終黃金版) ★ 使用最新的 2.5-Flash 聽錄音 (支援音訊且快速) ★
            max_retries_audio = 3
            attempt_audio = 0
            
            # 定義這個「完美平衡」的模型 (支援音訊、速度快、最新版)
            AUDIO_MODEL_NAME = "gemini-2.5-flash" 
            
            while attempt_audio < max_retries_audio:
                try:
                    # 1. 呼叫 API (使用 2.5-Flash 模型來處理音訊)
                    speech_response = client.models.generate_content(
                        model=AUDIO_MODEL_NAME,  # <--- 這裡改用 2.5-Flash！
                        contents=[audio_file, audio_prompt]
                    )
                    
                    # 2. (如果成功) 處理回應
                    vision_analysis = speech_response.text 
                    print(f"--- (聽覺專家) 語音分析成功 (使用 {AUDIO_MODEL_NAME}) ---")
                    break # 成功，跳出迴圈
    
                # 3. (如果失敗)
                except Exception as audio_e:
                    attempt_audio += 1
                    print(f"!!! (聽覺專家) 警告：API 呼叫失敗 (第 {attempt_audio} 次)。錯誤：{audio_e}")
                    
                    if attempt_audio < max_retries_audio:
                        print(f"    ... 正在重試，等待 2 秒...")
                        time.sleep(2) 
                    else:
                        print(f"!!! (聽覺專家) 嚴重錯誤：重試 {max_retries_audio} 次後仍然失敗。")
                        raise audio_e # 重試失敗，拋出錯誤
            
            # (這行保持在迴圈之外) 這裡依然交給最聰明的 Pro 進行教學
            user_question = f"錄音內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"

        else: 
            # --- ★ 專家三：「純文字」輸入 ★ ---
            user_message_type = "text"
            user_question = event.message.text
            user_content = user_question 
            print(f"--- (文字 RAG) 收到來自 user_id '{user_id}' 的文字訊息... ---")

        # --- ★ 統一 RAG 流程 (無論是文字、圖片、還是錄音) ★ ---
        print(f"--- (RAG) 正在為「{user_question[:30]}...」執行 RAG 搜尋... ---")
        rag_context = find_relevant_chunks(user_question) 

        rag_prompt = f"""
        ---「相關段落」開始---
        {rag_context}
        ---「相關段落」結束---
        學生的「原始輸入」(可能是「指令」、「回答」、「圖片分析」或「錄音分析」)：「{user_question}」
        (請你「嚴格遵守」 System Prompt 中的「第十二紀元：中文指令」核心邏輯！...)
        """
        contents_to_send = [rag_prompt.replace("{rag_content}", "{rag_context}")]

        # --- ★ AI 宗師：「對話宗師」啟動 (★ 第十七紀元：加入自動重試) ★ ---
        print(f"--- (對話宗師) 正在呼叫 Gemini API ({CHAT_MODEL})... ---") # ★ (還原)
        
        max_retries = 2 
        attempt = 0
        
        while attempt < max_retries:
            try:
                # ★ (還原)
                response = chat_session.send_message(contents_to_send)
                final_response_text = response.text 
                print(f"--- (對話宗師) Gemini API 回應成功 (嘗試第 {attempt + 1} 次) ---")
                break 

            except Exception as chat_api_e:
                attempt += 1
                print(f"!!! (對話宗師) 警告：API 呼叫失敗 (第 {attempt} 次)。錯誤：{chat_api_e}")
                
                if attempt < max_retries:
                    print(f"    ... 正在重試，等待 2 秒...")
                    time.sleep(2) 
                else:
                    print(f"!!! (對話宗師) 嚴重錯誤：重試 {max_retries} 次後仍然失敗。")
                    raise chat_api_e 
        
        # ★ (移除) 圖像生成邏輯 ★
        
        # ★ (還原) 繪圖功能已移除，我們只需要一個 final_text
        line_replies.append(TextSendMessage(text=final_response_text.replace('\x00', '')))
        
        # 5. 儲存「更新後的記憶」(AI 記憶)
        print(f"--- (記憶) 正在儲存 user_id '{user_id}' 的對話紀錄... ---")
        save_chat_history(user_id, chat_session)
        print(f"--- (記憶) 對話紀錄儲存成功 ---")
        
        # ★ (移除) 語音合成 (TTS) 邏輯 ★

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫/RAG/視覺/聽覺操作失敗。錯誤：{e}")
        # ★ (一致性修正)
        final_response_text = "抱歉，JYM助教目前正在檢索記憶/教科書或冥想中，請稍後再試。"
        if not user_content: user_content = "Error during processing"
        if not user_message_type: user_message_type = "error"
        line_replies = [TextSendMessage(text=final_response_text)] # 確保有錯誤訊息回覆

    # ★★★【第八紀元：最終儲存】★★★
    # 6. 儲存「研究日誌」(人類研究)
    
    save_to_research_log(
        user_id=user_id.replace('\x00', ''),
        user_msg_type=user_message_type.replace('\x00', ''),
        user_content=user_content.replace('\x00', ''),
        image_url=image_url_to_save.replace('\x00', ''), 
        vision_analysis=vision_analysis.replace('\x00', ''), 
        rag_context=rag_context.replace('\x00', ''),
        ai_response=final_response_text.replace('\x00', '') # ★ (修正) 儲存 AI 的原始文字回應
    )

    # 7. 回覆使用者 (★ 還原)
    line_bot_api.reply_message(
        event.reply_token, 
        line_replies 
    )

# --- 步驟十：啟動「神殿」 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)