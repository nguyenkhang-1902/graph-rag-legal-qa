"""Tests cho scripts/eval_hybrid_reranker_baseline.py (T018 - baseline
Hybrid+Reranker MOI, do o 67k, huong G1-b da chot trong
CHECKLIST-GRAPHRAG-DUYET.md).

Chi test phan THUAN TUY, deterministic: `reciprocal_rank_fusion` (cong
thuc RRF chuan, sao chep tu D:\\RAG Chatbot\\app\\hybrid_retriever.py -
Dieu 1 "tham chieu doc, khong sua project cu"). Phan con lai (dense search
qua Chroma that, BM25 qua bm25s, reranker qua CrossEncoder that) duoc
verify bang chay that tren du lieu that (cung triet ly voi
tests/retrieval/test_entry_point.py - "verify voi model that, khong doan
cong thuc"), khong mock toan bo pipeline o day.
"""
from scripts import eval_hybrid_reranker_baseline as ehrb
from scripts.eval_hybrid_reranker_baseline import RRF_K, _evaluate, reciprocal_rank_fusion


def test_id_appearing_in_both_lists_ranks_above_id_in_only_one():
    sparse = ["a", "b", "c"]
    dense = ["b", "c", "a"]

    fused = reciprocal_rank_fusion([sparse, dense])

    # "b": rank 2 (sparse) + rank 1 (dense) = 1/62 + 1/61 (cao nhat)
    assert fused[0] == "b"


def test_id_appearing_in_only_one_list_still_included():
    sparse = ["a", "b"]
    dense = ["c", "d"]

    fused = reciprocal_rank_fusion([sparse, dense])

    assert set(fused) == {"a", "b", "c", "d"}


def test_empty_lists_returns_empty():
    assert reciprocal_rank_fusion([[], []]) == []


def test_matches_known_rrf_formula_value():
    # "x" o rank 1 trong danh sach 1 va rank 3 trong danh sach 2.
    # "y" CHI o rank 1 trong danh sach 2.
    sparse = ["x"]
    dense = ["z", "w", "x"]

    fused = reciprocal_rank_fusion([sparse, dense], rrf_k=60)

    expected_x_score = 1.0 / (60 + 1) + 1.0 / (60 + 3)
    expected_z_score = 1.0 / (60 + 1)
    # "x" (2 danh sach) phai tren "z" (1 danh sach, rank 1).
    assert expected_x_score > expected_z_score
    assert fused[0] == "x"


def test_default_rrf_k_is_60_standard_constant():
    """Hang so chuan trong literature (Cormack et al. 2009), khong tune
    rieng - dong bo voi D:\\RAG Chatbot\\app\\hybrid_retriever.py's
    RRF_K = 60."""
    assert RRF_K == 60


def test_single_list_preserves_original_order():
    ranked = ["p", "q", "r"]
    fused = reciprocal_rank_fusion([ranked])
    assert fused == ranked


# --- _evaluate checkpoint/resume (them sau lan chay that bi ngat giua
# chung, mat toan bo tien do buoc Reranker - xem TIEN_DO.md) ------------


def test_full_run_writes_result_to_checkpoint_completed(tmp_path, monkeypatch):
    monkeypatch.setattr(ehrb, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    questions = ["q1", "q2", "q3"]
    expected = ["a1", "a2", "a3"]
    checkpoint = {"completed": {}, "in_progress": None}

    result = _evaluate(
        "strategy-x", lambda q: [expected[questions.index(q)]], questions, expected, k=4,
        checkpoint=checkpoint, checkpoint_every=100,
    )

    assert result["hits"] == 3
    assert result["recall_at_k"] == 1.0
    assert checkpoint["completed"]["strategy-x"] == result
    assert checkpoint["in_progress"] is None
    assert (tmp_path / "checkpoint.json").is_file()


def test_resumes_from_in_progress_checkpoint_skips_already_scored_questions(tmp_path, monkeypatch):
    """Cau hoi 0-1 (next_index=2) da tinh xong voi 1 hit truoc do (tu lan
    chay bi ngat) - retrieve_fn cho 2 cau nay se tra ve SAI (chung minh
    KHONG duoc goi lai), chi cau con lai (index 2) duoc tinh that."""
    monkeypatch.setattr(ehrb, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    questions = ["q1", "q2", "q3"]
    expected = ["a1", "a2", "a3"]
    checkpoint = {
        "completed": {},
        "in_progress": {"name": "strategy-x", "next_index": 2, "hits": 1, "rr_total": 1.0},
    }

    def retrieve_fn(q):
        if q in ("q1", "q2"):
            raise AssertionError(f"khong duoc goi lai cho cau da tinh: {q}")
        return ["a3"]

    result = _evaluate(
        "strategy-x", retrieve_fn, questions, expected, k=4, checkpoint=checkpoint, checkpoint_every=100,
    )

    assert result["hits"] == 2
    assert result["total"] == 3


def test_in_progress_for_different_strategy_name_does_not_affect_this_run(tmp_path, monkeypatch):
    monkeypatch.setattr(ehrb, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    questions = ["q1"]
    expected = ["a1"]
    checkpoint = {
        "completed": {},
        "in_progress": {"name": "OTHER strategy", "next_index": 1, "hits": 99, "rr_total": 99.0},
    }

    result = _evaluate(
        "strategy-x", lambda q: ["a1"], questions, expected, k=4, checkpoint=checkpoint, checkpoint_every=100,
    )

    assert result["hits"] == 1
    assert result["total"] == 1


def test_checkpoints_saved_every_n_questions(tmp_path, monkeypatch):
    checkpoint_path = tmp_path / "checkpoint.json"
    monkeypatch.setattr(ehrb, "CHECKPOINT_PATH", checkpoint_path)
    questions = ["q1", "q2", "q3", "q4", "q5"]
    expected = ["a1", "a2", "a3", "a4", "a5"]
    checkpoint = {"completed": {}, "in_progress": None}

    seen_next_index_values = []
    original_save = ehrb._save_checkpoint

    def spy_save(cp):
        seen_next_index_values.append(
            cp["in_progress"]["next_index"] if cp["in_progress"] else "final"
        )
        original_save(cp)

    monkeypatch.setattr(ehrb, "_save_checkpoint", spy_save)

    _evaluate(
        "strategy-x", lambda q: [expected[questions.index(q)]], questions, expected, k=4,
        checkpoint=checkpoint, checkpoint_every=2,
    )

    # 5 cau, checkpoint_every=2 -> luu o cau 2, 4, va luu cuoi cung o cau 5
    # (het danh sach) + 1 lan nua khi ghi vao "completed".
    assert seen_next_index_values == [2, 4, 5, "final"]
