# --- 「神殿」：AI 宗師的核心 (第二十一紀元：Vertex AI 遷移版) ---
#
# SDK：★「全新」 google-cloud-aiplatform (Vertex AI) ★
# ... (之前的所有修正)
# 修正：25. ★ (重大 Bug 修正) 404 Model Not Found -> 降級至 1.5 Pro/Flash (GA 穩定版) ★
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage, ImageSendMessage 

# --- ★ (新) Vertex AI SDK ★ ---
import vertexai
# ★ (修正) 引入 Content
from vertexai.preview.generative_models import GenerativeModel, Part, Image, Content 
from vertexai.preview.vision_models import ImageGenerationModel
from vertexai.language_models import TextEmbeddingModel

from PIL import Image as PILImage
import io
import psycopg2 # 藍圖三：資料庫工具
import json     # 藍圖三：資料庫工具
import datetime # ★ 第七紀元：需要時間戳
import time     # ★ (新功能) 為了「自動重試」
import threading # ★ (新功能) 為了「非同步」繪圖

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

# ★ (新) Vertex AI 專案金鑰 ★
GCP_PROJECT_ID = os.environ.get('GCP_PROJECT_ID')
GCP_LOCATION = os.environ.get('GCP_LOCATION')

# --- 步驟二：神殿的基礎建設 ---
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- ★ (新) 連接 Vertex AI (神之鍛造廠) ★ ---
try:
    if not GCP_PROJECT_ID or not GCP_LOCATION:
        raise ValueError("GCP_PROJECT_ID 和 GCP_LOCATION 環境變數尚未設定！")
    
    # 讀取 Render 上的 Secret File ('service_account.json')
    CREDS = Credentials.from_service_account_file('service_account.json')
    print("--- (Vertex AI) 成功讀取 service_account.json ---")

    vertexai.init(project=GCP_PROJECT_ID, location=GCP_LOCATION, credentials=CREDS)
    print(f"--- (Vertex AI) ★ Vertex AI SDK 連接成功！專案：{GCP_PROJECT_ID}, 位置：{GCP_LOCATION} ★ ---")

except Exception as e:
    print(f"!!! 嚴重錯誤：無法初始化 Vertex AI。錯誤：{e}")
    print("    (★ 提醒：請檢查 IAM 權限是否已新增 `Vertex AI User` 和 `Storage Object Admin` ★)")

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
    # (我們使用與 Vertex AI 相同的 CREDS)
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive.file'
    ]
    # ★ 重新加上 Scopes
    CREDS_WITH_SCOPES = CREDS.with_scopes(SCOPES)
    gc = gspread.authorize(CREDS_WITH_SCOPES)
    
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

# --- ★ (新) Vertex AI 模型定義 ★ ---
# ★ (修正) 降級至 GA (General Availability) 穩定版模型 ★
CHAT_MODEL_NAME = 'gemini-2.5-pro'         # ★ 修正
VISION_MODEL_NAME = 'gemini-2.5-flash-image'       # ★ 修正
EMBEDDING_MODEL_NAME = 'text-embedding-004'    # (OK)
IMAGE_GEN_MODEL_NAME = 'imagen-3.0-generate-002' # (OK)
VECTOR_DIMENSION = 768

# --- ★ (新) Vertex AI 安全設定 ★ ---
from vertexai.preview.generative_models import HarmCategory as VertexHarmCategory, HarmBlockThreshold as VertexHarmBlockThreshold

safety_settings = {
    VertexHarmCategory.HARM_CATEGORY_HATE_SPEECH: VertexHarmBlockThreshold.BLOCK_NONE,
    VertexHarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: VertexHarmBlockThreshold.BLOCK_NONE,
    VertexHarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: VertexHarmBlockThreshold.BLOCK_NONE,
    VertexHarmCategory.HARM_CATEGORY_HARASSMENT: VertexHarmBlockThreshold.BLOCK_NONE,
}

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

# --- ★ 「繪圖魔法」指令 (Vertex AI 版) ★ ---
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

