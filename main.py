import os
import json
import datetime
import psycopg2
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Google GenAI (PS5 SDK)
from google import genai
from google.genai import types
from pgvector.psycopg2 import register_vector

from io import BytesIO
from PIL import Image

# -----------------------------
# Step 1: Read env vars (Render)
# -----------------------------
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
DATABASE_URL = os.environ.get('DATABASE_URL')
# GEMINI_API_KEY will be picked up automatically by genai.Client()

CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# -----------------------------
# Step 2: Flask/LINE bot wiring
# -----------------------------
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# -----------------------------
# Step 3: GenAI client (PS5)
# -----------------------------
try:
    client = genai.Client()
    print('--- (Gemini) ★ PS5 SDK (google-genai) 連接成功！ ★ ---')
except Exception as e:
    print(f'!!! 嚴重錯誤：無法設定 Google API Key (GEMINI_API_KEY)。錯誤：{e}')
    client = None

# -----------------------------
# Step 4: Cloudinary
# -----------------------------
try:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
    )
    print('--- (Cloudinary) 永恆檔案館連接成功！ ---')
except Exception as e:
    print(f'!!! 嚴重錯誤：無法連接到 Cloudinary。錯誤：{e}')

# -----------------------------
# Step 5: Models / constants
# -----------------------------
CHAT_MODEL = 'gemini-2.5-pro'
VISION_MODEL = 'gemini-2.5-flash-image'
EMBEDDING_MODEL = 'text-embedding-004'
VECTOR_DIMENSION = 768

generation_config = types.GenerateContentConfig(
    temperature=0.6,
    top_p=0.9,
    max_output_tokens=1024,
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
    ],
)

# -----------------------------
# Step 6: DB helpers
# -----------------------------
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f'!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}')
        return None

def initialize_database():
    conn = get_db_connection()
    if not conn:
        return
    try:
        register_vector(conn)
        print('--- (SQL) `register_vector` 成功 ---')
        with conn.cursor() as cur:
            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS chat_history (
                    user_id TEXT PRIMARY KEY,
                    history JSONB
                );
                '''
            )
            print('--- (SQL) 表格 `chat_history` 確認/建立成功 ---')

            cur.execute(
                f'''
                CREATE TABLE IF NOT EXISTS physics_vectors (
                    id SERIAL PRIMARY KEY,
                    content TEXT,
                    embedding VECTOR({{}})
                );
                '''.format(VECTOR_DIMENSION)
            )
            print(f'--- (SQL) 表格 `physics_vectors` (維度 {VECTOR_DIMENSION}) 確認/建立成功 ---')

            cur.execute(
                '''
                CREATE TABLE IF NOT EXISTS research_log (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    user_id TEXT,
                    user_message_type TEXT,
                    user_content TEXT,
                    image_url TEXT,
                    vision_analysis TEXT,
                    rag_context TEXT,
                    ai_response TEXT
                );
                '''
            )
            print('--- (SQL) 表格 `research_log` (含 image_url) 確認/建立成功 ---')

            conn.commit()
    except Exception as e:
        print(f'!!! 錯誤：無法初始化資料庫表格。錯誤：{e}')
    finally:
        conn.close()

# -----------------------------
# Step 7: chat memory helpers
# -----------------------------
def get_chat_history(user_id: str):
    conn = get_db_connection()
    history_list = []
    if not conn:
        return history_list
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT history FROM chat_history WHERE user_id = %s;', (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                for item in row[0]:
                    role = item.get('role', 'user')
                    parts_text = item.get('parts', [])
                    if role in ('user', 'model'):
                        history_list.append(
                            types.Content(
                                role=role,
                                parts=[types.Part.from_text(text=t) for t in parts_text],
                            )
                        )
    except Exception as e:
        print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
    finally:
        conn.close()
    return history_list

def save_chat_history(user_id: str, chat_session):
    conn = get_db_connection()
    if not conn:
        return
    try:
        history_to_save = []
        history = chat_session.get_history()
        if history:
            for msg in history:
                if msg.role in ('user', 'model'):
                    parts_text = [p.text for p in msg.parts if hasattr(p, 'text')]
                    history_to_save.append({'role': msg.role, 'parts': parts_text})
        with conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO chat_history (user_id, history)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                ''',
                (user_id, json.dumps(history_to_save)),
            )
            conn.commit()
    except Exception as e:
        print(f"!!! 錯誤：無法儲存 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
    finally:
        conn.close()

# -----------------------------
# Step 8: RAG retrieval (FIXED)
# -----------------------------
def find_relevant_chunks(query_text: str, k: int = 3):
    """Return top-k textbook chunks using pgvector ANN search."""
    if not client:
        return 'N/A'
    conn = None
    try:
        print(f'--- (RAG) 正在為問題「{query_text[:20]}...」向 Gemini 請求向量... ---')
        emb_resp = client.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[query_text],
        )
        query_embedding = emb_resp.embeddings[0].values

        print('--- (RAG) 正在連接資料庫以搜尋向量... ---')
        conn = get_db_connection()
        if not conn:
            return 'N/A'
        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                'SELECT content FROM physics_vectors ORDER BY embedding <-> %s::vector LIMIT %s',
                (query_embedding, k),
            )
            rows = cur.fetchall()

        if not rows:
            print('--- (RAG) 警告：在資料庫中找不到相關段落。 ---')
            return 'N/A'

        context = "\n\n---\n\n".join([r[0] for r in rows])
        print(f'--- (RAG) 成功找到 {len(rows)} 個相關段落！ ---')
        return context
    except Exception as e:
        print(f'!!! (RAG) 嚴重錯誤：在 `find_relevant_chunks` 中失敗。錯誤：{e}')
        return 'N/A'
    finally:
        if conn:
            conn.close()

