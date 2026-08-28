"""Tests cho logic cham diem QA (scripts/eval_bhxh_qa.py) - khong goi
LLM/Neo4j, chi kiem tra ham cham diem thuan."""
import json
from pathlib import Path

from scripts.eval_bhxh_qa import _score_free, _score_mc, _score_out_of_scope, _score_true_false

QA_PATH = Path("data/eval/bhxh_qa_set.json")


def test_true_false_dung():
    assert _score_true_false("Đúng.", "Đúng") is True
    assert _score_true_false("Câu này Sai.", "Đúng") is False


def test_true_false_sai_and_khong_dung():
    assert _score_true_false("Sai", "Sai") is True
    assert _score_true_false("Điều này không đúng.", "Sai") is True
    assert _score_true_false("Đúng", "Sai") is False


def test_mc_extracts_letter():
    assert _score_mc("C", "C") is True
    assert _score_mc("Đáp án: C) 06 tháng", "C") is True
    assert _score_mc("B", "C") is False


def test_mc_extracts_letter_with_qualifier_words_between_dap_an_and_la():
    """Bug that tim thay khi dao sau nguyen nhan QA accuracy tut sau doi
    Luat Viec lam 2025 (xem README.md "Vi sao 89.1%->86.4%"): LLM viet "dap an CHINH XAC la B" - hai
    tu "CHINH XAC" chen giua "dap an" va "la" khien pattern cu (chi cho
    phep LA/:/khoang trang ngay sau "DAP AN") khong khop, cham SAI oan du
    noi dung dung."""
    ans = (
        "Dựa trên quy định tại Điều 41..., người lao động phải đóng bảo hiểm "
        "thất nghiệp đủ 12 tháng trong vòng 24 tháng...\n\n"
        "Vì vậy, đáp án chính xác là:\n\nB) 12 tháng"
    )
    assert _score_mc(ans, "B") is True


def test_free_text_needs_all_key_facts():
    ans = "Lao động nữ nghỉ 06 tháng, trước sinh không quá 02 tháng."
    facts_ok, cite_ok = _score_free(ans, ["06 tháng", "02 tháng"], ["45-2019-qh14_dieu-139"], ["45-2019-qh14_dieu-139"])
    assert facts_ok is True and cite_ok is True
    # thieu 1 fact -> fail
    facts_ok2, _ = _score_free("nghỉ 06 tháng", ["06 tháng", "02 tháng"], [], ["x"])
    assert facts_ok2 is False


def test_out_of_scope_recognizes_refusal_markers():
    assert _score_out_of_scope("Chưa tìm thấy quy định cụ thể trong dữ liệu.") is True
    assert _score_out_of_scope("Xin lỗi, không có thông tin về vấn đề này.") is True
    # LLM bia noi dung -> KHONG duoc coi la refusal.
    assert _score_out_of_scope("Cách nấu phở là dùng xương bò hầm 6 tiếng.") is False


def test_qa_set_schema_valid():
    data = json.loads(QA_PATH.read_text(encoding="utf-8"))
    qs = data["questions"]
    assert len(qs) >= 10
    for q in qs:
        assert q["type"] in {"true_false", "multiple_choice", "free_text", "out_of_scope"}
        if q["type"] == "true_false":
            assert q["gold_article_ids"] and q["answer"] in {"Đúng", "Sai"}
        elif q["type"] == "multiple_choice":
            assert q["gold_article_ids"] and q["answer"] in q["options"]
        elif q["type"] == "free_text":
            assert q["gold_article_ids"] and q["key_facts"]
        else:  # out_of_scope: khong co gold, khong co dap an
            assert q["gold_article_ids"] == []