# ★ (修正) Vertex AI 模型初始化 (★ 語法修正 ★)
try:
    chat_model = GenerativeModel(
        CHAT_MODEL_NAME,
        system_instruction=[system_prompt], # ★ (修正) System Prompt 在此傳入
        safety_settings=safety_settings      # ★ (修正) Safety Settings 在此傳入
    )
    vision_model = GenerativeModel(
        VISION_MODEL_NAME,
        safety_settings=safety_settings      # ★ (修正) 也為視覺模型加入安全設定
    )
    embedding_model = TextEmbeddingModel.from_pretrained(EMBEDDING_MODEL_NAME)
    image_gen_model = ImageGenerationModel.from_pretrained(IMAGE_GEN_MODEL_NAME)
    print(f"--- (Vertex AI) 所有 AI 專家 (Pro, Flash, Embedding, Imagen) 均已成功初始化！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：初始化 Vertex AI 模型失敗。錯誤：{e}")
    chat_model = None # 禁用

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

# --- ★ (新) Vertex AI 版 `get_chat_history` (★ 語法修正 ★) ---
def get_chat_history(user_id):
    conn = get_db_connection()
    history_list = [] # ★ Vertex AI 需要 `Content` 物件列表
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    history_json = result[0]
                    # ★ 重建 Vertex AI 的 Content 列表
                    for item in history_json:
                        role = item.get('role', 'user')
                        # ★ Vertex AI 的角色是 'user' 和 'model'
                        parts_text = item.get('parts', [])
                        if (role == 'user' or role == 'model') and parts_text:
                            # 過濾掉 {draw:...} 標籤，只保留純文字的部分
                            filtered_parts = [p for p in parts_text if not p.strip().startswith('{draw:')]
                            if filtered_parts:
                                # ★ (修正) Vertex AI 需要的是 Content 物件
                                role_to_use = "user" if role == "user" else "model"
                                parts_to_use = [Part.from_text(text) for text in filtered_parts]
                                history_list.append(Content(role=role_to_use, parts=parts_to_use))
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            if conn: conn.close()
    return history_list 

# --- ★ (新) Vertex AI 版 `save_chat_history` ★ ---
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            history_to_save = []
            # ★ Vertex AI 的語法是 .history
            history = chat_session.history 
            if history:
                for message in history:
                    # (我們只儲存 user 和 model 的對話)
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
            if conn: conn.close()

# --- ★ (新) Vertex AI 版 `find_relevant_chunks` ★ ---
def find_relevant_chunks(query_text, k=3):
    conn = None
    if not embedding_model: return "N/A"
    try:
        cleaned_query_text = query_text.replace('\x00', '')
        print(f"--- (RAG) 正在為問題「{cleaned_query_text[:20]}...」向 Vertex AI 請求向量... ---")
        
        # ★ Vertex AI 的語法
        result = embedding_model.get_embeddings([cleaned_query_text])
        query_vector = result[0].values 

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


