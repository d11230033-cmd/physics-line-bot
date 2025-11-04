# --- 「神殿」：AI 宗師的核心 (第十三紀元：精準讀取版) ---
#
# 版本：Neon 記憶 + 雙重專家 + 檔案館 + 指令中心
# 修正：1. `gemini-1.0-pro` (修復 404 / 2.5-pro 錯誤)
# 修正：2. `::vector` (修復 RAG 搜尋)
# 修正：3. Python 3.11 / WEB_CONCURRENCY=1 (在 Render 設定)
# 修正：4. ★ 第十三紀元：Socratic Evaluator (精準視覺) ★
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

# --- 步驟四：AI 宗師的「靈魂」核心 (★ 第十二紀元：中文指令 ★) ---
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是「蘇格拉底式評估法」(Socratic Evaluator)。
你「只會」收到兩種輸入：學生的「純文字提問」，或是由「視覺專家」預先分析好的「圖片內容分析」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

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
            * 「太棒了！學生答對了。我的回應『必須』：1. 肯定他（例如：『完全正確！』、『沒錯！』）。 2. 總結我們剛剛的發現。 3. 提出『下一個』合乎邏輯的蘇格拉底式問題。」
        * **【B2. 如果學生「答錯了」】:**
            * 「啊，學生答錯了。他以為是『...』，但正確答案是『...』。」
            * 「我的回應『必須』是：1. 用『溫和、鼓勵』的方式，『委婉地指出』他的答案『可能需要重新思考』。」
            * 「例如：『嗯... 讓我們再檢查一下那個計算。』或『你離答案很近了，但我們來確認一下... (卡住的概念)』」
            * 「2. 接著，『立刻』提出一個『更簡單』、『更聚焦』的『引導性問題』，幫助他『自己』想通。」

# --- ★ 「第十紀元：教學策略」★ ---
4.  **【RAG 策略】:** (僅在【B. 正常對話】模式下啟用) 在你「內心思考」或「提出問題」之前，你「必須」優先查閱「相關段落」。你的所有提問，都必須 100% 基於「相關段LO」中的知識。
5.  **【學習診斷】:** (Point 4) 當一個完整的題目被引導完畢後，你「必須」詢問學生：「經過剛剛的引導，你對於『...』(例如：力矩) 這個概念，是不是更清楚了呢？」
6.  **【類題確認】:** (Point 4) 如果學生回答「是」或「學會了」，你「必須」立刻「產生一個」與剛剛題目「概念相似，但數字或情境不同」的「新類題」，來「確認」學生是否真的學會了。
"""

# --- 步驟五 & 六：AI 宗師的「大腦」設定 (★ 專家一：對話宗師 ★) ---
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro', # ★ 修正：使用 0.8.5 兼容的「正確」名稱 (修復 404 / 2.5-pro 錯誤)
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

            # --- ★ 專家二：「視覺專家」啟動 (第十三紀元：精準讀取版) ★ ---
            print(f"--- (視覺專家) 正在分析圖片... ---")
            vision_model = genai.GenerativeModel('gemini-2.5-flash-image') 
            img = Image.open(io.BytesIO(image_bytes)) # 重新打開 bytes 以供 vision

            # ★ 第十三紀元：使用「精準讀取」的視覺 Prompt ★
            vision_prompt = """
            你是一個「精準的」光學掃描儀 (OCR) 和「圖表分析」工具。
            你的「唯一」任務是「客觀地」、「逐字地」、「逐點地」描述圖片內容。

            **「絕對禁止」**：
            * 「絕對禁止」你「自己」去「解讀」物理意義。
            * 「絕對禁止」你「自己」去「計算」答案。

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
        print(f"--- (RAG) TAG: 正在為「{user_question[:30]}...」執行 RAG 搜尋... ---")
        rag_context = find_relevant_chunks(user_question) # ★ 記錄「RAG 內容」

        # ★ 第十二紀元：修改 RAG 提示詞 (中文版) ★
        rag_prompt = f"""
        ---「相關段落」開始---
        {rag_context}
        ---「相關段落」結束---

        學生的「原始輸入」(可能是「指令」或「回答」)：「{user_question}」

        (請你「嚴格遵守」 System Prompt 中的「第十二紀元：中文指令」核心邏輯！
        1.  「首先」檢查「原始輸入」是否為「一個指令」(例如：教我物理觀念)。如果是，請「立刻執行指令」。
        2.  「如果不是」指令，才「接著」使用「相關段落」和「評估者邏輯」來回應。)
        """
        prompt_parts = [rag_prompt]

        # --- ★ 專家一：「對話宗師」啟動 (第十二紀元：評估版) ★ ---
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