# --- 「神殿」：AI 宗師的核心 (第八紀元：永恆檔案館版) ---
#
# 版本：Neon 記憶 + 雙重專家 (視覺+對話) + 完整修正
# 新功能：植入「Cloudinary」，儲存「原始圖片 URL」到「research_log」
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, content_types
from PIL import Image
import io
import psycopg2 # 藍圖三：資料庫工具
import json     # 藍圖三：資料庫工具
import datetime # ★ 第七紀元：需要時間戳

# --- ★ 第八紀元：永恆檔案館工具 ★ ---
import cloudinary
import cloudinary.uploader
import cloudinary.api

# --- ★ 第五紀元：向量 RAG 工具 ★ ---
from pgvector.psycopg2 import register_vector

# --- 步驟一：神殿的鑰匙 (從 Render.com 讀取) ---
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
DATABASE_URL = os.environ.get('DATABASE_URL')

# ★ 第八紀元：檔案館金鑰 ★
CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET')

# --- 步驟二：神殿的基礎建設 ---
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 步驟三：連接「神之鍛造廠」(Gemini) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    print(f"!!! 嚴重錯誤：無法設定 Google API Key。錯誤：{e}")

# --- ★ 第八紀元：連接「永恆檔案館」(Cloudinary) ★ ---
try:
    cloudinary.config( 
        cloud_name = CLOUDINARY_CLOUD_NAME, 
        api_key = CLOUDINARY_API_KEY, 
        api_secret = CLOUDINARY_API_SECRET 
    )
    print("--- (Cloudinary) 永恆檔案館連接成功！ ---")
except Exception as e:
    print(f"!!! 嚴重錯誤：無法連接到 Cloudinary。錯誤：{e}")

# --- ★ 第五紀元：定義「向量轉換」模型 (Gemini) ★ ---
EMBEDDING_MODEL = 'models/text-embedding-004' # (0.8.5 兼容)
VECTOR_DIMENSION = 768 # ★ 向量維度 768

# --- 步驟四：AI 宗師的「靈魂」核心 (★ 最終完整 Prompt ★) ---
system_prompt = """
你是一位頂尖大學物理系教授，專精高中教師甄試解題、物理奧林匹亞的解題，更是的台灣高中物理專業教學AI，叫做「JYM物理助教」。
你的教學風格是「蘇格拉底式評估法」(Socratic Evaluator)。
你「只會」收到兩種輸入：學生的「純文字提問」，或是由「視覺專家」預先分析好的「圖片內容分析」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

# --- ★ 「第九紀元：評估者」核心邏輯 ★ ---
# 這是你最重要的思考流程！

當學生回答了你「上一個」問題時，你「必須」執行以下「內心思考」：

1.  **【內心思考 - 步驟 1：自我解答】**
    * 「學生回答了『...』。在我回應之前，我必須先自己『在內心』計算或推導出我上一個問題的『正確答案』是什麼？」
    * (例如：a-t 圖面積代表『速度變化量』。從 0 到 10 秒，面積是 1/2 * 10 * 5 = 25 m/s)

2.  **【內心思考 - 步驟 2：評估對錯】**
    * 「學生的答案『...』是否 100% 匹配我『內心』的正確答案？」

3.  **【內心思考 - 步驟 3：分支應對 (★ 關鍵 ★)】**
    * **【A. 如果學生「答對了」】:**
        * 「太棒了！學生答對了。我的回應『必須』：1. 肯定他（例如：『完全正確！』、『沒錯！』）。 2. 總結我們剛剛的發現（例如：『我們成功找出了速度變化量是 25 m/s』）。 3. 提出『下一個』合乎邏輯的蘇格拉底式問題（例如：『那麼，如果我們知道了「速度變化量」，我們要如何找出 10 秒時的「最終速度」呢？』）。」
    * **【B. 如果學生「答錯了」 (★ 修正 Point 1 的 Bug ★)】:**
        * 「啊，學生答錯了。他以為是『...』，但正確答案是『...』。」
        * 「我『絕對不能』說『你答錯了』！」
        * 「我也『絕對不能』像他答對一樣，繼續問下一題 (★ 這就是那個 Bug！★)！」
        * 「我的回應『必須』是：1. 忽略他的錯誤答案。 2. 針對他『卡住的那個概念』，提出一個『更簡單』、『更聚焦』的『引導性問題』，幫助他『自己』想通。」
        * (例如：如果學生把 a-t 圖面積算成 50，我不能說『錯了』，也不能說『好，那下一步...』。我應該問：「我們再來確認一下 a-t 圖的『面積』。這是一個三角形，對吧？你還記得三角形的面積公式是什麼嗎？」)

# --- ★ 「第九紀元：教學策略」★ ---
4.  **【RAG 策略】:** 在你「內心思考」或「提出問題」之前，你「必須」優先查閱「相關段落」。你的所有提問，都必須 100% 基於「相關段落」中的知識。如果「相關段落」沒有資訊 (N/A)，則使用你的基礎知識。
5.  **【學習診斷】:** (Point 4) 當一個完整的題目被引導完畢後，你「必須」詢問學生：「經過剛剛的引導，你對於『...』(例如：力矩) 這個概念，是不是更清楚了呢？」
6.  **【類題確認】:** (Point 4) 如果學生回答「是」或「學會了」，你「必須」立刻「產生一個」與剛剛題目「概念相似，但數字或情境不同」的「新類題」，來「確認」學生是否真的學會了。

# --- 你的「教學流程」---
* (舊的教學流程已併入「評估者核心邏輯」)
"""

