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
# 0.65 (khong phai 0.75 khoi tao luc scaffold T004) - hieu chinh bang du
# lieu that T017 (research.md ADR-004): 0.75 loc oan 52% expected_article_id
# dung (trung vi similarity cua ket qua dung ~0.7426), Strict recall
# 59.4%->90.6% sau khi ha xuong 0.65. Da doc tay 10/10 case "lat" + held-out
# split-half xac nhan khong phai overfitting - xem ADR-004 chi tiet.
SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.65"))

# So Article toi da dua vao ngu canh cho LLM (T028). 10 KHONG phai so tuy y -
# do that tren 793 cau Zalo gold cho thay recall BAO HOA dung o day:
#   k        4      6      8     10     12     15     20
#   Recall 71.1%  74.0%  75.2%  75.4%  75.4%  75.4%  75.4%
# Sau khi them vector cap Khoan, so ung vien trung binh tang 6.0 -> 17.1
# Article/cau hoi. Cat o 10 KHONG MAT GI ve recall ma giam 41% luong ngu canh
# (LLM nhanh hon, it nhieu hon). Doi so nay thi PHAI do lai, khong doan.
MAX_CONTEXT_ARTICLES: int = int(os.getenv("MAX_CONTEXT_ARTICLES", "10"))

# --- Ingest (spec.md FR-008 / research.md ADR-002) ---
INGEST_BATCH_SIZE: int = int(os.getenv("INGEST_BATCH_SIZE", "200"))

# --- Neo4j (constitution Điều 10 — auth luôn bật, credentials qua .env) ---
NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "changeme")

# --- Ollama (LLM local, constitution "Nền tảng & hạ tầng") ---
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")
# num_ctx: cua so ngu canh Ollama. Mac dinh qwen2.5 chi 2048/4096 -> 10 Dieu
# luat (co Dieu dai) VUOT -> ngu canh bi CAT AM THAM -> LLM tra loi lech/lan
# (vd nham "Luat 2014"). Dat 8192 de chua du ngu canh + prompt. temperature
# thap de tra loi bam ngu canh, it bia (P3).
OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
OLLAMA_TEMPERATURE: float = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))

# --- Reranker (cross-encoder, P3) ---
# Sau entry-point (dense) + traversal, cham diem lai ung vien theo query bang
# cross-encoder -> Dieu dung trong tam len dau truoc khi cat MAX_CONTEXT_ARTICLES
# (giai quyet Q bam Dieu phu). Model DA cache offline.
RERANK_ENABLED: bool = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANKER_MODEL: str = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
# CPU: GPU 8GB da co bge-m3 (embedder) + qwen-7b (Ollama) -> reranker GPU se
# OOM. CPU cham hon (~vai giay/cau) nhung an toan.
RERANKER_DEVICE: str = os.getenv("RERANKER_DEVICE", "cpu")
RERANKER_MAX_LENGTH: int = int(os.getenv("RERANKER_MAX_LENGTH", "1024"))
# So ung vien fetch de rerank (rong hon MAX_CONTEXT_ARTICLES de reranker co
# du lua chon truoc khi cat).
RERANK_FETCH_K: int = int(os.getenv("RERANK_FETCH_K", "15"))

# --- Chroma (vector store, chỉ dùng tìm entry-point — data-model.md) ---
CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
CHROMA_COLLECTION_NAME: str = os.getenv("CHROMA_COLLECTION_NAME", "legal_articles")

# --- Embedding (T009f — app/retrieval/embedder.py + scripts/backfill_embeddings.py,
# research.md sổ bẫy 12e: model reload crash trên Windows nếu không cache) ---
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
# Batch size cho embedding inference (T009f) — KHÁC với INGEST_BATCH_SIZE
# (batch số file ingest vào Neo4j/checkpoint): đây là batch số text đưa vào
# 1 lần gọi model, throughput characteristics khác nhau, không gộp chung.
EMBED_BATCH_SIZE: int = int(os.getenv("EMBED_BATCH_SIZE", "32"))
