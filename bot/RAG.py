import json
import logging
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from zai import ZaiClient
from config import DB_PATH, COLLECTION_NAME, EMBEDDING_MODEL, RERANKER_MODEL, ZAI_API_KEY
from db import get_connection

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
你是一位專業且親切的長照知識助手。你的任務是協助民眾理解複雜的長照資訊。
請根據提供的「參考資料」回答使用者的問題。

回答原則：
1. 白話與整理：請將參考資料中的資訊「消化整理」過，用淺顯易懂的白話文簡短回答。
   - 避免直接複製貼上生硬的法規文字。
   - 使用數字編號（1. 2. 3.）來呈現重點，讓長輩或家屬能一目了然。
2. 容忍錯別字：若使用者的問題有錯字（例如「申青」），請自動視為正確術語（例如「申請」）並回答。
3. 忠於資料：答案的核心事實必須來自參考資料，不可憑空捏造。
4. 無資料時：只有在參考資料「完全不相關」或「找不到答案」時，才回答「資料庫中沒有相關資訊」。
5. 格式限制：回答時絕對禁止使用以下符號：
   - 禁止使用星號 *
   - 禁止使用雙星號 **
   - 禁止使用井號 #
   - 禁止使用反引號 `
   - 禁止使用底線強調 _
   請使用純文字格式回答，可以用數字編號（1. 2. 3.）或換行來分段。
"""

# 改寫問題用的 Prompt
REWRITE_PROMPT_TEMPLATE = """你的任務是將「最新問題」補充完整，讓它變成一個可以獨立搜尋的完整句子。

規則：
1. 根據「對話歷史」判斷使用者在討論什麼主題
2. 如果「最新問題」缺少主詞或主題，請補上
3. 只輸出改寫後的句子，不要有任何解釋或前綴

範例1：
對話歷史：長照服務
最新問題：怎麼收費
輸出：長照服務怎麼收費

範例2：
對話歷史：日間照顧中心
最新問題：申請條件
輸出：日間照顧中心的申請條件

範例3：
對話歷史：居家服務
最新問題：費用多少
輸出：居家服務費用多少

現在請處理：
對話歷史：{history}
最新問題：{question}
輸出："""

class RAGSystem:
    def __init__(self, user_id=None):
        logger.info("正在啟動 RAG 系統...")

        self.user_id = user_id

        # 1. 連接 ChromaDB
        self.client = chromadb.PersistentClient(path=DB_PATH)
        self.collection = self.client.get_collection(name=COLLECTION_NAME)

        # 2. 載入 Embedding 模型 (用於檢索)
        logger.info(f"載入 Embedding 模型: {EMBEDDING_MODEL}")
        self.embed_model = SentenceTransformer(EMBEDDING_MODEL)

        # 3. 載入 Reranker 模型 (用於精排序)
        logger.info(f"載入 Reranker 模型: {RERANKER_MODEL}")
        self.reranker = CrossEncoder(RERANKER_MODEL)

        # 4. 初始化 LLM Client (Zai)
        logger.info("初始化 LLM Client...")
        self.llm_client = ZaiClient(api_key=ZAI_API_KEY)

        # 5. 從資料庫載入對話記憶
        self.max_history_turns = 3
        self.chat_history = self._load_chat_history()

        logger.info("RAG 系統就緒")
        
    def _load_chat_history(self):
        """從資料庫載入 chat_history"""
        if not self.user_id:
            return []
        
        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT chat_history FROM user_state WHERE user_id = %s",
                (self.user_id,)
            )
            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result and result['chat_history']:
                return json.loads(result['chat_history'])
            return []

        except Exception as e:
            logger.error(f"載入對話記憶失敗: {e}")
            return []
        
    def _save_chat_history(self):
        """將 chat_history 儲存到資料庫"""
        if not self.user_id:
            return
        
        try:
            # 限制記憶長度：超過 3 輪對話（6 則訊息）就刪掉最舊的
            max_messages = self.max_history_turns * 2  # 3 輪 = 6 則訊息
            if len(self.chat_history) > max_messages:
                # 只保留最新的 6 則訊息
                self.chat_history = self.chat_history[-max_messages:]
            
            conn = get_connection()
            cursor = conn.cursor()
            history_json = json.dumps(self.chat_history, ensure_ascii=False)
            cursor.execute(
                "UPDATE user_state SET chat_history = %s WHERE user_id = %s",
                (history_json, self.user_id)
            )
            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            logger.error(f"儲存對話記憶失敗: {e}")

    def _rewrite_query(self, user_question):
        """
        [內部方法] 利用 LLM 改寫問題
        """
        # 如果沒有歷史紀錄，不需要改寫，直接回傳原問題
        if not self.chat_history:
            return user_question

        user_questions = [msg['content'] for msg in self.chat_history if msg["role"] == "user"]
        recent_questions = user_questions[-2:] if len(user_questions) > 2 else user_questions

        if not recent_questions:
            return user_question

        # 將歷史問題合併成一個主題字串
        history_str = "、".join(recent_questions)
        
        prompt = REWRITE_PROMPT_TEMPLATE.format(history=history_str, question=user_question)

        logger.info(f"改寫用的歷史問題: {recent_questions}")

        try:
            response = self.llm_client.chat.completions.create(
                model="glm-4.5-flash",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3
            )
            rewritten_query = response.choices[0].message.content.strip()
            logger.info(f"LLM 改寫結果: {rewritten_query}")

            prefixes_to_remove = ["輸出：", "輸出:", "改寫後：", "改寫後:"]
            for prefix in prefixes_to_remove:
                if rewritten_query.startswith(prefix):
                    rewritten_query = rewritten_query[len(prefix):].strip()

            if not rewritten_query or len(rewritten_query) < 2:
                logger.warning("改寫結果為空，使用原始問題")
                return user_question

            return rewritten_query
        except Exception as e:
            logger.error(f"改寫失敗，使用原始問題: {e}")
            return user_question

    def retrieve(self, user_question, top_k_retrieval=10, top_n_rerank=3):
        """
        1. 轉向量 -> 2. 初步檢索 (Top 10) -> 3. Rerank (Top 3)
        """
        # --- 步驟 A: 向量檢索 (Retrieval) ---
        # BGE 模型建議在 Query 前面加上特定指令以提升效果 
        query_instruction = "為這個句子生成表示以用於檢索相關文章："
        query_emb = self.embed_model.encode(query_instruction + user_question, normalize_embeddings=True).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_emb],
            n_results=top_k_retrieval,
            include=['documents'] # 我們需要內容跟 ID
        )
        
        # Chroma 回傳的是 list of list (因為可以一次查多個 query)，我們取第 0 個
        retrieved_docs = results['documents'][0]
        retrieved_ids = results['ids'][0]
        
        if not retrieved_docs:
            return []

        # --- 步驟 B: 重排序 (Rerank) ---
        # 準備 Reranker 需要的格式: [[Query, Doc1], [Query, Doc2]...]
        pairs = [[user_question, doc] for doc in retrieved_docs]
        
        # 計算分數 (Logits)
        scores = self.reranker.predict(pairs)
        
        # 結合資料並排序
        ranked_results = []
        for doc, chunk_id, score in zip(retrieved_docs, retrieved_ids, scores):
            ranked_results.append({
                "chunk_id": chunk_id,
                "content": doc,
                "score": float(score) # 轉成 float 方便閱讀
            })
            
        # 依照分數由高到低排序
        ranked_results.sort(key=lambda x: x['score'], reverse=True)
        
        # --- 🔥 修改開始：動態斷層篩選邏輯 ---
        
        # 1. 基礎過濾：先濾掉分數太爛的 (例如 < -8)
        valid_candidates = [res for res in ranked_results if res['score'] > 0]
        
        if not valid_candidates:
            return []

        return valid_candidates[:1]
    
    def chat(self, user_question):
        """改寫 -> 檢索 -> 生成 -> 記憶"""

        if user_question == "/clear":
            self.chat_history = []
            return "對話記憶已清除。", []

        logger.info("思考上下文中...")
        search_query = self._rewrite_query(user_question)

        if search_query != user_question:
            logger.info(f"問題改寫為: {search_query}")

        logger.info("正在搜尋資料...")
        
        # 1. 取得檢索結果
        top_chunks = self.retrieve(search_query)
        
        if not top_chunks:
            return "❌ 資料庫中找不到相關資訊，無法回答您的問題。", []

        # 顯示一下檢索到的 Chunk ID (方便 Debug)
        # print(f"   --> 參考了 Chunk IDs: {[c['chunk_id'] for c in top_chunks]}")

        # 2. 組合 Prompt
        # 將 Top Chunks 結合成字串
        context_str = "\n\n".join([f"【資料 {i+1}】: {c['content']}" for i, c in enumerate(top_chunks)])
        # print(f"\n🐛 [Debug] 餵給 LLM 的 Context 預覽:\n{context_str[:200]}...\n")
        # 3. 呼叫 LLM
        try:
            response = self.llm_client.chat.completions.create(
                model="glm-4.5-flash",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"參考資料:\n{context_str}\n\n問題: {user_question}\n回覆:"
                    }
                ],
                thinking={"type": "disabled"}, # 依照你的要求
                max_tokens=300,
                temperature=0.2,
            )
            
            answer = response.choices[0].message.content
            
            # 5. 更新對話記憶
            self.chat_history.append({"role": "user", "content": user_question})
            self.chat_history.append({"role": "assistant", "content": answer})
            
            self._save_chat_history()
            
            return answer, top_chunks

        except Exception as e:
            return f"❌ LLM 生成發生錯誤: {e}", top_chunks

_rag_instances = {}
_max_instances = 10

def get_rag_instance(user_id):
    global _rag_instances

    if len(_rag_instances) >= _max_instances and user_id not in _rag_instances:
        oldest_user = next(iter(_rag_instances))
        del _rag_instances[oldest_user]

    if user_id not in _rag_instances:
        _rag_instances[user_id] = RAGSystem(user_id=user_id)
    else:
        _rag_instances[user_id].chat_history = _rag_instances[user_id]._load_chat_history()

    return _rag_instances[user_id]

def main(user_question, user_id):
    rag = get_rag_instance(user_id=user_id)
    ai_response, references = rag.chat(user_question)
    return {
        'success': True,
        'answer': ai_response,
        'references': references
    }

# ===========================
# 測試區 (模擬使用者)
# ===========================
if __name__ == "__main__":
    rag = RAGSystem(user_id="113b6730-8447-4f80-a68a-e3650bd1363f")

    while True:
        user_input = input("\n請輸入問題 (輸入 q 離開): ")
        if user_input.lower() == 'q':
            break

        ai_response, references = rag.chat(user_input)
        print("\n🤖 AI 回答:")
        print(ai_response)