# -----------------------------
# Step 9: Research log
# -----------------------------
def save_to_research_log(user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response):
    conn = get_db_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                '''
                INSERT INTO research_log
                (user_id, user_message_type, user_content, image_url, vision_analysis, rag_context, ai_response)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                ''',
                (user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response),
            )
            conn.commit()
            print('--- (研究日誌) 儲存成功 ---')
    except Exception as e:
        print(f'!!! 錯誤：無法儲存「研究日誌」。錯誤：{e}')
    finally:
        conn.close()

initialize_database()

@app.route('/callback', methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except Exception:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    user_id = event.source.user_id

    if not client:
        print('!!! 嚴重錯誤：Gemini Client 未初始化！')
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text='抱歉，宗師目前金鑰遺失，請檢查環境變數 GEMINI_API_KEY。'),
        )
        return

    user_message_type = 'unknown'
    user_content = ''
    image_url_to_save = ''
    vision_analysis = ''
    rag_context = ''
    final_text = ''

    past_history = get_chat_history(user_id)

    try:
        chat_session = client.chats.create(
            model=CHAT_MODEL,
            history=past_history,
            config=generation_config,
        )
    except Exception as start_chat_e:
        print(f'!!! 錯誤：無法開啟聊天：{start_chat_e}')
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text='抱歉，宗師暫時繁忙中。'))
        return

    if isinstance(event.message, TextMessage):
        user_message_type = 'text'
        user_content = event.message.text.strip()
        rag_context = find_relevant_chunks(user_content, k=3)

        prompt = f"""
你是物理教師助手。請根據下列「教材知識庫」補充解答（若為 N/A 則直接回覆）：
[教材知識庫]
{rag_context}

[學生提問]
{user_content}
""".strip()

        try:
            response = chat_session.send_message(prompt)
            final_text = response.text
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=final_text))
        except Exception as chat_e:
            print(f'!!! 錯誤：Gemini 回覆失敗：{chat_e}')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='抱歉，我卡住了，稍後再試！'))
            return

    elif isinstance(event.message, ImageMessage):
        user_message_type = 'image'
        try:
            message_content = line_bot_api.get_message_content(event.message.id)
            img_bytes = message_content.content

            upload_result = cloudinary.uploader.upload(
                img_bytes,
                folder='line-uploads',
                resource_type='image',
            )
            image_url_to_save = upload_result.get('secure_url', '')

            try:
                mime = Image.open(BytesIO(img_bytes)).get_format_mimetype() or 'image/jpeg'
            except Exception:
                mime = 'image/jpeg'

            vision_resp = client.models.generate_content(
                model=VISION_MODEL,
                contents=[
                    '請用中文條列說明這張照片的重點（最多 6 點）。',
                    types.Part.from_bytes(data=img_bytes, mime_type=mime),
                ],
            )
            vision_analysis = vision_resp.text
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=vision_analysis))
        except Exception as img_e:
            print(f'!!! 錯誤：影像處理失敗：{img_e}')
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text='影像辨識目前無法使用。'))

    try:
        save_chat_history(user_id, chat_session)
        save_to_research_log(
            user_id=user_id,
            user_msg_type=user_message_type,
            user_content=user_content,
            image_url=image_url_to_save,
            vision_analysis=vision_analysis,
            rag_context=rag_context,
            ai_response=final_text or vision_analysis,
        )
    except Exception as save_e:
        print(f'!!! 錯誤：寫入歷史/研究日誌失敗：{save_e}')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
