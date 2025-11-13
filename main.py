# ==============================================================================
# JYM 物理 AI 助教 - v3.4 自動讀檔進階版 (含詳細註解)
# ==============================================================================
# 版本特色：
# 1. [自動化] 啟動時自動掃描 corpus 資料夾，若資料庫是空的，就自動讀取所有 PDF。
# 2. [防呆] 自動偵測資料庫狀態，避免重複讀取導致資料重複。
# 3. [背景執行] 使用多執行緒 (Threading) 技術，讀檔過程在背景運作，不會導致 Render 啟動超時。
# ==============================================================================

import os
import io
import json
import datetime
import time
import requests

# --- 引入多執行緒與檔案搜尋工具 (v3.4 新增) ---
import threading  # 讓程式可以「一心二用」，一邊服務學生，一邊在後台讀書
import glob       # 用來搜尋資料夾裡的所有 PDF 檔案

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
from pypdf import PdfReader        # 讀取 PDF 講義用

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

# 連線 Gemini
try:
    client = genai.Client()
    print("✅ Gemini Client 連線成功")
except Exception as e:
    print(f"❌ Gemini 連線失敗: {e}")
    client = None

# 連線 Cloudinary
try:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET
    )
    print("✅ Cloudinary 連線成功")
except Exception as e:
    print(f"❌ Cloudinary 連線失敗: {e}")

# 連線 Google Sheets
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
VISION_MODEL = 'gemini-2.5-flash'
AUDIO_MODEL = 'gemini-2.5-flash'
EMBEDDING_MODEL = 'models/text-embedding-004'
VECTOR_DIMENSION = 768
MAX_HISTORY_LENGTH = 20 

# System Prompt
system_prompt = """
你是由頂尖大學物理系博士開發的「JYM物理AI助教」，你是台灣高中物理教育的權威。
### 核心指令
1. **蘇格拉底式教學**：絕對禁止直接給出答案，必須透過提問引導學生思考。
2. **語言**：使用自然的繁體中文 (台灣用語)。
3. **知識庫運用**：若提供的 context 中有相關物理觀念，請優先使用。
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
                # 啟用向量功能
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                conn.commit()
            register_vector(conn)
            with conn.cursor() as cur:
                # 建立資料表 (對話紀錄、向量知識庫、研究日誌)
                cur.execute("CREATE TABLE IF NOT EXISTS chat_history (user_id TEXT PRIMARY KEY, history JSONB);")
                cur.execute(f"CREATE TABLE IF NOT EXISTS physics_vectors (id SERIAL PRIMARY KEY, content TEXT, embedding VECTOR({VECTOR_DIMENSION}));")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS research_log (
                        id SERIAL PRIMARY KEY, timestamp TIMESTZ DEFAULT CURRENT_TIMESTAMP, 
                        user_id TEXT, user_message_type TEXT, user_content TEXT, 
                        image_url TEXT, vision_analysis TEXT, rag_context TEXT, ai_response TEXT
                    );""")
                # 補丁：確保 image_url 欄位存在
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

def save_pdf_content(pdf_text, source_name="unknown"):
    """將 PDF 文字切塊並存入向量資料庫"""
    if not pdf_text or not client: return False
    
    # 切塊設定 (每 1000 字一塊)
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
            
            # 在內容前加上來源標記 (例如 [來源: 選修物理.pdf])
            content_with_source = f"[來源: {source_name}] {chunk}"
            
            # 轉成向量
            res = client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=[content_with_source.replace('\x00', '')]
            )
            vector = res.embeddings[0].values
            
            # 寫入 DB
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                    (content_with_source, vector)
                )
            count += 1
            # 稍微休息 0.5 秒，避免同時塞太多請求給 Google
            time.sleep(0.5)
            
        conn.commit()
        print(f"✅ 成功儲存 {count} 個片段 (來自 {source_name})")
        return count
    except Exception as e:
        print(f"❌ PDF 儲存失敗: {e}")
        return False
    finally:
        conn.close()

# --- ★ v3.4 核心功能：自動匯入 Corpus 的背景小精靈 ---
def auto_import_corpus():
    """
    背景檢查：
    1. 檢查資料庫是不是空的？
    2. 如果是空的，就把 corpus 資料夾裡的所有 PDF 讀進去。
    3. 如果已經有資料，就跳過 (避免重複)。
    """
    # 先睡 5 秒，確保資料庫連線已經建立好
    time.sleep(5)
    print("🔍 [背景任務] 開始檢查是否需要自動匯入 corpus...")
    
    conn = get_db_connection()
    if not conn:
        print("❌ [背景任務] 無法連線資料庫，跳過自動匯入")
        return

    try:
        with conn.cursor() as cur:
            # 查詢目前資料庫有幾筆資料
            cur.execute("SELECT COUNT(*) FROM physics_vectors")
            count = cur.fetchone()[0]
        
        # 防呆機制：如果已經有資料，就不讀了
        if count > 0:
            print(f"✅ 資料庫已有 {count} 筆資料，跳過自動匯入 (避免重複)。")
            return
        
        print("🚀 資料庫為空，開始讀取 corpus 資料夾...")
        
        # 搜尋 corpus 資料夾下的所有 .pdf
        pdf_files = glob.glob("corpus/*.pdf")
        
        if not pdf_files:
            print("⚠️ corpus 資料夾內找不到 .pdf 檔案")
            return
            
        # 開始一本一本讀
        for pdf_path in pdf_files:
            file_name = os.path.basename(pdf_path)
            print(f"📖 正在讀取：{file_name} ...")
            try:
                reader = PdfReader(pdf_path)
                text_content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
                
                if text_content.strip():
                    save_pdf_content(text_content, source_name=file_name)
                else:
                    print(f"⚠️ {file_name} 內容為空")
                    
            except Exception as e:
                print(f"❌ 讀取 {file_name} 失敗: {e}")
        
        print("🎉 [背景任務] 所有 corpus 檔案匯入完成！")
        
    except Exception as e:
        print(f"❌ 自動匯入過程發生錯誤: {e}")
    finally:
        conn.close()

