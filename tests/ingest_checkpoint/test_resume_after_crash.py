"""Test tich hop T009c: chung minh co che savepoint/resume (state_store.py
T009b + app/ingest.py T009d) hoat dong dung khi ket hop voi nhau.

Khong the `kill -9` that trong pytest - mo phong crash bang cach INJECT mot
fault vao mock Neo4jClient.run(): raise exception khi thay tham so `doc_id`
khop voi mot van ban CU THE (van ban thu hai cua batch index 2, tuc la mot
batch SAU batch dau tien, dung theo yeu cau brief - "not the first batch",
de chung minh cac batch DA hoan tat truoc do khong bi lam lai).

Fixture corpus theo dung hinh dang that (task-2f-brief.md - moi file la
DUY NHAT mot Dieu, ten file "{doc_prefix}_{so_dieu}.md"): moi file o day
la mot van ban RIENG (doc_prefix rieng, doc00..doc07) chi co 1 Dieu, de giu
nguyen kich ban goc "8 van ban rieng biet trai qua 3 batch". Match fault
qua `doc_id` (KHONG con dung `title` - `parse_article_chunk()` luon de
`title` rong, khac voi `parse_document()` cu ma test nay ban dau dung -
xem task-2f-brief.md) vi `doc_id` la thu duy nhat phan biet moi van ban va
CHI query MERGE Document moi truyen ca `doc_id` LAN `title` cung luc (xem
upsert.py._DOCUMENT_QUERY) - dung dieu kien do de chac chan chi khop dung
Document-upsert query, khong nham voi query khac.

Khong dung Neo4j that (cung quy uoc "honest mocking" nhu test_upsert.py):
mock o muc Neo4jClient (client.run) - upsert.py/ingest.py chi goi qua
interface nay.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.extraction.slugify import slugify_doc_name
from app.ingest import BatchSizeMismatchError, run_ingest
from app.ingest_checkpoint.state_store import IngestCheckpointStore

_NUM_FILES = 8
_BATCH_SIZE = 3  # -> 3 batch: [0,1,2]=idx0, [3,4,5]=idx1, [6,7]=idx2


def _doc_prefixes() -> list[str]:
    return [f"doc{i:02d}" for i in range(_NUM_FILES)]


def _doc_ids() -> list[str]:
    return [slugify_doc_name(prefix) for prefix in _doc_prefixes()]


def _filenames() -> list[str]:
    # "{doc_prefix}_{so_dieu}.md" - moi van ban chi co 1 Dieu (so_dieu=1).
    return [f"{prefix}_1.md" for prefix in _doc_prefixes()]


def _write_corpus(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for i, filename in enumerate(_filenames()):
        content = f"# Điều 1. Quy định số {i}\n\nNội dung điều một của văn bản số {i}.\n"
        (data_dir / filename).write_text(content, encoding="utf-8")


def _make_faulty_client(fault_doc_id: str) -> tuple[MagicMock, dict]:
    """Mock Neo4jClient voi client.run() raise khi kwargs['doc_id'] ==
    fault_doc_id VA loi goi do dung la Document-upsert query (nhan dien qua
    su co mat dong thoi cua `title` trong cung loi goi - xem
    upsert.py._DOCUMENT_QUERY) - VA CHI KHI fault dang "active" (toggle qua
    dict tra ve, de test tat fault o lan chay thu hai ma khong can tao lai
    mock/mat lich su side_effect)."""
    state = {"fault_active": True}

    def run_side_effect(query, **kwargs):
        if (
            state["fault_active"]
            and kwargs.get("doc_id") == fault_doc_id
            and "title" in kwargs
        ):
            raise RuntimeError(f"simulated crash on document {fault_doc_id!r}")
        return []

    mock_client = MagicMock()
    mock_client.run.side_effect = run_side_effect
    return mock_client, state


def _doc_ids_seen_in_calls(mock_client: MagicMock) -> set[str]:
    return {
        call.kwargs["doc_id"]
        for call in mock_client.run.call_args_list
        if "doc_id" in call.kwargs and "title" in call.kwargs
    }


def test_resume_after_crash_skips_completed_batches(tmp_path):
    data_dir = tmp_path / "corpus"
    _write_corpus(data_dir)

    doc_ids = _doc_ids()
    # batch index 2 = files[6:8] -> 2nd document of batch 2 = files[7].
    fault_doc_id = doc_ids[7]

    state_file = tmp_path / "state" / "ingest_checkpoint.json"
    state_store = IngestCheckpointStore(state_file)

    mock_client, fault_state = _make_faulty_client(fault_doc_id)

    # --- Run 1: crash partway through batch index 2 ------------------------
    with pytest.raises(RuntimeError, match="simulated crash"):
        run_ingest(
            data_dir,
            batch_size=_BATCH_SIZE,
            client=mock_client,
            state_store=state_store,
        )

    # Batches 0 and 1 fully completed and marked done; batch 2 interrupted.
    assert state_store.get_last_completed_batch() == 1

    # Sanity: batch 0/1 documents (doc_ids[0:6]) were in fact processed
    # before the crash, and batch 2's first document (doc_ids[6]) was
    # processed successfully before the crash hit on doc_ids[7] (2nd doc of
    # batch 2). The call for doc_ids[7] itself IS recorded by the mock even
    # though it raised (Mock records call args before invoking
    # side_effect), so it isn't asserted absent here.
    seen_run1 = _doc_ids_seen_in_calls(mock_client)
    for doc_id in doc_ids[0:6]:
        assert doc_id in seen_run1
    assert doc_ids[6] in seen_run1

    # --- Remove the fault, reset call history, run again --------------------
    fault_state["fault_active"] = False
    mock_client.reset_mock()  # clears call history, keeps side_effect

    run_ingest(
        data_dir,
        batch_size=_BATCH_SIZE,
        client=mock_client,
        state_store=state_store,
    )

    # (a) Resume starts at batch 2, NOT 0/1: none of batch 0/1's documents
    # were reprocessed in this second run.
    seen_run2 = _doc_ids_seen_in_calls(mock_client)
    for doc_id in doc_ids[0:6]:
        assert doc_id not in seen_run2
    # Batch 2's documents (doc_ids[6], doc_ids[7]) WERE processed this run.
    assert doc_ids[6] in seen_run2
    assert doc_ids[7] in seen_run2

    # (b) run completed successfully (no exception raised above is already
    # proof), (c) checkpoint now reflects the final batch index (0-based,
    # 3 batches total -> final index 2).
    assert state_store.get_last_completed_batch() == 2


def test_fault_actually_raises_on_the_targeted_document_call():
    # Focused unit check on the fault-injection helper itself, independent
    # of run_ingest - guards against the injection silently matching the
    # wrong call (e.g. a Clause/Article query that also happens to carry a
    # `doc_id`-shaped kwarg by coincidence) and the integration test above
    # passing for the wrong reason.
    mock_client, _ = _make_faulty_client("doc07")

    with pytest.raises(RuntimeError, match="simulated crash"):
        mock_client.run("MERGE (d:Document ...)", doc_id="doc07", title="")

    # A different doc_id does not trigger the fault.
    result = mock_client.run("MERGE (d:Document ...)", doc_id="doc06", title="")
    assert result == []

    # A call carrying `doc_id` but WITHOUT `title` (e.g. Article-under-
    # document query, which uses `parent_id` not `doc_id`... this checks
    # the "title must also be present" guard directly) does not trigger the
    # fault even if doc_id happens to match.
    result = mock_client.run("MATCH (parent:Document ...)", doc_id="doc07")
    assert result == []


# --- Review finding: resuming with a DIFFERENT batch_size than the one --
# --- that produced the checkpoint must be detected and refused, not -----
# --- silently resumed against the wrong file slice. ----------------------


def test_resume_with_different_batch_size_raises_and_refuses(tmp_path):
    data_dir = tmp_path / "corpus"
    _write_corpus(data_dir)

    state_file = tmp_path / "state" / "ingest_checkpoint.json"
    state_store = IngestCheckpointStore(state_file)

    # Run 1: complete successfully with batch_size=3 (no fault) -> leaves a
    # checkpoint recording batch_size=3.
    mock_client_1 = MagicMock()
    mock_client_1.run.return_value = []
    run_ingest(
        data_dir,
        batch_size=_BATCH_SIZE,
        client=mock_client_1,
        state_store=state_store,
    )
    assert state_store.get_last_completed_batch() == 2  # 3 batches, all done

    # Simulate: operator (or a changed INGEST_BATCH_SIZE env var) reruns
    # with a DIFFERENT batch_size against the same checkpoint/state_store.
    # This must be detected and refused - not silently resumed with wrong
    # batch boundaries.
    mock_client_2 = MagicMock()
    mock_client_2.run.return_value = []
    with pytest.raises(BatchSizeMismatchError, match="batch_size"):
        run_ingest(
            data_dir,
            batch_size=_BATCH_SIZE + 1,
            client=mock_client_2,
            state_store=state_store,
        )

    # Nothing from run 2 should have been processed - it must refuse before
    # touching any document.
    assert mock_client_2.run.call_count == 0
    # Checkpoint is unchanged by the refused run.
    assert state_store.get_last_completed_batch() == 2


def test_fresh_start_does_not_require_batch_size_match(tmp_path):
    # No prior checkpoint at all -> nothing to compare batch_size against,
    # so any batch_size is accepted on a fresh start.
    data_dir = tmp_path / "corpus"
    _write_corpus(data_dir)

    state_file = tmp_path / "state" / "ingest_checkpoint.json"
    state_store = IngestCheckpointStore(state_file)

    mock_client = MagicMock()
    mock_client.run.return_value = []

    run_ingest(
        data_dir,
        batch_size=_BATCH_SIZE,
        client=mock_client,
        state_store=state_store,
    )

    assert state_store.get_last_completed_batch() == 2
    assert state_store.get_last_batch_size() == _BATCH_SIZE


def test_resume_with_same_batch_size_still_works(tmp_path):
    # Resuming with the SAME batch_size as the checkpoint must NOT be
    # falsely rejected (no false-positive mismatch).
    data_dir = tmp_path / "corpus"
    _write_corpus(data_dir)

    doc_ids = _doc_ids()
    fault_doc_id = doc_ids[7]

    state_file = tmp_path / "state" / "ingest_checkpoint.json"
    state_store = IngestCheckpointStore(state_file)

    mock_client, fault_state = _make_faulty_client(fault_doc_id)

    with pytest.raises(RuntimeError, match="simulated crash"):
        run_ingest(
            data_dir,
            batch_size=_BATCH_SIZE,
            client=mock_client,
            state_store=state_store,
        )
    assert state_store.get_last_completed_batch() == 1

    fault_state["fault_active"] = False
    mock_client.reset_mock()

    # Same batch_size as before -> must resume normally, not raise
    # BatchSizeMismatchError.
    run_ingest(
        data_dir,
        batch_size=_BATCH_SIZE,
        client=mock_client,
        state_store=state_store,
    )

    assert state_store.get_last_completed_batch() == 2
