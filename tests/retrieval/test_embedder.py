"""Tests cho app/retrieval/embedder.py (T009f).

Khong co model/Chroma that trong sandbox test - mock o ranh gioi (cung quy
uoc "honest mocking" nhu tests/test_ingest.py mock Neo4jClient): mock lop
`SentenceTransformer` (khong tai model that ~2GB) VA `chromadb.PersistentClient`
(khong ghi file that ra dia).

Trong tam: (1) model duoc cache - CHI construct 1 lan cho ca process du goi
embed_texts nhieu lan (guard truc tiep cho research.md so bay 12e - crash
native tren Windows khi load lai SentenceTransformer nhieu lan), (2)
embed_texts batch toan bo text trong MOT loi goi encode (khong loop tung
text), (3) Chroma collection cung duoc cache tuong tu, (4) upsert_embeddings
goi dung collection.upsert voi ids/documents/embeddings/metadatas khop nhau.
"""
import os

import numpy as np
import pytest
from unittest.mock import MagicMock

from app.retrieval import embedder


def test_module_defaults_hf_hub_offline_to_avoid_redundant_network_checks():
    """cProfile that (2026-08-04, chan doan GPU cham) xac nhan: moi lan
    construct SentenceTransformer, thu vien goi ~34 HTTP request kiem tra
    revision moi cua model tren Hugging Face Hub - DU model da cache day du
    tren may (6.1/8.76s init time la network, xem TIEN_DO.md). Module nay
    phai tu dat HF_HUB_OFFLINE=1 (bang setdefault - khong ghi de neu nguoi
    van hanh da tu dat gia tri khac de ho chu dong tai model MOI chua
    cache)."""
    assert os.environ.get("HF_HUB_OFFLINE") == "1"


@pytest.fixture(autouse=True)
def _reset_embedder_caches():
    """Cache o cap module (`_model_cache`/`_collection_cache`) se ro ri
    trang thai giua cac test neu khong reset - dam bao moi test bat dau tu
    trang thai "chua load gi" va khong de lai instance mock cho test sau."""
    embedder._model_cache["instance"] = None
    embedder._collection_cache["instance"] = None
    yield
    embedder._model_cache["instance"] = None
    embedder._collection_cache["instance"] = None


def _mock_sentence_transformer_cls(encode_return: np.ndarray) -> MagicMock:
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_instance.encode.return_value = encode_return
    mock_cls.return_value = mock_instance
    return mock_cls


def test_embed_texts_calls_encode_once_with_full_batch(monkeypatch):
    mock_cls = _mock_sentence_transformer_cls(
        np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
    )
    monkeypatch.setattr(embedder, "SentenceTransformer", mock_cls)

    texts = ["van ban mot", "van ban hai", "van ban ba"]
    result = embedder.embed_texts(texts)

    mock_cls.return_value.encode.assert_called_once_with(
        texts, convert_to_numpy=True
    )
    assert result == [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]


def test_embed_texts_reuses_cached_model_across_calls(monkeypatch):
    """Guard truc tiep cho so bay 12e: goi embed_texts 2 lan (lan luot, khong
    xen ke) - SentenceTransformer(...) CHI duoc construct 1 lan duy nhat."""
    mock_cls = _mock_sentence_transformer_cls(np.array([[0.1, 0.2]]))
    monkeypatch.setattr(embedder, "SentenceTransformer", mock_cls)

    embedder.embed_texts(["van ban mot"])
    embedder.embed_texts(["van ban hai"])

    assert mock_cls.call_count == 1
    assert mock_cls.return_value.encode.call_count == 2


def test_embed_texts_loads_model_with_configured_name_and_device(monkeypatch):
    mock_cls = _mock_sentence_transformer_cls(np.array([[0.1, 0.2]]))
    monkeypatch.setattr(embedder, "SentenceTransformer", mock_cls)
    monkeypatch.setattr(embedder, "_resolve_device", lambda: "cpu")
    monkeypatch.setattr(embedder.config, "EMBEDDING_MODEL", "BAAI/bge-m3")

    embedder.embed_texts(["van ban mot"])

    mock_cls.assert_called_once_with("BAAI/bge-m3", device="cpu")


def test_get_chroma_collection_caches_singleton_across_calls(monkeypatch):
    mock_collection = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_client_cls = MagicMock(return_value=mock_client_instance)
    monkeypatch.setattr(embedder.chromadb, "PersistentClient", mock_client_cls)

    first = embedder.get_chroma_collection()
    second = embedder.get_chroma_collection()

    assert first is second is mock_collection
    assert mock_client_cls.call_count == 1


def test_get_chroma_collection_uses_configured_persist_dir_and_name(monkeypatch):
    mock_collection = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_client_cls = MagicMock(return_value=mock_client_instance)
    monkeypatch.setattr(embedder.chromadb, "PersistentClient", mock_client_cls)
    monkeypatch.setattr(embedder.config, "CHROMA_PERSIST_DIR", "/tmp/chroma_test")
    monkeypatch.setattr(embedder.config, "CHROMA_COLLECTION_NAME", "legal_articles_test")

    embedder.get_chroma_collection()

    mock_client_cls.assert_called_once_with(path="/tmp/chroma_test")
    mock_client_instance.get_or_create_collection.assert_called_once_with(
        name="legal_articles_test",
        metadata={"hnsw:space": "cosine"},
    )


