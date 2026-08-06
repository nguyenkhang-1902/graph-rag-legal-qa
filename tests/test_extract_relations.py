"""Tests cho scripts/extract_relations.py (T013 - orchestration).

Cung quy uoc "honest mocking" voi tests/test_extract_terms.py: mock
Neo4jClient VA `relation_llm.classify_candidate` (khong goi Ollama that
trong unit test - da co test rieng cho `_call_ollama`/`classify_candidate`
trong tests/extraction/test_relation_llm.py), dung file that trong
tmp_path cho discover/parse (tai dung app.ingest's helper qua
run_extract_relations that - kiem tra CA pipeline noi voi nhau dung, chi
LLM call la mock boundary duy nhat).

Trong tam:
  1. Mot Article co candidate (trigger + trich dan co ten van ban) va LLM
     xac nhan -> upsert_relations duoc goi voi dung relationship_type/rows.
  2. LLM tra ve None (khong xac nhan quan he) -> KHONG ghi vao Neo4j.
  3. Nhieu quan he khac loai -> upsert_relations duoc goi RIENG cho moi
     relationship_type (Cypher type khong tham so hoa duoc - upsert.py).
  4. Khong co candidate nao -> classify_candidate KHONG duoc goi (giu dung
     muc dich candidate narrowing: giam so lan goi LLM).
  5. Batching: nhieu row hon batch_size -> nhieu loi goi upsert_relations.
  6. Client injection: giong pattern run_extract_terms.
"""
from pathlib import Path
from unittest.mock import MagicMock

from app.extraction.relation_llm import ExtractedRelation
from app.extraction.slugify import slugify_doc_name
from scripts.extract_relations import run_extract_relations


def _write_article_chunk_file(
    data_dir: Path, filename: str, so_dieu: int, title: str, body: str
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    content = f"# Điều {so_dieu}. {title}\n\n{body}\n"
    (data_dir / filename).write_text(content, encoding="utf-8")


def _make_mock_client() -> MagicMock:
    return MagicMock()


def test_confirmed_candidate_triggers_upsert_relations_with_correct_type(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir,
        "01_2020_tt-btp_1.md",
        1,
        "A",
        "Điều 5 Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau: nội dung mới.",
    )

    mock_client = _make_mock_client()
    mock_upsert_relations = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_relations.upsert_relations", mock_upsert_relations
    )
    mock_classify = MagicMock(
        return_value=ExtractedRelation(
            target_article_id="luat-doanh-nghiep-2020_dieu-5",
            relationship_type="AMENDS",
            confidence=0.9,
            ly_do="sửa đổi trực tiếp",
        )
    )
    monkeypatch.setattr("scripts.extract_relations.classify_candidate", mock_classify)

    run_extract_relations(data_dir, client=mock_client)

    doc_id = slugify_doc_name("01_2020_tt-btp")
    mock_upsert_relations.assert_called_once_with(
        mock_client,
        "AMENDS",
        [
            {
                "source_article_id": f"{doc_id}_dieu-1",
                "target_article_id": "luat-doanh-nghiep-2020_dieu-5",
                "confidence": 0.9,
                "ly_do": "sửa đổi trực tiếp",
            }
        ],
    )


def test_llm_not_confirming_relation_writes_nothing(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir,
        "01_2020_tt-btp_1.md",
        1,
        "A",
        "Điều 5 Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau: nội dung mới.",
    )

    mock_client = _make_mock_client()
    mock_upsert_relations = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_relations.upsert_relations", mock_upsert_relations
    )
    monkeypatch.setattr(
        "scripts.extract_relations.classify_candidate", MagicMock(return_value=None)
    )

    run_extract_relations(data_dir, client=mock_client)

    mock_upsert_relations.assert_not_called()


def test_no_candidate_does_not_call_llm(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_1.md", 1, "A", "Không có gì đặc biệt ở đây cả."
    )

    mock_client = _make_mock_client()
    mock_classify = MagicMock()
    monkeypatch.setattr("scripts.extract_relations.classify_candidate", mock_classify)
    monkeypatch.setattr(
        "scripts.extract_relations.upsert_relations", MagicMock()
    )

    run_extract_relations(data_dir, client=mock_client)

    mock_classify.assert_not_called()


def test_different_relationship_types_call_upsert_relations_separately(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir,
        "01_2020_tt-btp_1.md",
        1,
        "A",
        "Điều 5 Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau: nội dung mới.",
    )
    _write_article_chunk_file(
        data_dir,
        "02_2020_tt-btp_1.md",
        1,
        "B",
        "Điều 8 Luật Đầu tư 2020 hết hiệu lực kể từ ngày văn bản này ban hành.",
    )

    mock_client = _make_mock_client()
    mock_upsert_relations = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_relations.upsert_relations", mock_upsert_relations
    )

    def fake_classify(source_article_id, candidate):
        if candidate.relationship_type_hint == "AMENDS":
            return ExtractedRelation(
                target_article_id=candidate.target_article_id,
                relationship_type="AMENDS",
                confidence=0.9,
                ly_do="x",
            )
        return ExtractedRelation(
            target_article_id=candidate.target_article_id,
            relationship_type="CONFLICTS_WITH",
            confidence=0.8,
            ly_do="y",
        )

    monkeypatch.setattr(
        "scripts.extract_relations.classify_candidate", MagicMock(side_effect=fake_classify)
    )

    run_extract_relations(data_dir, client=mock_client)

    called_types = {c.args[1] for c in mock_upsert_relations.call_args_list}
    assert called_types == {"AMENDS", "CONFLICTS_WITH"}
    assert mock_upsert_relations.call_count == 2


def test_batching_splits_rows_across_multiple_upsert_calls(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    for i in range(1, 6):
        _write_article_chunk_file(
            data_dir,
            f"01_2020_tt-btp_{i}.md",
            i,
            f"Dieu {i}",
            f"Điều {i} Luật Doanh nghiệp 2020 được sửa đổi, bổ sung như sau.",
        )

    mock_client = _make_mock_client()
    mock_upsert_relations = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_relations.upsert_relations", mock_upsert_relations
    )
    monkeypatch.setattr(
        "scripts.extract_relations.classify_candidate",
        MagicMock(
            side_effect=lambda source_article_id, candidate: ExtractedRelation(
                target_article_id=candidate.target_article_id,
                relationship_type="AMENDS",
                confidence=0.9,
                ly_do="x",
            )
        ),
    )

    run_extract_relations(data_dir, client=mock_client, batch_size=2)

    # 5 quan he xac nhan, batch_size=2 -> 3 loi goi (2+2+1).
    assert mock_upsert_relations.call_count == 3
    batch_sizes = sorted(len(c.args[2]) for c in mock_upsert_relations.call_args_list)
    assert batch_sizes == [1, 2, 2]


def test_owns_and_closes_client_when_not_injected(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Khong co gi.")

    mock_client = _make_mock_client()
    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr("scripts.extract_relations.Neo4jClient", mock_client_cls)

    run_extract_relations(data_dir)

    mock_client_cls.assert_called_once_with()
    mock_client.close.assert_called_once()


def test_does_not_close_injected_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Khong co gi.")

    mock_client = _make_mock_client()
    run_extract_relations(data_dir, client=mock_client)

    mock_client.close.assert_not_called()
