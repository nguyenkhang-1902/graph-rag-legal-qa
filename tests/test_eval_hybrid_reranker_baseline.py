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
import pytest

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
    checkpoint = {"completed": {}, "in_progress": {}}

    result = _evaluate(
        "strategy-x", lambda q: [expected[questions.index(q)]], questions, expected, k=4,
        checkpoint=checkpoint, checkpoint_every=100,
    )

    assert result["hits"] == 3
    assert result["recall_at_k"] == 1.0
    assert checkpoint["completed"]["strategy-x"] == result
    assert "X" not in checkpoint["in_progress"]
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
        "in_progress": {
            "strategy-x": {"name": "strategy-x", "next_index": 2, "hits": 1,
                           "rr_total": 1.0}
        },
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
        "in_progress": {
            "OTHER strategy": {"name": "OTHER strategy", "next_index": 1,
                               "hits": 99, "rr_total": 99.0}
        },
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
    checkpoint = {"completed": {}, "in_progress": {}}

    seen_next_index_values = []
    original_save = ehrb._save_checkpoint

    def spy_save(cp):
        seen_next_index_values.append(
            cp["in_progress"]["strategy-x"]["next_index"]
            if cp["in_progress"].get("strategy-x")
            else "final"
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


# --- Checkpoint PHAI ghi so cau hoi, va tu choi resume khi lech -----------
# BUG THAT da xay ra (2026-08-08): checkpoint khong ghi so cau hoi. Lan chay
# dau do Dense-only + Hybrid tren 793 cau; lan resume sau chay voi
# `--limit-queries` mac dinh (50) -> script BO QUA 2 chien luoc da xong (do o
# 793 cau) roi do chien luoc thu 3 o 50 cau, va IN CA BA CANH NHAU nhu the so
# sanh duoc:
#     Dense-only          82.0%  (650/793)
#     Hybrid RRF          79.2%  (628/793)
#     Hybrid + Reranker   92.0%  ( 46/50)   <-- KHAC QUY MO
# 92.0% tro thanh mot con so vo nghia trong bang so sanh.
#
# Day DUNG cung lop bug ma du an DA HOC va DA CHAN o app/ingest.py
# (`BatchSizeMismatchError`: checkpoint khong ghi `batch_size` -> resume voi
# batch size khac se am tham bo sot hang nghin van ban). Ap dung y nguyen
# nguyen tac do o day: PHAT HIEN va TU CHOI chay, khong tu dong hoa giai.


def test_checkpoint_records_question_count():
    from scripts.eval_hybrid_reranker_baseline import QuestionCountMismatchError  # noqa: F401

    # Chi can symbol ton tai - hanh vi kiem o cac test duoi.


def test_refuses_resume_when_question_count_differs(tmp_path, monkeypatch):
    from scripts.eval_hybrid_reranker_baseline import (
        QuestionCountMismatchError,
        _check_question_count_matches_checkpoint,
    )

    checkpoint = {"completed": {"x": {}}, "in_progress": None, "n_questions": 793}
    with pytest.raises(QuestionCountMismatchError, match="793"):
        _check_question_count_matches_checkpoint(checkpoint, 50)


def test_allows_resume_when_question_count_matches():
    from scripts.eval_hybrid_reranker_baseline import (
        _check_question_count_matches_checkpoint,
    )

    checkpoint = {"completed": {"x": {}}, "in_progress": None, "n_questions": 793}
    _check_question_count_matches_checkpoint(checkpoint, 793)  # khong raise


def test_old_checkpoint_without_question_count_is_not_blocked():
    # Checkpoint ghi TRUOC khi truong nay ton tai -> khong the so sanh tu du
    # lieu khong co. Bo qua kiem tra (giong cach ingest.py xu ly checkpoint cu
    # khong co `batch_size`), khong pha vo moi checkpoint cu mot cach vo ich.
    from scripts.eval_hybrid_reranker_baseline import (
        _check_question_count_matches_checkpoint,
    )

    _check_question_count_matches_checkpoint({"completed": {"x": {}}}, 50)


def test_fresh_checkpoint_is_never_blocked():
    # Chua co chien luoc nao xong -> khong phai resume -> khong kiem tra.
    from scripts.eval_hybrid_reranker_baseline import (
        _check_question_count_matches_checkpoint,
    )

    _check_question_count_matches_checkpoint(
        {"completed": {}, "in_progress": None, "n_questions": 793}, 50
    )


def test_default_limit_queries_is_all_questions():
    # Mac dinh CU la 50 - mot cai bay cho script BASELINE: chay khong tham so
    # se ra con so tren 50 cau roi bi hieu la baseline chinh thuc. Baseline
    # phai mac dinh do TOAN BO gold set (None = khong gioi han), giong
    # `eval_zalo_recall.py` cua du an cu (`--limit` la tuy chon).
    import inspect

    from scripts.eval_hybrid_reranker_baseline import run_eval

    assert inspect.signature(run_eval).parameters["limit_queries"].default is None


def test_cli_default_matches_function_default_for_limit_queries():
    # BUG THAT tu gay ra (2026-08-08): doi default cua `run_eval` tu 50 -> None
    # nhung QUEN default cua argparse -> argparse van truyen 50 vao, ghi de gia
    # tri mac dinh cua ham. Chay CLI khong tham so van do tren 50 cau, va
    # checkpoint ghi n_questions=50. "Sua nua voi" nhu vay khong test nao cu
    # bat duoc vi test chi kiem signature cua ham.
    import inspect

    from scripts.eval_hybrid_reranker_baseline import build_arg_parser, run_eval

    cli_default = build_arg_parser().parse_args(["data/raw"]).limit_queries
    fn_default = inspect.signature(run_eval).parameters["limit_queries"].default
    assert cli_default == fn_default, (
        f"default CLI ({cli_default!r}) khac default ham ({fn_default!r}) - "
        "CLI se ghi de gia tri mac dinh cua ham"
    )


def test_completing_one_strategy_does_not_wipe_another_strategys_in_progress():
    # BUG THAT (2026-08-08) da lam MAT 720/793 cau da rerank (~5.6 gio may):
    # `_evaluate` set `checkpoint["in_progress"] = None` VO DIEU KIEN khi mot
    # chien luoc xong. Khi them chien luoc "2b" vao giua luc reranker dang co
    # state do dang (next_index=720), viec 2b hoan tat da XOA state cua
    # reranker -> lan chay sau bat dau lai tu 0.
    #
    # `in_progress` chi duoc xoa khi no THUOC VE chinh chien luoc vua xong.
    checkpoint = {
        "completed": {},
        "in_progress": {
            "3. Hybrid + Reranker": {
                "name": "3. Hybrid + Reranker", "next_index": 720,
                "hits": 631, "rr_total": 538.5,
            }
        },
        "n_questions": 3,
    }
    saved = []
    original = ehrb._save_checkpoint
    ehrb._save_checkpoint = lambda c: saved.append(c)
    try:
        ehrb._evaluate(
            "2b. Hybrid (khac)",
            lambda q: ["dung"],
            ["q1", "q2", "q3"],
            ["dung", "dung", "dung"],
            4,
            checkpoint,
        )
    finally:
        ehrb._save_checkpoint = original

    assert "2b. Hybrid (khac)" in checkpoint["completed"]
    assert "3. Hybrid + Reranker" in checkpoint["in_progress"], (
        "state do dang cua chien luoc KHAC da bi xoa"
    )
    assert checkpoint["in_progress"]["3. Hybrid + Reranker"]["next_index"] == 720


def test_completing_a_strategy_clears_its_own_in_progress():
    checkpoint = {
        "completed": {},
        "in_progress": {"X": {"name": "X", "next_index": 2, "hits": 1, "rr_total": 1.0}},
        "n_questions": 3,
    }
    original = ehrb._save_checkpoint
    ehrb._save_checkpoint = lambda c: None
    try:
        ehrb._evaluate("X", lambda q: ["dung"], ["q1", "q2", "q3"],
                       ["dung", "dung", "dung"], 4, checkpoint)
    finally:
        ehrb._save_checkpoint = original

    assert "X" not in checkpoint["in_progress"]