# --- ★ (新) Vertex AI 版：在「背景」繪圖 (使用 Imagen 3) ★ ---
def generate_and_push_image(user_id, draw_command):
    if not image_gen_model:
        print("!!! (背景) 錯誤：Imagen 3 模型未初始化。")
        line_bot_api.push_message(user_id, TextSendMessage(text="抱歉，JYM助教的繪圖核心未啟動。"))
        return
        
    try:
        print(f"--- (繪圖魔法 - 背景) JYM助教請求繪圖：'{draw_command}' (使用 {IMAGE_GEN_MODEL_NAME}) ---")
        
        # ★ (新) Vertex AI Imagen 3 語法 ★
        image_gen_response = image_gen_model.generate_images(
            prompt=f"一張關於'{draw_command}'的物理教學示意圖。風格簡潔、清晰、易於理解，適合高中生。繁體中文。",
            number_of_images=1
        )
        
        if image_gen_response.images:
            image_data = image_gen_response.images[0]._image_bytes # 取得圖片的位元組
            
            print("--- (繪圖魔法 - 背景) 正在上傳生成的圖片到 Cloudinary... ---")
            upload_gen_image_result = cloudinary.uploader.upload(
                io.BytesIO(image_data),
                resource_type="image",
                folder="ai_guru_generated_images" 
            )
            generated_image_url = upload_gen_image_result.get('secure_url')
            
            if generated_image_url:
                print(f"--- (繪圖魔法 - 背景) 圖片生成並上傳成功！URL: {generated_image_url} ---")
                
                # ★★★ 使用 PUSH_MESSAGE (推送訊息) ★★★
                line_bot_api.push_message(
                    user_id,
                    ImageSendMessage(
                        original_content_url=generated_image_url,
                        preview_image_url=generated_image_url
                    )
                )
            else:
                print("!!! (背景) 錯誤：生成的圖片上傳 Cloudinary 失敗。")
                line_bot_api.push_message(user_id, TextSendMessage(text="抱歉，JYM助教試圖畫一張圖，但目前畫不出來。"))
        else:
            print("!!! (背景) 錯誤：Imagen 3 圖像生成回應為空。")
            line_bot_api.push_message(user_id, TextSendMessage(text="抱歉，JYM助教試圖畫一張圖，但目前畫不出來。"))
    
    except Exception as gen_image_e:
        print(f"!!! (背景) 嚴重錯誤：圖像生成或上傳失敗。錯誤：{gen_image_e}")
        line_bot_api.push_message(user_id, TextSendMessage(text="抱歉，JYM助教試圖畫一張圖，但目前遇到了一些困難。"))


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

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 遷移到 Vertex AI ★) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage)) # ★ 支援 AudioMessage ★
def handle_message(event):

    user_id = event.source.user_id

    if not chat_model:
        print("!!! 嚴重錯誤：Vertex AI Client 未初始化！(金鑰或權限可能錯誤)")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="抱歉，JYM助教目前金鑰遺失，請檢查 Render 環境變數。"))
        return

    # --- ★ 第八紀元：初始化研究日誌變數 ★ ---
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = "" 
    vision_analysis = "" 
    rag_context = "" 
    final_response_text = "" # AI 的原始文字回應 (用於日誌)
    line_replies = []        # 準備傳送給 LINE 的訊息列表
    
    # ★ (新功能) 判斷是否已經生成過圖片，避免重複生成 ★
    generated_image_in_this_session = False 
    
    # 1. 讀取「過去的記憶」
    past_history = get_chat_history(user_id)

    # 2. 根據「過去的記憶」開啟「對話」
    try:
         # ★ (修正) Vertex AI 語法 ★
         chat_session = chat_model.start_chat(
             history=past_history
             # ★ (修正) 移除錯誤的 generation_config
         )
         # ★ (修正) 移除多餘的 send_message 和 history 清除

    except Exception as start_chat_e:
         print(f"!!! 警告：從歷史紀錄開啟對話失敗。使用空對話。錯誤：{start_chat_e}")
         # ★ (修正) Vertex AI 語法 ★
         chat_session = chat_model.start_chat(
             history=[]
             # ★ (修正) 移除錯誤的 generation_config
         )
         # ★ (修正) 移除多餘的 send_message 和 history 清除

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

            print(f"--- (視覺專家) 正在分析圖片 (使用 {VISION_MODEL_NAME})... ---")
            # ★ (新) Vertex AI 語法
            img = Image(image_bytes)

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

            vision_response = vision_model.generate_content(
                [img, vision_prompt],
                # ★ (修正) Vertex AI 中，安全設定已在模型初始化時設定
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
            
            # ★ (新) Vertex AI 語法
            audio_file = Part.from_data(data=audio_bytes, mime_type='audio/m4a')

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
            
            speech_response = chat_model.generate_content(
                [audio_file, audio_prompt],
                # ★ (修正) Vertex AI 中，安全設定已在模型初始化時設定
            )
            
            vision_analysis = speech_response.text 
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

        rag_prompt = f"""
        ---「相關段落」開始---
        {rag_context}
        ---「相關段落」結束---
        學生的「原始輸入」(可能是「指令」、「回答」、「圖片分析」或「錄音分析」)：「{user_question}」
        (請你「嚴格遵守」 System Prompt 中的「第十二紀元：中文指令」核心邏輯！...)
        """
        contents_to_send = [rag_prompt.replace("{rag_content}", "{rag_context}")]

        # --- ★ AI 宗師：「對話宗師」啟動 (★ 第十七紀元：加入自動重試) ★ ---
        print(f"--- (對話宗師) 正在呼叫 Vertex AI ({CHAT_MODEL_NAME})... ---")
        
        max_retries = 2 
        attempt = 0
        
        while attempt < max_retries:
            try:
                # ★ (新) Vertex AI 語法
                response = chat_session.send_message(contents_to_send)
                final_response_text = response.text 
                print(f"--- (對話宗師) Vertex AI 回應成功 (嘗試第 {attempt + 1} 次) ---")
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
        
        # --- ★ (新功能) 圖像生成邏輯 (★ 修正版：非同步 ★) ---
        if "{draw:" in final_response_text and not generated_image_in_this_session:
            start_index = final_response_text.find("{draw:")
            end_index = final_response_text.find("}", start_index)
            
            if start_index != -1 and end_index != -1:
                draw_command = final_response_text[start_index + len("{draw:"):end_index].strip()
                final_response_text_without_draw = final_response_text.replace(final_response_text[start_index:end_index+1], "").strip()
                
                print(f"--- (繪圖魔法) 偵測到繪圖指令：'{draw_command}' ---")
                
                instant_reply_text = f"好的，JYM助教正在為您繪製「{draw_command}」，請稍候..."
                
                if final_response_text_without_draw:
                    instant_reply_text += f"\n\n{final_response_text_without_draw}"
                
                line_replies.append(TextSendMessage(text=instant_reply_text.replace('\x00', '')))
                
                print(f"--- (繪圖魔法) 正在啟動背景執行緒來繪圖... ---")
                # ★ (新) 我們呼叫的是新版 Vertex AI 繪圖函式
                thread = threading.Thread(target=generate_and_push_image, args=(user_id, draw_command))
                thread.start()

                generated_image_in_this_session = True 
                
            else: # 標籤不完整，當成普通文字處理
                line_replies.append(TextSendMessage(text=final_response_text.replace('\x00', '')))
        
        if not generated_image_in_this_session:
            line_replies.append(TextSendMessage(text=final_response_text.replace('\x00', '')))
        
        # 5. 儲存「更新後的記憶」(AI 記憶)
        print(f"--- (記憶) 正在儲存 user_id '{user_id}' 的對話紀錄... ---")
        save_chat_history(user_id, chat_session)
        print(f"--- (記憶) 對話紀錄儲存成功 ---")
        
    except Exception as e:
        print(f"!!! 嚴重錯誤：Vertex AI 呼叫或資料庫/RAG/視覺/聽覺/繪圖操作失敗。錯誤：{e}")
        final_response_text = "抱歉，JYM助教目前正在檢索記憶/教科書或冥想中，請稍後再試。"
        if not user_content: user_content = "Error during processing"
        if not user_message_type: user_message_type = "error"
        line_replies = [TextSendMessage(text=final_response_text)] 

    # ★★★【第八紀元：最終儲存】★★★
    # 6. 儲存「研究日誌」(人類研究)
    
    save_to_research_log(
        user_id=user_id.replace('\x00', ''),
        user_msg_type=user_message_type.replace('\x00', ''),
        user_content=user_content.replace('\x00', ''),
        image_url=image_url_to_save.replace('\x00', ''), 
        vision_analysis=vision_analysis.replace('\x00', ''), 
        rag_context=rag_context.replace('\x00', ''),
        ai_response=final_response_text.replace('\x00', '') 
    )

    # 7. 回覆使用者 (★ 現在只回覆「請稍候...」或「純文字」)
    line_bot_api.reply_message(
        event.reply_token, 
        line_replies 
    )

# --- 步驟十：啟動「神殿」 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)