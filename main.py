# ==============================================================================
# JYM 物理 AI 助教 - v4.01 快速修復版
# ==============================================================================
# 修正項目：
# 1. [資料庫] 修正 PostgreSQL 資料型態拼字錯誤 (TIMESTZ -> TIMESTAMPTZ)，解決資料表無法建立的問題。
# ==============================================================================

import os
import io
import json
import datetime
import time
import requests

# --- 引入多執行緒與檔案搜尋工具 ---
import threading
import glob

# --- 網頁框架與 LINE SDK ---
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, AudioMessage, FileMessage, TextSendMessage, FollowEvent

# --- Google AI (Gemini) ---
from google import genai
from google.genai import types

# --- 檔案處理工具 ---
from PIL import Image as PILImage
from pypdf import PdfReader

# --- 資料庫 (PostgreSQL) ---
import psycopg2
from pgvector.psycopg2 import register_vector
import cloudinary
import cloudinary.uploader

# --- Google 試算表 ---
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

try:
    client = genai.Client()
    print("✅ Gemini Client 連線成功")
except Exception as e:
    print(f"❌ Gemini 連線失敗: {e}")
    client = None

try:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    print("✅ Cloudinary 連線成功")
except Exception as e:
    print(f"❌ Cloudinary 連線失敗: {e}")

try:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive.file']
    CREDS = Credentials.from_service_account_file('service_account.json', scopes=SCOPES)
    gc = gspread.authorize(CREDS)
    SPREADSHEET_KEY = "1Evd8WACx_uDUl04c5x2jADFxgLl1A3jW2z0_RynTmhU" 
    sh = gc.open_by_key(SPREADSHEET_KEY)
    worksheet = sh.get_worksheet(0)
    print("✅ Google Sheets 連線成功")
except Exception as e:
    print(f"⚠️ Google Sheets 連線失敗: {e}")
    worksheet = None

# ==========================================
# 3. 模型設定
# ==========================================
CHAT_MODEL = 'gemini-2.5-flash'
VISION_MODEL = 'gemini-2.5-flash-image'
AUDIO_MODEL = 'gemini-2.5-flash'
EMBEDDING_MODEL = 'models/text-embedding-004'
VECTOR_DIMENSION = 768
MAX_HISTORY_LENGTH = 20 

