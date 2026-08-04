"""Tests cho scripts/backfill_embeddings.py (T009f).

Khong co Neo4j/Chroma/model that trong sandbox test - mock o ranh gioi
(cung quy uoc "honest mocking" nhu tests/test_ingest.py): mock Neo4jClient
(nhu tests/test_ingest.py da lam) VA `app.retrieval.embedder.upsert_embeddings`
(khong tai model that) - dung file that trong `tmp_path` cho phan discover/
parse (tai dung `app.ingest`'s helper, khong duplicate).

Trong tam theo brief:
1. Article DA co chroma_id (tra ve tu truy van Neo4j da mock) bi bo qua -
   khong bao gio dat toi (mocked) embed_texts/upsert_embeddings.
2. Article CHUA co chroma_id duoc embed va Neo4j node duoc cap nhat
   chroma_id == article_id.
3. Batching: nhieu file duoc embed trong MOT loi goi upsert_embeddings/
   batch, khong phai 1 loi goi/file (phan throughput-nhay cam).
"""
from pathlib import Path
from unittest.mock import MagicMock, call

from app.extraction.slugify import slugify_doc_name
from scripts.backfill_embeddings import run_backfill


def _write_article_chunk_file(
    data_dir: Path, filename: str, so_dieu: int, title: str, body: str
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    content = f"# Điều {so_dieu}. {title}\n\n{body}\n"
    (data_dir / filename).write_text(content, encoding="utf-8")


def _make_mock_client(already_embedded_article_ids: set[str] | None = None) -> MagicMock:
    """Mock Neo4jClient - `run()` tra ve ket qua khac nhau tuy cau Cypher:
    cau truy van "chroma_id IS NOT NULL" tra ve tap article_id da co (gia
    lap trang thai Neo4j that), cac cau khac (UNWIND SET chroma_id) tra ve
    [] (khong dung ket qua)."""
    already = already_embedded_article_ids or set()

    def _run(query: str, **params):
        if "chroma_id IS NOT NULL" in query:
            return [{"article_id": aid} for aid in already]
        return []

    mock_client = MagicMock()
    mock_client.run.side_effect = _run
    return mock_client


def test_articles_with_existing_chroma_id_are_skipped(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Noi dung A.")
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_2.md", 2, "B", "Noi dung B.")

    doc_id = slugify_doc_name("01_2020_tt-btp")
    already_embedded = {f"{doc_id}_dieu-1"}  # dieu 1 da co chroma_id
    mock_client = _make_mock_client(already_embedded)

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10, client=mock_client)

    # Chi Dieu 2 (chua co chroma_id) duoc embed.
    assert mock_upsert.call_count == 1
    _, kwargs = mock_upsert.call_args
    assert kwargs["ids"] == [f"{doc_id}_dieu-2"]


def test_articles_without_chroma_id_get_embedded_and_neo4j_updated(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_1.md", 1, "Pham vi", "Noi dung dieu mot."
    )

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10, client=mock_client)

    doc_id = slugify_doc_name("01_2020_tt-btp")
    expected_article_id = f"{doc_id}_dieu-1"

    mock_upsert.assert_called_once()
    _, kwargs = mock_upsert.call_args
    assert kwargs["ids"] == [expected_article_id]
    assert "Noi dung dieu mot." in kwargs["texts"][0]
    assert kwargs["metadatas"] == [{"doc_id": doc_id, "so_dieu": 1}]

    # Neo4j duoc cap nhat chroma_id == article_id qua mot cau UNWIND.
    update_calls = [
        c
        for c in mock_client.run.call_args_list
        if "SET a.chroma_id" in c.args[0]
    ]
    assert len(update_calls) == 1
    assert update_calls[0].kwargs["ids"] == [expected_article_id]


def test_multiple_files_embedded_in_one_batch_call_not_one_per_file(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Noi dung A.")
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_2.md", 2, "B", "Noi dung B.")
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_3.md", 3, "C", "Noi dung C.")

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10, client=mock_client)

    # 3 file, batch_size=10 -> phai gom vao MOT loi goi upsert_embeddings
    # duy nhat (khong phai 3 loi goi rieng le) - day la phan throughput-nhay
    # cam ma brief nhan manh.
    assert mock_upsert.call_count == 1
    _, kwargs = mock_upsert.call_args
    assert len(kwargs["ids"]) == 3


def test_batch_size_splits_into_multiple_upsert_calls(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Noi dung A.")
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_2.md", 2, "B", "Noi dung B.")
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_3.md", 3, "C", "Noi dung C.")

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=2, client=mock_client)

    # 3 file, batch_size=2 -> 2 batch (2 + 1) - dung ranh gioi batch, va
    # khong phai 1 loi goi/file.
    assert mock_upsert.call_count == 2
    batch_sizes = sorted(len(c.kwargs["ids"]) for c in mock_upsert.call_args_list)
    assert batch_sizes == [1, 2]


def test_run_backfill_reuses_dedup_so_duplicate_content_file_not_embedded_twice(
    tmp_path, monkeypatch
):
    # Cung article_id, cung noi dung (an toan tu dong dedup, ADR-003) - chi
    # file dau tien theo thu tu sort duoc dua vao vong lap embed.
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgdđt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10, client=mock_client)

    mock_upsert.assert_called_once()
    _, kwargs = mock_upsert.call_args
    assert len(kwargs["ids"]) == 1


def test_run_backfill_owns_and_closes_client_when_not_injected(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Noi dung A.")

    mock_client = _make_mock_client(already_embedded_article_ids=set())
    mock_client_cls = MagicMock(return_value=mock_client)
    monkeypatch.setattr("scripts.backfill_embeddings.Neo4jClient", mock_client_cls)

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10)

    mock_client_cls.assert_called_once_with()
    mock_client.close.assert_called_once()


def test_run_backfill_does_not_close_injected_client(tmp_path, monkeypatch):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Noi dung A.")

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10, client=mock_client)

    mock_client.close.assert_not_called()
