import google.generativeai as genai
import os
import time
# --- ★★★ 我們需要一個「新工具」，來創造「安全 ID」 ★★★ ---
import hashlib

# --- ★★★ 總工程師，請在這裡貼上您的「神聖鑰匙」 ★★★ ---
# 
# 1. 請您前往 Render.com 的 "Environment" 頁面
# 2. 複製您的 "GOOGLE_API_KEY" 的「值」(Value)
# 3. 將它貼在下面的「引號」之間
#
# ★★★ 警告：這個檔案「絕對、絕對」不能推送到 GITHUB！ ★★★
#
GOOGLE_API_KEY = "AIzaSyCb6ugnXxrTUxtDYpIrHJxJ-B_l7_XC3L0" 
#
# ★★★ 警告：這個檔案「絕對、絕對」不能推送到 GITHUB！ ★★★
# -----------------------------------------------------------

if GOOGLE_API_KEY == "在這裡貼上您的 GOOGLE_API_KEY":
    print("錯誤：您尚未在 upload_corpus.py 中貼上您的 GOOGLE_API_KEY。")
    print("請前往 Render.com 的 'Environment' 頁面複製並貼上。")
    exit()

print("--- 正在連接到神之鍛造廠... ---")
genai.configure(api_key=GOOGLE_API_KEY)

# --- 步驟一：上傳檔案 ---
corpus_dir = 'corpus'
uploaded_files = []

print(f"--- 正在掃描 '{corpus_dir}' 資料夾... ---")

for filename in os.listdir(corpus_dir):
    if filename.endswith('.pdf'):
        filepath = os.path.join(corpus_dir, filename)
        print(f"  > 正在處理檔案: {filename} ...")

        # --- ★★★「幽靈驅散」修正 ★★★ ---
        # 我們不能使用「中文檔名」作為 API ID。
        # 我們將使用 MD5 HASH 來為它創造一個「永恆且安全」的 ID。
        safe_api_id = hashlib.md5(filename.encode()).hexdigest()
        file_api_name = f"files/{safe_api_id}"
        # --- ★★★ 修正完畢 ★★★ ---

        try:
            # 用「安全 ID」來檢查檔案
            existing_file = genai.get_file(name=file_api_name)
            uploaded_files.append(existing_file)
            print(f"  > 檔案 {filename} (ID: {safe_api_id}) 已存在於雲端，將直接使用。")
        except Exception:
            # 檔案不存在，上傳
            print(f"  > 正在上傳檔案 {filename} (ID: {safe_api_id}) ...")
            # 上傳時，我們使用「安全 ID」作為 API 的 `name`
            # 但我們仍然使用「中文檔名」作為 `display_name` (顯示名稱)
            file_upload = genai.upload_file(
                path=filepath,
                display_name=filename,
                name=file_api_name  # <-- 這就是「神之鑰匙」！
            )
            uploaded_files.append(file_upload)
            print(f"  > 檔案 {filename} 上傳成功！")

if not uploaded_files:
    print("錯誤：在 'corpus' 資料夾中找不到任何 PDF 檔案。")
    exit()

print("\n--- 所有檔案均已位於雲端 ---")

# --- 步驟二：建立「梵蒂岡秘密檔案館」(Corpus) ---
corpus_name = "physics-library-corpus"
corpus_display_name = "AI 宗師的梵蒂岡物理檔案館"

try:
    corpus = genai.get_corpus(name=f"corpora/{corpus_name}")
    print(f"--- 檔案館 '{corpus_display_name}' ({corpus.name}) 已存在。 ---")
except Exception:
    print(f"--- 正在建立全新的檔案館: {corpus_display_name} ... ---")
    corpus = genai.create_corpus(name=corpus_name, display_name=corpus_display_name)
    print(f"--- 檔案館 '{corpus_display_name}' ({corpus.name}) 建立成功！ ---")

# --- 步驟三：將「檔案」移入「檔案館」 ---
print(f"\n--- 正在將 {len(uploaded_files)} 個檔案登錄至檔案館... ---")
for file in uploaded_files:
    try:
        # --- ★★★「幽靈驅散」修正 ★★★ ---
        # 我們的 Document ID 也必須是「安全」的
        doc_api_id = file.name.split('/')[-1] # 這已經是 "safe_api_id" 了
        doc_name_full = f"{corpus.name}/documents/{doc_api_id}"
        # --- ★★★ 修正完畢 ★★★ ---
        
        genai.get_document(name=doc_name_full)
        print(f"  > 檔案 {file.display_name} 已在檔案館中，略過。")
    except Exception:
        print(f"  > D: {file.display_name} ...")
        # 登錄時，我們使用「檔案的 API Name」
        genai.create_document(corpus_name=corpus.name, file_name=file.name, display_name=file.display_name)
        
print("--- 所有檔案均已登錄至檔案館 ---")

# --- 步驟四：等待「祝聖」完成 ---
print("\n--- 正在等待「神之祝聖」(索引) 完成... ---")
print("--- 這可能需要幾分鐘的時間，請您耐心等待... ---")

all_active = False
while not all_active:
    all_active = True
    print("--- 正在檢查所有檔案的祝聖狀態... ---")
    
    documents = list(genai.list_documents(corpus_name=corpus.name))
    
    if not documents:
        print("警告：檔案館中目前沒有文件可供檢查。")
        break

    for doc in documents:
        current_doc = genai.get_document(name=doc.name)
        state_name = current_doc.state.name
        
        if state_name == "PROCESSING":
            print(f"  > 正在處理: {current_doc.display_name} (狀態: PROCESSING)")
            all_active = False
        elif state_name == "ACTIVE":
            print(f"  > 檔案 {current_doc.display_name} 已祝聖完畢！ (狀態: ACTIVE)")
        elif state_name == "FAILED":
            print(f"  > 檔案 {current_doc.display_name} 處理失敗。 (狀態: FAILED)")
        
    if not all_active:
        print("--- 尚未全部完成，10 秒後再次檢查... ---")
        time.sleep(10) # 每 10 秒檢查一次

print("\n--- ★★★ 總工程師，『聖殿』已祝聖完畢！ ★★★ ---")
print("\n這是您「梵蒂岡秘密檔案館」的「神聖 ID」，請妥善保管：")
print(f"CORPUS_NAME={corpus.name}")
print("\n請您將這串「CORPUS_NAME=...」完整地複製並貼上到 Render.com 的「Environment Variables」(秘密保險箱) 中！")
print("\n--- 神之鍛造廠：任務完畢 ---")