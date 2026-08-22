"""app/retrieval/reranker.py (P3): cham diem lai ung vien Article theo query
bang cross-encoder (BAAI/bge-reranker-v2-m3) - dua Dieu DUNG TRONG TAM len dau
truoc khi cat `config.MAX_CONTEXT_ARTICLES`.

Trach nhiem: chi "noi chuyen voi reranker model" (constitution Dieu 5). Model
CHAY TREN CPU (`config.RERANKER_DEVICE`) vi GPU 8GB da co bge-m3 (embedder) +
qwen-7b (Ollama) - them reranker len GPU se OOM.

Model duoc lazy-load va CACHE o cap module (KHONG tao CrossEncoder moi moi
lan goi - cung so bay native tren Windows voi SentenceTransformer trong
embedder.py, tranh crash khi load lai xen ke). Logic sao y `Reranker` trong
scripts/eval_hybrid_reranker_baseline.py (T018)."""
from __future__ import annotations

import logging

from app import config

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        # Import muon: `app.retrieval.embedder` dat HF_HUB_OFFLINE=1 luc import
        # (dam bao load model tu cache, khong goi mang). CrossEncoder import
        # sau do de dung cung runtime sentence_transformers.
        import app.retrieval.embedder  # noqa: F401  (side effect: HF_HUB_OFFLINE)
        from sentence_transformers import CrossEncoder

        logger.info(
            "tai reranker %r (device=%s, max_length=%d)",
            config.RERANKER_MODEL,
            config.RERANKER_DEVICE,
            config.RERANKER_MAX_LENGTH,
        )
        _model = CrossEncoder(
            config.RERANKER_MODEL,
            device=config.RERANKER_DEVICE,
            max_length=config.RERANKER_MAX_LENGTH,
        )
    return _model


def rerank_ids(
    query: str,
    candidate_ids: list[str],
    texts: dict[str, str],
    top_k: int,
) -> list[str]:
    """Cham diem lai tung cap (query, full_text), tra ve top_k article_id sap
    theo diem GIAM DAN.

    Ung vien KHONG co text (Article ngoai corpus / chi preview / chua embed)
    KHONG cham diem duoc -> giu nguyen thu tu goc va noi vao SAU cac id da
    rerank (de van du top_k, khong lam bien mat Dieu chi vi thieu full_text).
    `candidate_ids` rong -> tra ve rong (khong tai model)."""
    scoreable = [(cid, texts[cid]) for cid in candidate_ids if texts.get(cid)]
    if not scoreable:
        return list(candidate_ids)[:top_k]

    model = _get_model()
    scores = model.predict([(query, text) for _cid, text in scoreable])
    by_score = sorted(zip(scoreable, scores), key=lambda pair: pair[1], reverse=True)
    ranked = [cid for (cid, _text), _score in by_score]

    # Noi cac id khong scoreable (giu thu tu goc) vao sau.
    scoreable_set = {cid for cid, _t in scoreable}
    tail = [cid for cid in candidate_ids if cid not in scoreable_set]
    return (ranked + tail)[:top_k]
