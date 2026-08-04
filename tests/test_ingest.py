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
    ArticleIdCollisionError,
    _all_articles,
    _detect_and_dedupe_collisions,
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


# === run_ingest: pre-flight article_id collision detection (T009e, =======
# research.md ADR-003) ======================================================
#
# Corpus that chua ban ghi trung lap: cung mot van ban xuat hien duoi 2
# cach viet filename khac nhau chi lech dau tieng Viet (vd "bgddt" vs
# "bgdđt") - slugify_doc_name() gop 2 doc_prefix nay ve CUNG mot doc_id, nen
# 2 file khac nhau tinh ra CUNG article_id. "03_2021_tt-bgddt_1.md" (khong
# dau "đ") sap xep TRUOC "03_2021_tt-bgdđt_1.md" (co dau "đ") theo thu tu
# sort cua discover_documents (code point 'd' < 'đ').


def test_run_ingest_identical_duplicate_article_id_dedupes_to_one_upsert(tmp_path):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgdđt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
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

    expected_doc_id = slugify_doc_name("03_2021_tt-bgddt")

    # Chi file DAU TIEN (theo thu tu sort) duoc thuc su upsert - file trung
    # noi dung bi bo qua hoan toan, khong bao gio dat toi Neo4j.
    doc_ids_seen = _doc_id_kwargs_seen(mock_client)
    assert doc_ids_seen == [expected_doc_id]

    articles_seen = _article_kwargs_seen(mock_client)
    assert articles_seen == [
        {"article_id": f"{expected_doc_id}_dieu-1", "so_dieu": 1}
    ]


def test_detect_and_dedupe_collisions_keeps_first_file_in_sort_order(tmp_path):
    """Bo sung coverage sau review finding (task-2g): test dedup phia tren
    (`test_run_ingest_identical_duplicate_article_id_dedupes_to_one_upsert`)
    chi chung minh "dung 1 upsert xay ra" - vi 2 file trung NOI DUNG hoan
    toan (bat buoc de dedup kich hoat), khong co cach nao phan biet file NAO
    trong 2 file duoc giu qua noi dung article. Test nay goi thang
    `_detect_and_dedupe_collisions` va kiem tra GIA TRI TRA VE (danh sach
    file da dedup) de xac nhan chinh xac file DAU TIEN theo thu tu sort
    (`discover_documents`, code point 'd' < 'đ') duoc giu lai - neu logic
    dedup vo tinh doi sang set()/dict khong dam bao thu tu thay vi dua vao
    danh sach `files` da sort, test nay se FAIL (co the giu nham file "co
    dau" thay vi "khong dau")."""
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgdđt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )

    files = discover_documents(data_dir)
    # Xac nhan gia dinh thu tu sort ma test nay dua vao (khong dau "đ" xep
    # TRUOC co dau "đ") - day chinh la file du kien duoc GIU LAI sau dedup.
    assert [f.name for f in files] == [
        "03_2021_tt-bgddt_1.md",
        "03_2021_tt-bgdđt_1.md",
    ]

    deduped = _detect_and_dedupe_collisions(files)

    assert [f.name for f in deduped] == ["03_2021_tt-bgddt_1.md"]


def test_run_ingest_conflicting_duplicate_article_id_raises_before_any_neo4j_call(
    tmp_path,
):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddt_1.md", 1, "Pham vi", "Noi dung phien ban A."
    )
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgdđt_1.md", 1, "Pham vi", "Noi dung phien ban B - KHAC."
    )

    state_store = IngestCheckpointStore(tmp_path / "state" / "ingest_checkpoint.json")
    mock_client = MagicMock()
    mock_client.run.return_value = []

    with pytest.raises(ArticleIdCollisionError):
        run_ingest(
            data_dir,
            batch_size=2,
            client=mock_client,
            state_store=state_store,
        )

    # Pre-flight thuc su - khong file nao trong corpus (kho khong chi 2 file
    # xung dot) duoc dua toi Neo4j truoc khi raise.
    assert mock_client.run.call_count == 0


def test_run_ingest_collision_error_message_names_article_id_and_both_files(tmp_path):
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddt_1.md", 1, "Pham vi", "Noi dung phien ban A."
    )
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgdđt_1.md", 1, "Pham vi", "Noi dung phien ban B - KHAC."
    )

    state_store = IngestCheckpointStore(tmp_path / "state" / "ingest_checkpoint.json")
    mock_client = MagicMock()
    mock_client.run.return_value = []

    expected_doc_id = slugify_doc_name("03_2021_tt-bgddt")
    expected_article_id = f"{expected_doc_id}_dieu-1"

    with pytest.raises(ArticleIdCollisionError) as exc_info:
        run_ingest(
            data_dir,
            batch_size=2,
            client=mock_client,
            state_store=state_store,
        )

    message = str(exc_info.value)
    assert expected_article_id in message
    assert "03_2021_tt-bgddt_1.md" in message
    assert "03_2021_tt-bgdđt_1.md" in message


def test_run_ingest_no_collisions_behaves_identically_to_before(tmp_path):
    # Corpus binh thuong (khong co file nao trung article_id) - pre-flight
    # scan khong duoc lam thay doi hanh vi quan sat duoc gi ca (Dieu 1 - chi
    # them, khong can thiep vao duong di binh thuong).
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "Noi dung A.")
    _write_article_chunk_file(data_dir, "02_2020_nd-cp_1.md", 1, "B", "Noi dung B.")

    state_store = IngestCheckpointStore(tmp_path / "state" / "ingest_checkpoint.json")
    mock_client = MagicMock()
    mock_client.run.return_value = []

    run_ingest(
        data_dir,
        batch_size=2,
        client=mock_client,
        state_store=state_store,
    )

    doc_ids_seen = _doc_id_kwargs_seen(mock_client)
    assert doc_ids_seen == [
        slugify_doc_name("01_2020_tt-btp"),
        slugify_doc_name("02_2020_nd-cp"),
    ]
    assert len(_article_kwargs_seen(mock_client)) == 2


def test_run_ingest_three_way_collision_two_identical_one_different_raises(tmp_path):
    # Nhom 3 file cung article_id: 2 giong het nhau + 1 khac - BAT KY sai
    # khac nao trong nhom cung du kich hoat raise (khong "majority wins").
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgdđt_1.md", 1, "Pham vi", "Noi dung giong het nhau."
    )
    # Bien the thu 3: dau caron tren "t" (NFD-decompose -> "t" + combining
    # mark, cung bi slugify_doc_name strip het) - mot ky tu Unicode KHAC
    # han (khong phai chi doi hoa/thuong ASCII) de tranh dung ten file tren
    # he thong file khong phan biet hoa/thuong (Windows/NTFS).
    _write_article_chunk_file(
        data_dir, "03_2021_tt-bgddť_1.md", 1, "Pham vi", "Noi dung KHAC han."
    )

    state_store = IngestCheckpointStore(tmp_path / "state" / "ingest_checkpoint.json")
    mock_client = MagicMock()
    mock_client.run.return_value = []

    with pytest.raises(ArticleIdCollisionError):
        run_ingest(
            data_dir,
            batch_size=3,
            client=mock_client,
            state_store=state_store,
        )

    assert mock_client.run.call_count == 0
