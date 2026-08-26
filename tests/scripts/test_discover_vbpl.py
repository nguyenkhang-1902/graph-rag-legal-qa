"""Tests cho resolver discover_vbpl - CHI cac ham THUAN (khong chay mang/
Playwright): parse metadata ket qua + import module. Phan click/search that
duoc xac minh bang chay tay end-to-end (co mang), khong o unit test."""
from scripts.discover_vbpl import parse_result_meta


def test_parse_result_meta_full():
    # Text that trich tu khoi <li> ket qua vbpl.vn (search "145/2020/NĐ-CP").
    text = (
        "Nghị định số 145/2020/NĐ-CP Quy định chi tiết ... quan hệ lao động "
        "PDF Lược đồ Tải về Trạng thái: Hết hiệu lực một phần "
        "Ngày ban hành: 14/12/2020 Ngày hiệu lực: 01/02/2021 Cơ quan..."
    )
    meta = parse_result_meta(text)
    assert meta["trang_thai"] == "Hết hiệu lực một phần"
    assert meta["ngay_ban_hanh"] == "14/12/2020"
    assert meta["ngay_hieu_luc"] == "01/02/2021"


def test_parse_result_meta_missing_fields_returns_none():
    meta = parse_result_meta("Nghị định vu vơ không có metadata")
    assert meta == {
        "trang_thai": None,
        "ngay_ban_hanh": None,
        "ngay_hieu_luc": None,
    }


def test_discover_vbpl_imports():
    import scripts.discover_vbpl as dv

    assert hasattr(dv, "search_vbpl") and hasattr(dv, "main")
