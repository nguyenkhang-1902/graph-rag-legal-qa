"""Tests cho cac helper thuan (khong dung Neo4j) trong app/ingest.py (T009d):
`discover_documents`, `make_batches`, `_all_articles`,
`parse_filename_doc_prefix_and_so_dieu` (task-2f). Vong lap tich hop day du
(`run_ingest` + resume) duoc test rieng o
tests/ingest_checkpoint/test_resume_after_crash.py; test task-2f duoi day
("hai file cung doc_prefix -> cung doc_id trong Neo4j") cung dung
`run_ingest` (mock Neo4jClient, "honest mocking" nhu cac test do) vi day la
hanh vi tich hop giua `app/ingest.py` va `upsert.py` (MERGE), khong the
kiem tra chi tu ham thuan.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.extraction.slugify import slugify_doc_name
from app.extraction.structure_parser import Article, Chapter, ParsedDocument
from app.ingest import (
    _all_articles,
    discover_documents,
    make_batches,
    parse_filename_doc_prefix_and_so_dieu,
    run_ingest,
)
from app.ingest_checkpoint.state_store import IngestCheckpointStore


def _touch(dir_path: Path, name: str) -> None:
    (dir_path / name).write_text("x", encoding="utf-8")


def test_discover_documents_sorted_by_filename(tmp_path):
    for name in ["b.md", "a.md", "c.md"]:
        _touch(tmp_path, name)

    files = discover_documents(tmp_path)

    assert [f.name for f in files] == ["a.md", "b.md", "c.md"]


def test_discover_documents_excludes_readme(tmp_path):
    for name in ["doc1.md", "README.md", "doc2.md"]:
        _touch(tmp_path, name)

    files = discover_documents(tmp_path)

    assert [f.name for f in files] == ["doc1.md", "doc2.md"]


def test_discover_documents_ignores_non_md_files(tmp_path):
    _touch(tmp_path, "doc1.md")
    _touch(tmp_path, "notes.txt")

    files = discover_documents(tmp_path)

    assert [f.name for f in files] == ["doc1.md"]


def test_discover_documents_applies_limit_after_sorting(tmp_path):
    for name in ["c.md", "a.md", "b.md"]:
        _touch(tmp_path, name)

    files = discover_documents(tmp_path, limit=2)

    assert [f.name for f in files] == ["a.md", "b.md"]


def test_discover_documents_limit_none_means_all(tmp_path):
    for name in ["a.md", "b.md"]:
        _touch(tmp_path, name)

    files = discover_documents(tmp_path, limit=None)

    assert len(files) == 2


def test_make_batches_splits_into_fixed_size_chunks():
    files = [Path(f"{i}.md") for i in range(7)]

    batches = make_batches(files, batch_size=3)

    assert len(batches) == 3
    assert [len(b) for b in batches] == [3, 3, 1]
    assert batches[0] == files[0:3]
    assert batches[1] == files[3:6]
    assert batches[2] == files[6:7]


def test_make_batches_empty_file_list():
    assert make_batches([], batch_size=5) == []


def test_all_articles_includes_top_level_and_chapter_articles():
    top_level = Article(
        article_id="doc_dieu-1", so_dieu=1, noi_dung_preview="", full_text="", clauses=[]
    )
    in_chapter = Article(
        article_id="doc_dieu-2", so_dieu=2, noi_dung_preview="", full_text="", clauses=[]
    )
    chapter = Chapter(chapter_id="doc_chuong-1", so_chuong=1, tieu_de="", articles=[in_chapter])
    parsed = ParsedDocument(
        doc_id="doc", title="Doc", chapters=[chapter], articles=[top_level]
    )

    articles = _all_articles(parsed)

    assert articles == [top_level, in_chapter]


# === parse_filename_doc_prefix_and_so_dieu (task-2f) =======================
#
# Corpus that: "{doc_prefix}_{so_dieu}.md", vd "01_2020_tt-btp_7.md" - doc
# prefix chinh no cung chua dau "_" nen phai tach dung cum "_<so>" CUOI
# CUNG cua ten file, va phai xu ly dung dau tieng Viet trong doc_prefix
# (Dieu 11 constitution).


def test_parse_filename_doc_prefix_and_so_dieu_basic():
    doc_prefix, so_dieu = parse_filename_doc_prefix_and_so_dieu(
        Path("01_2020_tt-btp_7.md")
    )

    assert doc_prefix == "01_2020_tt-btp"
    assert so_dieu == 7


def test_parse_filename_doc_prefix_and_so_dieu_handles_diacritics_in_prefix():
    # doc_prefix chua dau tieng Viet (script fetch chi strip ky tu khong
    # phai chu/so, khong strip dau - xem brief).
    doc_prefix, so_dieu = parse_filename_doc_prefix_and_so_dieu(
        Path("01_2019_nđ-cp_8.md")
    )

    assert doc_prefix == "01_2019_nđ-cp"
    assert so_dieu == 8


def test_parse_filename_doc_prefix_and_so_dieu_multiple_underscores_in_prefix():
    doc_prefix, so_dieu = parse_filename_doc_prefix_and_so_dieu(
        Path("02_2021_tt-bgdđt_5.md")
    )

    assert doc_prefix == "02_2021_tt-bgdđt"
    assert so_dieu == 5


def test_parse_filename_doc_prefix_and_so_dieu_raises_on_no_trailing_number():
    with pytest.raises(ValueError, match="khong_hop_le"):
        parse_filename_doc_prefix_and_so_dieu(Path("khong_hop_le.md"))


def test_parse_filename_doc_prefix_and_so_dieu_raises_mentions_the_file():
    bad_path = Path("some_dir") / "malformed-filename.md"

    with pytest.raises(ValueError) as exc_info:
        parse_filename_doc_prefix_and_so_dieu(bad_path)

    assert "malformed-filename.md" in str(exc_info.value)


# === run_ingest: hai file cung doc_prefix -> gop ve CUNG mot doc_id ========
# (task-2f) ==================================================================


def _write_article_chunk_file(
    data_dir: Path, filename: str, so_dieu: int, title: str, body: str
) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    content = f"# Điều {so_dieu}. {title}\n\n{body}\n"
    (data_dir / filename).write_text(content, encoding="utf-8")


def _doc_id_kwargs_seen(mock_client: MagicMock) -> list[str]:
    return [
        call.kwargs["doc_id"]
        for call in mock_client.run.call_args_list
        if "doc_id" in call.kwargs and "title" in call.kwargs
    ]


def _article_kwargs_seen(mock_client: MagicMock) -> list[dict]:
    return [
        {"article_id": call.kwargs["article_id"], "so_dieu": call.kwargs["so_dieu"]}
        for call in mock_client.run.call_args_list
        if "article_id" in call.kwargs
    ]


def test_run_ingest_two_files_same_doc_prefix_merge_into_same_doc_id(tmp_path):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_1.md", 1, "Phạm vi điều chỉnh", "Nội dung điều một."
    )
    _write_article_chunk_file(
        data_dir, "01_2020_tt-btp_2.md", 2, "Đối tượng áp dụng", "Nội dung điều hai."
    )

    state_store = IngestCheckpointStore(tmp_path / "state" / "ingest_checkpoint.json")
    mock_client = MagicMock()
    mock_client.run.return_value = []

    run_ingest(
        data_dir,
        batch_size=2,
        client=mock_client,
        state_store=state_store,
    )

    expected_doc_id = slugify_doc_name("01_2020_tt-btp")

    doc_ids_seen = _doc_id_kwargs_seen(mock_client)
    assert len(doc_ids_seen) == 2  # ca hai file deu goi upsert_document
    assert doc_ids_seen == [expected_doc_id, expected_doc_id]

    articles_seen = _article_kwargs_seen(mock_client)
    assert len(articles_seen) == 2
    so_dieu_seen = {a["so_dieu"] for a in articles_seen}
    assert so_dieu_seen == {1, 2}
    for a in articles_seen:
        assert a["article_id"] == f"{expected_doc_id}_dieu-{a['so_dieu']}"
