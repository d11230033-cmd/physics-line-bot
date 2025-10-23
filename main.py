# --- 「神殿」：AI 宗師的核心 ---
#
# 這份 main.py 已經 100% 植入了「藍圖二：蘇格拉底的新靈魂」。
# 
# -----------------------------------

import os
import pathlib
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, ImageMessage, TextSendMessage
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from PIL import Image
import io

# --- 步驟一：神殿的鑰匙 (從 Render.com 讀取) ---
# 這些秘密，我們將會儲存在 Render 的「秘密保險箱」(Environment Variables) 中
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
LINE_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

# --- 步驟二：神殿的基礎建設 ---
app = Flask(__name__)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 步驟三：連接「神之鍛造廠」(Gemini) ---
try:
    genai.configure(api_key=GOOGLE_API_KEY)
except Exception as e:
    print(f"!!! 嚴重錯誤：無法設定 Google API Key。請檢查 Render 上的 GOOGLE_API_KEY 是否正確。錯誤：{e}")

# --- 步驟四：AI 宗師的「靈魂」核心 (System Prompt) ---
#
# ★★★ 「藍圖二」：蘇格拉底的新靈魂 (已植入) ★★★
#
system_prompt = """
你是一位頂尖的台灣高中物理教學AI，叫做「AI 宗師」。
你的教學風格是 100% 的「蘇格拉底式教學法」。

# --- 你的「絕對核心」指令 ---
1.  **「永遠不要」** 給出「直接的答案」或「最終的解題步驟」。
2.  你的 **「唯一」** 職責，是透過「提問」來引導學生。
3.  你的 **「所有」** 回應，**「必須」** 以一個「引導性的問題」來結束。
4.  **「絕對禁止」** 說出「答案是...」或「你應該要...」。

# --- 你的「教學流程」---
1.  **「確認問題」**：當學生提問時（無論是文字或圖片），首先，用「你自己的話」複述一遍問題，確保你理解正確。
2.  **「拆解問題」**：接著，提出一個「最小的、最關鍵的」起始問題，引導學生思考「第一步」。
3.  **「逐步引導」**：根據學生的回答，再提出「下一個」引導性問題。
4.  **「保持鼓勵」**：你的語氣必須充滿耐心與鼓勵。多使用「很好！」、「沒錯！」、「你快想到了！」、「這是一個很棒的切入點！」

# --- 「情境模擬」---

# 【情境一：學生問一個「觀念」】
#   學生：「老師，什麼是『動量守恆』？」
#   你（錯誤的）：「動量守恆是指一個系統不受外力時，總動量不變。」
#   你（正確的）：「這是一個非常核心的觀念！在我們討論『守恆』之前，你還記得我們是怎麼『定義』動量的嗎？」

# 【情境二：學生問一個「解題」（附圖）】
#   學生：「老師，這題怎麼算？」
#   你（錯誤的）：「首先，你要畫力圖，然後把力分解...」
#   你（正確的）：「好的，老師看到題目了。這是一道關於『斜面上的力平衡』的問題。你覺得，在我們開始列方程式之前，『最重要』的第一步是什麼呢？」
#   學生：「畫力圖？」
#   你（正確的）：「完全正確！那麼，你能在這個木塊上，畫出『所有』作用在它上面的力嗎？（例如：重力、正向力...還有嗎？）」

# 【情境三：學生卡住了】
#   學生：「我不知道...」
#   你（錯誤的）：「答案是摩擦力。」
#   你（正確的）：「沒關係，我們一步一步來。你想像一下，如果這個斜面『完全光滑』，木塊會發生什麼事？...那現在，是什麼『阻止』了它滑下去呢？」

# --- 你的「工具使用」---
# 1.  【google_search】：當學生問到「時事」（例如：颱風）或「非物理知識」時，你可以使用它。但在「解物理題」時，優先使用你的「提問」邏輯。
# 2.  【search_private_library】：(我們目前暫時封存这个工具，請專注於「提問」)
"""

# --- 步驟五：AI 宗師的「神器」(Tools) ---
#
# ★★★ 「時光回溯」修正：使用兼容 0.8.5 版本的語法 ★★★
# (我們不再使用 genai.Tool，而是直接傳遞 FunctionDeclaration 列表)
#

# 神器一：Google 搜尋
google_search_func = genai.FunctionDeclaration(
        name='google_search',
        description='當學生詢問非物理專業知識、時事、天氣、或「AI 宗師」無法回答的即時資訊時，使用此工具。',
        parameters=genai.Schema(
            type=genai.Type.OBJECT,
            properties={
                'query': genai.Schema(type=genai.Type.STRING, description='要搜尋的關鍵字')
            },
            required=['query']
        )
    )

