import google.generativeai as genai
import os

# --- ★★★ 請在這裡貼上您最新的 V3 API 金鑰 ★★★ ---
# (就是您為 physics-bot-v2 專案建立的那把新鑰匙)
GOOGLE_API_KEY = "AIzaSyCb6ugnXxrTUxtDYpIrHJxJ-B_l7_XC3L0"
# --- ---

genai.configure(api_key=GOOGLE_API_KEY)

print("=== 正在向 Google 查詢您可用的 AI 模型清單... ===")
try:
    model_count = 0
    for m in genai.list_models():
        # 我們只關心能用來生成內容的模型
        if 'generateContent' in m.supported_generation_methods:
            print(f"找到可用模型: {m.name}")
            model_count += 1

    if model_count == 0:
        print("\n>>> 診斷結果：您的專案目前沒有任何可用的生成模型。")
        print(">>> 這 100% 是 Google 端的部署延遲問題，請耐心等待 12-24 小時後再試。")
    else:
        print(f"\n>>> 診斷結果：恭喜！您共有 {model_count} 個可用模型！請將 main.py 中的模型名稱換成上面列表中的任何一個！")

except Exception as e:
    print(f"\n=== 發生錯誤 ===")
    print("無法成功查詢模型清單，這通常代表您的專案權限尚未完全同步。")
    print("請確認您的 V3 API 金鑰是否正確貼上，並請耐心等待數小時後再試。")
    print("\n詳細錯誤訊息：")
    print(e)