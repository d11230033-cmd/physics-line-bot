# === 引用我們安裝好的工具 ===
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage,
    MessagingApiBlob
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent

import google.generativeai as genai
# --- 最終的兼容性修正 (不再需要 Part) ---
from google.generativeai.types import GenerationConfig, Tool

import os
import requests
from PIL import Image
import io

# === 中央廚房設定 ===
app = Flask(__name__)

# --- ★★★ 最終的神殿部署版鑰匙 ★★★ ---
# 我們將從「秘密保險箱」(環境變數) 中讀取鑰匙
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', None)
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY', None)

# 檢查鑰匙是否都已成功讀取
if not all([channel_access_token, channel_secret, GOOGLE_API_KEY, SERPAPI_API_KEY]):
    print("錯誤：並非所有的神聖鑰匙都已在環境變數中設定！")
    # 在生產環境中，您可能希望程式在此處停止
    
# === 全新的「工具箱」系統 ===

# --- 神器一：超級計算機 ---
def calculator(expression: str):
    """
    這是一個超級計算機，可以執行加減乘除等數學運算。
    例如：'3 * (5 + 2)' 或 '25**0.5' (開根號)。
    """
    print(f"Calculator received expression: {expression}")
    allowed_chars = "0123456789.+-*/() "
    clean_expression = expression.replace(" ", "")
    if not all(char in allowed_chars for char in clean_expression):
        return "錯誤：運算式包含不安全的字元。"
    try:
        result = eval(clean_expression)
        return f"計算結果：{result}"
    except Exception as e:
        return f"計算錯誤：{e}"

# --- 神器二：網際網路搜尋 ---
def google_search(query: str):
    """
    當你需要查詢最新的、真實世界的資訊、或非學術定義時，使用這個工具。
    """
    print(f"Google Search received query: {query}")
    url = "https://serpapi.com/search.json"
    params = {"q": query, "api_key": SERPAPI_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        search_results = response.json()
        if "answer_box" in search_results and "answer" in search_results["answer_box"]:
            return f"搜尋到的答案：{search_results['answer_box']['answer']}"
        elif "organic_results" in search_results and search_results["organic_results"]:
            return f"搜尋到的頂尖結果：{search_results['organic_results'][0]['snippet']}"
        else:
            return "找不到相關資訊。"
    except Exception as e:
        return f"搜尋時發生錯誤: {e}"

# --- 神器三：維基百科搜尋 (您親手打造的專業圖書館) ---
def search_wikipedia(query: str):
    """
    這是一把專用的神器，只在維基百科 (Wikipedia) 中搜尋。當學生詢問一個明確的物理学「定義」或「概念」(例如：什麼是熵？) 時，優先使用這個工具。
    """
    print(f"Wikipedia Search received query: {query}")
    search_query = f"{query} site:zh.wikipedia.org" # 強制在中文維基百科中搜尋
    url = "https://serpapi.com/search.json"
    params = {"q": search_query, "api_key": SERPAPI_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        search_results = response.json()
        if "knowledge_graph" in search_results and "description" in search_results["knowledge_graph"]:
            return f"在維基百科中找到的定義：{search_results['knowledge_graph']['description']}"
        elif "organic_results" in search_results and search_results["organic_results"]:
            return f"在維基百科中找到的相關資料：{search_results['organic_results'][0]['snippet']}"
        else:
            return "在維基百科中找不到相關資訊。"
    except Exception as e:
        return f"在維基百科搜尋時發生錯誤: {e}"

# === AI 角色與核心指令 (最終學者版) ===
system_prompt_text = """
# Role & Goal
- AI Coach: "物理老師的小幫手".
- Style: Encouraging, patient, Socratic.
- Mission: Guide high school students to solve physics problems themselves, DO NOT give direct answers.

# Research & Verification Principles (研究與驗證原則)
- **Tool Selection Priority:** You now have two search tools.
    - When a student asks for a clear "definition" or "concept" (e.g., 'What is entropy?'), you MUST prioritize using the `search_wikipedia` tool.
    - For general, up-to-the-minute information, news, or non-definitional queries, use the `Google Search` tool.
- **Critical Assessment:** When using any search tool, you MUST critically assess the source. Prioritize academic institutions (.edu), scientific organizations (NASA, CERN), and reputable encyclopedias.
- **Never Trust Forums or Blogs:** Absolutely forbid using information from forums or personal blogs as the primary source for factual answers.
- **Always Mention Context:** When presenting any law or formula, you must consider its limitations and context.

# Formatting Rules (格式化指令)
- **No LaTeX:** All your responses must be plain text. Absolutely forbid using the `$` symbol.
- **Correct Example:** 加速度是 a = 2.04 m/s^2

# Core Workflow: Guided Learning
## Step 1: Confirm Interaction (Mandatory for Images)
1. Receive an image.
2. Perform OCR internally.
3. Restate all key conditions.
4. End with the exact question: "我辨識出的題目條件如上，請問是否完全正確？請回覆『正確』或提供需要修正的地方。"
## Step 2: Start Guidance
- On user confirmation ("正確"), reply: "好的，條件確認無誤。我們一起來分析這道題目吧！" then proceed to Step 3.
## Step 3: Socratic Dialogue (The Core Loop!)
- **Goal:** Break down the problem through questions.
- **First Question:** Always start by asking for the core concept. e.g., "看到這個題目，你首先會想到哪個核心的物理觀念或定律呢？"
- **Handle Errors/Stuck:** If the student is wrong or says "不知道", DO NOT give the answer. Provide a simpler hint.
## Step 4: Summarize & Extend
- After the student finds the correct answer, praise them.
- Then, provide a summary of THEIR solution process in a clean note format.
"""

# === Gemini AI 專家設定 ===
genai.configure(api_key=GOOGLE_API_KEY)
# --- 專家一：我們的「對話宗師」(搭載三神器) ---
text_model = genai.GenerativeModel(
    model_name='gemini-2.5-pro',
    tools=[calculator, google_search, search_wikipedia] # 登錄所有神器
)
# --- 專家二：我們的「視覺專家」 ---
vision_model = genai.GenerativeModel(model_name='gemini-2.5-flash-image')
conversation_history = {}

# === LINE Bot 基礎設定 ===
configuration = Configuration(access_token=channel_access_token)
handler = WebhookHandler(channel_secret)

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# === 處理訊息的核心 (最終兼容版！) ===
def handle_gemini_response(chat, response):
    try:
        response_part = response.parts[0]
        if response_part.function_call:
            function_call = response_part.function_call
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}
            
            print(f"AI 想要使用工具: {tool_name}, 參數: {tool_args}") # 修正: 移除非預期字元 'DDE'

            tool_result = "" # 修正: 確保 tool_result 總是被定義
            if tool_name == "calculator":
                tool_result = calculator(**tool_args)
            elif tool_name == "google_search":
                tool_result = google_search(**tool_args)
            elif tool_name == "search_wikipedia": # ★★★ 讓 AI 能夠使用新神器 ★★★
                tool_result = search_wikipedia(**tool_args)
            else:
                tool_result = f"錯誤：未知的工具 {tool_name}"

            print(f"工具執行結果: {tool_result}")

            # --- 最終的兼容性修正 (不再依賴 Part) ---
            final_response = chat.send_message(
                Tool.from_dict(
                    {'function_response