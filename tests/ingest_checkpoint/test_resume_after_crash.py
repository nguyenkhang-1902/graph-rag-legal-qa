"""Test tich hop T009c: chung minh co che savepoint/resume (state_store.py
T009b + app/ingest.py T009d) hoat dong dung khi ket hop voi nhau.

Khong the `kill -9` that trong pytest - mo phong crash bang cach INJECT mot
fault vao mock Neo4jClient.run(): raise exception khi thay tham so `title`
khop voi mot van ban CU THE (van ban thu hai cua batch index 2, tuc la mot
batch SAU batch dau tien, dung theo yeu cau brief - "not the first batch",
de chung minh cac batch DA hoan tat truoc do khong bi lam lai).

Khong dung Neo4j that (cung quy uoc "honest mocking" nhu test_upsert.py):
mock o muc Neo4jClient (client.run) - upsert.py/ingest.py chi goi qua
interface nay.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.ingest import run_ingest
from app.ingest_checkpoint.state_store import IngestCheckpointStore

_NUM_FILES = 8
_BATCH_SIZE = 3  # -> 3 batch: [0,1,2]=idx0, [3,4,5]=idx1, [6,7]=idx2


def _titles() -> list[str]:
    return [f"Văn Bản Số {i}" for i in range(_NUM_FILES)]


def _filenames() -> list[str]:
    return [f"doc-{i:02d}.md" for i in range(_NUM_FILES)]


def _write_corpus(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename, title in zip(_filenames(), _titles()):
        content = f"# {title}\n\nĐiều 1. Quy định chung\n\nNội dung điều một.\n"
        (data_dir / filename).write_text(content, encoding="utf-8")


def _make_faulty_client(fault_title: str) -> tuple[MagicMock, dict]:
    """Mock Neo4jClient voi client.run() raise khi kwargs['title'] ==
    fault_title (chi Document-upsert query truyen `title` - xem
    upsert.py._DOCUMENT_QUERY) - VA CHI KHI fault dang "active" (toggle qua
    dict tra ve, de test tat fault o lan chay thu hai ma khong can tao lai
    mock/mat lich su side_effect)."""
    state = {"fault_active": True}

    def run_side_effect(query, **kwargs):
        if state["fault_active"] and kwargs.get("title") == fault_title:
            raise RuntimeError(f"simulated crash on document {fault_title!r}")
        return []

    mock_client = MagicMock()
    mock_client.run.side_effect = run_side_effect
    return mock_client, state


def _titles_seen_in_calls(mock_client: MagicMock) -> set[str]:
    return {
        call.kwargs["title"]
        for call in mock_client.run.call_args_list
        if "title" in call.kwargs
    }


def test_resume_after_crash_skips_completed_batches(tmp_path):
    data_dir = tmp_path / "corpus"
    _write_corpus(data_dir)

    titles = _titles()
    filenames = _filenames()
    # batch index 2 = files[6:8] -> 2nd document of batch 2 = files[7].
    fault_title = titles[7]

    state_file = tmp_path / "state" / "ingest_checkpoint.json"
    state_store = IngestCheckpointStore(state_file)

    mock_client, fault_state = _make_faulty_client(fault_title)

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

    # Sanity: batch 0/1 documents (titles[0:6]) were in fact processed
    # before the crash, and batch 2's first document (titles[6]) was
    # processed successfully before the crash hit on titles[7] (2nd doc of
    # batch 2). The call for titles[7] itself IS recorded by the mock even
    # though it raised (Mock records call args before invoking
    # side_effect), so it isn't asserted absent here.
    seen_run1 = _titles_seen_in_calls(mock_client)
    for title in titles[0:6]:
        assert title in seen_run1
    assert titles[6] in seen_run1

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
    seen_run2 = _titles_seen_in_calls(mock_client)
    for title in titles[0:6]:
        assert title not in seen_run2
    # Batch 2's documents (titles[6], titles[7]) WERE processed this run.
    assert titles[6] in seen_run2
    assert titles[7] in seen_run2

    # (b) run completed successfully (no exception raised above is already
    # proof), (c) checkpoint now reflects the final batch index (0-based,
    # 3 batches total -> final index 2).
    assert state_store.get_last_completed_batch() == 2


def test_fault_actually_raises_on_the_targeted_document_call():
    # Focused unit check on the fault-injection helper itself, independent
    # of run_ingest - guards against the injection silently matching the
    # wrong call (e.g. a Chapter/Article/Clause query that also happens to
    # carry a `title`-shaped kwarg by coincidence) and the integration test
    # above passing for the wrong reason.
    mock_client, _ = _make_faulty_client("Văn Bản Số 7")

    with pytest.raises(RuntimeError, match="simulated crash"):
        mock_client.run("MERGE (d:Document ...)", doc_id="x", title="Văn Bản Số 7")

    # A different title does not trigger the fault.
    result = mock_client.run("MERGE (d:Document ...)", doc_id="y", title="Khác")
    assert result == []
