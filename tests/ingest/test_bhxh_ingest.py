"""Tests cho T5 (BHXH-P1): `ingest_vbpl_doc` - adapter tu text da render cua
vbpl.vn (Playwright) sang graph, qua engine THAT (parse_vbpl_content ->
build_doc_identity -> upsert_document).

Cung pattern voi tests/graph_store/test_temporal_upsert.py: mock
`Neo4jClient.run` (MagicMock), kiem tra Cypher + tham so GUI DI cho query
Document - KHONG chay Playwright/mang, KHONG chay Neo4j that (Ruling 2).
`FIXTURE` la text THAT (Dieu 1-2 Luat BHXH 41/2024/QH15), khong phai gia
lap - dam bao test khop dung dinh dang `parse_vbpl_content` ky vong.
"""
from pathlib import Path
from unittest.mock import MagicMock

from scripts.fetch_bhxh_corpus import _strip_page_chrome, ingest_vbpl_doc

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "bhxh"
    / "luat-bhxh-2024-excerpt.txt"
)

BODY_FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "bhxh"
    / "vbpl-detail-page-body-excerpt.txt"
)


def test_ingest_vbpl_doc_sets_effective_date_and_che_do():
    client = MagicMock()
    noi_dung_text = FIXTURE.read_text(encoding="utf-8")

    doc_id = ingest_vbpl_doc(
        client, noi_dung_text, che_do=["huu_tri", "mot_lan", "thai_san"]
    )

    # Cau Document (call dau tien cua upsert_document) phai mang ngay_hieu_luc
    # trich tu cau "co hieu luc ke tu ngay 01 thang 7 nam 2025" trong fixture
    # (KHONG truyen thuoc_tinh_text - parse_vbpl_content phai tu roi vao
    # noi_dung_text, dung nhu doc string cua ham do).
    q = client.run.call_args_list[0].args[0]
    kwargs = client.run.call_args_list[0].kwargs
    assert "ngay_hieu_luc" in q and "che_do" in q
    assert kwargs["doc_id"] == doc_id
    assert kwargs["ngay_hieu_luc"] == "2025-07-01"
    assert kwargs["che_do"] == ["huu_tri", "mot_lan", "thai_san"]
    # ngay_het_hieu_luc khong co nguon nao trong fixture (khong co
    # thuoc_tinh_text) -> phai la None, KHONG doan bua.
    assert kwargs["ngay_het_hieu_luc"] is None


def test_ingest_vbpl_doc_returns_the_actual_graph_merge_key():
    # `upsert_document` LUON dung `parsed.doc_id` (khong phai
    # `identity.doc_id` sinh boi build_doc_identity/slugify - xem ghi chu
    # trong fetch_bhxh_corpus.ingest_vbpl_doc) lam khoa MERGE cua node
    # Document. doc_id tra ve PHAI khop dung tham so `doc_id` da gui cho
    # Cypher, neu khong `MATCH (d:Document {doc_id: $id})` voi doc_id tra
    # ve se KHONG tim thay node vua ghi (day chinh la loi phat hien khi
    # viet test nay: fixture khong co dong "# title" nen parsed.doc_id la
    # "41-2024-QH15" - CHUA slugify - khac voi ident.doc_id da slugify).
    client = MagicMock()
    noi_dung_text = FIXTURE.read_text(encoding="utf-8")

    doc_id = ingest_vbpl_doc(client, noi_dung_text, che_do=["huu_tri"])

    kwargs = client.run.call_args_list[0].kwargs
    assert doc_id == kwargs["doc_id"]


def test_ingest_vbpl_doc_writes_article_hierarchy_from_fixture():
    # Fixture co Dieu 1 va Dieu 2 (voi khoan 1) trong Chuong I - dam bao
    # pipeline day toi upsert_document that (khong chi dung o Document node).
    client = MagicMock()
    noi_dung_text = FIXTURE.read_text(encoding="utf-8")

    ingest_vbpl_doc(client, noi_dung_text, che_do=["huu_tri"])

    all_queries = [call.args[0] for call in client.run.call_args_list]
    assert any("MERGE (a:Article" in q for q in all_queries)
    assert any("MERGE (c:Chapter" in q for q in all_queries)


# --- _strip_page_chrome: bug that phat hien khi chay smoke T5 -------------
#
# `page.inner_text("body")` mang ca breadcrumb/menu/bang tom tat dau trang
# (co dong "Ngay co hieu luc: --" roi "Ngay cap nhat: <ngay Playwright fetch
# trang>") TRUOC noi dung THAT cua van ban. Neu khong cat, parser doc nham
# "ngay cap nhat trang" thanh ngay_hieu_luc PHAP LY (sai hoan toan). Fixture
# `vbpl-detail-page-body-excerpt.txt` la TRICH THAT tu ket qua fetch
# `BHXH_CORPUS_URLS[0]` (2026-08-21) - khong phai gia lap.


def test_strip_page_chrome_removes_nav_and_metadata_strip():
    raw = BODY_FIXTURE.read_text(encoding="utf-8")

    stripped = _strip_page_chrome(raw)

    # Chrome (breadcrumb, menu, "Ngay cap nhat") phai bien mat.
    assert "Trang chủ" not in stripped
    assert "Ngày cập nhật" not in stripped
    # Noi dung THAT cua van ban phai con nguyen, bat dau tu quoc hieu.
    assert stripped.lstrip().startswith("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")
    assert "Điều 1. Phạm vi điều chỉnh" in stripped


def test_strip_page_chrome_fixes_false_positive_ngay_hieu_luc():
    # Regression cho chinh loi da phat hien: KHONG cat -> parser bat nham
    # "14/08/2026" (ngay cap nhat trang, tu dong "Ngay co hieu luc: --" rong
    # roi "Ngay cap nhat: 14/08/2026" ngay sau). CO cat -> dung "2025-07-01"
    # (ngay hieu luc PHAP LY that, trich tu chinh van ban).
    from app.extraction.vbpl_parser import parse_vbpl_content

    raw = BODY_FIXTURE.read_text(encoding="utf-8")

    without_strip = parse_vbpl_content(raw)
    assert without_strip.ngay_hieu_luc == "2026-08-14"  # bug: ngay cap nhat trang

    with_strip = parse_vbpl_content(_strip_page_chrome(raw))
    assert with_strip.ngay_hieu_luc == "2025-07-01"  # dung: ngay hieu luc that


def test_strip_page_chrome_returns_input_unchanged_when_marker_absent():
    # Input da la text sach (khong co chrome, vd fixture Dieu 1-2 hien co)
    # -> khong tim thay marker -> tra ve nguyen van, khong cat nham.
    clean_text = FIXTURE.read_text(encoding="utf-8")
    assert _strip_page_chrome(clean_text) == clean_text
