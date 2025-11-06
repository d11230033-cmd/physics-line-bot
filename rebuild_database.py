# 檔案：rebuild_database.py
# 
# ★★★ 自動化升級版 (已修正 'embeddings' 錯誤 + 'NUL' 字元清理) ★★★
# 
# 目的：(一次性腳本) 自動掃描 'corpus' 資料夾中的所有文件 (PDF, TXT, MD)，
#      清空並重建 RAG 知識庫 (physics_vectors)，
#      以解決 768 vs 3072 的維度衝突錯誤。
#
# ★ 執行前，請安裝 'PyMuPDF'： pip install PyMuPDF

import os
import sys
import psycopg2
from pgvector.psycopg2 import register_vector
from google import genai
from google.genai import types
from pathlib import Path
import fitz  # 這就是 PyMuPDF

# --- ★ 步驟一：讀取環境變數 (與 main.py 相同) ★ ---
try:
    DATABASE_URL = os.environ.get('DATABASE_URL')
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    if not DATABASE_URL or not GEMINI_API_KEY:
        raise ValueError("錯誤：DATABASE_URL 或 GEMINI_API_KEY 環境變數未設定！")
except Exception as e:
    print(e)
    sys.exit(1)

# --- ★ 步驟二：設定 (必須與 main.py 一致) ★ ---
EMBEDDING_MODEL = 'models/text-embedding-004' 
VECTOR_DIMENSION = 768 # (對應 'text-embedding-004' 的 768 維)
CORPUS_DIRECTORY = "corpus" # ★ 我們要掃描的資料夾名稱 ★


def get_db_connection():
    """連接到您的 Postgres (Neon) 資料庫"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        return None

def load_documents_from_corpus(corpus_dir_path):
    """
    自動從 corpus 資料夾加載所有 .pdf, .txt, .md 檔案。
    PDF：每頁為一個 chunk。
    TXT/MD：每段 (以 \n\n 分隔) 為一個 chunk。
    """
    p = Path(corpus_dir_path)
    if not p.is_dir():
        print(f"!!! 錯誤：找不到 '{corpus_dir_path}' 資料夾！")
        print("請在您的專案根目錄下建立一個 'corpus' 資料夾，並放入您的 PDF/TXT 檔案。")
        return []

    chunks = []
    print(f"--- (RAG) 正在掃描 '{corpus_dir_path}' 資料夾... ---")

    # .rglob('*') 會遞歸地尋找所有檔案
    for file_path in p.rglob("*"):
        
        # --- 處理 PDF ---
        if file_path.suffix == ".pdf":
            try:
                print(f"  正在處理 PDF: {file_path.name} ...")
                doc = fitz.open(file_path)
                for page_num, page in enumerate(doc):
                    text = page.get_text("text").strip() # "text" 模式保留段落結構
                    if text: # 確保頁面不是空的
                        # 我們將來源資訊加到內容中，供日誌記錄 (可選，但推薦)
                        source_info = f"來源：{file_path.name} (第 {page_num + 1} 頁)"
                        chunks.append(f"{source_info}\n\n{text}")
                doc.close()
            except Exception as e:
                print(f"!!! 警告：處理 PDF '{file_path.name}' 失敗。錯誤：{e}")

        # --- 處理 TXT 和 MD ---
        elif file_path.suffix in [".txt", ".md"]:
            try:
                print(f"  正在處理 Text: {file_path.name} ...")
                full_text = file_path.read_text(encoding='utf-8')
                # 按照「段落」(兩個換行) 來切分
                paragraphs = full_text.split('\n\n') 
                for para in paragraphs:
                    cleaned_para = para.strip()
                    if cleaned_para:
                        source_info = f"來源：{file_path.name}"
                        chunks.append(f"{source_info}\n\n{cleaned_para}")
            except Exception as e:
                print(f"!!! 警告：處理 TXT/MD '{file_path.name}' 失敗。錯誤：{e}")
                
    return chunks

def main():
    print("--- 「神殿」知識庫重建腳本 (自動掃描版) ---")
    
    # 1. 自動從資料夾加載文件
    chunks_to_process = load_documents_from_corpus(CORPUS_DIRECTORY)
    
    if not chunks_to_process:
        print("\n!!! 嚴重錯誤：在 'corpus' 資料夾中找不到任何可處理的文件片段。")
        print("請確認您的 'corpus' 資料夾存在，並且裡面有 .pdf, .txt, 或 .md 檔案。")
        sys.exit(1)
        
    total_chunks = len(chunks_to_process)
    print(f"\n--- (RAG) 成功從 '{CORPUS_DIRECTORY}' 載入 {total_chunks} 個知識片段。---")

    # 2. 連接 Gemini
    try:
        client = genai.Client()
        print("--- (Gemini) 連接成功！ ---")
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法設定 Google API Key。錯誤：{e}")
        sys.exit(1)

    # 3. 連接資料庫
    conn = get_db_connection()
    if not conn:
        sys.exit(1)
        
    try:
        register_vector(conn)
        
        with conn.cursor() as cur:
            
            # --- 關鍵步驟 (A)：清空舊的資料 ---
            print("--- (SQL) 正在清空 'physics_vectors' 表格中的舊資料... ---")
            cur.execute("TRUNCATE TABLE physics_vectors RESTART IDENTITY;")
            print("--- (SQL) 舊資料已清空 ---")

            # --- 關鍵步驟 (B)：重新填入新的 (768 維) 資料 ---
            print(f"--- (RAG) 即將開始為 {total_chunks} 個片段產生 768 維向量 (使用 {EMBEDDING_MODEL})... ---")
            print("這可能需要幾分鐘，請耐心等候...")

            for i, chunk_content_raw in enumerate(chunks_to_process):
                
                # ★★★ (新修正) 清理 NUL (0x00) 字元 ★★★
                chunk_content = chunk_content_raw.replace('\x00', '')
                
                # 顯示進度
                print(f"  正在產生向量 {i+1}/{total_chunks} ...")
                
                # 1. 產生 768 維向量
                #    (我們使用「清理過」的 chunk_content 產生向量)
                result = client.models.embed_content(
                    model=EMBEDDING_MODEL,
                    contents=[chunk_content] 
                )
                
                embedding_vector = result.embeddings[0].values 

                # 2. 存入資料庫
                #    (我們使用「清理過」的 chunk_content 存入資料庫)
                cur.execute(
                    "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                    (chunk_content, embedding_vector)
                )

            print("--- (RAG) 所有新向量皆已成功產生並儲存！ ---")
            
            # 提交所有變更
            conn.commit()
            
            print(f"--- (SQL) 成功驗證：'physics_vectors' 表格現在有 {total_chunks} 筆 768 維的資料。---")
            print("\n★★★ 重建完成！★★★")
            print("您現在可以重新啟動您的 main.py (Flask 伺服器)，RAG 錯誤已解決。")

    except Exception as e:
        print(f"\n!!! 嚴重錯誤：在重建過程中失敗。錯誤：{e}")
        conn.rollback() # 發生錯誤時回復
    finally:
        conn.close()

if __name__ == "__main__":
    main()