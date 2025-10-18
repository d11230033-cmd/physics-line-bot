import requests
import json

# --- ★★★ 請在這裡貼上您最新的 V3 API 金鑰 ★★★ ---
API_KEY = "AIzaSyCb6ugnXxrTUxtDYpIrHJxJ-B_l7_XC3L0"
# --- ---

# 我們要測試的模型名稱
model_name = "gemini-pro"

# Google Gemini API 的網址
url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"

# 我們要送出的請求內容
headers = {"Content-Type": "application/json"}
data = {
    "contents": [{
        "parts": [{
            "text": "你好，世界！"
        }]
    }]
}

print("=== 正在直接呼叫 Google API... ===")
try:
    # 發送請求
    response = requests.post(url, headers=headers, data=json.dumps(data))

    # 解析並印出回應
    response_json = response.json()

    print("=== Google API 回應狀態碼 ===")
    print(response.status_code)

    print("\n=== Google API 完整回應內容 ===")
    # 使用 json.dumps 美化輸出
    print(json.dumps(response_json, indent=2, ensure_ascii=False))

except Exception as e:
    print(f"\n=== 發生錯誤 ===")
    print(e)