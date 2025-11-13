# ==============================================================================
# JYM 物理 AI 助教 - v3.3 全能講師版 (含詳細註解)
# ==============================================================================
# 功能總覽：
# 1. 物理教學：基於 Gemini 1.5 Flash 模型，使用蘇格拉底式引導。
# 2. 圖片/語音：支援學生上傳題目照片或錄音提問。
# 3. 記憶功能：擁有短期記憶，能進行連續對話 (可輸入「重來」清除)。
# 4. RAG (大腦)：能從資料庫搜尋物理知識。
# 5. PDF 學習 (新)：老師傳 PDF 給機器人，它會自動讀取並存入大腦。
# 6. 研究日誌：所有對話紀錄都會同步存到 Google Sheets 與 資料庫。
# ==============================================================================

import os
import io
import json
import datetime
import time
import requests

# --- 網頁框架與 LINE SDK ---
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, FileMessage, TextSendMessage, FollowEvent

# --- Google AI (Gemini) ---
from google import genai
from google.genai import types

# --- 檔案處理工具 ---
from PIL import Image as PILImage  # 處理圖片
from pypdf import PdfReader        # ★ v3.3 新增：用來讀取 PDF 講義

# --- 資料庫 (PostgreSQL) ---
import psycopg2
from pgvector.psycopg2 import register_vector  # 向量資料庫擴充 (RAG 核心)
import cloudinary
import cloudinary.uploader

# --- Google 試算表 ---
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# 1. 環境變數設定 (從 Render 後台讀取)
# ==========================================
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get('DATABASE_URL')  # 資料庫連線網址
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# ==========================================
# 2. 服務初始化 (啟動各項工具)
# ==========================================
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 2.1 連接 Gemini AI ---
try:
    client = genai.Client()
    print("✅ Gemini Client 連線成功")
except Exception as e:
    print(f"❌ Gemini 連線失敗: {e}")
    client = None

# --- 2.2 連接 Cloudinary (圖床) ---
try:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    print("✅ Cloudinary 連線成功")
except Exception as e:
    print(f"❌ Cloudinary 連線失敗: {e}")

# --- 2.3 連接 Google Sheets (研究日誌) ---
try:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']
    # 讀取您上傳的 json 金鑰檔案
    CREDS = Credentials.from_service_account_file('service_account.json', scopes=SCOPES)
    gc = gspread.authorize(CREDS)
    SPREADSHEET_KEY = "1Evd8WACx_uDUl04c5x2jADFxgLl1A3jW2z0_RynTmhU"  # 您的試算表 ID
    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.get_worksheet(0)
    print("✅ Google Sheets 連線成功")
except Exception as e:
    print(f"⚠️ Google Sheets 連線失敗 (僅影響紀錄，不影響問答): {e}")
    worksheet = None

# ==========================================
# 3. 模型參數設定
# ==========================================
# 指定使用 Google 最新、速度最快的 Flash 模型
CHAT_MODEL = 'gemini-2.5-flash'
VISION_MODEL = 'gemini-2.5-flash'
AUDIO_MODEL = 'gemini-2.5-flash'
EMBEDDING_MODEL = 'models/text-embedding-004'  # 用來把文字轉成向量數字
VECTOR_DIMENSION = 768   # 向量維度 (固定值)
MAX_HISTORY_LENGTH = 20  # 記憶長度 (記住最近 20 句話)

# ==========================================
# 4. System Prompt (AI 的人設靈魂)
# ==========================================
system_prompt = """
你是由頂尖大學物理系博士開發的「JYM物理AI助教」，你是台灣高中物理教育的權威。

### 核心指令
1.  **蘇格拉底式教學**：**絕對禁止**直接給出答案。你必須透過提問引導學生思考。
2.  **語言**：使用自然的繁體中文 (台灣用語)。
3.  **身份**：你是有耐心、鼓勵學生的家教，不是冷冰冰的搜尋引擎。
4.  **知識庫運用**：若提供的 context 中有相關物理觀念，請優先使用該資訊進行教學。

### ★ 格式規範 (LINE 介面專用)
1.  **禁止 LaTeX**：LINE 無法顯示 LaTeX 語法，請用 Unicode 符號 (如 F=ma, v², θ)。
2.  **排版**：適當使用換行與條列式，讓手機閱讀更舒適。
"""

