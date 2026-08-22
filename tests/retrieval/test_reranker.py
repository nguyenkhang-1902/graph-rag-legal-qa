"""Tests cho app/retrieval/reranker.py (P3).

Mock cross-encoder model (khong tai model that) - kiem tra LOGIC sap xep +
xu ly ung vien thieu text, khong kiem tra chat luong diem cua model.
"""
from unittest.mock import MagicMock

from app.retrieval import reranker


def _fake_model(scores: list[float]) -> MagicMock:
    model = MagicMock()
    model.predict.return_value = scores
    return model


def test_rerank_sorts_by_score_desc_and_cuts_top_k(monkeypatch):
    # 3 ung vien, diem khien thu tu dao lai: c (0.9) > a (0.5) > b (0.1).
    monkeypatch.setattr(reranker, "_get_model", lambda: _fake_model([0.5, 0.1, 0.9]))
    out = reranker.rerank_ids(
        "q",
        ["a", "b", "c"],
        {"a": "text a", "b": "text b", "c": "text c"},
        top_k=2,
    )
    assert out == ["c", "a"]


def test_rerank_appends_untexted_candidates_after_scored(monkeypatch):
    # "b" khong co text -> khong cham diem, giu lai o SAU cac id da rerank.
    monkeypatch.setattr(reranker, "_get_model", lambda: _fake_model([0.2, 0.9]))
    out = reranker.rerank_ids(
        "q",
        ["a", "b", "c"],
        {"a": "text a", "c": "text c"},  # b thieu text
        top_k=3,
    )
    # scored: c (0.9) > a (0.2); roi b (khong text) noi sau.
    assert out == ["c", "a", "b"]


def test_rerank_empty_candidates_returns_empty_without_loading_model(monkeypatch):
    called = {"loaded": False}

    def _boom():
        called["loaded"] = True
        raise AssertionError("khong duoc tai model khi khong co ung vien")

    monkeypatch.setattr(reranker, "_get_model", _boom)
    assert reranker.rerank_ids("q", [], {}, top_k=5) == []
    assert called["loaded"] is False


def test_rerank_no_scoreable_text_returns_original_order_without_model(monkeypatch):
    monkeypatch.setattr(
        reranker, "_get_model", lambda: (_ for _ in ()).throw(AssertionError("khong tai"))
    )
    # Khong ung vien nao co text -> tra ve thu tu goc (cat top_k), khong tai model.
    out = reranker.rerank_ids("q", ["a", "b", "c"], {}, top_k=2)
    assert out == ["a", "b"]
