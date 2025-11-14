import os
import logging
import time
import threading
import json
import tempfile
from datetime import datetime

# --- 1. 基礎框架 (Flask & Line Bot) ---
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest,
    TextMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    ImageMessageContent,
    AudioMessageContent
)

# --- 2. AI 大腦 (使用最新的 google-genai SDK) ---
from google import genai
from google.genai import types

# --- 3. 原始功能回歸 (Google Sheets) ---
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 4. 進階功能疊加 (PDF 處理 & PostgreSQL 資料庫) ---
from pypdf import PdfReader
import psycopg2
from psycopg2.extras import Json

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==========================================
# 配置區 (從 Render 環境變數讀取)
# ==========================================
CHANNEL_ACCESS_TOKEN = os.environ.get('CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.environ.get('CHANNEL_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# 初始化設定
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# [更新] 初始化 Google GenAI Client
gemini_client = genai.Client(api_key=GOOGLE_API_KEY)

# ==========================================
# [安全性升級] Google Sheets 連線
# ==========================================
def init_google_sheet():
    """連線 Google Sheet (優先尋找 Secret Files)"""
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        key_path = "/etc/secrets/service_account.json"
        if not os.path.exists(key_path):
            key_path = "service_account.json"
        if not os.path.exists(key_path):
            key_path = "credentials.json"

        if not os.path.exists(key_path):
            print("⚠️ 找不到金鑰檔案，Google Sheet 功能暫停。")
            return None

        creds = ServiceAccountCredentials.from_json_keyfile_name(key_path, scope)
        client = gspread.authorize(creds)
        sheet = client.open("Research_Log").sheet1 
        print(f"✅ Google Sheet 連線成功 (使用金鑰: {key_path})")
        return sheet
    except Exception as e:
        print(f"⚠️ Google Sheet 連線錯誤: {e}")
        return None

google_sheet = init_google_sheet()

# ==========================================
# [進階核心] PostgreSQL 資料庫
# ==========================================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def initialize_database():
    """初始化資料庫結構"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS teaching_materials (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                embedding vector(768),
                filename TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS imported_files (
                id SERIAL PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                imported_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                user_id TEXT,
                user_name TEXT,
                message_type TEXT,
                input_content TEXT,
                output_content TEXT,
                timestamp TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        conn.commit()
        print("✅ 資料庫結構檢查完成")
    except Exception as e:
        print(f"❌ 資料庫初始化失敗: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# ==========================================
# [自動學習] 背景讀書系統 (RAG) - SDK 更新版
# ==========================================
def extract_text_from_pdf(pdf_stream):
    try:
        reader = PdfReader(pdf_stream)
        text = ""
        for page in reader.pages:
            p_text = page.extract_text()
            if p_text: text += p_text
        return text.replace('\x00', '')
    except Exception as e:
        print(f"❌ PDF 解析失敗: {e}")
        return ""

def get_embedding(text):
    """取得向量 (使用新版 SDK)"""
    for _ in range(3):
        try:
            # [更新] 新版 Embedding 語法
            response = gemini_client.models.embed_content(
                model="text-embedding-004",
                contents=text
            )
            # 新版回傳的是物件，需取出 values
            return response.embeddings[0].values
        except Exception as e:
            print(f"Embedding 錯誤: {e}")
            time.sleep(1)
    return None

def background_learning_task():
    """持續監控 materials 資料夾"""
    with app.app_context():
        materials_dir = "materials"
        if not os.path.exists(materials_dir):
            os.makedirs(materials_dir)

        while True:
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                try:
                    cur.execute("SELECT filename FROM imported_files")
                    imported = {row[0] for row in cur.fetchall()}
                except:
                    conn.rollback()
                    time.sleep(10)
                    continue

                for f_name in os.listdir(materials_dir):
                    if f_name.endswith(".pdf") and f_name not in imported:
                        print(f"📚 正在研讀新教材：{f_name}...")
                        path = os.path.join(materials_dir, f_name)
                        
                        with open(path, 'rb') as f:
                            text = extract_text_from_pdf(f)
                        
                        if not text.strip(): continue
                        
                        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
                        for chunk in chunks:
                            vec = get_embedding(chunk)
                            if vec:
                                cur.execute(
                                    "INSERT INTO teaching_materials (content, embedding, filename) VALUES (%s, %s, %s)",
                                    (chunk, vec, f_name)
                                )
                                time.sleep(0.5)
                        
                        cur.execute("INSERT INTO imported_files (filename) VALUES (%s)", (f_name,))
                        conn.commit()
                        print(f"✅ {f_name} 研讀完畢！")
                
                cur.close()
                conn.close()
            except Exception as e:
                print(f"⚠️ 背景學習任務異常: {e}")
            
            time.sleep(60)

threading.Thread(target=background_learning_task, daemon=True).start()

# ==========================================
# [商業核心] 雙重紀錄系統
# ==========================================
def log_interaction(user_id, user_name, m_type, input_text, output_text):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if google_sheet:
        try:
            google_sheet.append_row([timestamp, user_id, user_name, m_type, input_text, output_text])
        except Exception as e:
            print(f"❌ Sheet 寫入失敗: {e}")

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO system_logs (user_id, user_name, message_type, input_content, output_content)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, user_name, m_type, input_text, output_text))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ DB Log 寫入失敗: {e}")

# ==========================================
# [邏輯核心] 對話處理 (SDK 更新版)
# ==========================================
def search_knowledge_base(query, top_k=3):
    vec = get_embedding(query)
    if not vec: return ""
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT content, filename FROM teaching_materials
        ORDER BY embedding <=> %s::vector LIMIT %s;
    """, (vec, top_k))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    if not rows: return ""
    return "\n\n".join([f"【參考資料:{r[1]}】\n{r[0]}" for r in rows])

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=(TextMessageContent, ImageMessageContent, AudioMessageContent))
def handle_message(event):
    user_id = event.source.user_id
    
    user_name = "Unknown"
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            profile = line_bot_api.get_profile(user_id)
            user_name = profile.display_name
    except: pass

    m_type = event.message.type
    final_response = "（思考中...）"
    user_log_content = ""

    try:
        # A. 文字處理 (使用新版 generate_content)
        if m_type == 'text':
            text = event.message.text
            user_log_content = text
            
            if text == "!status":
                sheet_status = "✅ 連線中" if google_sheet else "❌ 未連線"
                final_response = f"📊 系統狀態報告 (v2.0 GenAI)\nGoogle Sheet: {sheet_status}\n資料庫: 正常\nSDK: google-genai\n\n我是你的全能物理助教！"
            else:
                knowledge_context = search_knowledge_base(text)
                prompt = f"""
                你是一位專業物理助教。
                請參考以下資料庫中的教材回答問題 (若有相關內容)：
                {knowledge_context}
                
                學生問題：{text}
                """
                
                # [更新] 新版生成語法
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=prompt
                )
                final_response = response.text

        # B. 圖片處理 (使用新版 Bytes 處理)
        elif m_type == 'image':
            user_log_content = "(傳送圖片)"
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                msg_content = line_bot_api.get_message_content(event.message.id)
                img_data = msg_content.read()
                
                # [更新] 直接將 bytes 封裝成 Part 物件
                image_part = types.Part.from_bytes(data=img_data, mime_type="image/jpeg")
                
                response = gemini_client.models.generate_content(
                    model='gemini-2.5-flash-image',
                    contents=["這是一題物理題目，請幫我詳細解題：", image_part]
                )
                final_response = response.text

        # C. 語音處理 (使用新版 File Upload)
        elif m_type == 'audio':
            user_log_content = "(傳送語音)"
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                msg_content = line_bot_api.get_message_content(event.message.id)
                
                with tempfile.NamedTemporaryFile(suffix='.m4a', delete=False) as temp_file:
                    for chunk in msg_content.iter_content():
                        temp_file.write(chunk)
                    temp_path = temp_file.name

                try:
                    # [更新] 新版檔案上傳與生成
                    uploaded_file = gemini_client.files.upload(path=temp_path)
                    
                    # 等待處理完成 (新版狀態檢查)
                    while uploaded_file.state.name == "PROCESSING":
                        time.sleep(1)
                        uploaded_file = gemini_client.files.get(name=uploaded_file.name)

                    response = gemini_client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=["請回答這段語音的問題：", uploaded_file]
                    )
                    final_response = response.text
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

        # 回覆 User
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=final_response)]
                )
            )

    except Exception as e:
        logger.error(f"處理錯誤: {e}")
        final_response = "抱歉，系統目前忙碌中，請稍後再試。"
        try:
            with ApiClient(configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=final_response)]
                    )
                )
        except: pass

    log_interaction(user_id, user_name, m_type, user_log_content, final_response)

initialize_database()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)