system_prompt = """
你是由頂尖大學物理系博士開發的「JYM物理AI助教」，你是台灣高中物理教育的權威。
### 核心指令
1. **蘇格拉底式教學**：絕對禁止直接給出答案，必須透過提問引導學生思考。
2. **語言**：使用自然的繁體中文 (台灣用語)。
3. **引用權威**：若 context 中有教材內容 (標註為 [來源: xxx])，請務必參考，並在回答中融合該觀念。
### 格式規範
1. 禁止 LaTeX，請用 Unicode 符號 (如 v², θ)。
2. 適當分段，適合手機閱讀。
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
# 4. 核心函式庫
# ==========================================

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ 資料庫連線失敗: {e}")
        return None

def initialize_database():
    """系統啟動時初始化資料表"""
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()
            register_vector(conn)
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT PRIMARY KEY, history JSONB);")
                cur.execute(f"CREATE TABLE IF NOT EXISTS physics_vectors (id SERIAL PRIMARY KEY, content TEXT, embedding VECTOR({VECTOR_DIMENSION}));")
                
                # ★ 修正：TIMESTZ -> TIMESTAMPTZ
                cur.execute("CREATE TABLE IF NOT EXISTS imported_files (filename TEXT PRIMARY KEY, imported_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP);")
                
                # ★ 修正：TIMESTZ -> TIMESTAMPTZ
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_log (
                        id SERIAL PRIMARY KEY, timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, 
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
                print("✅ 資料庫 v4.01 架構初始化完成")
        except Exception as e:
            print(f"❌ 資料庫初始化錯誤: {e}")
        finally:
            conn.close()

def save_pdf_content(pdf_text, source_name="unknown"):
    if not pdf_text or not client: return False
    
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
            if len(chunk.strip()) < 50: continue
            
            content_with_source = f"[來源: {source_name}] {chunk}"
            
            res = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=[content_with_source.replace('\x00', '')]
            )
            vector = res.embeddings[0].values
            
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                    (content_with_source, vector)
                )
            count += 1
            time.sleep(0.3)
            
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO imported_files (filename) VALUES (%s) ON CONFLICT (filename) DO UPDATE SET imported_at = CURRENT_TIMESTAMP",
                (source_name,)
            )
        
        conn.commit()
        print(f"✅ 成功儲存 {count} 個片段 (來自 {source_name})")
        return count
    except Exception as e:
        print(f"❌ PDF 儲存失敗: {e}")
        return False
    finally:
        conn.close()

def auto_import_corpus_v4():
    time.sleep(3)
    print("🔍 [v4.0 智慧同步] 開始檢查 corpus 資料夾...")
    
    conn = get_db_connection()
    if not conn:
        print("❌ 無法連線資料庫，跳過同步")
        return

    try:
        processed_files = set()
        # 因為上面的 initialize_database 會先執行，所以這裡現在應該能找到表了
        with conn.cursor() as cur:
            cur.execute("SELECT filename FROM imported_files")
            rows = cur.fetchall()
            for row in rows:
                processed_files.add(row[0])
        
        print(f"📚 資料庫目前已收錄 {len(processed_files)} 本書。")

        pdf_files = glob.glob("corpus/*.pdf")
        if not pdf_files:
            print("⚠️ corpus 資料夾是空的")
            return

        new_files_count = 0
        for pdf_path in pdf_files:
            file_name = os.path.basename(pdf_path)
            if file_name in processed_files:
                continue
            
            print(f"🚀 發現新教材：{file_name}，開始吸收...")
            try:
                reader = PdfReader(pdf_path)
                text_content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
                
                if text_content.strip():
                    save_pdf_content(text_content, source_name=file_name)
                    new_files_count += 1
                else:
                    print(f"⚠️ {file_name} 內容為空")
            except Exception as e:
                print(f"❌ 讀取 {file_name} 失敗: {e}")
        
        if new_files_count == 0:
            print("✅ 所有教材都已是最新的，無需更新。")
        else:
            print(f"🎉 更新完成！共吸收了 {new_files_count} 本新講義。")
            
    except Exception as e:
        print(f"❌ 自動匯入過程發生錯誤: {e}")
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

# --- 歷史紀錄 & Log ---
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
        except Exception as e: pass
        finally: conn.close()
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
        except Exception as e: pass
        finally: conn.close()

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
        except Exception as e: pass
        finally: conn.close()
    if worksheet:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            row_data = [now_utc, user_id, msg_type, content, img_url, analysis, rag_ctx, response]
            worksheet.append_row(row_data)
        except: pass

def send_loading_animation(user_id):
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    data = {"chatId": user_id, "loadingSeconds": 20}
    try: requests.post(url, headers=headers, json=data, timeout=5)
    except: pass

# --- 啟動程序 ---
initialize_database()
threading.Thread(target=auto_import_corpus_v4, daemon=True).start()

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="👨‍🏫 您好，我是 JYM 物理 AI 教授 (v4.01)。\n我已具備「增量學習」能力，會自動消化您上傳的新講義。\n請隨時向我提問！")
    )

@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage, FileMessage))
def handle_message(event):
    user_id = event.source.user_id
    send_loading_animation(user_id)

    # --- Admin Commands ---
    if isinstance(event.message, TextMessage):
        user_text = event.message.text.strip()
        if user_text == "!status":
            conn = get_db_connection()
            status_msg = "📊 助教工作報告：\n"
            if conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM physics_vectors")
                    vec_count = cur.fetchone()[0]
                    cur.execute("SELECT filename FROM imported_files")
                    files = cur.fetchall()
                conn.close()
                file_list = "\n".join([f"- {row[0]}" for row in files])
                status_msg += f"🧠 知識庫片段數：{vec_count}\n📚 已吸收書單：\n{file_list}"
            else:
                status_msg += "❌ 資料庫連線失敗"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=status_msg))
            return

        if user_text == "!sync":
            threading.Thread(target=auto_import_corpus_v4, daemon=True).start()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🚀 收到指令！正在背景強制掃描新講義..."))
            return

        if user_text == "!clear":
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("TRUNCATE TABLE chat_history")
                    cur.execute("TRUNCATE TABLE physics_vectors")
                    cur.execute("TRUNCATE TABLE imported_files")
                    conn.commit()
                conn.close()
                line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 已執行：大腦完全格式化。所有知識與記憶已清空。"))
            return

        if user_text.lower() in ["重來", "清除", "reset"]:
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
                    conn.commit()
                conn.close()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧹 記憶已清除，我們可以重新開始了。"))
            return 

    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = ""
    vision_analysis = ""
    search_query_for_rag = "" 
    
    past_history = get_chat_history(user_id)
    try:
        chat_session = client.chats.create(model=CHAT_MODEL, history=past_history, config=generation_config)
    except:
        chat_session = client.chats.create(model=CHAT_MODEL, history=[], config=generation_config)

    user_question = ""

    try:
        if isinstance(event.message, ImageMessage):
            user_message_type = "image"
            msg_content = line_bot_api.get_message_content(event.message.id)
            img_bytes = msg_content.content
            try:
                upload_res = cloudinary.uploader.upload(img_bytes)
                image_url_to_save = upload_res.get('secure_url')
            except:
                image_url_to_save = "upload_failed"
            img = PILImage.open(io.BytesIO(img_bytes))
            vision_res = client.models.generate_content(model=VISION_MODEL, contents=[img, "描述圖片並提取物理關鍵字"])
            vision_analysis = vision_res.text
            user_question = f"圖片分析：{vision_analysis}。請教學。"
            search_query_for_rag = vision_analysis

        elif isinstance(event.message, AudioMessage):
            user_message_type = "audio"
            msg_content = line_bot_api.get_message_content(event.message.id)
            audio_bytes = msg_content.content
            audio_part = types.Part(inline_data=types.Blob(data=audio_bytes, mime_type='audio/m4a'))
            try:
                speech_res = client.models.generate_content(model=AUDIO_MODEL, contents=[audio_part, "逐字稿與語氣分析"])
                vision_analysis = speech_res.text
            except:
                vision_analysis = "語音辨識失敗"
            user_question = f"語音內容：{vision_analysis}。請教學。"
            search_query_for_rag = vision_analysis

        else:
            user_message_type = "text"
            user_text = event.message.text
            user_content = user_text
            user_question = user_text
            if len(user_text) > 2:
                search_query_for_rag = user_text

        if search_query_for_rag:
            rag_context = find_relevant_chunks(search_query_for_rag)
        else:
            rag_context = "N/A"

        rag_prompt = f"參考教材：\n{rag_context}\n\n學生問題：{user_question}\n請依System Prompt回應，若有使用教材請標註來源。"
        response = chat_session.send_message([rag_prompt])
        final_response_text = response.text 

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_response_text))
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"Error: {e}")
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 系統繁忙中，請稍後再試"))
        except: pass

    save_to_research_log(user_id, user_message_type, user_content, image_url_to_save, vision_analysis, rag_context, final_response_text)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)