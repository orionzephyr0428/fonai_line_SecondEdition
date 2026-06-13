import os
from dotenv import load_dotenv
load_dotenv()

# ── LINE Bot ─────────────────────────────
LINE_CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')

# ── MySQL ────────────────────────────────
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', 3306))
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')

# ── ChromaDB ─────────────────────────────
DB_PATH = os.getenv('DB_PATH')
COLLECTION_NAME = os.getenv('COLLECTION_NAME')

# ── AI 模型 ───────────────────────────────
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL')
RERANKER_MODEL = os.getenv('RERANKER_MODEL')
ZAI_API_KEY = os.getenv('ZaiClient_api_key')

# ── 呼叫crawler ───────────────────────────
CRAWLER_BASE_URL = os.getenv('CRAWLER_BASE_URL')
REQUEST_TIMEOUT_CONNECT = int(os.getenv('REQUEST_TIMEOUT_CONNECT', 10))
REQUEST_TIMEOUT_READ = int(os.getenv('REQUEST_TIMEOUT_READ', 120))