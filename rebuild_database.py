# 檔案：rebuild_database.py
# 
# ★★★ (最終版) 自動化升級版 (已修正 'embeddings', 'NUL' 錯誤) ★★★
# ★★★ (新功能) 新增「延遲」與「自動重試」以處理 API 速率限制 (500 錯誤) ★★★

import os
import sys
import psycopg2
from pgvector.psycopg2 import register_vector
from google import genai
from google.genai import types
from pathlib import Path
import fitz  # 這就是 PyMuPDF
import time  # ★ (新功能) 引入 time 模組來控制延遲

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
VECTOR_DIMENSION = 768 
CORPUS_DIRECTORY = "corpus" 

# --- ★ (新功能) 延遲與重試設定 ★ ---
REQUEST_DELAY = 0.5  # (秒) 每次 API 呼叫之間延遲 0.5 秒 (避免速率限制)
MAX_RETRIES = 3      # 每個片段最多重試 3 次
RETRY_DELAY = 5      # (秒) 重試前等待 5 秒

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
    """
    p = Path(corpus_dir_path)
    if not p.is_dir():
        print(f"!!! 錯誤：找不到 '{corpus_dir_path}' 資料夾！")
        return []

    chunks = []
    print(f"--- (RAG) 正在掃描 '{corpus_dir_path}' 資料夾... ---")

    for file_path in p.rglob("*"):
        
        if file_path.suffix == ".pdf":
            try:
                print(f"  正在處理 PDF: {file_path.name} ...")
                doc = fitz.open(file_path)
                for page_num, page in enumerate(doc):
                    text = page.get_text("text").strip() 
                    if text:
                        source_info = f"來源：{file_path.name} (第 {page_num + 1} 頁)"
                        chunks.append(f"{source_info}\n\n{text}")
                doc.close()
            except Exception as e:
                print(f"!!! 警告：處理 PDF '{file_path.name}' 失敗。錯誤：{e}")

        elif file_path.suffix in [".txt", ".md"]:
            try:
                print(f"  正在處理 Text: {file_path.name} ...")
                full_text = file_path.read_text(encoding='utf-8')
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
    print("--- 「神殿」知識庫重建腳本 (自動掃描 + 延遲 + 重試版) ---")
    
    chunks_to_process = load_documents_from_corpus(CORPUS_DIRECTORY)
    
    if not chunks_to_process:
        print("\n!!! 嚴重錯誤：在 'corpus' 資料夾中找不到任何可處理的文件片段。")
        sys.exit(1)
        
    total_chunks = len(chunks_to_process)
    print(f"\n--- (RAG) 成功從 '{CORPUS_DIRECTORY}' 載入 {total_chunks} 個知識片段。---")

    try:
        client = genai.Client()
        print("--- (Gemini) 連接成功！ ---")
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法設定 Google API Key。錯誤：{e}")
        sys.exit(1)

    conn = get_db_connection()
    if not conn:
        sys.exit(1)
        
    try:
        register_vector(conn)
        
        with conn.cursor() as cur:
            
            print("--- (SQL) 正在清空 'physics_vectors' 表格中的舊資料... ---")
            cur.execute("TRUNCATE TABLE physics_vectors RESTART IDENTITY;")
            print("--- (SQL) 舊資料已清空 ---")

            print(f"--- (RAG) 即將開始為 {total_chunks} 個片段產生 {VECTOR_DIMENSION} 維向量... ---")
            print(f"--- (RAG) 由於已啟用 {REQUEST_DELAY} 秒延遲，預計總耗時約 { (total_chunks * REQUEST_DELAY / 60):.1f} 分鐘... ---")

            for i, chunk_content_raw in enumerate(chunks_to_process):
                
                # (1) 清理 NUL (0x00) 字元
                chunk_content = chunk_content_raw.replace('\x00', '')
                
                print(f"  正在處理片段 {i+1}/{total_chunks} ...")
                
                embedding_vector = None
                retries_left = MAX_RETRIES

                # ★★★ (新功能) 自動重試迴圈 ★★★
                while retries_left > 0:
                    try:
                        # (A) ★ (新功能) 禮貌性延遲 ★
                        time.sleep(REQUEST_DELAY)

                        # (B) 嘗試呼叫 API
                        result = client.models.embed_content(
                            model=EMBEDDING_MODEL,
                            contents=[chunk_content] 
                        )
                        embedding_vector = result.embeddings[0].values
                        
                        # (C) 成功 -> 跳出重試迴圈
                        break 
                    
                    except Exception as e:
                        print(f"!!! 警告：API 呼叫失敗 (片段 {i+1})。錯誤：{e}")
                        retries_left -= 1
                        
                        if retries_left > 0:
                            print(f"    ... 正在重試 (剩餘 {retries_left} 次)，等待 {RETRY_DELAY} 秒...")
                            time.sleep(RETRY_DELAY)
                        else:
                            print(f"!!! 嚴重錯誤：片段 {i+1} 重試 {MAX_RETRIES} 次後仍然失敗。")
                            print(f"    失敗的片段內容 (前 50 字)：{chunk_content[:50]}...")
                            # 拋出錯誤，中止整個腳本
                            raise e

                # (2) 存入資料庫 (僅在重試成功後)
                if embedding_vector:
                    cur.execute(
                        "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                        (chunk_content, embedding_vector)
                    )
                else:
                    # (理論上 'raise e' 會阻止程式跑到這裡，但作為保險)
                    print(f"!!! 嚴重錯誤：片段 {i+1} 未能產生向量，已跳過。")


            print("--- (RAG) 所有新向量皆已成功產生並儲存！ ---")
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