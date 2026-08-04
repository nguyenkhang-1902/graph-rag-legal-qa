"""Tests cho app/retrieval/entry_point.py (T010).

Da so test mock o ranh gioi (cung quy uoc "honest mocking" nhu
tests/retrieval/test_embedder.py): mock `embed_texts` va Chroma collection's
`.query` return value, khong tai model/Chroma that. Rieng
`test_real_model_and_chroma_confirms_distance_to_similarity_conversion` la
test THAT DUY NHAT - dung model BGE-m3 that + mot Chroma collection tam
thoi, doc lap (tmp_path, TEN COLLECTION RIENG) de xac nhan cong thuc
`similarity = 1 - distance` dung tren chromadb==1.5.9 that, khong chi la
gia dinh code. Test nay KHONG dung `config.CHROMA_PERSIST_DIR` that (khong
dung/ghi vao chroma_db/ that dang duoc backfill that o may nay).

SIMILARITY_THRESHOLD mac dinh (config.py) la 0.75 - cac test mock duoi day
dung gia tri nay lam moc, voi distance/similarity cu the da tinh tay trong
comment o moi test.
"""
import numpy as np
import pytest
from unittest.mock import MagicMock

from app import config
from app.retrieval import embedder, entry_point


@pytest.fixture(autouse=True)
def _reset_embedder_caches():
    """Cache o cap module trong embedder.py se ro ri trang thai giua cac
    test (dac biet quan trong cho test that o cuoi file - phai bat dau tu
    trang thai chua load gi de tro ve dung collection/model duoc chi dinh
    trong tung test)."""
    embedder._model_cache["instance"] = None
    embedder._collection_cache["instance"] = None
    yield
    embedder._model_cache["instance"] = None
    embedder._collection_cache["instance"] = None


def _mock_chroma_query_result(ids: list[str], distances: list[float]) -> dict:
    """Chroma `collection.query(...)` tra ve dict voi cac key la list-of-list
    (mot list con cho moi query_embedding dau vao - o day luon chi co 1)."""
    return {"ids": [ids], "distances": [distances]}


def test_returns_only_results_above_threshold_with_correct_similarity(monkeypatch):
    """SIMILARITY_THRESHOLD mac dinh = 0.75.
    distance=0.1 -> similarity = 1 - 0.1 = 0.9  (>= 0.75, GIU LAI)
    distance=0.4 -> similarity = 1 - 0.4 = 0.6  (< 0.75, LOC BO)
    """
    monkeypatch.setattr(entry_point, "embed_texts", lambda texts: [[0.1, 0.2]])
    mock_collection = MagicMock()
    mock_collection.query.return_value = _mock_chroma_query_result(
        ids=["dieu_1", "dieu_2"], distances=[0.1, 0.4]
    )
    monkeypatch.setattr(entry_point, "get_chroma_collection", lambda: mock_collection)

    result = entry_point.find_entry_points("cau hoi test", top_k=5)

    assert len(result) == 1
    assert result[0].article_id == "dieu_1"
    assert result[0].similarity == pytest.approx(0.9)


def test_empty_chroma_collection_returns_empty_list(monkeypatch):
    monkeypatch.setattr(entry_point, "embed_texts", lambda texts: [[0.1, 0.2]])
    mock_collection = MagicMock()
    mock_collection.query.return_value = _mock_chroma_query_result(
        ids=[], distances=[]
    )
    monkeypatch.setattr(entry_point, "get_chroma_collection", lambda: mock_collection)

    result = entry_point.find_entry_points("cau hoi test", top_k=5)

    assert result == []


def test_all_results_below_threshold_returns_empty_list(monkeypatch):
    """distance=0.5 -> similarity=0.5, distance=0.9 -> similarity=0.1 - ca
    hai deu < SIMILARITY_THRESHOLD (0.75)."""
    monkeypatch.setattr(entry_point, "embed_texts", lambda texts: [[0.1, 0.2]])
    mock_collection = MagicMock()
    mock_collection.query.return_value = _mock_chroma_query_result(
        ids=["dieu_1", "dieu_2"], distances=[0.5, 0.9]
    )
    monkeypatch.setattr(entry_point, "get_chroma_collection", lambda: mock_collection)

    result = entry_point.find_entry_points("cau hoi test", top_k=5)

    assert result == []


