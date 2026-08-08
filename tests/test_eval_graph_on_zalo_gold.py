"""Tests cho scripts/eval_graph_on_zalo_gold.py (T018, manh con thieu).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi script ton tai.

=== VI SAO CAN SCRIPT NAY ===
Truoc do KHONG co so lieu nao cho phep so sanh Graph RAG voi baseline:
  - `eval_graph_recall.py` (T017) do Graph RAG tren **32 cau multi-hop** tu
    soan, dung strict/lenient recall (moi cau co NHIEU dap an).
  - `eval_hybrid_reranker_baseline.py` (T018) do baseline tren **793 cau Zalo
    gold**, dung Recall@4 (moi cau co MOT dap an).
Dat 90.6% canh 82.1% la so sanh HAI BO CAU HOI KHAC NHAU - dung loi phuong
phap da phat hien o DOT 13. Script nay chay Graph RAG tren DUNG 793 cau Zalo
gold, dung DUNG metric cua baseline.

=== HAI CON SO, VA VI SAO PHAI CO CA HAI ===
Danh sach xep hang cua Graph RAG la: entry point (dense, toi da `top_k`) TRUOC,
roi Article tim them qua traversal SAU. Hau qua toan hoc quan trong: voi
`top_k=5` va `k=4`, **4 slot dau LUON la entry point** - traversal khong bao gio
chen duoc vao top-4. Nghia la Recall@4 cua Graph RAG bang dung Recall@4 cua
dense-only (tru phan bi SIMILARITY_THRESHOLD loc bo, chi co the lam GIAM).

Vi vay script bao CA HAI:
  1. `recall_at_k` - CAT danh sach con k phan tu. So sanh TRUC TIEP duoc voi
     baseline, nhung theo cau truc thi khong the hon dense-only.
  2. `recall_expanded` - dap an nam BAT KY DAU trong tap mo rong (entry point
     + traversal). Cho thay traversal them duoc gi, nhung KHONG so sanh duoc
     voi Recall@4 (tap lon hon nhieu).
Bao mot con so ma khong bao con kia la trinh bay gay nham lan - dung dieu can
tranh theo muc I1 trong CHECKLIST.
"""
import pytest

from scripts.eval_graph_on_zalo_gold import evaluate_ranked_lists


def test_recall_at_k_only_counts_expected_inside_first_k():
    # Dap an o vi tri 5 -> KHONG tinh cho recall_at_k=4, NHUNG van tinh cho
    # recall_expanded (day chinh la truong hop traversal "them" duoc).
    result = evaluate_ranked_lists([["a", "b", "c", "d", "dung"]], ["dung"], k=4)
    assert result["recall_at_k"] == 0.0
    assert result["recall_expanded"] == 1.0


def test_recall_at_k_counts_expected_inside_first_k():
    result = evaluate_ranked_lists([["a", "dung", "c", "d", "e"]], ["dung"], k=4)
    assert result["recall_at_k"] == 1.0
    assert result["recall_expanded"] == 1.0


def test_mrr_uses_position_in_full_ranked_list_not_truncated():
    # MRR duoc tinh tren danh sach DAY DU (khong cat) - de phan biet duoc
    # "tim thay o vi tri 5" voi "khong tim thay". Neu cat truoc khi tinh MRR
    # thi ca hai deu ra 0 va mat thong tin.
    result = evaluate_ranked_lists([["a", "b", "c", "d", "dung"]], ["dung"], k=4)
    assert result["mrr"] == pytest.approx(1 / 5)


def test_mrr_is_one_when_expected_first():
    result = evaluate_ranked_lists([["dung", "b"]], ["dung"], k=4)
    assert result["mrr"] == 1.0


def test_not_found_anywhere_gives_zero_on_all_three_metrics():
    result = evaluate_ranked_lists([["a", "b"]], ["khong-co"], k=4)
    assert result["recall_at_k"] == 0.0
    assert result["recall_expanded"] == 0.0
    assert result["mrr"] == 0.0


def test_averages_across_questions():
    ranked = [["dung1", "x"], ["y", "z", "dung2"]]
    expected = ["dung1", "dung2"]
    result = evaluate_ranked_lists(ranked, expected, k=2)
    # Cau 1: trong top-2 -> hit. Cau 2: o vi tri 3, ngoai top-2 -> miss o
    # recall_at_k nhung hit o recall_expanded.
    assert result["recall_at_k"] == 0.5
    assert result["recall_expanded"] == 1.0
    assert result["mrr"] == pytest.approx((1.0 + 1 / 3) / 2)


def test_reports_question_count_for_audit():
    # Bai hoc tu bug DOT 15 (92.0% do tren 50 cau bi in canh so do tren 793
    # cau): moi ket qua PHAI mang theo so cau hoi de khong bao gio bi doc lech
    # quy mo nua.
    result = evaluate_ranked_lists([["a"], ["b"]], ["a", "b"], k=1)
    assert result["total"] == 2


def test_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="khong khop"):
        evaluate_ranked_lists([["a"], ["b"]], ["a"], k=1)


def test_empty_input_returns_zeros_not_crash():
    result = evaluate_ranked_lists([], [], k=4)
    assert result["recall_at_k"] == 0.0
    assert result["recall_expanded"] == 0.0
    assert result["mrr"] == 0.0
    assert result["total"] == 0
