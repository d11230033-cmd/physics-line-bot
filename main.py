# ==============================================================================
# JYM 物理 AI 助教 - 最終穩定版 (v3.0)
# ==============================================================================
# 更新日誌：
# 1. [修正] 模型改為 gemini-2.5-flash，徹底解決 429 Too Many Requests (過熱) 問題。
# 2. [新增] 本地端攔截「重來/清除」指令，確保重置絕對成功，不消耗 AI 額度。
# 3. [優化] System Prompt 強制禁止 LaTeX，確保 LINE 數學公式顯示完美。
# ==============================================================================

import os
import io
import json
import datetime
import time
import requests  # 用於呼叫 LINE Loading API

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage

# Google GenAI SDK (Gemini)
from google import genai
from google.genai import types

# 圖片處理與資料庫
from PIL import Image as PILImage
import psycopg2
from pgvector.psycopg2 import register_vector
import cloudinary
import cloudinary.uploader

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. 環境變數設定
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get('DATABASE_URL')
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# ==========================================
# 2. 服務初始化
# ==========================================
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 初始化 Gemini ---
try:
    client = genai.Client() # 自動讀取 GEMINI_API_KEY
    print("✅ Gemini Client 連線成功")
except Exception as e:
    print(f"❌ Gemini 連線失敗: {e}")
    client = None

# --- 初始化 Cloudinary ---
try:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    print("✅ Cloudinary 連線成功")
except Exception as e:
    print(f"❌ Cloudinary 連線失敗: {e}")

# --- 初始化 Google Sheets ---
try:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']
    CREDS = Credentials.from_service_account_file('service_account.json', scopes=SCOPES)
    gc = gspread.authorize(CREDS)
    SPREADSHEET_KEY = "1Evd8WACx_uDUl04c5x2jADFxgLl1A3jW2z0_RynTmhU" 
    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.get_worksheet(0)
    print("✅ Google Sheets 連線成功")
except Exception as e:
    print(f"⚠️ Google Sheets 連線失敗 (僅影響紀錄): {e}")
    worksheet = None

# ==========================================
# 3. 模型與參數設定
# ==========================================
# ★ 關鍵修改：使用 Flash 模型以確保回應速度與避免頻率限制錯誤
CHAT_MODEL = 'gemini-2.5-flash'
VISION_MODEL = 'gemini-2.5-flash-image' # Flash 模型現在已原生支援視覺
AUDIO_MODEL = 'gemini-2.5-flash'
EMBEDDING_MODEL = 'models/text-embedding-004'
VECTOR_DIMENSION = 768

# 記憶長度限制 (只留最後 20 則訊息)
MAX_HISTORY_LENGTH = 20 

# ==========================================
# 4. System Prompt (教學靈魂 - 數學顯示優化版)
# ==========================================
system_prompt = """
你是由頂尖大學物理系博士開發的「JYM物理AI助教」，你是台灣高中物理教育的權威。

### 核心指令
1.  **蘇格拉底式教學**：**絕對禁止**直接給出答案。你必須透過提問引導學生思考。
2.  **語言**：使用自然的繁體中文 (台灣用語)。
3.  **身份**：你是有耐心、鼓勵學生的家教，不是冷冰冰的搜尋引擎。

### ★ 格式規範 (LINE 介面專用 - 非常重要)
1.  **禁止 LaTeX**：LINE 無法顯示 LaTeX 語法 (如 $F=ma$, \\frac{...})，**請絕對不要使用**。
2.  **使用純文字公式**：請用易讀的 Unicode 符號替代。
    * 正確範例：F = ma , v² = v₀² + 2as , θ (角度) , λ (波長) , Δt , μ (摩擦係數) , π
    * 錯誤範例：$v^2$, $\\theta$, $\\Delta t$, \\mu
3.  **排版**：適當使用換行與條列式，讓手機閱讀更舒適。

### 教學流程
1.  **判斷意圖**：
    * 若學生要求「教我觀念」，請詢問具體單元。
    * 若學生要求「解題」，請他上傳題目圖片。
    * 若學生要求「找錯」，請他上傳計算過程。
    * 若學生要求「出題」，請先詢問年級、單元與難度。
2.  **思考邏輯**：
    * 先在內心計算正確答案。
    * 評估學生的理解斷層在哪裡。
3.  **回應策略**：
    * 若學生答對：給予讚美，並出一個類似題(數據不同)確認他真的懂了。
    * 若學生答錯：溫柔指出盲點，給予一個小的提示，讓他再試一次。

### RAG 知識庫運用
* 系統會提供「相關教材段落」。
* 請優先參考教材中的定義與公式。
* 若教材不足，請自信地運用你身為物理博士的內建知識。
"""

generation_config = types.GenerateContentConfig(
    system_instruction=system_prompt,
    temperature=0.7, 
    safety_settings=[
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    ]
)

# ==========================================
# 5. 輔助函式庫
# ==========================================

