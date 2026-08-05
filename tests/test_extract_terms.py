"""Tests cho scripts/extract_terms.py (T012 hoan thien - orchestration).

Cung quy uoc "honest mocking" voi tests/test_backfill_embeddings.py: mock
Neo4jClient, dung file that trong tmp_path cho discover/parse (tai dung
app.ingest's helper qua run_extract_terms that, khong mock rieng
term_extractor/upsert - kiem tra CA pipeline noi voi nhau dung).

Trong tam theo TIEN_DO.md DOT 6:
  1. Mot Article dinh nghia thuat ngu -> upsert_definitions duoc goi voi
     dung row.
  2. Mot Article KHAC dung lai thuat ngu do (van ban B dung thuat ngu dinh
     nghia o van ban A, bat ke thu tu file) -> upsert_term_usages duoc goi
     dung sau khi TOAN BO dinh nghia da duoc thu thap (2-pass).
  3. Article TU dinh nghia mot thuat ngu KHONG duoc tinh la "dung lai" no
     (khong ghi ca DEFINES lan USES_TERM cho cung cap article-term).
  4. Khong co dinh nghia/su dung nao -> khong goi Neo4j.
  5. Batching: nhieu row hon batch_size -> nhieu loi goi upsert_* (chia
     batch), khong phai 1 loi goi khong gioi han.
  6. Client injection: giong pattern run_backfill (so huu vs injected).
"""
from pathlib import Path
from unittest.mock import MagicMock, call

from app.extraction.slugify import slugify_doc_name
from scripts.extract_terms import run_extract_terms


def _write_article_chunk_file(
    data_dir: Path, filename: str, so_dieu: int, title: str, body: str
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    content = f"# Điều {so_dieu}. {title}\n\n{body}\n"
    (data_dir / filename).write_text(content, encoding="utf-8")


def _make_mock_client() -> MagicMock:
    return MagicMock()


def test_article_with_quoted_definition_triggers_upsert_definitions(
    tmp_path, monkeypatch
):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir,
        "01_2020_tt-btp_1.md",
        1,
        "Giải thích từ ngữ",
        '“Ngày” được hiểu là ngày dương lịch.',
    )

    mock_client = _make_mock_client()
    mock_upsert_defs = MagicMock()
    mock_upsert_usages = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_definitions", mock_upsert_defs
    )
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_term_usages", mock_upsert_usages
    )

    run_extract_terms(data_dir, client=mock_client)

    doc_id = slugify_doc_name("01_2020_tt-btp")
    mock_upsert_defs.assert_called_once()
    _, rows = mock_upsert_defs.call_args[0]
    assert rows == [
        {
            "article_id": f"{doc_id}_dieu-1",
            "term_id": "ngay",
            "ten_thuat_ngu": "Ngày",
            "dinh_nghia": "ngày dương lịch",
        }
    ]
    # Khong co Article nao khac dung lai thuat ngu nay - USES_TERM khong
    # duoc goi voi row nao.
    mock_upsert_usages.assert_not_called()


def test_article_b_using_term_defined_in_article_a_triggers_uses_term(
    tmp_path, monkeypatch
):
    """2-pass: Dieu 2 dung lai "Ngay" duoc dinh nghia o Dieu 1 - phai
    duoc phat hien DU thu tu duyet file la 1 truoc 2 (van hoat dung ngay
    ca khi nguoc lai, vi TOAN BO dinh nghia duoc thu thap TRUOC khi tinh
    USES_TERM cho bat ky Article nao)."""
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_1.md", 1, "A", '“Ngày” được hiểu là ngày dương lịch.'
    )
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_2.md", 2, "B", "Thời hạn tính theo Ngày làm việc."
    )

    mock_client = _make_mock_client()
    mock_upsert_usages = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_term_usages", mock_upsert_usages
    )

    run_extract_terms(data_dir, client=mock_client)

    doc_id = slugify_doc_name("01_2020_tt-btp")
    mock_upsert_usages.assert_called_once()
    _, rows = mock_upsert_usages.call_args[0]
    assert rows == [{"article_id": f"{doc_id}_dieu-2", "term_id": "ngay"}]


def test_article_defining_term_is_not_also_marked_as_using_it(tmp_path, monkeypatch):
    """Dieu 1 TU dinh nghia "Ngay" - khong duoc coi la "dung lai" chinh
    thuat ngu no vua dinh nghia (khong ghi ca DEFINES lan USES_TERM cho
    cung cap article-term)."""
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir,
        "01_2020_tt-btp_1.md",
        1,
        "A",
        '“Ngày” được hiểu là ngày dương lịch, và văn bản luôn nhắc lại Ngày trong các điều khoản.',
    )

    mock_client = _make_mock_client()
    mock_upsert_usages = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_term_usages", mock_upsert_usages
    )

    run_extract_terms(data_dir, client=mock_client)

    mock_upsert_usages.assert_not_called()


def test_no_definitions_or_usages_calls_neither_upsert_function(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_1.md", 1, "A", "Không có định nghĩa nào ở đây."
    )

    mock_client = _make_mock_client()
    mock_upsert_defs = MagicMock()
    mock_upsert_usages = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_definitions", mock_upsert_defs
    )
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_term_usages", mock_upsert_usages
    )

    run_extract_terms(data_dir, client=mock_client)

    mock_upsert_defs.assert_not_called()
    mock_upsert_usages.assert_not_called()


def test_batching_splits_rows_across_multiple_upsert_calls(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    for i in range(1, 6):
        _write_article_chunk_file(
            data_dir,
            f"01_2020_tt-btp_{i}.md",
            i,
            f"Dieu {i}",
            f'"Thuật ngữ {i}" được hiểu là định nghĩa số {i}.',
        )

    mock_client = _make_mock_client()
    mock_upsert_defs = MagicMock()
    monkeypatch.setattr(
        "scripts.extract_terms.upsert_definitions", mock_upsert_defs
    )

    run_extract_terms(data_dir, client=mock_client, batch_size=2)

    # 5 dinh nghia, batch_size=2 -> 3 loi goi (2+2+1).
    assert mock_upsert_defs.call_count == 3
    batch_sizes = sorted(len(c.args[1]) for c in mock_upsert_defs.call_args_list)
    assert batch_sizes == [1, 2, 2]


def test_owns_and_closes_client_when_not_injected(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Khong co gi.")

    mock_client = _make_mock_client()
    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr("scripts.extract_terms.Neo4jClient", mock_client_cls)

    run_extract_terms(data_dir)

    mock_client_cls.assert_called_once_with()
    mock_client.close.assert_called_once()


def test_does_not_close_injected_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Khong co gi.")

    mock_client = _make_mock_client()
    run_extract_terms(data_dir, client=mock_client)

    mock_client.close.assert_not_called()
