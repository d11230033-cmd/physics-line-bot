# --- 「神殿」：AI 宗師的核心 (第二十一紀元：JYM 助教完全體 - 含詳細註解版) ---
#
# SDK版本：使用 google-genai (新版 PS5 SDK)
# 功能：整合 LINE Bot, Gemini 2.5, PostgreSQL (Neon), Cloudinary, Google Sheets
# -----------------------------------

import os
import pathlib
import io
import json
import datetime
import time

# --- 網頁伺服器與 LINE Bot SDK ---
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage

# --- Google Gemini AI SDK (新版) ---
from google import genai
from google.genai import types
from google.genai.types import HarmCategory, HarmBlockThreshold

# --- 圖片處理工具 ---
# ★ 注意：這裡將 PIL 的 Image 重新命名為 PILImage，避免與 LineBot 的 ImageMessage 衝突
from PIL import Image as PILImage

# --- 資料庫工具 (PostgreSQL) ---
import psycopg2

# --- 圖片上傳工具 (Cloudinary) ---
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- 向量資料庫工具 (pgvector) ---
from pgvector.psycopg2 import register_vector

# --- Google Sheets 試算表工具 ---
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 步驟一：讀取環境變數與金鑰 (從 Render 後台設定)
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get('DATABASE_URL')         # Neon 資料庫連線網址
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# ==========================================
# 步驟二：初始化基礎服務
# ==========================================
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 初始化 Gemini Client ---
try:
    # 自動從環境變數 GEMINI_API_KEY 讀取金鑰
    client = genai.Client()
    print("--- (Gemini) 連接成功！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法設定 Gemini Client。錯誤：{e}")
    client = None

# --- 初始化 Cloudinary (圖片圖床) ---
try:
    cloudinary.config( 
        cloud_name = CLOUDINARY_CLOUD_NAME, 
        api_key = CLOUDINARY_API_KEY, 
        api_secret = CLOUDINARY_API_SECRET 
    )
    print("--- (Cloudinary) 連接成功！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法連接 Cloudinary。錯誤：{e}")

# --- 初始化 Google Sheets (試算表) ---
try:
    # 設定權限範圍：讀寫試算表 + 讀取雲端硬碟檔案
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file'
    ]
    # 讀取專案目錄下的 service_account.json 金鑰檔
    CREDS = Credentials.from_service_account_file('service_account.json', scopes=SCOPES)
    gc = gspread.authorize(CREDS)
    
    # ★ 設定目標試算表的 Key (請確認此 Key 正確)
    SPREADSHEET_KEY = "1Evd8WACx_uDUl04c5x2jADFxgLl1A3jW2z0_RynTmhU" 
    
    # 開啟試算表並取得第一個工作表 (Sheet1)
    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.get_worksheet(0) 
    print(f"--- (Google Sheets) 連接成功！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法連接 Google Sheets。錯誤：{e}")
    worksheet = None

# ==========================================
# 步驟三：定義 AI 模型版本與參數
# ==========================================
CHAT_MODEL = 'gemini-2.5-pro'           # 主對話模型 (高智商)
VISION_MODEL = 'gemini-2.5-flash-image' # 視覺模型 (速度快、看圖強)
AUDIO_MODEL = 'gemini-2.5-flash'        # 聽覺模型 (處理音訊)
EMBEDDING_MODEL = 'models/text-embedding-004' # 向量模型 (RAG用)
VECTOR_DIMENSION = 768                  # 向量維度

