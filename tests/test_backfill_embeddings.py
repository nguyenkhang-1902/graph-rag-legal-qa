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
from scripts.backfill_embeddings import (
    _batch_cap_for_length,
    _group_into_length_aware_batches,
    run_backfill,
)


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


def test_pending_articles_are_batched_sorted_by_text_length(tmp_path, monkeypatch):
    """Chan doan that (2026-08-04): corpus that co do dai Dieu lech rat manh
    (trung vi 298 token nhung co Dieu toi 4737 token). Neu KHONG sap xep,
    mot Dieu dai vo tinh loi vao batch se buoc CA batch pad theo do dai do
    (batch=64 tren mau that CHAM HON 7.7 lan/item so voi batch=32 - xem
    TIEN_DO.md). Sap xep `pending` theo do dai text TRUOC khi chia batch -
    nhom cac Dieu dai tuong duong vao cung batch - la fix truc tiep cho gap
    nay. Test nay dung 4 file do dai CACH BIET RO RANG (ngan/ngan/dai/dai)
    de xac nhan batch KHONG con theo thu tu discover (bang chu cai) nua ma
    theo do dai."""
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "x" * 10)
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_2.md", 2, "B", "y" * 5000)
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_3.md", 3, "C", "z" * 20)
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_4.md", 4, "D", "w" * 6000)

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=2, client=mock_client)

    doc_id = slugify_doc_name("01_2020_tt-btp")
    assert mock_upsert.call_count == 2
    batch_id_sets = [set(c.kwargs["ids"]) for c in mock_upsert.call_args_list]
    # 2 Dieu ngan nhat (1, 3) phai o CUNG mot batch, 2 Dieu dai nhat (2, 4)
    # o batch con lai - KHONG phai theo thu tu file (1,2 / 3,4).
    assert {f"{doc_id}_dieu-1", f"{doc_id}_dieu-3"} in batch_id_sets
    assert {f"{doc_id}_dieu-2", f"{doc_id}_dieu-4"} in batch_id_sets


def test_batch_cap_for_length_uses_smaller_cap_for_longer_tiers():
    """Nguong 2751/7640 ky tu lay tu quet THAT toan bo 61,069 file trong
    data/raw (2026-08-04, p90/p99 - xem TIEN_DO.md). Van ban cang dai,
    batch-size cang phai nho de tranh OOM tren GPU 6GB (da xac nhan that:
    batch=128 voi van ban ~4737 token da OOM)."""
    # Tang ngan (<=2751 ky tu, p90): dung nguyen max_batch_size.
    assert _batch_cap_for_length(2751, max_batch_size=32) == 32
    # Tang trung (2751 < do dai <=7640, p90-p99): cap ve 8 (< 32 yeu cau).
    assert _batch_cap_for_length(2752, max_batch_size=32) == 8
    assert _batch_cap_for_length(7640, max_batch_size=32) == 8
    # Tang dai (>7640 ky tu, p99+, se cham max_seq_length khi encode): cap
    # ve 1 - xu ly tung file rieng, khong ghep batch (chua co du lieu that
    # de kiem chung an toan o muc lon hon).
    assert _batch_cap_for_length(7641, max_batch_size=32) == 1
    # max_batch_size nho hon cap tang - khong duoc VUOT max_batch_size du
    # tang nao (vd --batch-size 4 tay - khong the "tang" batch-size len 8).
    assert _batch_cap_for_length(100, max_batch_size=4) == 4
    assert _batch_cap_for_length(3000, max_batch_size=4) == 4


def test_group_into_length_aware_batches_splits_outlier_into_own_small_batch():
    """9 item NGAN (~100 ky tu, tang 1) + 1 item DAI (~8000 ky tu, tang 3) -
    da sap xep tang dan. max_batch_size=32 (nhu config.EMBED_BATCH_SIZE):
    9 item ngan phai gom CHUNG 1 batch (tang 1 cho phep toi 32), item dai
    phai o RIENG 1 batch (tang 3 cap = 1) - khong duoc ghep chung."""
    pending = [(f"id{i}", "x" * 100, {}) for i in range(9)]
    pending.append(("id_dai", "y" * 8000, {}))

    batches = _group_into_length_aware_batches(pending, max_batch_size=32)

    assert len(batches) == 2
    short_batch, long_batch = batches
    assert len(short_batch) == 9
    assert len(long_batch) == 1
    assert long_batch[0][0] == "id_dai"


def test_group_into_length_aware_batches_respects_max_batch_size_within_tier():
    """5 item NGAN (tang 1, cho phep toi da) nhung max_batch_size=2 - phai
    chia thanh nhieu batch <=2 item, khong gom het vao 1 batch dù cung
    tang."""
    pending = [(f"id{i}", "x" * 10, {}) for i in range(5)]

    batches = _group_into_length_aware_batches(pending, max_batch_size=2)

    assert [len(b) for b in batches] == [2, 2, 1]


def test_run_backfill_isolates_extremely_long_article_into_its_own_batch(
    tmp_path, monkeypatch
):
    """Kiem chung end-to-end qua run_backfill that (khong chi ham thuan
    tuy): 1 file cuc dai (>7640 ky tu, tang 3) DU batch_size mac dinh 10
    van khong duoc gop chung voi cac file ngan khac - phai la 1 loi goi
    upsert_embeddings RIENG chi co 1 item."""
    data_dir = tmp_path / "corpus"
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_1.md", 1, "A", "x" * 10)
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_2.md", 2, "B", "y" * 10)
    _write_article_chunk_file(data_dir, "01_2020_tt-btp_3.md", 3, "C", "z" * 8000)

    mock_client = _make_mock_client(already_embedded_article_ids=set())

    mock_upsert = MagicMock()
    monkeypatch.setattr(
        "scripts.backfill_embeddings.embedder.upsert_embeddings", mock_upsert
    )

    run_backfill(data_dir, batch_size=10, client=mock_client)

    doc_id = slugify_doc_name("01_2020_tt-btp")
    assert mock_upsert.call_count == 2
    call_id_sets = [set(c.kwargs["ids"]) for c in mock_upsert.call_args_list]
    assert {f"{doc_id}_dieu-1", f"{doc_id}_dieu-2"} in call_id_sets
    assert {f"{doc_id}_dieu-3"} in call_id_sets


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
