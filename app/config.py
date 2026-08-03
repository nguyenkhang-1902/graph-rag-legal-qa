"""Config trung tâm cho graph-rag-legal-qa (T004).

Constitution Điều 4 (hằng số qua config, đọc từ `.env`, không hard-code
rải rác trong code). Mọi ngưỡng/hằng số dùng ở nhiều module (số hop
traverse, ngưỡng similarity, batch size ingest, kết nối Neo4j/Ollama/
Chroma) PHẢI đọc qua module này, không đọc `os.environ` trực tiếp ở nơi
khác.

Giá trị mặc định khớp `.env.example`. `INGEST_BATCH_SIZE=200` là giá trị
khởi điểm (xem `research.md` ADR-002 và `CHECKLIST-GRAPHRAG-DUYET.md` D1)
— sẽ điều chỉnh sau khi đo throughput LLM extraction thật trên 100-200
văn bản đầu, không phải giá trị cuối cùng.
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- Retrieval / traversal (spec.md FR-005, FR-004) ---
MAX_HOP: int = int(os.getenv("MAX_HOP", "2"))
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))

# --- Ingest (spec.md FR-008 / research.md ADR-002) ---
INGEST_BATCH_SIZE: int = int(os.getenv("INGEST_BATCH_SIZE", "200"))

# --- Neo4j (constitution Điều 10 — auth luôn bật, credentials qua .env) ---
NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "changeme")

# --- Ollama (LLM local, constitution "Nền tảng & hạ tầng") ---
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

# --- Chroma (vector store, chỉ dùng tìm entry-point — data-model.md) ---
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