generation_config = types.GenerateContentConfig(
    system_instruction=system_prompt,
    temperature=0.7,  # 創意度 (0.7 比較自然，不會太死板)
    safety_settings=[ # 關閉安全過濾，避免物理題目(如碰撞)被誤判為暴力
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
        types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
    ]
)

# ==========================================
# 5. 輔助函式庫 (工具箱)
# ==========================================

def send_loading_animation(user_id):
    """發送 LINE 的 Loading 動畫，讓使用者知道機器人正在思考"""
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
    """取得資料庫連線 (如果斷線會報錯)"""
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ 資料庫連線失敗: {e}")
        return None

def initialize_database():
    """系統啟動時，自動建立需要的資料表 (Table)"""
    conn = get_db_connection()
    if conn:
        try:
            # 1. 啟用向量擴充功能
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()

            register_vector(conn) # 註冊向量型別

            # 2. 建立資料表
            with conn.cursor() as cur:
                # 對話歷史表
                cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT PRIMARY KEY, history JSONB);")
                # 物理知識向量表 (RAG 用)
                cur.execute(f"CREATE TABLE IF NOT EXISTS physics_vectors (id SERIAL PRIMARY KEY, content TEXT, embedding VECTOR({VECTOR_DIMENSION}));")
                # 研究日誌表
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_log (
                        id SERIAL PRIMARY KEY, timestamp TIMESTZ DEFAULT CURRENT_TIMESTAMP, 
                        user_id TEXT, user_message_type TEXT, user_content TEXT, 
                        image_url TEXT, vision_analysis TEXT, rag_context TEXT, ai_response TEXT
                    );""")
                # 補丁：確保 image_url 欄位存在 (舊版升級用)
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

def save_pdf_content(pdf_text):
    """★ 核心功能：把 PDF 文字切塊並轉成向量存入資料庫"""
    if not pdf_text or not client: return False
    
    # 設定切塊大小 (每 1000 字切一塊，前後重疊 100 字以免切斷語意)
    chunk_size = 1000
    overlap = 100
    chunks = []
    for i in range(0, len(pdf_text), chunk_size - overlap):
        chunks.append(pdf_text[i:i+chunk_size])
    
    conn = get_db_connection()
    if not conn: return False
    
    try:
        register_vector(conn)
        count = 0
        for chunk in chunks:
            if len(chunk.strip()) < 50: continue # 太短的片段不存
            
            # 呼叫 Google AI 取得向量 (Embedding)
            res = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=[chunk.replace('\x00', '')]
            )
            vector = res.embeddings[0].values
            
            # 存入 SQL 資料庫
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                    (chunk, vector)
                )
            count += 1
        conn.commit()
        print(f"✅ 成功儲存 {count} 個 PDF 片段")
        return count
    except Exception as e:
        print(f"❌ PDF 儲存失敗: {e}")
        return False
    finally:
        conn.close()

def find_relevant_chunks(query_text, k=3):
    """RAG 檢索：拿使用者的問題去資料庫找最像的 3 個知識點"""
    conn = None
    if not client: return "N/A"
    try:
        # 把使用者的問題轉成向量
        result = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[query_text.replace('\x00', '')]
        )
        query_vector = result.embeddings[0].values

        conn = get_db_connection()
        if not conn: return "N/A"
        register_vector(conn)
        
        # 使用向量距離 (<->) 搜尋最接近的 k 筆資料
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM physics_vectors ORDER BY embedding <-> %s::vector LIMIT %s",
                (query_vector, k)
            )
            results = cur.fetchall()
        
        if not results: return "N/A"
        
        # 把找到的資料串起來
        context = "\n\n---\n\n".join([row[0] for row in results])
        return context
    except Exception as e:
        print(f"⚠️ RAG 搜尋錯誤: {e}")
        return "N/A"
    finally:
        if conn: conn.close()

def get_chat_history(user_id):
    """從資料庫取出這個人的歷史對話紀錄"""
    conn = get_db_connection()
    history_list = []
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    history_json = result[0]
                    # 將 JSON 轉回 Gemini SDK 看得懂的物件格式
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
    """把最新的對話紀錄存回資料庫"""
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
            
            # 只保留最後 N 筆，避免記憶體爆炸
            if len(history_to_save) > MAX_HISTORY_LENGTH:
                history_to_save = history_to_save[-MAX_HISTORY_LENGTH:]

            with conn.cursor() as cur:
                # 使用 Upsert 語法 (有就更新，沒有就新增)
                cur.execute("""
                    INSERT INTO chat_history (user_id, history) VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save)))
                conn.commit()
        except Exception as e:
            print(f"⚠️ 儲存歷史失敗: {e}")
        finally:
            conn.close()

