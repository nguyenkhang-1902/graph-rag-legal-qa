"""Tests cho freshness check (GD2) - CHI ham THUAN classify_status + import.
Phan search that (mang) xac minh bang chay tay."""
from scripts.check_corpus_freshness import (
    STATUS_CURRENT,
    STATUS_EXPIRED,
    STATUS_PARTIAL,
    STATUS_UNKNOWN,
    classify_status,
)


def test_classify_current():
    assert classify_status("Còn hiệu lực") == STATUS_CURRENT


def test_classify_expired_full():
    assert classify_status("Hết hiệu lực toàn bộ") == STATUS_EXPIRED
    assert classify_status("Hết hiệu lực") == STATUS_EXPIRED


def test_classify_partial_takes_precedence():
    # "Het hieu luc mot phan" chua ca "het hieu luc" -> phai ra PARTIAL, khong EXPIRED.
    assert classify_status("Hết hiệu lực một phần") == STATUS_PARTIAL


def test_classify_unknown_on_empty_or_noise():
    assert classify_status(None) == STATUS_UNKNOWN
    assert classify_status("") == STATUS_UNKNOWN
    assert classify_status("Đang cập nhật") == STATUS_UNKNOWN


def test_freshness_imports():
    import scripts.check_corpus_freshness as m
    assert hasattr(m, "main") and hasattr(m, "_live_status")


def test_title_matches_so_hieu_exact():
    from scripts.check_corpus_freshness import title_matches_so_hieu
    assert title_matches_so_hieu("Nghị định số 12/2022/NĐ-CP Quy định xử phạt", "12/2022/NĐ-CP")


def test_title_matches_rejects_superstring():
    # "112/2022/NĐ-CP" KHONG duoc coi la khop "12/2022/NĐ-CP".
    from scripts.check_corpus_freshness import title_matches_so_hieu
    assert not title_matches_so_hieu("Nghị định số 112/2022/NĐ-CP Biểu thuế", "12/2022/NĐ-CP")
