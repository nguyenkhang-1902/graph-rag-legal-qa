"""Tests cho T3 (BHXH-P1): Document mang metadata hieu luc (ngay_hieu_luc,
ngay_het_hieu_luc, trang_thai, che_do) + DocIdentity mo rong.

Cung pattern voi tests/graph_store/test_upsert.py: mock `Neo4jClient.run`,
kiem tra Cypher + tham so GUI DI - khong chay Neo4j that, khong fixture
`neo4j_client`.
"""
from unittest.mock import MagicMock

from app.extraction.doc_identity import DocIdentity
from app.extraction.structure_parser import parse_document
from app.graph_store.upsert import upsert_document


def test_document_query_sends_effective_fields():
    client = MagicMock()
    parsed = parse_document("Điều 1. Phạm vi.\n1. Nội dung.", fallback_doc_id="41_2024_luat")
    ident = DocIdentity(
        doc_id="41_2024_luat",
        so_hieu="41/2024/QH15",
        loai_vb="Luật",
        title="Luật 41/2024/QH15",
        ngay_hieu_luc="2025-07-01",
        ngay_het_hieu_luc=None,
        trang_thai="active",
        che_do=["huu_tri"],
    )
    upsert_document(client, parsed, batch_id="t3", identity=ident)
    # Cau Document (call dau tien) phai mang params hieu luc + query chua field moi
    q, kwargs = client.run.call_args_list[0].args[0], client.run.call_args_list[0].kwargs
    assert "ngay_hieu_luc" in q and "trang_thai" in q and "che_do" in q
    assert kwargs["ngay_hieu_luc"] == "2025-07-01" and kwargs["trang_thai"] == "active"
    assert kwargs["che_do"] == ["huu_tri"]


def test_upsert_document_without_identity_still_works_and_omits_new_params():
    # Nhanh _DOCUMENT_QUERY cu (khong truyen identity) KHONG duoc thay doi -
    # khong gui 4 param moi (se am tham xoa gia tri da ghi truoc do neu gui
    # null, cung triet ly voi so_hieu/loai_vb da co san trong upsert.py).
    client = MagicMock()
    parsed = parse_document("Điều 1. Phạm vi.\n1. Nội dung.", fallback_doc_id="doc-khong-identity")

    upsert_document(client, parsed, batch_id="t3")

    q, kwargs = client.run.call_args_list[0].args[0], client.run.call_args_list[0].kwargs
    for field in ("ngay_hieu_luc", "ngay_het_hieu_luc", "trang_thai", "che_do"):
        assert field not in q
        assert field not in kwargs
