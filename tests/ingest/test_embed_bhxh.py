"""Test cho scripts/embed_bhxh.py (BHXH-P2-T1): embed corpus BHXH da luu
(data/raw/bhxh/*.txt, tu fetch_bhxh_corpus/T5) vao Chroma collection
`legal_articles`.

Mock `app.retrieval.embedder.upsert_embeddings` (MagicMock) - test nay
KHONG duoc chay embedding model that (cham, can GPU/tai model) hay Chroma
that (xem brief). `embed_bhxh_txt` phai: doc file -> parse_vbpl_content ->
gom TOAN BO Article (ke ca trong Chuong, qua app.ingest._all_articles) ->
goi upsert mot lan voi (ids, texts, metadatas) dung dinh dang engine da
thiet lap (backfill_embeddings.py:158-168) - article_id KHONG duoc
slugify/lowercase (phai giu nguyen dang "..._dieu-N" khop voi Neo4j
Article.article_id da ingest that, xem brief)."""
import re
from pathlib import Path
from unittest.mock import MagicMock

import scripts.embed_bhxh as embed_bhxh_module
from scripts.embed_bhxh import embed_bhxh_txt

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "bhxh"
    / "luat-bhxh-2024-excerpt.txt"
)

_ARTICLE_ID_RE = re.compile(r"_dieu-\d+$")


def test_embed_bhxh_txt_upserts_articles_with_correct_ids_and_metadata(monkeypatch):
    mock_upsert = MagicMock()
    monkeypatch.setattr(embed_bhxh_module.embedder, "upsert_embeddings", mock_upsert)

    count = embed_bhxh_txt([FIXTURE])

    mock_upsert.assert_called_once()
    kwargs = mock_upsert.call_args.kwargs
    ids = kwargs["ids"]
    texts = kwargs["texts"]
    metadatas = kwargs["metadatas"]

    # Fixture co Dieu 1 va Dieu 2 -> it nhat 2 article.
    assert len(ids) >= 2
    assert count == len(ids)
    assert len(texts) == len(ids)
    assert len(metadatas) == len(ids)

    # article_id KHONG duoc slugify/lowercase - phai khop dung dang
    # "{doc_id}_dieu-{so_dieu}" ma parse_vbpl_content sinh ra (brief: PHAI
    # khop Neo4j Article.article_id da ingest that).
    assert any(_ARTICLE_ID_RE.search(article_id) for article_id in ids)
    assert all(article_id for article_id in ids)

    # full_text (documents) khong duoc rong.
    assert all(text.strip() for text in texts)

    # Metadata phai mang doc_id + so_dieu (backfill_embeddings.py pattern).
    for meta in metadatas:
        assert "doc_id" in meta and meta["doc_id"]
        assert "so_dieu" in meta and isinstance(meta["so_dieu"], int)