def find_relevant_chunks(query_text, k=3):
    """RAG 檢索功能"""
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

def get_chat_history(user_id):
    """讀取歷史紀錄"""
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
    """儲存歷史紀錄"""
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

def save_to_research_log(user_id, msg_type, content, img_url, analysis, rag_ctx, response):
    """寫入研究日誌"""
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

def send_loading_animation(user_id):
    """發送 LINE Loading 動畫"""
    url = "https://api.line.me/v2/bot/chat/loading/start"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"}
    data = {"chatId": user_id, "loadingSeconds": 20}
    try:
        requests.post(url, headers=headers, json=data, timeout=5)
    except:
        pass

# 初始化資料庫
initialize_database()

# ★ 啟動背景小精靈！ (Daemon=True 代表如果主程式關閉，這個執行緒也會自動關閉)
threading.Thread(target=auto_import_corpus, daemon=True).start()

# ==========================================
# 5. Webhook & 訊息處理
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

# --- FollowEvent (歡迎訊息) ---
@handler.add(FollowEvent)
def handle_follow(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="🎉 歡迎！JYM 物理 AI 助教已就緒。\n\n(後台正在努力消化講義中，如果剛開始回答不夠精準，請稍等幾分鐘喔！)")
    )

# --- MessageEvent (主要對話) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage, AudioMessage, FileMessage))
def handle_message(event):
    user_id = event.source.user_id
    send_loading_animation(user_id)

    if not client:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="系統維護中"))
        return
    
    # 保留「手動上傳 PDF」功能 (作為備用)
    if isinstance(event.message, FileMessage):
        if event.message.file_name.lower().endswith('.pdf'):
            msg_content = line_bot_api.get_message_content(event.message.id)
            temp_pdf_path = f"/tmp/{event.message.id}.pdf"
            try:
                with open(temp_pdf_path, 'wb') as fd:
                    for chunk in msg_content.iter_content():
                        fd.write(chunk)
                reader = PdfReader(temp_pdf_path)
                text_content = ""
                for page in reader.pages:
                    extracted = page.extract_text()
                    if extracted:
                        text_content += extracted + "\n"
                if text_content.strip():
                    chunks_count = save_pdf_content(text_content, source_name=event.message.file_name)
                    reply = f"✅ 手動補充教材：{event.message.file_name}\n📚 已吸收 {chunks_count} 個知識片段！"
                else:
                    reply = "⚠️ PDF 無法解析文字"
                if os.path.exists(temp_pdf_path):
                    os.remove(temp_pdf_path)
            except Exception as e:
                reply = "❌ 處理錯誤"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
            return
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="📂 只支援 PDF 喔"))
            return

    # 清除記憶功能
    if isinstance(event.message, TextMessage):
        if event.message.text.strip().lower() in ["重來", "清除", "reset"]:
            conn = get_db_connection()
            if conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
                    conn.commit()
                conn.close()
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="🧹 記憶已清除"))
            return 

    # 標準對話流程
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
        # 處理圖片
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

        # 處理語音
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

        # 處理文字
        else:
            user_message_type = "text"
            user_text = event.message.text
            user_content = user_text
            user_question = user_text
            if len(user_text) > 2:
                search_query_for_rag = user_text

        # 執行 RAG
        if search_query_for_rag:
            rag_context = find_relevant_chunks(search_query_for_rag)
        else:
            rag_context = "N/A"

        rag_prompt = f"參考教材：\n{rag_context}\n\n學生問題：{user_question}\n請依System Prompt回應。"
        response = chat_session.send_message([rag_prompt])
        final_response_text = response.text 

        # 自動小尾巴
        if len(final_response_text) > 50:
            final_response_text += "\n\n(💡 輸入「重來」可清除記憶)"

        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_response_text))
        save_chat_history(user_id, chat_session)

    except Exception as e:
        print(f"Error: {e}")
        try:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="發生錯誤"))
        except: pass

    # 寫入 Log
    save_to_research_log(user_id, user_message_type, user_content, image_url_to_save, vision_analysis, rag_context, final_response_text)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)