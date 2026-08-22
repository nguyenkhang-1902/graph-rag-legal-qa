"""Tests cho BHXH-P2-T2: `extract_bhxh_references.py` - trich xuat canh
REFERENCES (trich dan noi van ban) cho corpus BHXH da fetch, cho multi-hop
graph traversal hoat dong.

Cung pattern voi `tests/ingest/test_bhxh_ingest.py`: mock `upsert_references`
(MagicMock) - KHONG chay Neo4j that. Dung engine THAT cho phan parse/extract
(`parse_vbpl_content`, `extract_references`) - fixture la text THAT (Dieu
1-2 Luat BHXH 41/2024/QH15), khong phai gia lap.
"""
from pathlib import Path
from unittest.mock import MagicMock

import scripts.extract_bhxh_references as extract_bhxh_references_module
from scripts.extract_bhxh_references import _noidung_files, extract_bhxh_references

FIXTURE = (
    Path(__file__).resolve().parent.parent
    / "fixtures"
    / "bhxh"
    / "luat-bhxh-2024-excerpt.txt"
)

# Fixture goc (Dieu 1-2 Luat BHXH) khong chua trich dan "Dieu N" nao - them
# mot cau trich dan tong hop o CUOI file (nam trong noi dung Dieu 2, Dieu
# CUOI CUNG cua fixture) de co mot test case biet truoc ket qua resolve
# (theo brief task-2: "add a small synthetic text with a known citation").
_SYNTHETIC_CITATION = (
    "\nViệc xác định đối tượng tham gia được hướng dẫn chi tiết theo Điều 2 "
    "của Luật này.\n"
)


def _write_fixture_pair(tmp_path: Path, slug: str = "luat-bhxh-2024") -> Path:
    """Ghi mot cap file `<slug>.txt` (noi_dung = fixture that + cau trich
    dan tong hop) / `<slug>.tt.txt` (thuoc_tinh rong - fixture da co du so
    hieu trong chinh noi_dung) vao `tmp_path`, tra ve duong dan file
    noi_dung (dung dinh dang `fetch_bhxh_corpus.py` da ghi ra dia)."""
    noi_dung_text = FIXTURE.read_text(encoding="utf-8") + _SYNTHETIC_CITATION
    noi_dung_path = tmp_path / f"{slug}.txt"
    noi_dung_path.write_text(noi_dung_text, encoding="utf-8")
    (tmp_path / f"{slug}.tt.txt").write_text("", encoding="utf-8")
    return noi_dung_path


def test_noidung_files_excludes_thuoc_tinh_sidecars(tmp_path):
    _write_fixture_pair(tmp_path, slug="van-ban-a")
    _write_fixture_pair(tmp_path, slug="van-ban-b")

    files = _noidung_files(tmp_path)

    names = [p.name for p in files]
    assert names == ["van-ban-a.txt", "van-ban-b.txt"]
    assert not any(name.endswith(".tt.txt") for name in names)


def test_extract_bhxh_references_calls_upsert_once_per_article(tmp_path):
    # Dung upsert_references THAT (khong monkeypatch) - `client` la MagicMock
    # nen `client.run(...)` ben trong upsert_references chi ghi lai loi goi,
    # KHONG dung Neo4j that (cung nguyen tac voi test_bhxh_ingest.py).
    noi_dung_path = _write_fixture_pair(tmp_path)
    client = MagicMock()

    total = extract_bhxh_references([noi_dung_path], client)

    # Dung 1 cau trich dan tong hop trong toan bo fixture (Dieu 2) -> tong
    # so trich dan = 1, va upsert_references THAT goi client.run() DUNG 1
    # lan (Dieu 1 co list rong -> khong goi client.run, Dieu 2 co 1 trich
    # dan -> 1 loi goi client.run).
    assert total == 1
    assert client.run.call_count == 1


def test_extract_bhxh_references_resolves_known_citation_to_dieu_2(tmp_path, monkeypatch):
    noi_dung_path = _write_fixture_pair(tmp_path)
    client = MagicMock()
    mock_upsert = MagicMock()
    monkeypatch.setattr(
        extract_bhxh_references_module, "upsert_references", mock_upsert
    )

    extract_bhxh_references([noi_dung_path], client)

    # DUNG 2 loi goi (1 / Dieu) - moi loi goi la (client, article_id, list).
    assert mock_upsert.call_count == 2
    all_article_ids = [c.args[1] for c in mock_upsert.call_args_list]
    assert all(isinstance(c.args[2], list) for c in mock_upsert.call_args_list)
    assert all(c.args[0] is client for c in mock_upsert.call_args_list)

    # Cau trich dan tong hop nam trong Dieu 2 (Dieu cuoi cung cua fixture) -
    # tim loi goi cho article_id ket thuc "_dieu-2", assert no chua DUNG MOT
    # ExtractedReference tro toi "..._dieu-2" (tu trich dan, "cua Luat nay").
    dieu_2_calls = [
        c for c in mock_upsert.call_args_list if c.args[1].endswith("_dieu-2")
    ]
    assert len(dieu_2_calls) == 1
    references = dieu_2_calls[0].args[2]
    assert len(references) == 1
    assert references[0].target_article_id.endswith("_dieu-2")
    assert "Điều 2" in references[0].raw_text

    # Dieu 1 (khong chua trich dan) phai duoc goi voi list RONG - KHONG bi
    # bo qua/skip (idempotent, dam bao moi Dieu deu duoc xu ly du khong co
    # trich dan nao, giong _ingest_one_file goi upsert_references vo dieu
    # kien cho MOI article).
    dieu_1_calls = [
        c for c in mock_upsert.call_args_list if c.args[1].endswith("_dieu-1")
    ]
    assert len(dieu_1_calls) == 1
    assert dieu_1_calls[0].args[2] == []
