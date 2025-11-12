# --- 「神殿」：AI 宗師的核心 (第十九紀元：繪圖復活版) ---
#
# SDK：★「全新」 google-genai (PS5 SDK) ★
# ... (之前的所有修正)
# 修正：14. ★ (繪圖復活) 確認 gemini-2.5-flash-image 支援圖像生成 ★
# 修正：15. ★ (繪圖復活) 將繪圖模型設置為 gemini-2.5-flash-image ★
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
# ★ (復活) 重新引入 ImageSendMessage
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage, ImageSendMessage 

# --- ★ 第十四紀元：全新 SDK ★ ---
from google import genai
from google.genai import types
from google.genai.types import HarmCategory, HarmBlockThreshold

from PIL import Image
import io
import psycopg2 # 藍圖三：資料庫工具
import json     # 藍圖三：資料庫工具
import datetime # ★ 第七紀元：需要時間戳
import time     # ★ (新功能) 為了「自動重試」

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

# ★ (還原) 第八紀元：檔案館金鑰 ★
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# --- 步驟二：神殿的基礎建設 ---
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- ★ 第十四紀元：連接「神之鍛造廠」(Gemini PS5) ★ ---
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

# --- ★ 第十五紀元：定義「雙重專家」模型 (★ 繪圖模型修正為 gemini-2.5-flash-image) ★ ---
CHAT_MODEL = 'gemini-2.5-pro'           # ★ 專家一：複雜推理、★ (新) 聽覺
VISION_MODEL = 'gemini-2.5-flash-image'  # ★ 專家二：影像分析
IMAGE_GEN_MODEL = 'gemini-2.5-flash-image' # ★ (繪圖復活) 現在它也可以繪圖了！
EMBEDDING_MODEL = 'models/text-embedding-004' # (保持不變，這是標準)
VECTOR_DIMENSION = 768 # ★ 向量維度 768

# --- 步驟四：AI 宗師的「靈魂」核心 (★ 重新啟用繪圖指令 ★) ---
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
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

# --- ★ 「繪圖魔法」指令 (第十九紀元：繪圖復活) ★ ---
* **你可以生成圖片。** 當你判斷「一張圖」會比「純文字」更能幫助學生理解**物理概念、力圖、運動軌跡、光學路徑、電路圖、圖表關係或任何幾何概念**時，你「必須」在回應中**「使用圖像生成標籤」**。
* **生成圖片的格式：** 在你希望生成圖片的地方，插入這個標籤：`{draw:<圖片的詳細描述>}`。
* **範例：**
    * 如果你想畫一個自由落體的示意圖：`{draw:一個從高處自由落下的球，旁邊有重力向量向下}`
    * 如果你想畫一個電路圖：`{draw:一個包含電池、燈泡和開關的簡單串聯電路圖}`
    * 如果你想畫一個速度時間圖：`{draw:一個橫軸為時間(t)縱軸為速度(v)的速度時間圖，顯示物體以等加速度從靜止開始加速的直線}`
* **限制：** 你**一次對話中「最多」只能生成一張圖片**。如果已經生成過圖片，就不要再生成。
* **圖片描述要求：**
    * **「必須」** 使用「繁體中文」。
    * **「必須」** 盡可能「詳細」、「具體」，描述圖片的「核心物理元素」和「關係」。
    * **「絕對禁止」** 在 `draw:` 後面加入任何「非描述性」的內容 (例如：「請畫」、「宗師畫圖」)。

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
    * **如果輸入 100% 完全等於 `出物理題目檢測我`:**
        * 你的任務是：1. 你的「相關段落」是 [N/A]。 2. 你「必須」立刻「產生一個」與物理相關的「新類題」(蘇格拉底式)。 3. 提出这个問題。
        * (你「必須」忽略 RAG，並「停止」後續評估。)

* **【B. 如果學生的「輸入」**「不是」**上述指令 (★ 這代表他正在「正常對話」或「回答問題」★)】:**
    * 你才「啟動」你「正常」的「第十紀元：評估者核心邏輯」：

    1.  **【內心思考 - 步驟 1：自我解答】**
        * 「學生回答了『...』。在我回應之前，我必須先自己『在內心』計算或推導出我上一個問題的『正確答案』是什麼？」
        * (例如：「視覺專家」分析圖 11 說峰值在 t=1。所以「正確答案」是 t=1。)

    2.  **【內心思考 - 步驟 2：評估對錯】**
        * 「學生的答案『...』是否 100% 匹配我『內心』的正確答案？」

    3.  **【內心思考 - 步驟 3：分支應對 (★ 關鍵 ★)】</b>
        * **【B1. 如果學生「答對了」】:**
            * 「太棒了！學生答對了。我的回應『必須』：1. 肯定他（例如：『完全正確！』、『沒錯！』）。 2. 總結我們剛剛的發現。 3. 提出『下一個』合乎邏輯的蘇格拉底式問題。」
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