# --- 步驟五 & 六：AI 宗師的「大腦」設定 (★ 專家一：對話宗師 ★) ---
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro', # ★ 修正：使用 0.8.5 兼容的「正確」名稱 (修復 404)
    system_instruction=system_prompt,
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# --- 步驟七：連接「外部大腦」(Neon 資料庫) (★ 完整修正版 ★) ---

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        return None

# 函數：初始化資料庫（★ 升級：同時建立 research_log ★）
def initialize_database():
    conn = get_db_connection()
    if conn:
        try:
            register_vector(conn)
            print("--- (SQL) `register_vector` 成功 ---")

            with conn.cursor() as cur:
                # 表格一：AI 的「記憶」
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        user_id TEXT PRIMARY KEY,
                        history JSONB
                    );
                """)
                print("--- (SQL) 表格 'chat_history' 確認/建立成功 ---")

                # 表格二：AI 的「知識庫」
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS physics_vectors (
                        id SERIAL PRIMARY KEY,
                        content TEXT,
                        embedding VECTOR({VECTOR_DIMENSION})
                    );
                """)
                print(f"--- (SQL) 表格 'physics_vectors' (維度 {VECTOR_DIMENSION}) 確認/建立成功 ---")

                # ★★★【第八紀元：升級表格】★★★
                # 表格三：人類的「研究日誌」(加入 image_url)
                cur.execute("""
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
                """)
                # 檢查 image_url 欄位是否存在，如果不存在就加入
                cur.execute("""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name='research_log' AND column_name='image_url'
                        ) THEN
                            ALTER TABLE research_log ADD COLUMN image_url TEXT;
                        END IF;
                    END$$;
                """)
                print("--- (SQL) ★ 第八紀元：表格 'research_log' (含 image_url) 確認/建立/升級成功 ★ ---")

                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法初始化資料庫表格。錯誤：{e}")
        finally:
            conn.close()