# ==========================================
# 步驟四：JYM 助教的「靈魂」 (System Prompt)
# ==========================================
system_prompt = """
你是由頂尖大學物理系博士開發的「JYM物理AI助教」，你是台灣高中物理教育的權威。
你的專長是高中物理教師甄試、物理奧林匹亞競賽，以及引導學生釐清觀念。

### 核心指令 (Core Directives)
1.  **教學風格**：採用「蘇格拉底式教學法」(Socratic Method)。**絕對禁止**直接給出答案或完整解題步驟。你必須透過「層層遞進的提問」引導學生自己想出答案。
2.  **語言要求**：**必須**使用自然的「繁體中文 (台灣用語)」。
3.  **輸入來源**：你會收到學生的「純文字」，或是由專家系統預先處理過的「圖片內容描述」或「錄音逐字稿」。請將這些描述視為學生當下的真實情境，不要對使用者提及「我看到分析文字說...」這類後台資訊。

### 第一階段：意圖判斷 (Intent Classification)
收到使用者訊息後，請優先判斷是否符合以下「特殊指令」。若是，請執行對應動作並**忽略**後續的 RAG 與教學邏輯。

* **指令 A：`教我物理觀念`**
    * **回應**：「好的，你想學習什麼物理觀念呢？（例如：力矩、簡諧運動、都卜勒效應）」

* **指令 B：`教我解物理試題`**
    * **回應**：「沒問題！請你把『題目』拍下來傳給我，或者直接用文字敘述題目。」

* **指令 C：`我想知道這題哪裡算錯`**
    * **回應**：「我很樂意幫你找盲點！請你把『你的手寫計算過程』拍下來傳給我。」

* **指令 D：`出物理題目檢測我`**
    * **任務**：不要立刻出題。
    * **回應**：「沒問題！為了出最適合你的題目，請告訴我：\n1. **年級** (例如：高二)\n2. **單元** (例如：2-1 動量)\n3. **難易度** (例如：中等)\n\n請直接回覆上述資訊即可！」

* **指令 E：(學生正在指定出題範圍，如「高二 動量 困難」)**
    * **任務**：
        1.  讀取學生指定的條件。
        2.  運用你的內建物理題庫，**立刻設計**一題符合該條件的類題。
        3.  直接拋出題目，等待學生回答。

### 第二階段：蘇格拉底教學邏輯 (Socratic Logic)
若非上述特殊指令，則進入正常教學模式。請依序執行以下思考流程：

**1. [內心演練] 自我解題**
   * 閱讀學生的問題、圖片描述或錄音內容。
   * 在回應之前，先在內心計算出正確答案與觀念邏輯。
   * *注意：不要將此過程輸出給學生。*

**2. [內心演練] 評估學生狀態**
   * 學生的回答是正確的嗎？
   * 如果錯誤，他的盲點在哪裡？（是觀念錯誤？計算粗心？還是定義不清？）

**3. [回應策略] 分支執行**
   * **情況 A：學生答對了**
       * 給予明確肯定（如：「完全正確！」、「漂亮！」）。
       * 簡單總結這個觀念的重點。
       * **學習診斷**：詢問學生：「經過剛剛的練習，你對於這個觀念是不是更清楚了？」
       * **★ 筆記與類題 (若學生確認學會)**：
           * 若學生表示學會了，請列出「重點筆記整理」(條列式)。
           * 接著說：「為了確認你完全掌握，這裡有一題『類似題』試試看：」
           * 立刻生成一題概念相似但數據不同的新題目。

   * **情況 B：學生答錯了**
       * **絕對不要**直接說「你錯了，答案是X」。
       * 請用溫和語氣指出疑點（例如：「嗯... 你的動量守恆算式列得很漂亮，但要注意正負號的方向性喔...」）。
       * 提出一個「簡化版」或「引導性」的**小問題**，引導他修正錯誤。

### 第三階段：知識庫運用 (RAG Protocol)
* 系統會提供「相關段落 (RAG Context)」。
* **優先級**：請優先參考 RAG 提供的定義與例題。
* **例外**：若 RAG 內容不足以回答（例如具體計算題），請自信地運用你身為物理博士的「內建知識」來引導教學。

### 回應格式規範
* 數學公式請盡量使用易讀的格式 (例如: F = ma, v^2 = v0^2 + 2as)。
* 保持語氣親切、專業、有耐心，像一位循循善誘的家教老師。
"""

# --- Gemini 生成設定 (關閉安全過濾以便教學) ---
generation_config = types.GenerateContentConfig(
    system_instruction=system_prompt,
    safety_settings=[
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    ]
)

# ==========================================
# 步驟五：資料庫與記憶管理函式
# ==========================================

# 1. 取得資料庫連線
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        return None

# 2. 初始化資料庫 (建立表格)
def initialize_database():
    conn = get_db_connection()
    if conn:
        try:
            # 啟用 pgvector 擴充功能
            register_vector(conn)
            with conn.cursor() as cur:
                # 建立對話歷史表
                cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT PRIMARY KEY, history JSONB);")
                # 建立物理知識向量表
                cur.execute(f"CREATE TABLE IF NOT EXISTS physics_vectors (id SERIAL PRIMARY KEY, content TEXT, embedding VECTOR({VECTOR_DIMENSION}));")
                # 建立研究日誌表 (包含圖片URL欄位)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_log (
                        id SERIAL PRIMARY KEY, timestamp TIMESTZ DEFAULT CURRENT_TIMESTAMP, user_id TEXT,
                        user_message_type TEXT, user_content TEXT, image_url TEXT,
                        vision_analysis TEXT, rag_context TEXT, ai_response TEXT
                    );""")
                # 自動修復：如果 log 表缺少 image_url 欄位，自動補上
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='research_log' AND column_name='image_url'
                        ) THEN ALTER TABLE research_log ADD COLUMN image_url TEXT; END IF;
                    END$$;""")
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法初始化資料庫表格。錯誤：{e}")
        finally:
            conn.close()

