# --- 「神殿」：AI 宗師的核心 ---
#
# ★★★ 「徹底簡化」版：已移除所有 Tools 功能，兼容 0.8.5 ★★★
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
# ★★★ 「藍圖二」：蘇格拉底的新靈魂 (保持不變) ★★★
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
#   你（正確的）：「這是一個非常核心的觀念！在我們討論『守恆』之前，你還記得我們是怎麼『定義』動量的嗎？」
# 【情境二：學生問一個「解題」（附圖）】
#   學生：「老師，這題怎麼算？」
#   你（正確的）：「好的，老師看到題目了。這是一道關於『斜面上的力平衡』的問題。你覺得，在我們開始列方程式之前，『最重要』的第一步是什麼呢？」
# 【情境三：學生卡住了】
#   學生：「我不知道...」
#   你（正確的）：「沒關係，我們一步一步來。你想像一下，如果這個斜面『完全光滑』，木塊會發生什麼事？...那現在，是什麼『阻止』了它滑下去呢？」

# --- 你的「工具使用」--- (已移除)
"""

# --- 步驟五 & 六：AI 宗師的「大腦」設定 (已移除 Tools) ---
model = genai.GenerativeModel(
    model_name='gemini-2.5-pro',
    system_instruction=system_prompt,
    # ★★★ 已移除 tools 參數 ★★★
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# --- 步驟七：神殿的「記憶體」--- (保持不變)
chat_sessions = {}

# --- 步驟八：神殿的「入口」(Webhook) --- (保持不變)
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# --- 步驟九：神殿的「主控室」(處理訊息) (已移除 Tools 處理) ---
@handler.add(MessageEvent, message=(TextMessage, ImageMessage))
def handle_message(event):

    user_id = event.source.user_id
    if user_id not in chat_sessions:
        chat_sessions[user_id] = model.start_chat()
    chat_session = chat_sessions[user_id]

    try:
        if isinstance(event.message, ImageMessage):
            message_content = line_bot_api.get_message_content(event.message.id)
            image_bytes = io.BytesIO(message_content.content)
            img = Image.open(image_bytes)
            prompt_parts = ["老師，這張圖片上的物理問題（如下圖）要怎麼思考？", img]
        else:
            prompt_parts = [event.message.text]

        # ★★★ 呼叫 Gemini (無 Tools) ★★★
        response = chat_session.send_message(prompt_parts)

        # ★★★ 直接取得回應 (已移除 function_call 檢查) ★★★
        final_text = response.text

    except Exception as e:
        print(f"!!! 嚴重錯誤：Gemini API 呼叫失敗。錯誤：{e}")
        final_text = "抱歉，宗師目前正在冥想中，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=final_text)
    )

# --- 步驟十：啟動「神殿」 --- (保持不變)
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)