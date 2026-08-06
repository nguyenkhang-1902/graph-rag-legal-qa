"""Tests cho scripts/eval_graph_recall.py (T017).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi
scripts/eval_graph_recall.py ton tai.

Khac biet voi D:\\RAG Chatbot\\scripts\\eval_zalo_recall.py (ban goc,
dung lam tham chieu phuong phap theo spec.md FR-007) - xem module
docstring cua eval_graph_recall.py de biet ly do day du:
  1. Ban goc: 1 cau hoi -> 1 "expected_source_file" duy nhat. O day: 1 cau
     hoi -> NHIEU "expected_article_ids" (cau hoi multi-hop can PHOI HOP
     nhieu Dieu de tra loi du, xem data/eval/multihop_eval_set.json).
  2. Ban goc: retrieved la list DA CO THU TU tu vector search truc tiep.
     O day: "retrieved" la hop cua {entry point (co thu tu similarity) +
     Article tim duoc qua graph traversal (KHONG co diem so, chi co canh)}
     - can dinh nghia RANH GIOI RO RANG cho "thu tu" de MRR co y nghia
     (xem _ranked_retrieved_article_ids).
"""
from unittest.mock import MagicMock

from app.retrieval.entry_point import EntryPointResult
from app.retrieval.traversal import TraversalEdge, TraversalResult
from scripts.eval_graph_recall import (
    _evaluate_question,
    _ranked_retrieved_article_ids,
    run_eval,
)


# --- _ranked_retrieved_article_ids ---------------------------------------


def test_ranked_ids_puts_entry_points_first_in_similarity_order(monkeypatch):
    entry_points = [
        EntryPointResult(article_id="a1", similarity=0.9),
        EntryPointResult(article_id="a2", similarity=0.8),
    ]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.find_entry_points", lambda q, top_k: entry_points
    )
    monkeypatch.setattr(
        "scripts.eval_graph_recall.traverse",
        lambda client, entry_ids, max_hop=None: TraversalResult(
            visited_article_ids={"a1", "a2"}, edges=[]
        ),
    )

    ranked = _ranked_retrieved_article_ids(
        "cau hoi", client=MagicMock(), top_k=5, max_hop=2
    )
    assert ranked == ["a1", "a2"]


def test_ranked_ids_appends_traversal_discovered_articles_after_entry_points(
    monkeypatch,
):
    entry_points = [EntryPointResult(article_id="a1", similarity=0.9)]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.find_entry_points", lambda q, top_k: entry_points
    )
    # a1 -> a2 -> a3 qua REFERENCES, thu tu xuat hien trong edges quyet
    # dinh thu tu rank sau entry point.
    edges = [
        TraversalEdge(from_article_id="a1", to_id="a2", relationship_type="REFERENCES"),
        TraversalEdge(from_article_id="a2", to_id="a3", relationship_type="REFERENCES"),
    ]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.traverse",
        lambda client, entry_ids, max_hop=None: TraversalResult(
            visited_article_ids={"a1", "a2", "a3"}, edges=edges
        ),
    )

    ranked = _ranked_retrieved_article_ids(
        "cau hoi", client=MagicMock(), top_k=5, max_hop=2
    )
    assert ranked == ["a1", "a2", "a3"]


def test_ranked_ids_ignores_defines_edges_to_terms(monkeypatch):
    entry_points = [EntryPointResult(article_id="a1", similarity=0.9)]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.find_entry_points", lambda q, top_k: entry_points
    )
    edges = [
        TraversalEdge(from_article_id="a1", to_id="ngay", relationship_type="DEFINES"),
        TraversalEdge(from_article_id="a1", to_id="a2", relationship_type="REFERENCES"),
    ]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.traverse",
        lambda client, entry_ids, max_hop=None: TraversalResult(
            visited_article_ids={"a1", "a2"},
            edges=edges,
            visited_term_ids={"ngay"},
        ),
    )

    ranked = _ranked_retrieved_article_ids(
        "cau hoi", client=MagicMock(), top_k=5, max_hop=2
    )
    # "ngay" la term_id (tu canh DEFINES), KHONG duoc xuat hien trong danh
    # sach article_id da xep hang.
    assert "ngay" not in ranked
    assert ranked == ["a1", "a2"]


