import json
import os
import chromadb
from sentence_transformers import SentenceTransformer
from config import DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL

DATA_FILE = "data_for_rag.json"

def main():
    # 1. 讀取資料
    if not os.path.exists(DATA_FILE):
        print(f"❌ 找不到 {DATA_FILE}")
        return

    print("📖 正在讀取 JSON 資料...")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        chunks = data['chunks'] # 只讀取 chunks 部分

    # 2. 初始化 Embedding 模型
    print(f"📥 載入 Embedding 模型: {EMBEDDING_MODEL}...")
    # normalize_embeddings=True 對於 Cosine Similarity 很重要
    model = SentenceTransformer(EMBEDDING_MODEL)

    # 3. 初始化 ChromaDB (持久化儲存)
    print(f"💽 初始化 ChromaDB (儲存於 {DB_PATH})...")
    client = chromadb.PersistentClient(path=DB_PATH)
    
    # 如果集合已存在，先刪除舊的以確保資料乾淨 (可選)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print("   已清除舊的 Collection")
    except:
        pass

    # 建立新集合
    # metadata={"hnsw:space": "cosine"} 設定使用餘弦相似度
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"} 
    )

    # 4. 批次處理並寫入資料庫
    print(f"🚀 開始將 {len(chunks)} 筆資料寫入資料庫...")
    
    ids = []
    documents = []
    embeddings = []

    # 為了顯示進度，簡單用 batch 處理
    batch_size = 32
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i : i + batch_size]
        
        # 準備資料
        batch_texts = [c['content'] for c in batch_chunks]
        batch_ids = [str(c['chunk_id']) for c in batch_chunks] # ID 必須是字串

        # 轉向量
        batch_embeddings = model.encode(batch_texts, normalize_embeddings=True)
        
        # 加入列表
        ids.extend(batch_ids)
        documents.extend(batch_texts)
        embeddings.extend(batch_embeddings.tolist())
        
        print(f"   已處理 {i + len(batch_chunks)} / {len(chunks)}")

    # 5. 一次性寫入 Chroma
    collection.add(
        documents=documents,
        embeddings=embeddings,
        ids=ids
    )

    print(f"✅ 建庫完成！資料已儲存至 {DB_PATH}")

if __name__ == "__main__":
    main()