import os
import fitz  # PyMuPDF
import psycopg2
from pgvector.psycopg2 import register_vector
# ★ 移除了 import SentenceTransformer ★
import google.generativeai as genai # ★ 改用 Gemini！
import json
import sys
import time # ★ 引入 time 模組來處理 API 速率

# --- ★★★【請您手動修改這裡 (2 個)】★★★ ---
#
# 1. 貼上您「真正」的 DATABASE_URL
DATABASE_URL = "postgresql://neondb_owner:npg_vWtEfRAp3xI9@ep-wispy-frog-a1c8vdbz-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require" 
#
# 2. 貼上您「真正」的 GOOGLE_API_KEY
GOOGLE_API_KEY = "AIzaSyCb6ugnXxrTUxtDYpIrHJxJ-B_l7_XC3L0"
#
# --- ★★★【修改完畢】★★★ ---

# ★ 使用 Gemini 的嵌入模型
EMBEDDING_MODEL = 'models/text-embedding-004' # (0.8.5 兼容)
VECTOR_DIMENSION = 768 # ★ 向量維度改為 768

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
            print(f"  > (RAG) 正在讀取 PDF: {filename}")
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
    """主執行函數：(★ 第五紀元：Gemini Embedding 版 ★)"""

    # 檢查金鑰
    if "postgresql://neondb_owner:npg_vWtEf...sslmode=require" in DATABASE_URL:
        print("="*50)
        print("!!! 警告：您尚未更新 `upload_vectors.py` 中的 DATABASE_URL！")
        print("="*50)
        sys.exit(1)
    if "AIzaSy...YOUR_KEY_HERE" in GOOGLE_API_KEY:
        print("="*50)
        print("!!! 警告：您尚未更新 `upload_vectors.py` 中的 GOOGLE_API_KEY！")
        print("="*50)
        sys.exit(1)

    # --- ★★★【步驟一：本地處理 (慢速)】★★★
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

        # ★ 改為配置 Gemini API
        print(f"--- (本地) 步驟 2/4：配置 Google Gemini API... ---")
        genai.configure(api_key=GOOGLE_API_KEY)
        print("--- (本地) Gemini API 配置成功！ ---")

        # ★ 改為使用 Gemini API 轉換向量
        # Gemini API 有速率限制 (QPM)，我們需要分批處理並加入延遲
        print(f"--- (本地) 步驟 3/4：將 {len(chunks)} 個段落轉換為 Gemini 向量... ---")
        embeddings = []
        batch_size = 25 # 速率限制約 1500/min (25/sec)，我們保守一點
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i+batch_size]
            try:
                # (0.8.5 版的語法)
                result = genai.embed_content(
                    model=EMBEDDING_MODEL,
                    content=batch_chunks,
                    task_type="retrieval_document"
                )
                embeddings.extend(result['embedding'])
                print(f"  > (AI) 已處理 {len(embeddings)} / {len(chunks)} 個向量...")
            except Exception as embed_e:
                print(f"!!! (AI) 錯誤：Gemini Embedding API 呼叫失敗。錯誤：{embed_e}")
                # 如果 API 報錯 (例如速率)，我們等待更久
                print("... API 呼叫失敗，等待 20 秒後重試 ...")
                time.sleep(20)
                # 重試一次
                try:
                    result = genai.embed_content(
                        model=EMBEDDING_MODEL,
                        content=batch_chunks,
                        task_type="retrieval_document"
                    )
                    embeddings.extend(result['embedding'])
                    print(f"  > (AI) (重試成功) 已處理 {len(embeddings)} / {len(chunks)} 個向量...")
                except Exception as embed_e2:
                    print(f"!!! (AI) 嚴重錯誤：重試失敗！錯誤：{embed_e2}。跳過此批次。")

            # 嚴格遵守速率限制，每批次後等待
            time.sleep(1.2) # 每秒處理 25 個

        print(f"--- (本地) 向量轉換完畢！共 {len(embeddings)} 個向量 ---")

    except Exception as e:
        print(f"\n\n!!! 災難級錯誤：在「本地處理」過程中失敗。錯誤：{e}")
        sys.exit(1)

    # --- ★★★【步驟二：資料庫處理 (快速)】★★★
    conn = None
    try:
        print(f"\n--- (遠端) 步驟 4/4：連接資料庫並上傳 {len(embeddings)} 筆資料... ---")
        conn = get_db_connection()
        if not conn:
            sys.exit(1)

        register_vector(conn)
        print("--- (SQL) 向量類型 `register_vector` 成功 ---")

        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("--- (SQL) `vector` 擴充功能已確認 ---")

            # ★ 重建表格！刪除舊的 384 維表格！
            cur.execute("DROP TABLE IF EXISTS physics_vectors;")
            print("--- (SQL) ★ 已刪除舊的 `physics_vectors` 表格 ★ ---")

            # ★ 建立新的 768 維表格！
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS physics_vectors (
                    id SERIAL PRIMARY KEY,
                    content TEXT,
                    embedding VECTOR({VECTOR_DIMENSION})
                );
            """)
            print(f"--- (SQL) ★ 新的 `physics_vectors` 表格 (維度 {VECTOR_DIMENSION}) 已確認/建立 ★ ---")

            print("--- (SQL) 正在將資料「高速」上傳到 Neon 資料庫... ---")
            for i in range(len(embeddings)):
                content = chunks[i] # 確保 chunks 和 embeddings 索引一致
                embedding = embeddings[i]
                cur.execute(
                    "INSERT INTO physics_vectors (content, embedding) VALUES (%s, %s)",
                    (content, embedding)
                )

            conn.commit()

            print(f"\n\n--- ★★★ 最終勝利！ (第五紀元) ★★★ ---")
            print(f"--- ★★★ 成功將 {len(embeddings)} 個「Gemini 向量」上傳到 Neon 資料庫！ ★★★ ---")

    except Exception as e:
        print(f"\n\n!!! 災難級錯誤：在「資料庫上傳」過程中失敗。錯誤：{e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("--- 資料庫連接已關閉 ---")

if __name__ == "__main__":
    main()