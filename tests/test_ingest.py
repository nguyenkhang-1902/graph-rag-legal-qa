"""Tests cho cac helper thuan (khong dung Neo4j) trong app/ingest.py (T009d):
`discover_documents`, `make_batches`, `_all_articles`. Vong lap tich hop
day du (`run_ingest` + resume) duoc test rieng o
tests/ingest_checkpoint/test_resume_after_crash.py.
"""
from pathlib import Path

from app.extraction.structure_parser import Article, Chapter, ParsedDocument
from app.ingest import _all_articles, discover_documents, make_batches


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