# --- ★ 第十四紀元：定義「PS5」的「設定」 ★ ---
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
                        # ★ 處理潛在的 `{draw:...}` 標籤，不把它當成文字訊息 ★
                        if role == 'user' or role == 'model':
                            # 過濾掉 {draw:...} 標籤，只保留純文字的部分
                            filtered_parts = [p for p in parts_text if not p.strip().startswith('{draw:')]
                            if filtered_parts: # 只有在有實際文字內容時才添加
                                history_list.append(types.Content(role=role, parts=[types.Part.from_text(text=text) for text in filtered_parts]))
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    return history_list 

def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            history_to_save = []
            history = chat_session.get_history() 
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

def find_relevant_chunks(query_text, k=3):
    conn = None
    if not client: return "N/A"
    try:
        cleaned_query_text = query_text.replace('\x00', '')
        print(f"--- (RAG) 正在為問題「{cleaned_query_text[:20]}...」向 Gemini 請求向量... ---")
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

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 重新啟用繪圖功能 ★) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage)) # ★ 支援 AudioMessage ★
def handle_message(event):

    user_id = event.source.user_id

    if not client:
        print("!!! 嚴重錯誤：Gemini Client 未初始化！(金鑰可能錯誤)")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="抱歉，宗師目前金鑰遺失，請檢查 Render 環境變數 `GEMINI_API_KEY`。"))
        return

    # --- ★ 第八紀元：初始化研究日誌變數 ★ ---
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = "" 
    vision_analysis = "" 
    rag_context = "" 
    final_text = "" 
    
    # ★ (新功能) 判斷是否已經生成過圖片，避免重複生成 ★
    generated_image_in_this_session = False 
    
    # 1. 讀取「過去的記憶」
    past_history = get_chat_history(user_id)

    # 2. 根據「記憶」開啟「對話宗師」的對話
    try:
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
            img = Image.open(io.BytesIO(image_bytes)) 

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

            vision_response = client.models.generate_content(
                model=VISION_MODEL, 
                contents=[img, vision_prompt] 
            )
            vision_analysis = vision_response.text # ★ 存入共用變數
            print(f"--- (視覺專家) 分析完畢：{vision_analysis[:70]}... ---")

            user_question = f"圖片內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"

        elif isinstance(event.message, AudioMessage):
            # --- ★ (新功能) 專家二：「聽覺專家」啟動 ★ ---
            user_message_type = "audio"
            user_content = f"Audio received (Message ID: {event.message.id})" 
            image_url_to_save = "N/A (Audio Message)" # 聲音訊息沒有圖片 URL

            print(f"--- (聽覺專家) 收到來自 user_id '{user_id}' 的錄音，開始分析... ---")
            message_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = message_content.content
            
            audio_file = types.Part.from_data(data=audio_bytes, mime_type='audio/m4a')

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
            
            speech_response = client.models.generate_content(
                model=CHAT_MODEL, 
                contents=[audio_file, audio_prompt]
            )
            
            vision_analysis = speech_response.text # ★ 存入共用變數 (vision_analysis)
            print(f"--- (聽覺專家) 分析完畢：{vision_analysis[:70]}... ---")

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

        # ★ 第十二紀元：修改 RAG 提示詞 (中文版) ★
        rag_prompt = f"""
        ---「相關段落」開始---
        {rag_context}
        ---「相關段落」結束---

        學生的「原始輸入」(可能是「指令」、「回答」、「圖片分析」或「錄音分析」)：「{user_question}」

        (請你「嚴格遵守」 System Prompt 中的「第十二紀元：中文指令」核心邏輯！
        1.  「首先」檢查「原始輸入」是否為「一個指令」(例如：教我物理觀念)。如果是，請「立刻執行指令」。
        2.  「如果不是」指令，才「接著」使用「相關段落」和「評估者邏輯」來回應。)
        """
        contents_to_send = [rag_prompt.replace("{rag_content}", "{rag_context}")]

        # --- ★ AI 宗師：「對話宗師」啟動 (★ 第十七紀元：加入自動重試) ★ ---
        print(f"--- (對話宗師) 正在呼叫 Gemini API ({CHAT_MODEL})... ---")
        
        # ★ (新功能) 準備存放 LINE 回覆的列表 ★
        line_replies = []
        
        final_response_text = ""
        max_retries = 2 
        attempt = 0
        
        while attempt < max_retries:
            try:
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
        
        # --- ★ (新功能) 圖像生成邏輯 (★ 修正版：使用 gemini-2.5-flash-image) ★ ---
        if "{draw:" in final_response_text and not generated_image_in_this_session:
            start_index = final_response_text.find("{draw:")
            end_index = final_response_text.find("}", start_index)
            
            if start_index != -1 and end_index != -1:
                draw_command = final_response_text[start_index + len("{draw:"):end_index].strip()
                final_response_text_without_draw = final_response_text.replace(final_response_text[start_index:end_index+1], "").strip()
                
                print(f"--- (繪圖魔法) AI 宗師請求繪圖：'{draw_command}' (使用 {IMAGE_GEN_MODEL}) ---")
                try:
                    # ★ (修正) 使用 client.models.generate_content (因為 gemini-2.5-flash-image 是多模態模型)
                    # 並且將圖像生成指令放到 contents 中。
                    image_gen_response = client.models.generate_content(
                        model=IMAGE_GEN_MODEL, 
                        contents=[f"請生成一張關於'{draw_command}'的物理教學示意圖。風格簡潔、清晰、易於理解，適合高中生。繁體中文。"]
                    )
                    
                    # ★ (修正) gemini-2.5-flash-image 的圖像輸出格式不同
                    # 它會回傳一個包含圖片位元組的 Part
                    if image_gen_response.parts and image_gen_response.parts[0].mime_type.startswith('image/'):
                        image_data = image_gen_response.parts[0].data # 取得圖片的位元組
                        
                        print("--- (繪圖魔法) 正在上傳生成的圖片到 Cloudinary... ---")
                        upload_gen_image_result = cloudinary.uploader.upload(
                            io.BytesIO(image_data),
                            resource_type="image",
                            folder="ai_guru_generated_images" # 儲存到特定資料夾
                        )
                        generated_image_url = upload_gen_image_result.get('secure_url')
                        
                        if generated_image_url:
                            print(f"--- (繪圖魔法) 圖片生成並上傳成功！URL: {generated_image_url} ---")
                            line_replies.append(ImageSendMessage(
                                original_content_url=generated_image_url,
                                preview_image_url=generated_image_url
                            ))
                            generated_image_in_this_session = True 
                            image_url_to_save = generated_image_url # 更新日誌中的圖片URL
                        else:
                            print("!!! 錯誤：生成的圖片上傳 Cloudinary 失敗。")
                            line_replies.append(TextSendMessage(text="宗師試圖畫一張圖，但目前畫不出來。"))
                    else:
                        print("!!! 錯誤：gemini-2.5-flash-image 圖像生成回應為空或不是圖片。")
                        line_replies.append(TextSendMessage(text="宗師試圖畫一張圖，但目前畫不出來。"))
                
                except Exception as gen_image_e:
                    print(f"!!! 嚴重錯誤：圖像生成或上傳失敗。錯誤：{gen_image_e}")
                    line_replies.append(TextSendMessage(text="宗師試圖畫一張圖，但目前遇到了一些困難。"))

                # (無論繪圖是否成功) 都加入處理後的文字
                if final_response_text_without_draw:
                    line_replies.append(TextSendMessage(text=final_response_text_without_draw.replace('\x00', '')))
                
            else: # 標籤不完整，當成普通文字處理
                line_replies.append(TextSendMessage(text=final_response_text.replace('\x00', '')))
        else: # 沒有 {draw:...} 標籤，或已經生成過圖片，當成普通文字處理
            line_replies.append(TextSendMessage(text=final_response_text.replace('\x00', '')))
        
        final_text = "\n".join([r.text for r in line_replies if isinstance(r, TextSendMessage)]) # 紀錄純文字部分到日誌

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫/RAG/視覺/聽覺操作失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在檢索記憶/教科書或冥想中，請稍後再試。"
        if not user_content: user_content = "Error during processing"
        if not user_message_type: user_message_type = "error"

    # ★★★【第八紀元：最終儲存】★★★
    # 6. 儲存「研究日誌」(人類研究)
    
    save_to_research_log(
        user_id=user_id.replace('\x00', ''),
        user_msg_type=user_message_type.replace('\x00', ''),
        user_content=user_content.replace('\x00', ''),
        image_url=image_url_to_save.replace('\x00', ''), 
        vision_analysis=vision_analysis.replace('\x00', ''), 
        rag_context=rag_context.replace('\x00', ''),
        ai_response=final_text.replace('\x00', '')
    )

    # 7. 回覆使用者
    line_bot_api.reply_message(event.reply_token, line_replies)

# --- 步驟十：啟動「神殿」 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)