# 函數：讀取聊天紀錄 (AI 記憶)
def get_chat_history(user_id):
    conn = get_db_connection()
    history_json = [] 
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT history FROM chat_history WHERE user_id = %s;", (user_id,))
                result = cur.fetchone()
                if result and result[0]:
                    history_json = result[0] 
        except Exception as e:
            print(f"!!! 錯誤：無法讀取 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()
    return history_json 

# 函數：儲存聊天紀錄 (AI 記憶)
def save_chat_history(user_id, chat_session):
    conn = get_db_connection()
    if conn:
        try:
            history_to_save = []
            if chat_session.history: 
                for content in chat_session.history:
                    parts_text = []
                    if content.parts:
                        try:
                            parts_text = [part.text for part in content.parts if hasattr(part, 'text')]
                        except Exception as part_e:
                            print(f"!!! 警告：提取 history parts 時出錯: {part_e}。內容: {content}")

                    role = content.role if hasattr(content, 'role') else 'unknown' 
                    history_to_save.append({'role': role, 'parts': parts_text})

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO chat_history (user_id, history)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET history = EXCLUDED.history;
                """, (user_id, json.dumps(history_to_save)))
                conn.commit()
        except Exception as e:
            print(f"!!! 錯誤：無法儲存 user_id '{user_id}' 的歷史紀錄。錯誤：{e}")
        finally:
            conn.close()

# ★★★【第八紀元：升級函數】★★★
# 函數：儲存「研究日誌」(加入 image_url)
def save_to_research_log(user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response):
    conn = get_db_connection()
    if conn:
        try:
            print(f"--- (研究日誌) 正在儲存 user_id '{user_id}' 的完整互動... ---")
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO research_log 
                    (user_id, user_message_type, user_content, image_url, vision_analysis, rag_context, ai_response)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, user_msg_type, user_content, image_url, vision_analysis, rag_context, ai_response))
                conn.commit()
            print("--- (研究日誌) 儲存成功 ---")
        except Exception as e:
            print(f"!!! 錯誤：無法儲存「研究日誌」。錯誤：{e}")
        finally:
            conn.close()

# 函數：RAG 搜尋 (AI 知識庫)
def find_relevant_chunks(query_text, k=3):
    """搜尋最相關的 k 個教科書段落 (使用 Gemini Embedding)"""

    conn = None
    try:
        print(f"--- (RAG) 正在為問題「{query_text[:20]}...」向 Gemini 請求向量... ---")
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=[query_text], 
            task_type="retrieval_query" 
        )
        query_embedding = result['embedding'][0] 

        print("--- (RAG) 正在連接資料庫以搜尋向量... ---")
        conn = get_db_connection()
        if not conn:
            return "N/A"

        register_vector(conn)

        with conn.cursor() as cur:
            # ★ 修正：加入 ::vector 類型轉換 (修復 RAG 搜尋)
            cur.execute(
                "SELECT content FROM physics_vectors ORDER BY embedding <-> %s::vector LIMIT %s",
                (query_embedding, k)
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
        if conn:
            conn.close()

initialize_database()

# --- 步驟八：神殿的「入口」(Webhook) ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 步驟九：神殿的「主控室」(處理訊息) (★ 最終研究日誌版 ★) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):

    user_id = event.source.user_id

    # --- ★ 第八紀元：初始化研究日誌變數 ★ ---
    user_message_type = "unknown"
    user_content = ""
    image_url_to_save = "" # ★ 新增：儲存圖片 URL
    vision_analysis = ""
    rag_context = ""
    final_text = "" # AI 的最終回覆

    # 1. 讀取「過去的記憶」
    past_history = get_chat_history(user_id)

    # 2. 根據「記憶」開啟「對話宗師」的對話
    try:
         chat_session = model.start_chat(history=past_history) # model = 'gemini-2.5-pro'
    except Exception as start_chat_e:
         print(f"!!! 警告：從歷史紀錄開啟對話失敗。使用空對話。錯誤：{start_chat_e}")
         chat_session = model.start_chat(history=[])

    # 3. 準備「當前的輸入」(★ 兩階段專家系統 ★)
    prompt_parts = []
    user_question = "" 

    try:
        if isinstance(event.message, ImageMessage):
            # --- ★ 第八紀元：上傳圖片到「永恆檔案館」 ★ ---
            user_message_type = "image"
            user_content = f"Image received (Message ID: {event.message.id})" # 記錄圖片 ID

            print(f"--- (Cloudinary) 收到來自 user_id '{user_id}' 的圖片，開始上傳... ---")
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = message_content.content # ★ 直接使用原始 bytes

            try:
                upload_result = cloudinary.uploader.upload(image_bytes)
                image_url_to_save = upload_result.get('secure_url')
                if image_url_to_save:
                    print(f"--- (Cloudinary) 圖片上傳成功！URL: {image_url_to_save} ---")
                else:
                    print(f"!!! 錯誤：Cloudinary 未返回 URL。")
                    image_url_to_save = "upload_failed"
            except Exception as upload_e:
                print(f"!!! 嚴重錯誤：Cloudinary 圖片上傳失敗。錯誤：{upload_e}")
                image_url_to_save = f"upload_error: {upload_e}"

            # --- ★ 專家二：「視覺專家」啟動 ★ ---
            print(f"--- (視覺專家) 正在分析圖片... ---")
            vision_model = genai.GenerativeModel('gemini-2.5-flash-image') 
            img = Image.open(io.BytesIO(image_bytes)) # 重新打開 bytes 以供 vision

           vision_prompt = """
            
            你是一位頂尖的物理老師。這張圖片「有兩種可能」：
            1.「新問題」：它可能是一張包含「新問題」的講義或截圖。
            2.「學生作答」：它可能是一張學生「手寫的解題過程」。

            你的任務是「分析」並「二選一」：

            * **如果是「新問題」**：請「詳細、準recte地描述」這個問題的情境、所有變數、數字和它提出的問題。
            * **如果是「學生作答」**：請「詳細分析」學生的解題步驟。**找出「第一個」 conceptual (概念) 或 calculation (計算) 上的「錯誤」**。然後「明確指出」這個錯誤，並「提示」學生正確的思考方向或應該使用的「正確概念」。

            請直接開始你的分析。
            
            """

            vision_response = vision_model.generate_content([vision_prompt, img])
            vision_analysis = vision_response.text # ★ 記錄「視覺分析」
            print(f"--- (視覺專家) 分析完畢：{vision_analysis[:70]}... ---")

            user_question = f"圖片內容分析：『{vision_analysis}』。請基於這個分析，開始用蘇格拉底式教學法引導我。"

        else: 
            # --- ★ 傳統文字訊息 ★ ---
            user_message_type = "text"
            user_question = event.message.text
            user_content = user_question # ★ 記錄「學生文字」
            print(f"--- (文字 RAG) 收到來自 user_id '{user_id}' 的文字訊息... ---")

        # --- ★ 統一 RAG 流程 (無論是文字還是圖片分析) ★ ---
        print(f"--- (RAG) 正在為「{user_question[:30]}...」執行 RAG 搜尋... ---")
        rag_context = find_relevant_chunks(user_question) # ★ 記錄「RAG 內容」

        # 構建「RAG 提示詞」
        rag_prompt = f"""
        ---「相關段落」開始---
        {rag_context}
        ---「相關段落」結束---

        學生問題/圖片分析：「{user_question}」

        (請你嚴格遵守 System Prompt 中的指令，100% 基於上述「相關段落」，用「蘇格拉底式提問」來回應學生的問題。)
        """
        prompt_parts = [rag_prompt]

        # --- ★ 專家一：「對話宗師」啟動 ★ ---
        print(f"--- (對話宗師) 正在呼叫 Gemini API (gemini-2.5-pro)... ---")
        response = chat_session.send_message(prompt_parts) # ★ 呼叫 'gemini-1.0-pro'
        final_text = response.text # ★ 記錄「AI 回覆」
        print(f"--- (對話宗師) Gemini API 回應成功 ---")

        # 5. 儲存「更新後的記憶」(AI 記憶)
        print(f"--- (記憶) 正在儲存 user_id '{user_id}' 的對話紀錄... ---")
        save_chat_history(user_id, chat_session)
        print(f"--- (記憶) 對話紀錄儲存成功 ---")

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫或資料庫/RAG/視覺操作失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在檢索記憶/教科書或冥想中，請稍後再試。"
        # ★ 確保錯誤日誌也能被儲存
        if not user_content: user_content = "Error during processing"
        if not user_message_type: user_message_type = "error"

    # ★★★【第八紀元：最終儲存】★★★
    # 6. 儲存「研究日誌」(人類研究)
    # (無論成功或失敗，都儲存日誌)
    save_to_research_log(
        user_id=user_id,
        user_msg_type=user_message_type,
        user_content=user_content,
        image_url=image_url_to_save, # ★ 傳入「圖片 URL」
        vision_analysis=vision_analysis,
        rag_context=rag_context,
        ai_response=final_text
    )

    # 7. 回覆使用者
    line_bot_api.reply_message(
        event.reply_token, 
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)