# 3. 讀取使用者歷史對話
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
                    # 將資料庫中的 JSON 轉換回 Gemini 的 Content 物件格式
                    for item in history_json:
                        role = item.get('role', 'user')
                        parts_text = item.get('parts', [])
                        if role == 'user' or role == 'model':
                            history_list.append(types.Content(role=role, parts=[types.Part.from_text(text=text) for text in parts_text]))
        except Exception as e:
            print(f"!!! 錯誤：無法讀取歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    return history_list 

# 4. 儲存使用者歷史對話
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            history_to_save = []
            history = chat_session.get_history()
            if history:
                for message in history:
                    if message.role == 'user' or message.role == 'model':
                        # 只儲存文字部分，避免儲存過大的圖片資料
                        parts_text = [part.text for part in message.parts if hasattr(part, 'text')]
                        history_to_save.append({'role': message.role, 'parts': parts_text})
            with conn.cursor() as cur:
                # 使用 UPSERT 語法：若 user_id 存在則更新，否則新增
                cur.execute("""
                    INSERT INTO chat_history (user_id, history) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save)))
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法儲存歷史紀錄。錯誤：{e}")
        finally:
            conn.close()

# 5. RAG 搜尋：找尋相關教材
def find_relevant_chunks(query_text, k=3):
    conn = None
    if not client: return "N/A"
    try:
        cleaned_query_text = query_text.replace('\x00', '') # 清除 NULL 字元
        # 1. 將使用者問題轉換為向量
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[cleaned_query_text] 
        )
        query_vector = result.embeddings[0].values 

        # 2. 在資料庫中搜尋最相似的 k 個段落
        conn = get_db_connection()
        if not conn: return "N/A"
        register_vector(conn)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM physics_vectors ORDER BY embedding <-> %s::vector LIMIT %s",
                (query_vector, k)
            )
            results = cur.fetchall()
        if not results: return "N/A"
        
        # 3. 組合搜尋結果
        context = "\n\n---\n\n".join([row[0] for row in results])
        return context
    except Exception as e:
        print(f"!!! (RAG) 錯誤：{e}")
        return "N/A"
    finally:
        if conn: conn.close()

# 6. 儲存「研究日誌」到 Neon 資料庫與 Google Sheets
def save_to_research_log(user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response):
    # A. 寫入 Neon 資料庫
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO research_log 
                    (user_id, user_message_type, user_content, image_url, vision_analysis, rag_context, ai_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response))
                conn.commit()
        except Exception as e:
            print(f"!!! Neon Log Error: {e}")
        finally:
            conn.close()

    # B. 寫入 Google Sheets
    if worksheet:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            row_data = [now_utc, user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response]
            worksheet.append_row(row_data)
        except Exception as e:
            print(f"!!! Sheets Log Error: {e}")

# 程式啟動時初始化資料庫
initialize_database()

# ==========================================
# 步驟六：設定 Webhook 入口 (LINE 傳訊息來的地方)
# ==========================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# ==========================================
# 步驟七：訊息處理主邏輯 (核心)
# ==========================================
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage))
def handle_message(event):

    user_id = event.source.user_id

    # 防呆：如果 Gemini 沒連接成功，直接回報
    if not client:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="系統維護中 (API Key Error)"))
        return

    # 初始化 Log 變數
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = "" 
    vision_analysis = "" 
    rag_context = "" 
    final_response_text = ""
    
    # 1. 讀取並建立對話 Session (含歷史記憶)
    past_history = get_chat_history(user_id)
    try:
         chat_session = client.chats.create(
             model=CHAT_MODEL, 
             history=past_history, 
             config=generation_config 
         )
    except Exception as start_chat_e:
         print(f"History error: {start_chat_e}")
         chat_session = client.chats.create(model=CHAT_MODEL, history=[], config=generation_config)

    user_question = "" 

    # 2. 判斷訊息類型並處理
    try:
        # --- A. 處理圖片訊息 (Image) ---
        if isinstance(event.message, ImageMessage):
            user_message_type = "image"
            user_content = f"Image received" 

            # 取得圖片內容
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = message_content.content 

            # 上傳到 Cloudinary 取得網址 (為了存 Log)
            try:
                upload_result = cloudinary.uploader.upload(image_bytes)
                image_url_to_save = upload_result.get('secure_url')
            except Exception:
                image_url_to_save = "upload_failed"

            # 使用 PIL 開啟圖片 (記憶體中)
            img = PILImage.open(io.BytesIO(image_bytes))

            # 視覺辨識 Prompt
            vision_prompt = """
            你是一個精準的光學掃描儀 (OCR) 和圖表分析工具。
            請客觀地、詳細地描述這張圖片的內容：
            1. 如果有文字，請逐字讀出。
            2. 如果有數學算式，請轉換為清晰的格式。
            3. 如果有圖表或物理示意圖，請詳細描述其結構、座標軸、物體位置和受力情況。
            **絕對禁止** 自己嘗試解題或給出物理結論，只做客觀描述。
            """
            
            # 呼叫 Gemini Vision Model
            vision_response = client.models.generate_content(
                model=VISION_MODEL, 
                contents=[img, vision_prompt] 
            )
            vision_analysis = vision_response.text 
            # 將分析結果轉為文字輸入給主模型
            user_question = f"圖片內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"

        # --- B. 處理語音訊息 (Audio) ---
        elif isinstance(event.message, AudioMessage):
            user_message_type = "audio"
            user_content = f"Audio received" 
            image_url_to_save = "N/A (Audio)" 

            # 取得音訊內容
            message_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = message_content.content
            
            # 包裝音訊資料
            audio_file = types.Part(inline_data=types.Blob(data=audio_bytes, mime_type='audio/m4a'))

            # 語音辨識 Prompt
            audio_prompt = """
            請將這段錄音進行「逐字聽打」並分析學生的「語氣情感」。
            請回傳：
            1. 逐字稿：(繁體中文)
            2. 語氣分析：(例如：困惑、自信、焦急)
            """
            
            # 呼叫 Gemini Flash Model (支援語音)
            try:
                speech_response = client.models.generate_content(
                    model=AUDIO_MODEL,
                    contents=[audio_file, audio_prompt]
                )
                vision_analysis = speech_response.text 
            except Exception as e:
                vision_analysis = f"語音辨識失敗: {e}"
            
            user_question = f"錄音內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"

        # --- C. 處理純文字訊息 (Text) ---
        else: 
            user_message_type = "text"
            user_question = event.message.text
            user_content = user_question 

        # 3. 執行 RAG 檢索 (找物理教材)
        rag_context = find_relevant_chunks(user_question) 

        # 4. 組合最終 Prompt (System Prompt + RAG + User Input)
        rag_prompt = f"""
        ---「相關教材段落」開始---
        {rag_context}
        ---「相關教材段落」結束---
        
        學生的目前輸入：「{user_question}」
        
        請依據 System Prompt 中的指示與上述教材段落進行回應。
        """
        contents_to_send = [rag_prompt]

        # 5. 傳送給 Gemini 主模型 (含自動重試機制)
        max_retries = 2 
        attempt = 0
        while attempt < max_retries:
            try:
                response = chat_session.send_message(contents_to_send)
                final_response_text = response.text 
                break 
            except Exception as chat_api_e:
                attempt += 1
                time.sleep(2) # 等待 2 秒再試
                if attempt == max_retries:
                    final_response_text = "抱歉，我現在有點忙不過來，請稍後再試一次。"
        
        # 6. 回覆使用者 (LINE)
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=final_response_text.replace('\x00', ''))
        )
        
        # 7. 更新對話歷史到資料庫
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"!!! Handle Message Error: {e}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生系統錯誤，請稍後再試。"))

    # 8. 記錄完整 Log (研究日誌)
    save_to_research_log(
        user_id=user_id.replace('\x00', ''),
        user_msg_type=user_message_type,
        user_content=user_content.replace('\x00', ''),
        image_url=image_url_to_save, 
        vision_analysis=vision_analysis.replace('\x00', ''), 
        rag_context=rag_context.replace('\x00', ''),
        ai_response=final_response_text.replace('\x00', '')
    )

# ==========================================
# 步驟八：啟動 Flask 伺服器
# ==========================================
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)