def send_loading_animation(user_id):
    """發送 LINE Loading 動畫，降低使用者等待焦慮"""
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    data = {"chatId": user_id, "loadingSeconds": 20}
    try:
        requests.post(url, headers=headers, json=data, timeout=5)
    except Exception as e:
        print(f"⚠️ Loading 動畫發送失敗: {e}")

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ 資料庫連線失敗: {e}")
        return None

def initialize_database():
    """初始化 PostgreSQL 資料庫表格"""
    conn = get_db_connection()
    if conn:
        try:
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT PRIMARY KEY, history JSONB);")
                cur.execute(f"CREATE TABLE IF NOT EXISTS physics_vectors (id SERIAL PRIMARY KEY, content TEXT, embedding VECTOR({VECTOR_DIMENSION}));")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_log (
                        id SERIAL PRIMARY KEY, timestamp TIMESTZ DEFAULT CURRENT_TIMESTAMP, 
                        user_id TEXT, user_message_type TEXT, user_content TEXT, 
                        image_url TEXT, vision_analysis TEXT, rag_context TEXT, ai_response TEXT
                    );""")
                cur.execute("""
                    DO $$ BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='research_log' AND column_name='image_url'
                        ) THEN ALTER TABLE research_log ADD COLUMN image_url TEXT; END IF;
                    END$$;""")
                conn.commit()
                print("✅ 資料庫表格初始化完成")
        except Exception as e:
            print(f"❌ 資料庫初始化錯誤: {e}")
        finally:
            conn.close()

def get_chat_history(user_id):
    """從資料庫讀取歷史對話"""
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
                        if role == 'user' or role == 'model':
                            history_list.append(types.Content(
                                role=role, 
                                parts=[types.Part.from_text(text=t) for t in parts_text]
                            ))
        except Exception as e:
            print(f"⚠️ 讀取歷史失敗: {e}")
        finally:
            conn.close()
    return history_list

def save_chat_history(user_id, chat_session):
    """儲存對話歷史到資料庫"""
    conn = get_db_connection()
    if conn:
        try:
            history_to_save = []
            history = chat_session.get_history()
            if history:
                for message in history:
                    if message.role in ['user', 'model']:
                        parts_text = [p.text for p in message.parts if hasattr(p, 'text')]
                        history_to_save.append({'role': message.role, 'parts': parts_text})
            
            if len(history_to_save) > MAX_HISTORY_LENGTH:
                history_to_save = history_to_save[-MAX_HISTORY_LENGTH:]

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_history (user_id, history) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save)))
                conn.commit()
        except Exception as e:
            print(f"⚠️ 儲存歷史失敗: {e}")
        finally:
            conn.close()

def find_relevant_chunks(query_text, k=3):
    """RAG: 搜尋相關物理知識"""
    conn = None
    if not client: return "N/A"
    try:
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[query_text.replace('\x00', '')]
        )
        query_vector = result.embeddings[0].values

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
        
        context = "\n\n---\n\n".join([row[0] for row in results])
        return context
    except Exception as e:
        print(f"⚠️ RAG 搜尋錯誤: {e}")
        return "N/A"
    finally:
        if conn: conn.close()

def save_to_research_log(user_id, msg_type, content, img_url, analysis, rag_ctx, response):
    """寫入研究日誌 (DB + Sheets)"""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO research_log 
                    (user_id, user_message_type, user_content, image_url, vision_analysis, rag_context, ai_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, msg_type, content, img_url, analysis, rag_ctx, response))
                conn.commit()
        except Exception as e:
            print(f"⚠️ Log DB Error: {e}")
        finally:
            conn.close()

    if worksheet:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            row_data = [now_utc, user_id, msg_type, content, img_url, analysis, rag_ctx, response]
            worksheet.append_row(row_data)
        except Exception as e:
            print(f"⚠️ Log Sheet Error: {e}")

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

initialize_database()

# ==========================================
# 6. Webhook 路由
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
# 7. 訊息處理主控室 (Main Handler)
# ==========================================
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage))
def handle_message(event):
    user_id = event.source.user_id
    
    # 1. 收到訊息立刻送出 Loading 動畫
    send_loading_animation(user_id)

    if not client:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="系統維護中 (API Error)"))
        return

    # ★ (關鍵修復) 優先處理「清除記憶」指令
    # 這一段在建立 Gemini Session 之前執行，確保不消耗額度且絕對成功
    if isinstance(event.message, TextMessage):
        user_text_raw = event.message.text.strip().lower()
        RESET_KEYWORDS = ["重來", "清除", "reset", "clear", "清除記憶", "忘記"]
        
        if user_text_raw in RESET_KEYWORDS:
            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
                        conn.commit()
                    
                    print(f"🧹 使用者 {user_id} 記憶已清除 (Local Action)")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="🧹 沒問題！我已經把剛剛的對話都忘記了。\n我們可以重新開始囉！")
                    )
                except Exception as e:
                    print(f"Clear memory error: {e}")
                finally:
                    conn.close()
            return # 直接結束，不繼續執行後續的 AI 呼叫

    # 初始化變數
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = ""
    vision_analysis = ""
    rag_context = "N/A"
    final_response_text = ""
    search_query_for_rag = "" 

    # 建立對話 Session
    past_history = get_chat_history(user_id)
    try:
        chat_session = client.chats.create(
            model=CHAT_MODEL,
            history=past_history,
            config=generation_config 
        )
    except Exception as e:
        print(f"⚠️ Session Create Error: {e}, retrying with empty history")
        chat_session = client.chats.create(model=CHAT_MODEL, history=[], config=generation_config)

    user_question = "" 

    try:
        # --- A. 圖片處理 ---
        if isinstance(event.message, ImageMessage):
            user_message_type = "image"
            user_content = "Image received" 
            
            msg_content = line_bot_api.get_message_content(event.message.id)
            img_bytes = msg_content.content
            try:
                upload_res = cloudinary.uploader.upload(img_bytes)
                image_url_to_save = upload_res.get('secure_url')
            except:
                image_url_to_save = "upload_failed"

            img = PILImage.open(io.BytesIO(img_bytes))
            vision_prompt = "請客觀描述圖片內容，包含文字、算式、圖表結構。並提取3-5個物理關鍵字。"
            
            # 使用 Flash 進行視覺分析
            vision_res = client.models.generate_content(model=VISION_MODEL, contents=[img, vision_prompt])
            vision_analysis = vision_res.text
            
            user_question = f"圖片內容分析：『{vision_analysis}』。請依據此分析進行教學。"
            search_query_for_rag = vision_analysis

        # --- B. 語音處理 ---
        elif isinstance(event.message, AudioMessage):
            user_message_type = "audio"
            user_content = "Audio received"
            image_url_to_save = "N/A (Audio)"
            
            msg_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = msg_content.content
            audio_part = types.Part(inline_data=types.Blob(data=audio_bytes, mime_type='audio/m4a'))
            
            audio_prompt = """
            請將這段錄音進行「逐字聽打」並分析學生的「語氣情感」。
            請回傳：
            1. 逐字稿：(繁體中文)
            2. 語氣分析：(例如：困惑、自信、焦急)
            """
            
            max_retries_audio = 3
            attempt_audio = 0
            while attempt_audio < max_retries_audio:
                try:
                    speech_res = client.models.generate_content(
                        model=AUDIO_MODEL,
                        contents=[audio_part, audio_prompt]
                    )
                    vision_analysis = speech_res.text
                    print(f"--- (聽覺) 語音分析成功 ---")
                    break
                except Exception:
                    attempt_audio += 1
                    time.sleep(2)
                    if attempt_audio == max_retries_audio:
                        vision_analysis = "語音辨識失敗"
            
            user_question = f"錄音內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"
            search_query_for_rag = vision_analysis

        # --- C. 文字處理 ---
        else:
            user_message_type = "text"
            user_text = event.message.text
            user_content = user_text
            user_question = user_text 

            # RAG 略過判斷 (節省資源)
            SKIP_KEYWORDS = {
                "hi", "hello", "你好", "早安", "晚安", "謝謝", "thanks", "ok", "好", "收到", "是", "對", "沒錯",
                "a", "b", "c", "d", "e"
            }
            clean_input = user_text.strip().lower()
            
            should_skip = (
                clean_input in SKIP_KEYWORDS or 
                is_number(clean_input) or 
                (len(clean_input) < 2 and clean_input.isalnum())
            )
            
            if should_skip:
                search_query_for_rag = "" 
            else:
                search_query_for_rag = user_text

        # --- 4. RAG 與 回應 ---
        if search_query_for_rag:
            rag_context = find_relevant_chunks(search_query_for_rag)
        else:
            rag_context = "N/A (Skipped)"

        rag_prompt = f"""
        ---「相關教材段落」開始---
        {rag_context}
        ---「相關教材段落」結束---
        
        學生的目前輸入：「{user_question}」
        
        請依據 System Prompt 中的指示與上述教材段落進行回應。
        """
        contents_to_send = [rag_prompt]

        # 呼叫 Gemini (加入重試機制)
        max_retries = 2 
        attempt = 0
        while attempt < max_retries:
            try:
                response = chat_session.send_message(contents_to_send)
                final_response_text = response.text 
                break 
            except Exception as e:
                print(f"⚠️ Gemini Error: {e}")
                attempt += 1
                time.sleep(1)
                if attempt == max_retries:
                    final_response_text = "抱歉，JYM助教大腦運轉過熱，請稍後再試一次。"
        
        # 傳送回應給 LINE
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=final_response_text.replace('\x00', ''))
        )
        
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"❌ 處理訊息錯誤: {e}")
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生未知錯誤，請稍後再試。"))
        except:
            pass

    # 寫入 Log
    save_to_research_log(
        user_id.replace('\x00', ''), user_message_type, user_content.replace('\x00', ''),
        image_url_to_save, vision_analysis.replace('\x00', ''), 
        rag_context.replace('\x00', ''), final_response_text.replace('\x00', '')
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)