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
import os
from typing import Any

# HF_HUB_OFFLINE=1 (setdefault - khong ghi de neu nguoi van hanh da tu dat
# gia tri khac, vd de chu dong tai mot model MOI chua cache). Dat TRUOC khi
# import sentence_transformers/huggingface_hub - chan doan that (2026-08-04,
# cProfile SentenceTransformer(...) tren CPU) xac nhan: moi lan construct
# model, thu vien tu dong goi ~34 HTTP request kiem tra revision moi tren
# Hugging Face Hub - DU model da cache day du tren may (chiem 6.1/8.76s thoi
# gian khoi tao, ~70%). Model trong du an nay (config.EMBEDDING_MODEL) luon
# da duoc cache truoc (xem quickstart.md) nen bo qua kiem tra mang la an
# toan, tiet kiem ~1 lan/process. Xem TIEN_DO.md muc chan doan GPU cham.
os.environ.setdefault("HF_HUB_OFFLINE", "1")

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


def release_model() -> None:
    """Giai phong model embedding khoi bo nho (ke ca VRAM) va xoa cache.

    VI SAO CAN (bug that, 2026-08-08): `scripts/eval_hybrid_reranker_baseline.py`
    chet o cau 720/793 khi dang rerank. Do duoc luc dang chay: VRAM
    5,904/6,144 MiB (96%), GPU util 100%, KHONG throttle (52C, clock gan max).
    Nguyen nhan: CA HAI model cung thuong tru tren GPU - BGE-m3 (embedding,
    ~2.3GB) VA bge-reranker-v2-m3 (~2.3GB) - tren card 6GB, cong activations
    thi het cho.

    Nhung den giai doan rerank thi MOI ket qua dense da duoc tinh san xong
    (`dense_search_topk` chay truoc), nen model embedding khong con can. Goi
    ham nay truoc khi tai reranker.

    Chi giai phong MODEL, KHONG dong den Chroma collection: collection khong
    chiem VRAM va con duoc dung tiep (vd `get_texts` lay full text cho
    reranker) - giai phong nham se buoc mo lai client tren dia vo ich.

    An toan goi khi chua tai model gi (caller khong phai kiem tra truoc). Lan
    goi `_get_model()` sau do se tai lai model tu dau nhu binh thuong.
    """
    _model_cache["instance"] = None
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # pragma: no cover - torch khong co/khong dung CUDA
        # Khong de viec giai phong bo nho lam crash pipeline: day la toi uu,
        # khong phai buoc bat buoc ve mat dung dan.
        logger.debug("khong giai phong duoc VRAM (bo qua)", exc_info=True)


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
        # BGE-m3 + SIMILARITY_THRESHOLD (config.py) gia dinh cosine similarity
        # (0..1, giong het = 1.0, khop quy uoc cua D:\RAG Chatbot\app\conflict_detection.py).
        # Chroma mac dinh HNSW space la L2 neu khong chi dinh - PHAI chi ro
        # "hnsw:space": "cosine" o day, neu khong SIMILARITY_THRESHOLD se vo nghia
        # (L2 khong bi chan, khong am, THAP hon moi la giong hon - nguoc huong/khac
        # thang do voi cosine). Luu y: metadata nay CHI ap dung khi tao collection
        # moi - neu collection ten nay da ton tai voi metric khac, get_or_create_collection
        # se IM LANG bo qua metadata nay (xem docstring chromadb.api.client.Client
        # .get_or_create_collection, pinned chromadb==1.5.9).
        _collection_cache["instance"] = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection_cache["instance"]


def get_texts(article_ids: list[str]) -> dict[str, str]:
    """Tra ve dict `article_id -> full text` cho MOI id THUC SU co trong
    Chroma collection (`collection.get(ids=article_ids)`'s "documents"
    field) - id KHONG tim thay trong Chroma se KHONG xuat hien trong dict
    tra ve (missing key, khong phai gia tri `None`/chuoi rong), de caller
    (`serving/api.py`, T014) phan biet duoc "chua embed" (thieu key) voi
    "text rong that su" (key co, gia tri ""). Mot loi goi `collection.get`
    duy nhat (batched, khong phai mot loi goi cho moi id) - tai su dung
    `get_chroma_collection()` da cache, khong tao Chroma client moi (giu
    toan bo truy cap Chroma sau module nay, constitution Dieu 5).

    `article_ids` rong -> tra ve dict rong, khong goi Chroma."""
    if not article_ids:
        return {}

    collection = get_chroma_collection()
    result = collection.get(ids=article_ids)
    found_ids = result.get("ids") or []
    documents = result.get("documents") or []
    return dict(zip(found_ids, documents))


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
