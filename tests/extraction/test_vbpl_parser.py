"""test_vbpl_parser.py (BHXH-P1-T2): TDD cho app/extraction/vbpl_parser.py.

Input la text DA RENDER (khong phai HTML tho) tu 2 tab cua trang chi tiet
vbpl.vn: "Noi dung" (toan van) va "Thuoc tinh" (bang metadata nhan->gia
tri) - xem tests/fixtures/bhxh/vbpl-source-notes.md.
"""
from pathlib import Path

from app.extraction.vbpl_parser import parse_vbpl_content

FIX = Path(__file__).parent.parent / "fixtures" / "bhxh" / "luat-bhxh-2024-excerpt.txt"


def test_extracts_effective_date_and_articles():
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"))
    assert doc.ngay_hieu_luc == "2025-07-01"  # tu cau "co hieu luc ke tu ngay 01 thang 7 nam 2025"
    assert doc.parsed.articles or doc.parsed.chapters  # tach duoc Dieu 1, Dieu 2


def test_extracts_so_hieu_from_noi_dung_text():
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"))
    # "Luat Bao hiem xa hoi so 41/2024/QH15 ngay 29 thang 6 nam 2024..."
    assert doc.so == "41"
    assert doc.nam == "2024"
    assert doc.ma_hieu == "QH15"


def test_fixture_has_chuong_structure():
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"))
    assert len(doc.parsed.chapters) >= 1
    assert doc.parsed.chapters[0].so_chuong == 1
    dieu_ids = [a.article_id for a in doc.parsed.chapters[0].articles]
    assert any(aid.endswith("_dieu-1") for aid in dieu_ids)
    assert any(aid.endswith("_dieu-2") for aid in dieu_ids)


def test_ngay_het_hieu_luc_missing_returns_none():
    # Khong co thuoc_tinh_text va khong co cau "het hieu luc" trong noi
    # dung -> None, KHONG doan bua (constitution: khong doan).
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"))
    assert doc.ngay_het_hieu_luc is None


def test_thuoc_tinh_text_provides_ngay_hieu_luc_and_het_hieu_luc():
    thuoc_tinh = (
        "Số hiệu: 41/2024/QH15\n"
        "Loại văn bản: Luật\n"
        "Ngày có hiệu lực: 01/07/2025\n"
        "Ngày hết hiệu lực: --\n"
    )
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"), thuoc_tinh_text=thuoc_tinh)
    assert doc.ngay_hieu_luc == "2025-07-01"
    assert doc.ngay_het_hieu_luc is None  # "--" khong phai ngay hop le


def test_thuoc_tinh_text_with_real_het_hieu_luc_date():
    thuoc_tinh = (
        "Số hiệu: 41/2024/QH15\n"
        "Ngày có hiệu lực: 01/07/2025\n"
        "Ngày hết hiệu lực: 31/12/2030\n"
    )
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"), thuoc_tinh_text=thuoc_tinh)
    assert doc.ngay_het_hieu_luc == "2030-12-31"


def test_ngay_hieu_luc_absent_does_not_borrow_next_label_date():
    # "Ngay co hieu luc" la "--" (rong/khong co) nhung nhan KE TIEP ("Ngay
    # het hieu luc") co ngay that ngay sau do trong cua so ky tu quet -
    # PHAI tra None cho ngay_hieu_luc, KHONG duoc "muon" nham ngay cua
    # nhan khac (bug review round 1: cua so 60 ky tu co the tran qua nhan
    # ke tiep va doan bua sai truong). Dung noi_dung_text KHONG chua cum
    # "hieu luc" nao de co lap dung loi trong _extract_labeled_date, tranh
    # nham lan voi hanh vi fallback sang cau mo dau (da co test rieng o
    # test_thuoc_tinh_text_takes_priority_over_noi_dung_opening_sentence).
    noi_dung_khong_co_ngay = "# Van ban test\n\nĐiều 1. Tieu de\nNoi dung khong nhac ngay thang gi ca.\n"
    thuoc_tinh = (
        "Ngày có hiệu lực: --\n"
        "Ngày hết hiệu lực: 31/12/2030\n"
    )
    doc = parse_vbpl_content(noi_dung_khong_co_ngay, thuoc_tinh_text=thuoc_tinh)
    assert doc.ngay_hieu_luc is None
    assert doc.ngay_het_hieu_luc == "2030-12-31"


def test_thuoc_tinh_text_takes_priority_over_noi_dung_opening_sentence():
    # thuoc_tinh_text co ngay khac voi cau mo dau trong noi_dung_text ->
    # uu tien thuoc_tinh_text (brief: "HOAC", thuoc_tinh truoc).
    thuoc_tinh = "Ngày có hiệu lực: 15/08/2026\n"
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"), thuoc_tinh_text=thuoc_tinh)
    assert doc.ngay_hieu_luc == "2026-08-15"