def save_to_research_log(user_id, msg_type, content, img_url, analysis, rag_ctx, response):
    """雙重存檔：寫入 PostgreSQL 資料庫 + Google Sheets"""
    # 1. 寫入資料庫
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

    # 2. 寫入 Google Sheets (若有連線的話)
    if worksheet:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            row_data = [now_utc, user_id, msg_type, content, img_url, analysis, rag_ctx, response]
            worksheet.append_row(row_data)
        except Exception as e:
            print(f"⚠️ Log Sheet Error: {e}")

def is_number(s):
    """判斷字串是否為數字 (用來過濾無意義輸入)"""
    try:
        float(s)
        return True
    except ValueError:
        return False

# 程式啟動時先跑一次資料庫檢查
initialize_database()

# ==========================================
# 6. Webhook 路由 (LINE 訊息的入口)
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
# 7. 事件處理 (主邏輯區)
# ==========================================

# --- 7.1 加入好友/解除封鎖時的歡迎詞 ---
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
        "⚠️ **老師專屬功能**：\n"
        "老師若傳送 PDF 檔案給我，我會自動閱讀並把它記在腦海裡喔！\n"
        "(學生請傳題目照片或直接打字)"
    )
    
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=welcome_text)
    )

# --- 7.2 處理一般訊息 (文字/圖片/語音/檔案) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage, FileMessage))
def handle_message(event):
    user_id = event.source.user_id
    
    # A. 立刻送出 Loading 動畫 (避免使用者以為壞了)
    send_loading_animation(user_id)

    if not client:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="系統維護中 (API Error)"))
        return
    
    # --- B. ★ 特殊功能：如果收到 PDF 檔 ---
    if isinstance(event.message, FileMessage):
        file_name = event.message.file_name.lower()
        if file_name.endswith('.pdf'):
            # 1. 下載檔案
            msg_content = line_bot_api.get_message_content(event.message.id)
            temp_pdf_path = f"/tmp/{event.message.id}.pdf" # 存到暫存區
            
            try:
                with open(temp_pdf_path, 'wb') as fd:
                    for chunk in msg_content.iter_content():
                        fd.write(chunk)
                
                # 2. 讀取文字
                reader = PdfReader(temp_pdf_path)
                text_content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
                
                # 3. 存入向量資料庫 (呼叫上面的函式)
                if text_content.strip():
                    chunks_count = save_pdf_content(text_content)
                    if chunks_count:
                        reply = f"✅ 成功讀取 PDF：{event.message.file_name}\n📚 已吸收 {chunks_count} 個知識片段進入大腦！\n現在你可以考我裡面的內容了。"
                    else:
                        reply = "⚠️ PDF 讀取失敗：無法將內容轉換為知識向量。"
                else:
                    reply = "⚠️ PDF 內容似乎是空的，或無法解析文字。"
                
                # 4. 刪除暫存檔 (節省空間)
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)

            except Exception as e:
                print(f"PDF Error: {e}")
                reply = "❌ 處理 PDF 時發生錯誤，請確認檔案是否正常。"
            
            # 回報結果並結束，不進入一般對話
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        else:
            # 傳了非 PDF 的檔案
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📂 收到檔案，但我目前只支援讀取 PDF 格式的講義喔！"))
            return

    # --- C. 處理文字指令 (清除記憶) ---
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

    # --- D. 準備對話 ---
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = ""
    vision_analysis = ""
    rag_context = "N/A"
    final_response_text = ""
    search_query_for_rag = "" 

    # 讀取短期記憶
    past_history = get_chat_history(user_id)
    try:
        chat_session = client.chats.create(model=CHAT_MODEL, history=past_history, config=generation_config)
    except Exception:
        # 萬一歷史格式壞掉，就開一個新的對話
        chat_session = client.chats.create(model=CHAT_MODEL, history=[], config=generation_config)

    user_question = "" 

    try:
        # --- 情況 1: 收到圖片 ---
        if isinstance(event.message, ImageMessage):
            user_message_type = "image"
            user_content = "Image received" 
            
            # 下載並上傳到 Cloudinary 備份
            msg_content = line_bot_api.get_message_content(event.message.id)
            img_bytes = msg_content.content
            try:
                upload_res = cloudinary.uploader.upload(img_bytes)
                image_url_to_save = upload_res.get('secure_url')
            except:
                image_url_to_save = "upload_failed"

            # 請 AI 看圖
            img = PILImage.open(io.BytesIO(img_bytes))
            vision_prompt = "請客觀描述圖片內容，包含文字、算式、圖表結構。並提取3-5個物理關鍵字。"
            vision_res = client.models.generate_content(model=VISION_MODEL, contents=[img, vision_prompt])
            vision_analysis = vision_res.text
            
            # 將圖片描述變成學生的問題
            user_question = f"圖片內容分析：『{vision_analysis}』。請依據此分析進行教學。"
            search_query_for_rag = vision_analysis # 用圖片內容去搜資料庫

        # --- 情況 2: 收到語音 ---
        elif isinstance(event.message, AudioMessage):
            user_message_type = "audio"
            user_content = "Audio received"
            image_url_to_save = "N/A (Audio)"
            
            msg_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = msg_content.content
            audio_part = types.Part(inline_data=types.Blob(data=audio_bytes, mime_type='audio/m4a'))
            
            # 請 AI 聽音檔
            audio_prompt = "請將這段錄音進行「逐字聽打(繁體中文)」並分析學生的「語氣情感」。"
            
            # 簡單的重試機制 (怕 AI 一時沒聽懂)
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

        # --- 情況 3: 收到文字 ---
        else:
            user_message_type = "text"
            user_text = event.message.text
            user_content = user_text
            user_question = user_text 

            # 過濾掉無意義的廢話 (不用去資料庫搜)
            SKIP_KEYWORDS = {
                "hi", "hello", "你好", "早安", "晚安", "謝謝", "thanks", "ok", "好", "收到", "是", "對", "沒錯"
            }
            clean_input = user_text.strip().lower()
            should_skip = (clean_input in SKIP_KEYWORDS or is_number(clean_input) or (len(clean_input) < 2 and clean_input.isalnum()))
            
            if should_skip:
                search_query_for_rag = "" 
            else:
                search_query_for_rag = user_text

        # --- E. 執行 RAG (知識檢索) ---
        if search_query_for_rag:
            # 去資料庫找有沒有相關講義
            rag_context = find_relevant_chunks(search_query_for_rag)
        else:
            rag_context = "N/A (Skipped)"

        # --- F. 組合最終提示詞 ---
        rag_prompt = f"""
        ---「相關教材段落」開始---
        {rag_context}
        ---「相關教材段落」結束---
        
        學生的目前輸入：「{user_question}」
        請依據 System Prompt 中的指示與上述教材段落進行回應。
        """
        contents_to_send = [rag_prompt]

        # --- G. 發送給 AI 並取得回應 ---
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
        
        # ★ 貼心小尾巴：如果回應很長，就提醒可以清除記憶
        if len(final_response_text) > 50:
            final_response_text += "\n\n(💡 想要問新單元？請輸入「重來」清除記憶)"

        # 回傳給 LINE
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text=final_response_text.replace('\x00', ''))
        )
        
        # 儲存這次對話紀錄到 DB
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"❌ 處理訊息錯誤: {e}")
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生未知錯誤，請稍後再試。"))
        except:
            pass

    # --- H. 寫入研究日誌 (最後一步) ---
    save_to_research_log(
        user_id.replace('\x00', ''), user_message_type, user_content.replace('\x00', ''),
        image_url_to_save, vision_analysis.replace('\x00', ''), 
        rag_context.replace('\x00', ''), final_response_text.replace('\x00', '')
    )

# --- 啟動伺服器 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)