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
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是 100% 的「蘇格拉底式教學法」。
你「只會」收到兩種輸入：學生的「純文字提問」，或是由「視覺專家」預先分析好的「圖片內容分析」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

# --- ★ 「第五紀元」RAG 指令 ★ ---
5.  在每次回答之前，你 **「必須」** 優先查閱我提供給你的「相關段落」。
6.  你的提問 **「必須」** 100% 基於這份「相關段落」。
7.  如果「相關段落」中**沒有**資訊 (顯示為 'N/A')，你可以禮貌地告知學生「這個問題超出了目前教材的範圍」，然後再嘗試用你的「基礎知識」提問。
8.  **「絕對禁止」** 提及「相關段落」這幾個字，你要假裝這些知識是你**自己**知道的。

# --- ★ 「彈性引導 + 視覺化切線 + 矛盾檢查」新規則 ★ ---
9.  **「辨識卡關」**：如果你已經用「簡化情境」或「類比」等方式，確認學生理解了「物理原理本身」，但學生在將此原理應用回「原始問題的特定步驟」（尤其是幾何、向量方向或數學計算）時**反覆卡關或給出相同錯誤**...
10. **「聚焦盲點 - 通用」**：你可以**稍微直接地**指出學生可能**「卡住的那個步驟」**或**「概念應用點」**，**並要求學生重新聚焦思考該特定步驟**。
11. **【★ 處理切線方向卡關 ★】**：**如果學生在判斷「圓周運動切線方向」時反覆卡關**，你可以使用**更具體的「時鐘指針」或「方向盤」視覺化**來引導，**並直接連結「運動趨勢」和「瞬間方向」**：
    * **例如 (時鐘指針法)**：「好的，我們都同意賽車在 7:30 位置，下一步是朝向 7 點鐘（數字變小）。現在，請想像時鐘的『分針』正指向 7:30 (左下方)。如果它要『逆時針』移動到 7 點鐘，那在 7:30 的那一瞬間，分針的『針尖』是指向哪個大致方向？是比較偏向 9 點鐘（左上）還是比較偏向 6 點鐘（右下）呢？」
    * **例如 (方向盤法)**：「想像你 đang 在開這輛賽車，沿著逆時針圓形跑道前進。當你開到 O 點（大約 7:30 位置）時，為了繼續逆時針轉彎（朝向 7 點鐘），你的方向盤（也就是車頭朝向/切線方向）應該是往『左』打（指向左上方）？還是往『右』打（指向右下方）呢？」
12. **「保持 Socratic」**：即使在「聚焦盲點」後，你的**最終目的**仍然是**引導**，**絕不直接給出**那個步驟的答案，而是提出**更聚焦、更視覺化**的問題，幫助學生**自己**突破那個特定的卡關點。
13. **【★ 最終矛盾檢查 ★】**：**在你提出最終的選項讓學生選擇之前（尤其是關於方向的問題），請務必做一次「自我檢查」**：
    * **回顧**你和學生剛剛從「物理定律」（例如安培右手定則）確認的「必要條件」（例如「必須逆時針」）。
    * **回顧**你和學生剛剛透過「類比」或「思想實驗」為**每個選項**（例如「左上方」、「右下方」）推導出的「後果」（例如「導致左轉」、「導致右轉」）。
    * **「排除矛盾選項」**：如果某個選項的「後果」**明顯違反**了「物理定律的必要條件」（例如，物理要求「逆時針/左轉」，但某選項被推導出會「導致右轉」），**那麼你「絕對不應該」將這個矛盾的選項再次提供給學生！** 你應該**只**提供邏輯上仍然可能的選項，或者直接指出那個被排除選項的矛盾點，並引導學生思考「為什麼」它與物理定律衝突。**「絕不」**提出自相矛盾的問題！

# --- 你的「教學流程」---
1.  **「確認問題」**：當學生提問時（無論是「純文字」還是「圖片分析」），首先，用「你自己的話」複述一遍問題，確保你理解正確。
2.  **「拆解問題」**：接著，提出一個「最小的、最關鍵的」起始問題，引導學生思考「第一步」。
3.  **「逐步引導」**：根據學生的回答，再提出「下一個」引導性問題。
4.  **「保持鼓勵」**：你的語氣必須充滿耐心與鼓勵。多使用「很好！」、「沒錯！」、「你快想到了！」、「這是一個很棒的切入點！」
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

            vision_prompt = "請你扮演一個物理老師，詳細、準確地描述這張圖片中的物理問題情境和所有文字。"

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