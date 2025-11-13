# ==============================================================================
# JYM 物理 AI 助教 - 終極完結篇 (v3.2)
# ==============================================================================
# 更新日誌：
# 1. [核心] 模型鎖定 gemini-2.5-flash (速度最快、無頻率限制、穩定性最高)。
# 2. [體驗] 新增「自動小尾巴」，在長回應後提示學生如何清除記憶 (彌補選單缺憾)。
# 3. [安全] 資料庫初始化加入 CREATE EXTENSION vector 檢測，防止向量功能未開啟。
# 4. [完整] 包含歡迎訊息、數學顯示優化、Loading 動畫、RAG 檢索、研究日誌。
# ==============================================================================

import os
import io
import json
import datetime
import time
import requests

from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, TextSendMessage, FollowEvent

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
    client = genai.Client()
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
# 使用 Flash 以確保付費 Render 主機的效能最大化，且避免 429 過熱
CHAT_MODEL = 'gemini-2.5-flash'
VISION_MODEL = 'gemini-2.5-flash'
AUDIO_MODEL = 'gemini-2.5-flash'
EMBEDDING_MODEL = 'models/text-embedding-004'
VECTOR_DIMENSION = 768
MAX_HISTORY_LENGTH = 20 

# ==========================================
# 4. System Prompt (教學靈魂)
# ==========================================
system_prompt = """
你是由頂尖大學物理系博士開發的「JYM物理AI助教」，你是台灣高中物理教育的權威。

### 核心指令
1.  **蘇格拉底式教學**：**絕對禁止**直接給出答案。你必須透過提問引導學生思考。
2.  **語言**：使用自然的繁體中文 (台灣用語)。
3.  **身份**：你是有耐心、鼓勵學生的家教，不是冷冰冰的搜尋引擎。

### ★ 格式規範 (LINE 介面專用)
1.  **禁止 LaTeX**：LINE 無法顯示 LaTeX 語法 (如 $F=ma$)，**請絕對不要使用**。
2.  **使用純文字公式**：請用易讀的 Unicode 符號替代。
    * 正確範例：F = ma , v² = v₀² + 2as , θ , Δt , μ , π
    * 錯誤範例：$v^2$, $\\theta$, $\\Delta t$, \\mu
3.  **排版**：適當使用換行與條列式，讓手機閱讀更舒適。

### 教學流程
1.  **判斷意圖**：
    * 若學生要求「教我觀念」，請詢問具體單元。
    * 若學生要求「解題」，請他上傳題目圖片。
    * 若學生要求「找錯」，請他上傳計算過程。
    * 若學生要求「出題」，請先詢問年級、單元與難度。
2.  **回應策略**：
    * 若學生答對：給予讚美，並出一個類似題確認他真的懂了。
    * 若學生答錯：溫柔指出盲點，給予一個小的提示，讓他再試一次。
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
    """發送 LINE Loading 動畫"""
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
    """初始化 PostgreSQL 資料庫表格 (含安全鎖)"""
    conn = get_db_connection()
    if conn:
        try:
            # ★ 關鍵修正：確保 vector 擴充功能已啟用
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()

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
# 7. 事件處理 (歡迎訊息 & 訊息回應)
# ==========================================

# ★ FollowEvent: 針對舊有圖文選單設計的歡迎引導
@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    print(f"🎉 新使用者加入: {user_id}")
    
    welcome_text = (
        "🎉 歡迎來到 JYM 物理教室！\n"
        "我是你的 AI 專屬助教。\n\n"
        "👇 **你可以點選下方的選單來學習** 👇\n"
        "📖 教我物理觀念\n"
        "📝 教我解物理試題\n"
        "🔍 我想知道哪裡算錯\n"
        "🎯 出物理題目檢測我\n\n"
        "⚠️ **重要小撇步**：\n"
        "選單上沒有清除按鈕，所以若要換單元，請直接打字輸入 **「重來」** 來清除記憶喔！\n\n"
        "現在，試著傳一張題目給我，或點選選單試試看吧！💪"
    )
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=welcome_text)
    )

@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage))
def handle_message(event):
    user_id = event.source.user_id
    
    # 1. 收到訊息立刻送出 Loading 動畫
    send_loading_animation(user_id)

    if not client:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="系統維護中 (API Error)"))
        return

    # 2. 優先處理「清除記憶」指令
    if isinstance(event.message, TextMessage):
        user_text_raw = event.message.text.strip().lower()
        RESET_KEYWORDS = ["重來", "清除", "reset", "clear", "清除記憶", "忘記", "清空"]
        
        if user_text_raw in RESET_KEYWORDS:
            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
                        conn.commit()
                    
                    print(f"🧹 使用者 {user_id} 記憶已清除")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="🧹 沒問題！我已經把剛剛的對話都忘記了。\n我們可以重新開始囉！")
                    )
                except Exception as e:
                    print(f"Clear memory error: {e}")
                finally:
                    conn.close()
            return 

    # 初始化
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = ""
    vision_analysis = ""
    rag_context = "N/A"
    final_response_text = ""
    search_query_for_rag = "" 

    past_history = get_chat_history(user_id)
    try:
        chat_session = client.chats.create(model=CHAT_MODEL, history=past_history, config=generation_config)
    except Exception:
        chat_session = client.chats.create(model=CHAT_MODEL, history=[], config=generation_config)

    user_question = "" 

    try:
        # --- A. 圖片 ---
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
            
            vision_res = client.models.generate_content(model=VISION_MODEL, contents=[img, vision_prompt])
            vision_analysis = vision_res.text
            
            user_question = f"圖片內容分析：『{vision_analysis}』。請依據此分析進行教學。"
            search_query_for_rag = vision_analysis

        # --- B. 語音 ---
        elif isinstance(event.message, AudioMessage):
            user_message_type = "audio"
            user_content = "Audio received"
            image_url_to_save = "N/A (Audio)"
            
            msg_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = msg_content.content
            audio_part = types.Part(inline_data=types.Blob(data=audio_bytes, mime_type='audio/m4a'))
            
            audio_prompt = "請將這段錄音進行「逐字聽打(繁體中文)」並分析學生的「語氣情感」。"
            
            max_retries_audio = 3
            attempt_audio = 0
            while attempt_audio < max_retries_audio:
                try:
                    speech_res = client.models.generate_content(model=AUDIO_MODEL, contents=[audio_part, audio_prompt])
                    vision_analysis = speech_res.text
                    break
                except Exception:
                    attempt_audio += 1
                    time.sleep(2)
                    if attempt_audio == max_retries_audio:
                        vision_analysis = "語音辨識失敗"
            
            user_question = f"錄音內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"
            search_query_for_rag = vision_analysis

        # --- C. 文字 ---
        else:
            user_message_type = "text"
            user_text = event.message.text
            user_content = user_text
            user_question = user_text 

            SKIP_KEYWORDS = {
                "hi", "hello", "你好", "早安", "晚安", "謝謝", "thanks", "ok", "好", "收到", "是", "對", "沒錯",
                "a", "b", "c", "d", "e"
            }
            clean_input = user_text.strip().lower()
            should_skip = (clean_input in SKIP_KEYWORDS or is_number(clean_input) or (len(clean_input) < 2 and clean_input.isalnum()))
            
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

        max_retries = 2 
        attempt = 0
        while attempt < max_retries:
            try:
                response = chat_session.send_message(contents_to_send)
                final_response_text = response.text 
                break 
            except Exception:
                attempt += 1
                time.sleep(1)
                if attempt == max_retries:
                    final_response_text = "抱歉，JYM助教大腦運轉過熱，請稍後再試一次。"
        
        # ★ 優化：加上操作提示小尾巴 (彌補選單無清除按鈕的缺憾)
        if len(final_response_text) > 50:
            final_response_text += "\n\n(💡 想要問新單元？請輸入「重來」清除記憶)"

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

    save_to_research_log(
        user_id.replace('\x00', ''), user_message_type, user_content.replace('\x00', ''),
        image_url_to_save, vision_analysis.replace('\x00', ''), 
        rag_context.replace('\x00', ''), final_response_text.replace('\x00', '')
    )

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)