# 神器二：梵蒂岡秘密檔案館 (已封存)
search_library_func = genai.FunctionDeclaration(
        name='search_private_library',
        description='''
            當學生詢問「物理觀念」、「定義」、「公式」或「特定教科書內容」時，
            「絕對必須」優先使用此工具，在「梵蒂岡秘密檔案館」中搜尋權威答案。
            只有在檔案館中「找不到」相關資料時，才使用 google_search 或自己的知識。
        ''',
        parameters=genai.Schema(
            type=genai.Type.OBJECT,
            properties={
                'query': genai.Schema(type=genai.Type.STRING, description='要搜尋的物理觀念或問題關鍵字')
            },
            required=['query']
        )
    )

# --- 步驟六：AI 宗師的「大腦」設定 (修正版) ---
# (我們將修正後的 FunctionDeclaration 列表傳遞給 tools 參數)
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro',
    system_instruction=system_prompt,
    # ★★★ 修正：直接傳遞 FunctionDeclaration 列表 ★★★
    tools=[google_search_func, search_library_func],
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# ★★★ 語法修正完畢 ★★★

# --- 步驟七：神殿的「記憶體」--- (保持不變)
chat_sessions = {}

# --- 步驟八：神殿的「入口」(Webhook) ---
# (這是 Render 和 LINE 溝通的唯一通道)
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 步驟九：神殿的「主控室」(處理訊息) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):
    
    # 1. 取得使用者的「短期記憶」
    user_id = event.source.user_id
    if user_id not in chat_sessions:
        # 如果是新訪客，為他開啟一個「全新的記憶」
        chat_sessions[user_id] = model.start_chat()
    chat_session = chat_sessions[user_id] # 載入這位使用者的「對話紀錄」

    # 2. 準備「神諭」(AI 的回應)
    try:
        # 2a. 如果是「圖片」訊息
        if isinstance(event.message, ImageMessage):
            # 從 LINE 下載圖片
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = io.BytesIO(message_content.content)
            img = Image.open(image_bytes)
            
            # 準備要傳送給 Gemini 的「提示詞」
            prompt_parts = ["老師，這張圖片上的物理問題（如下圖）要怎麼思考？", img]
            
        # 2b. 如果是「文字」訊息
        else:
            # 準備要傳送給 Gemini 的「提示詞」
            prompt_parts = [event.message.text]

        # 3. ★★★ 呼叫「神之鍛造廠」 ★★★
        # (將「提示詞」傳送給 Gemini，並等待「神諭」)
        response = chat_session.send_message(prompt_parts)

        # 4. 檢查「神諭」是否需要「使用神器」
        if response.candidates[0].content.parts[0].function_call:
            
            # 4a. 取得「神諭」的「神器呼叫」指令
            tool_call = response.candidates[0].content.parts[0].function_call
            
            # 4b. 檢查「神器一：Google 搜尋」
            if tool_call.name == 'google_search':
                # (目前我們「假裝」執行了搜尋，因為我們還沒植入 Google Search API)
                print(f"--- AI 宗師嘗試使用 [google_search]，關鍵字：{tool_call.args['query']} ---")
                
                # 「假裝」的搜尋結果
                function_response_parts = [
                    genai.Part(
                        function_response=genai.FunctionResponse(
                            name='google_search',
                            response={
                                'result': '搜尋結果：根據中央氣象局，台北市目前 28 度，晴時多雲。',
                                'source': 'google.com'
                            }
                        )
                    )
                ]
                
                # 4c. 將「神器使用結果」回傳給 Gemini
                response = chat_session.send_message(function_response_parts)

            # 4d. 檢查「神器二：梵蒂岡秘密檔案館」(已封存)
            elif tool_call.name == 'search_private_library':
                print(f"--- AI 宗師嘗試使用 [search_private_library] (已封存)，關鍵字：{tool_call.args['query']} ---")
                
                function_response_parts = [
                    genai.Part(
                        function_response=genai.FunctionResponse(
                            name='search_private_library',
                            response={
                                'error': '錯誤：梵蒂岡秘密檔案館（藍圖一）尚未啟動。請優先使用「蘇格拉底式提問」來引導學生。'
                            }
                        )
                    )
                ]
                
                # 4e. 將「神器使用結果」回傳給 Gemini
                response = chat_session.send_message(function_response_parts)

        # 5. 取得「最終的神諭」(AI 的最終回答)
        final_text = response.text

    # 6. 如果「神之鍛造廠」發生了「未知錯誤」
    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在冥想中，請稍後再試。"

    # 7. 將「最終的神諭」傳回給 LINE 上的學生
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 (在 Render 上自動執行) ---
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)