def test_ranked_ids_does_not_duplicate_article_already_ranked(monkeypatch):
    entry_points = [
        EntryPointResult(article_id="a1", similarity=0.9),
        EntryPointResult(article_id="a2", similarity=0.8),
    ]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.find_entry_points", lambda q, top_k: entry_points
    )
    # a2 vua la entry point, vua duoc tro toi qua REFERENCES tu a1 - khong
    # duoc xuat hien 2 lan trong ranked list.
    edges = [
        TraversalEdge(from_article_id="a1", to_id="a2", relationship_type="REFERENCES"),
    ]
    monkeypatch.setattr(
        "scripts.eval_graph_recall.traverse",
        lambda client, entry_ids, max_hop=None: TraversalResult(
            visited_article_ids={"a1", "a2"}, edges=edges
        ),
    )

    ranked = _ranked_retrieved_article_ids(
        "cau hoi", client=MagicMock(), top_k=5, max_hop=2
    )
    assert ranked == ["a1", "a2"]
    assert ranked.count("a2") == 1


# --- _evaluate_question ---------------------------------------------------


def test_evaluate_question_all_found_true_when_every_expected_id_present():
    result = _evaluate_question(
        expected_article_ids=["a2", "a3"], ranked_article_ids=["a1", "a2", "a3", "a4"]
    )
    assert result["all_found"] is True
    assert result["found_count"] == 2
    assert result["expected_count"] == 2


def test_evaluate_question_all_found_false_when_one_missing():
    result = _evaluate_question(
        expected_article_ids=["a2", "a99"], ranked_article_ids=["a1", "a2", "a3"]
    )
    assert result["all_found"] is False
    assert result["found_count"] == 1
    assert result["expected_count"] == 2


def test_evaluate_question_reciprocal_rank_uses_best_min_rank_among_expected():
    # a3 o rank 3, a1 o rank 1 - MRR phai dung rank TOT NHAT (1), khong
    # phai rank te nhat hay trung binh.
    result = _evaluate_question(
        expected_article_ids=["a3", "a1"], ranked_article_ids=["a1", "a2", "a3"]
    )
    assert result["reciprocal_rank"] == 1.0  # rank 1 -> 1/1


def test_evaluate_question_reciprocal_rank_zero_when_none_found():
    result = _evaluate_question(
        expected_article_ids=["a99"], ranked_article_ids=["a1", "a2"]
    )
    assert result["reciprocal_rank"] == 0.0
    assert result["all_found"] is False


# --- run_eval (tich hop) ---------------------------------------------------


def test_run_eval_aggregates_strict_recall_lenient_recall_and_mrr(monkeypatch):
    questions = [
        {"id": "q1", "question": "cau 1", "expected_article_ids": ["a1"]},
        {"id": "q2", "question": "cau 2", "expected_article_ids": ["a1", "a2"]},
    ]

    def fake_ranked_ids(question, *, client, top_k, max_hop):
        if question == "cau 1":
            return ["a1", "a9"]  # tim thay het (1/1) - rank 1 -> RR=1.0
        return ["a9", "a2"]  # chi tim thay a2 (1/2), rank 2 -> RR=0.5

    monkeypatch.setattr(
        "scripts.eval_graph_recall._ranked_retrieved_article_ids", fake_ranked_ids
    )

    summary = run_eval(questions, client=MagicMock(), top_k=5, max_hop=2)

    # Strict: cau 1 dat (all_found), cau 2 khong dat -> 1/2 = 50%.
    assert summary["strict_recall"] == 0.5
    # Lenient (article-level): tong found=2 (a1 + a2), tong expected=3 (1+2).
    assert summary["lenient_recall"] == 2 / 3
    # MRR: trung binh (1.0 + 0.5) / 2.
    assert summary["mrr"] == 0.75
    assert summary["total_questions"] == 2


def test_run_eval_respects_limit_param(monkeypatch):
    questions = [
        {"id": f"q{i}", "question": f"cau {i}", "expected_article_ids": ["a1"]}
        for i in range(5)
    ]
    monkeypatch.setattr(
        "scripts.eval_graph_recall._ranked_retrieved_article_ids",
        lambda question, **kwargs: ["a1"],
    )

    summary = run_eval(questions[:2], client=MagicMock(), top_k=5, max_hop=2)
    assert summary["total_questions"] == 2