def test_results_sorted_by_similarity_descending_even_if_input_order_differs(
    monkeypatch,
):
    """Feed mock results KHONG theo thu tu similarity giam dan (dieu_3 co
    similarity cao nhat nhung dung cuoi trong input) - chung minh
    find_entry_points tu sap xep, khong dua vao thu tu Chroma tra ve.
    distance=0.3 -> similarity=0.7 (< 0.75, se bi loc, khong anh huong sort)
    distance=0.2 -> similarity=0.8
    distance=0.05 -> similarity=0.95
    """
    monkeypatch.setattr(entry_point, "embed_texts", lambda texts: [[0.1, 0.2]])
    mock_collection = MagicMock()
    mock_collection.query.return_value = _mock_chroma_query_result(
        ids=["dieu_low", "dieu_mid", "dieu_high"],
        distances=[0.3, 0.2, 0.05],
    )
    monkeypatch.setattr(entry_point, "get_chroma_collection", lambda: mock_collection)

    result = entry_point.find_entry_points("cau hoi test", top_k=5)

    assert [r.article_id for r in result] == ["dieu_high", "dieu_mid"]
    assert result[0].similarity > result[1].similarity


def test_embed_texts_called_once_with_only_the_query(monkeypatch):
    mock_embed = MagicMock(return_value=[[0.1, 0.2]])
    monkeypatch.setattr(entry_point, "embed_texts", mock_embed)
    mock_collection = MagicMock()
    mock_collection.query.return_value = _mock_chroma_query_result(
        ids=[], distances=[]
    )
    monkeypatch.setattr(entry_point, "get_chroma_collection", lambda: mock_collection)

    entry_point.find_entry_points("cau hoi rieng le cua nguoi dung", top_k=5)

    mock_embed.assert_called_once_with(["cau hoi rieng le cua nguoi dung"])


def test_real_model_and_chroma_confirms_distance_to_similarity_conversion(
    tmp_path, monkeypatch
):
    """Test THAT (khong mock model, khong mock Chroma) - dung BGE-m3 that +
    mot PersistentClient Chroma tam thoi trong tmp_path (KHONG dung
    config.CHROMA_PERSIST_DIR that - repo nay dang chay backfill embedding
    that vao chroma_db/ that o may nay, khong duoc dung chung).

    Xac nhan cu the: upsert 2 cau giong het nhau (article giong query) ->
    query lai bang chinh cau do -> distance phai ~0.0 -> similarity ~1.0.
    Upsert them 1 cau hoan toan khac chu de -> similarity cua no phai thap
    hon nhieu (< 0.75, bi loc boi threshold). Day la bang chung THAT cho
    cong thuc similarity = 1 - distance tren chromadb==1.5.9, khong phai
    gia dinh (xem module docstring cua entry_point.py)."""
    monkeypatch.setattr(config, "CHROMA_PERSIST_DIR", str(tmp_path / "chroma_test"))
    monkeypatch.setattr(config, "CHROMA_COLLECTION_NAME", "legal_articles_t010_smoke")

    identical_text = "Nguoi lao dong co quyen duoc nghi phep nam theo quy dinh."
    different_text = "Con meo dang ngu tren mai nha vao buoi chieu."

    embedder.upsert_embeddings(
        ids=["dieu_giong", "dieu_khac"],
        texts=[identical_text, different_text],
        metadatas=[{"note": "giong query"}, {"note": "khac chu de"}],
    )

    result = entry_point.find_entry_points(identical_text, top_k=5)

    article_ids = [r.article_id for r in result]
    assert "dieu_giong" in article_ids
    matched = next(r for r in result if r.article_id == "dieu_giong")
    # cau hoi trung khop tuyet doi voi mot van ban da upsert -> distance
    # phai rat gan 0 -> similarity rat gan 1.0 (cho phep sai so nho do
    # xap xi so hoc cua HNSW/embedding, khong phai bang chinh xac tuyet doi)
    assert matched.similarity > 0.99
    # van ban khac chu de hoan toan khong duoc vuot threshold mac dinh (0.75)
    assert "dieu_khac" not in article_ids
