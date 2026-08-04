"""embedder.py (T009f): module dung chung "noi chuyen voi embedding model +
Chroma" - dung boi CA `scripts/backfill_embeddings.py` (backfill mot lan cho
60,679 Article that da ingest vao Neo4j nhung chua co chroma_id, xem
task-3a-brief.md) LAN `retrieval/entry_point.py` (T010, chua lam - se dung
lai `embed_texts`/`get_chroma_collection` de embed cau hoi nguoi dung bang
CUNG mot model).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): load model
embedding (sentence-transformers, KHONG qua langchain wrapper - Dieu 1) +
truy cap Chroma collection. Khong chua logic doc file/parse/dedup (do la
app/ingest.py), khong chua logic CLI/orchestration (do la
scripts/backfill_embeddings.py).

=== Model caching (research.md so bay 12e) ===
Construct lai `SentenceTransformer(...)` nhieu lan trong CUNG mot tien
trinh - dac biet xen ke voi cac loi goi Ollama khac trong project nay - da
gay crash native that (access violation 0xC0000005) tren Windows o du an
truoc (D:\\RAG Chatbot\\app\\vectorstore.py, xem comment o do). Module nay
dung CUNG pattern: cache model + Chroma collection o cap module (dict
"_instance", khong phai bien module truc tiep - de co the reset duoc trong
test) - CHI load 1 lan cho ca process, moi loi goi `embed_texts`/
`get_chroma_collection` sau do tai su dung instance da cache.

Device selection (`_resolve_device`) doi tu `D:\\RAG Chatbot\\app\\device.py`'s
`resolve_device()` - KHONG import tu repo do (repo rieng), viet lai ban sao
nho o day (du nho de khong tinh la duplicate code chuong trinh, brief T009f
cho phep)."""
from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from sentence_transformers import SentenceTransformer

from app import config

logger = logging.getLogger(__name__)

# Cache o cap module (dict, khong phai bien module truc tiep) - cho phep
# test reset ve sach ("_model_cache["instance"] = None") ma khong can
# importlib.reload ca module (giu tuong thich voi pattern mock cua
# tests/test_ingest.py - mock o bien module, khong reload).
_model_cache: dict[str, Any] = {"instance": None}
_collection_cache: dict[str, Any] = {"instance": None}


def _resolve_device() -> str:
    """Tra ve 'cuda' neu torch phat hien GPU kha dung, nguoc lai 'cpu' -
    ban sao nho, doc lap repo cua `D:\\RAG Chatbot\\app\\device.py`'s
    `resolve_device()` (khong import xuyen repo)."""
    import torch  # import cuc bo - torch nang, chi tai khi thuc su can chon device

    return "cuda" if torch.cuda.is_available() else "cpu"


def _get_model() -> SentenceTransformer:
    """Tra ve SentenceTransformer da cache (load 1 lan duy nhat cho ca
    process - xem module docstring / so bay 12e). Load model qua
    `config.EMBEDDING_MODEL`, device qua `_resolve_device()`."""
    if _model_cache["instance"] is None:
        logger.info(
            "dang tai embedding model %r (device=%s) - lan dau tien trong "
            "tien trinh nay, se duoc cache lai cho cac loi goi sau",
            config.EMBEDDING_MODEL,
            _resolve_device(),
        )
        _model_cache["instance"] = SentenceTransformer(
            config.EMBEDDING_MODEL, device=_resolve_device()
        )
    return _model_cache["instance"]


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed mot danh sach text trong MOT loi goi model (batching - nhanh
    hon dang ke so voi goi model tung text mot trong vong lap, xem brief).
    Tra ve list of list[float] (mot vector cho moi text dau vao, cung thu
    tu)."""
    model = _get_model()
    embeddings = model.encode(texts, convert_to_numpy=True)
    return embeddings.tolist()


def get_chroma_collection() -> Collection:
    """Tra ve Chroma collection da cache (persist tai
    `config.CHROMA_PERSIST_DIR`, ten qua `config.CHROMA_COLLECTION_NAME`) -
    chi tao PersistentClient + get_or_create_collection 1 lan cho ca
    process, cac loi goi sau tai su dung instance da cache (cung ly do
    cache model o tren - tranh mo lai client/collection lap lai khong can
    thiet)."""
    if _collection_cache["instance"] is None:
        client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        _collection_cache["instance"] = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME
        )
    return _collection_cache["instance"]


def upsert_embeddings(
    ids: list[str], texts: list[str], metadatas: list[dict]
) -> None:
    """Embed `texts` (mot loi goi batch qua `embed_texts`) roi ghi vao
    Chroma collection bang `collection.upsert(...)` - dung `upsert` (khong
    phai `add`) de idempotent theo construction: chay lai voi cung `ids` se
    ghi de (khong loi trung id), khop voi ky luat idempotency da thiet lap
    trong project nay (vd upsert.py's MERGE-based Cypher)."""
    embeddings = embed_texts(texts)
    collection = get_chroma_collection()
    collection.upsert(
        ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas
    )
