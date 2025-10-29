import os
import fitz  # PyMuPDF
import psycopg2
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer
import json
import sys

# --- ★★★【請您手動修改這裡】★★★ ---
# 
# 請您「完整地」複製貼上您在 Render 秘密保險箱中的 DATABASE_URL
# (★ 確保是「已移除」多餘單引號的「正確」版本！)
#
DATABASE_URL = "postgresql://neondb_owner:npg_vWtEfRAp3xI9@ep-wispy-frog-a1c8vdbz-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require" 
#
# --- ★★★【修改完畢】★★★ ---

MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
VECTOR_DIMENSION = 384 

def get_db_connection():
    """建立到 Neon 資料庫的連接"""
    print(f"--- 正在連接到 Neon 資料庫... ---")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        print("--- 資料庫連接成功！ ---")
        return conn
    except Exception as e:
        print(f"!!! 嚴重錯誤：無法連接到資料庫。錯誤：{e}")
        print("!!! 請檢查您在 `upload_vectors.py` 中貼上的 DATABASE_URL 是否 100% 正確！")
        return None

def read_pdfs_from_corpus():
    """從 'corpus' 資料夾讀取所有 PDF 並提取文字 (★ 已修復 NUL 錯誤 ★)"""
    print(f"--- (RAG) 正在從 'corpus' 資料夾讀取所有 PDF... ---")
    corpus_text = ""
    corpus_dir = 'corpus'

    if not os.path.exists(corpus_dir):
        print(f"!!! (RAG) 錯誤：找不到 '{corpus_dir}' 資料夾！")
        return ""

    for filename in os.listdir(corpus_dir):
        if filename.endswith('.pdf'):
            filepath = os.path.join(corpus_dir, filename)
            print(f"  > (RAG)  đang 讀取 PDF: {filename}")
            try:
                with fitz.open(filepath) as doc:
                    for page in doc:
                        clean_text = page.get_text().replace('\x00', '')
                        corpus_text += clean_text + "\n\n"
            except Exception as pdf_e:
                print(f"!!! (RAG) 錯誤：讀取 PDF '{filename}' 失敗。錯誤：{pdf_e}")

        elif filename.endswith('.txt'):
            filepath = os.path.join(corpus_dir, filename)
            print(f"  > (RAG) 正在讀取 TXT: {filename}")
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    clean_text = f.read().replace('\x00', '')
                    corpus_text += clean_text + "\n\n"
            except Exception as txt_e:
                print(f"!!! (RAG) 錯誤：讀取 TXT '{filename}' 失敗。錯誤：{txt_e}")

    print(f"--- (RAG) 所有 PDF 讀取完畢。總共 {len(corpus_text)} 字元 (已清洗) ---")
    return corpus_text

def chunk_text(text, chunk_size=1000, overlap=200):
    """將長文本切割成帶有重疊的段落 (Chunk)"""
    print(f"--- (RAG) 正在將 {len(text)} 字元的文本切割成段落... ---")
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
        if start + chunk_size - overlap <= start:
            break

    if end < len(text) and start <= len(text):
         chunks.append(text[start:])

    print(f"--- (RAG) 文本切割完畢，共產生 {len(chunks)} 個段落 (Chunks) ---")
    return chunks

def main():
    """主執行函數：(★ 已修復超時錯誤：改變順序 ★)"""

    # 檢查 DATABASE_URL 是否已更新
    if "postgresql://neondb_owner:npg_vWtEf...sslmode=require" in DATABASE_URL:
        print("="*50)
        print("!!! 警告：您尚未更新 `upload_vectors.py` 中的 DATABASE_URL！")
        print("!!! 請將第 14 行的範例 URL 替換為您真正的 Neon 連接字串！")
        print("="*50)
        sys.exit(1)

    # --- ★★★【步驟一：本地處理 (慢速)】★★★
    # (在連接資料庫「之前」完成所有慢速工作)
    try:
        print("--- (本地) 步驟 1/4：讀取並切割 PDF... ---")
        full_text = read_pdfs_from_corpus()
        if not full_text:
            print("!!! (RAG) 沒有讀取到任何文字，程式終止。")
            sys.exit(1)

        chunks = chunk_text(full_text)
        if not chunks:
            print("!!! (RAG) 沒有產生任何文字段落，程式終止。")
            sys.exit(1)

        print(f"--- (本地) 步驟 2/4：載入向量模型 '{MODEL_NAME}'... (可能需要幾分鐘) ---")
        model = SentenceTransformer(MODEL_NAME)
        print("--- (本地) 向量模型載入成功！ ---")

        print(f"--- (本地) 步驟 3/4：將 {len(chunks)} 個段落轉換為向量... (這也會需要一點時間) ---")
        embeddings = model.encode(chunks)
        print(f"--- (本地) 向量轉換完畢！共 {len(embeddings)} 個向量 ---")

    except Exception as e:
        print(f"\n\n!!! 災難級錯誤：在「本地處理」過程中失敗。錯誤：{e}")
        sys.exit(1)

    # --- ★★★【步驟二：資料庫處理 (快速)】★★★
    # (所有慢速工作都完成了，「現在」才連接資料庫)
    conn = None # 初始化 conn
    try:
        print(f"\n--- (遠端) 步驟 4/4：連接資料庫並上傳 {len(chunks)} 筆資料... ---")
        conn = get_db_connection()
        if not conn:
            sys.exit(1)

        # 註冊向量類型 (現在連接是「新鮮的」，100% 會成功)
        register_vector(conn)
        print("--- (SQL) 向量類型 `register_vector` 成功 ---")

        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("--- (SQL) `vector` 擴充功能已確認 ---")

            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS physics_vectors (
                    id SERIAL PRIMARY KEY,
                    content TEXT,
                    embedding VECTOR({VECTOR_DIMENSION})
                );
            """)
            print(f"--- (SQL) `physics_vectors` 表格 (維度 {VECTOR_DIMENSION}) 已確認/建立 ---")

            cur.execute("TRUNCATE TABLE physics_vectors RESTART IDENTITY;")
            print("--- (SQL) 已清空舊的向量資料... ---")

            print("--- (SQL) 正在將資料「高速」上傳到 Neon 資料庫... ---")
            for i in range(len(chunks)):
                content = chunks[i]
                embedding = embeddings[i]
                cur.execute(
                    "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                    (content, embedding)
                )

            conn.commit() # ★ 提交所有變更

            print(f"\n\n--- ★★★ 最終勝利！ ★★★ ---")
            print(f"--- ★★★ 成功將 {len(chunks)} 個「教科書段落向量」上傳到 Neon 資料庫！ ★★★ ---")

    except Exception as e:
        print(f"\n\n!!! 災難級錯誤：在「資料庫上傳」過程中失敗。錯誤：{e}")
        if conn:
            conn.rollback() # 如果出錯，撤銷所有變更
    finally:
        if conn:
            conn.close()
            print("--- 資料庫連接已關閉 ---")

if __name__ == "__main__":
    main()