def test_get_chroma_collection_uses_cosine_hnsw_space(monkeypatch):
    """Chroma mac dinh HNSW space la L2 neu khong chi dinh - project nay
    dung BGE-m3 + SIMILARITY_THRESHOLD (config.py) theo quy uoc cosine
    similarity (0..1, giong het = 1.0). Phai chi ro "hnsw:space": "cosine"
    khi tao collection, neu khong SIMILARITY_THRESHOLD se vo nghia (L2
    khong bi chan/khong am, thap hon moi giong hon - nguoc huong voi
    cosine threshold)."""
    mock_collection = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.get_or_create_collection.return_value = mock_collection
    mock_client_cls = MagicMock(return_value=mock_client_instance)
    monkeypatch.setattr(embedder.chromadb, "PersistentClient", mock_client_cls)

    embedder.get_chroma_collection()

    _, kwargs = mock_client_instance.get_or_create_collection.call_args
    assert kwargs["metadata"] == {"hnsw:space": "cosine"}


def test_get_texts_returns_only_present_ids_omitting_missing(monkeypatch):
    """`collection.get(ids=[...])` (chromadb that) chi tra ve cac id THUC SU
    ton tai trong collection - "art_2" khong duoc yeu cau ket qua nen
    KHONG duoc xuat hien trong dict tra ve (missing key, khong phai None)."""
    mock_collection = MagicMock()
    mock_collection.get.return_value = {
        "ids": ["art_1", "art_3"],
        "documents": ["noi dung dieu 1", "noi dung dieu 3"],
    }
    monkeypatch.setattr(embedder, "get_chroma_collection", lambda: mock_collection)

    result = embedder.get_texts(["art_1", "art_2", "art_3"])

    mock_collection.get.assert_called_once_with(ids=["art_1", "art_2", "art_3"])
    assert result == {"art_1": "noi dung dieu 1", "art_3": "noi dung dieu 3"}
    assert "art_2" not in result


def test_get_texts_keeps_empty_string_document_distinct_from_missing(monkeypatch):
    """Id co trong Chroma nhung voi document rong ("") van phai xuat hien
    trong dict voi gia tri "" - phan biet voi id khong ton tai (missing
    key hoan toan), xem docstring get_texts."""
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": ["art_1"], "documents": [""]}
    monkeypatch.setattr(embedder, "get_chroma_collection", lambda: mock_collection)

    result = embedder.get_texts(["art_1"])

    assert result == {"art_1": ""}
    assert "art_1" in result


def test_get_texts_empty_input_returns_empty_dict_without_calling_chroma(monkeypatch):
    mock_collection = MagicMock()
    monkeypatch.setattr(embedder, "get_chroma_collection", lambda: mock_collection)

    result = embedder.get_texts([])

    assert result == {}
    mock_collection.get.assert_not_called()


def test_upsert_embeddings_embeds_then_upserts_matching_batch(monkeypatch):
    mock_collection = MagicMock()
    monkeypatch.setattr(embedder, "get_chroma_collection", lambda: mock_collection)
    monkeypatch.setattr(
        embedder, "embed_texts", lambda texts: [[0.1, 0.2] for _ in texts]
    )

    ids = ["doc_dieu-1", "doc_dieu-2"]
    texts = ["noi dung dieu mot", "noi dung dieu hai"]
    metadatas = [{"doc_id": "doc", "so_dieu": 1}, {"doc_id": "doc", "so_dieu": 2}]

    embedder.upsert_embeddings(ids=ids, texts=texts, metadatas=metadatas)

    mock_collection.upsert.assert_called_once_with(
        ids=ids,
        documents=texts,
        embeddings=[[0.1, 0.2], [0.1, 0.2]],
        metadatas=metadatas,
    )


# --- release_model: giai phong VRAM khi khong con can model -----------------
# BUG THAT (2026-08-08): `scripts/eval_hybrid_reranker_baseline.py` chet o cau
# 720/793 khi dang rerank. Do that luc dang chay: VRAM 5,904/6,144 MiB (96%),
# GPU util 100%, khong throttle. Nguyen nhan: CA HAI model cung thuong tru tren
# GPU - BGE-m3 (embedding, ~2.3GB) VA bge-reranker-v2-m3 (~2.3GB) - tren card
# 6GB. Nhung den giai doan rerank thi MOI ket qua dense da duoc tinh san xong,
# model embedding khong con can nua.


def test_release_model_clears_cache():
    import app.retrieval.embedder as emb

    emb._model_cache["instance"] = object()  # gia lap model da tai
    emb.release_model()
    assert emb._model_cache["instance"] is None


def test_release_model_is_safe_when_nothing_loaded():
    # Goi khi chua tai model gi -> khong duoc raise (caller khong phai kiem
    # tra truoc).
    import app.retrieval.embedder as emb

    emb._model_cache["instance"] = None
    emb.release_model()
    assert emb._model_cache["instance"] is None


def test_release_model_does_not_touch_chroma_collection():
    # Chi giai phong MODEL. Chroma collection khong chiem VRAM va con duoc
    # dung tiep (vd `get_texts` lay full text cho reranker) - giai phong nham
    # se buoc mo lai client tren dia khong can thiet.
    import app.retrieval.embedder as emb

    sentinel = object()
    emb._collection_cache["instance"] = sentinel
    emb.release_model()
    assert emb._collection_cache["instance"] is sentinel
    emb._collection_cache["instance"] = None
