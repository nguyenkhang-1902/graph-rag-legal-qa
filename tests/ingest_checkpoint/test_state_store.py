"""Tests cho app/ingest_checkpoint/state_store.py (T009b).

Khong dung file that trong repo - moi test dung `tmp_path` (pytest fixture)
de tro IngestCheckpointStore vao mot thu muc temp rieng, tranh dung cham
gi den `.state/` that cua may dev.

Cac case theo task-2e-brief.md:
  1. Store moi (chua co file) -> get_last_completed_batch() is None.
  2. mark_batch_done(0) roi get_last_completed_batch() == 0.
  3. Nhieu lan mark_batch_done lien tiep -> luon phan anh gia tri MOI NHAT.
  4. Persistence that: ghi qua mot instance, doc qua instance MOI tro cung
     file -> xac nhan dang doc tu dia, khong phai state trong bo nho.
  5. Atomicity: sau mark_batch_done, khong con file .tmp rot lai trong thu
     muc (rename da hoan tat).
  6. JSON hong/corrupt -> khong crash resume mai mai: coi nhu chua co
     checkpoint hop le, log canh bao, bat dau lai tu batch 0 (xem docstring
     get_last_completed_batch() trong state_store.py ve ly do chon huong
     nay thay vi raise).
"""
import json

from app.ingest_checkpoint.state_store import IngestCheckpointStore


# --- Case 1: fresh store -----------------------------------------------


def test_fresh_store_returns_none(tmp_path):
    store = IngestCheckpointStore(tmp_path / "checkpoint.json")

    assert store.get_last_completed_batch() is None


# --- Case 2: mark_batch_done(0) -----------------------------------------


def test_mark_batch_done_zero_then_read_back(tmp_path):
    store = IngestCheckpointStore(tmp_path / "checkpoint.json")

    store.mark_batch_done(0, batch_size=10)

    assert store.get_last_completed_batch() == 0


# --- Case 3: nhieu lan goi lien tiep -> luon la gia tri moi nhat --------


def test_multiple_sequential_mark_batch_done_reflects_latest(tmp_path):
    store = IngestCheckpointStore(tmp_path / "checkpoint.json")

    store.mark_batch_done(0, batch_size=10)
    assert store.get_last_completed_batch() == 0

    store.mark_batch_done(1, batch_size=10)
    assert store.get_last_completed_batch() == 1

    store.mark_batch_done(5, batch_size=10)
    assert store.get_last_completed_batch() == 5


# --- Case 4: persistence that qua instance MOI ---------------------------


def test_persists_across_new_store_instance_pointed_at_same_file(tmp_path):
    state_file = tmp_path / "checkpoint.json"

    writer = IngestCheckpointStore(state_file)
    writer.mark_batch_done(3, batch_size=10)

    reader = IngestCheckpointStore(state_file)
    assert reader.get_last_completed_batch() == 3


# --- Case 5: atomicity - khong con .tmp litter ----------------------------


def test_no_leftover_tmp_file_after_mark_batch_done(tmp_path):
    state_file = tmp_path / "checkpoint.json"
    store = IngestCheckpointStore(state_file)

    store.mark_batch_done(0, batch_size=10)
    store.mark_batch_done(1, batch_size=10)

    remaining_files = sorted(p.name for p in tmp_path.iterdir())
    assert remaining_files == ["checkpoint.json"]


def test_mark_batch_done_creates_parent_directory_if_missing(tmp_path):
    state_file = tmp_path / "nested" / "dir" / "checkpoint.json"
    store = IngestCheckpointStore(state_file)

    store.mark_batch_done(2, batch_size=10)

    assert state_file.exists()
    assert store.get_last_completed_batch() == 2


# --- Case 6: JSON hong/corrupt -> khong crash, coi nhu chua co checkpoint -


def test_corrupted_json_treated_as_no_checkpoint_and_does_not_raise(tmp_path, caplog):
    state_file = tmp_path / "checkpoint.json"
    state_file.write_text("{not valid json!!!", encoding="utf-8")
    store = IngestCheckpointStore(state_file)

    with caplog.at_level("WARNING"):
        result = store.get_last_completed_batch()

    assert result is None
    assert any("checkpoint" in record.message.lower() or "Checkpoint" in record.message for record in caplog.records)


def test_after_corrupted_json_a_fresh_mark_batch_done_overwrites_it(tmp_path):
    state_file = tmp_path / "checkpoint.json"
    state_file.write_text("not json at all", encoding="utf-8")
    store = IngestCheckpointStore(state_file)

    assert store.get_last_completed_batch() is None

    store.mark_batch_done(0, batch_size=10)

    assert store.get_last_completed_batch() == 0
    # File giờ phải chứa JSON hợp lệ (đã bị ghi đè bởi mark_batch_done).
    data = json.loads(state_file.read_text(encoding="utf-8"))
    assert data["last_completed_batch"] == 0


# --- batch_size round-trip (review finding: resume must detect a changed --
# --- batch_size, or it silently maps "batch N+1" to the wrong file slice) -


def test_batch_size_round_trips_through_mark_batch_done(tmp_path):
    store = IngestCheckpointStore(tmp_path / "checkpoint.json")

    assert store.get_last_batch_size() is None

    store.mark_batch_done(0, batch_size=37)

    assert store.get_last_batch_size() == 37


def test_get_last_batch_size_reflects_latest_mark_batch_done_call(tmp_path):
    store = IngestCheckpointStore(tmp_path / "checkpoint.json")

    store.mark_batch_done(0, batch_size=10)
    assert store.get_last_batch_size() == 10

    store.mark_batch_done(1, batch_size=25)
    assert store.get_last_batch_size() == 25


def test_get_last_batch_size_none_when_field_missing_from_file(tmp_path):
    # Checkpoint cu (ghi truoc khi truong "batch_size" ton tai) khong co
    # truong nay - phai tra ve None (khong crash, khong bia so lieu).
    state_file = tmp_path / "checkpoint.json"
    state_file.write_text(
        json.dumps({"last_completed_batch": 4}), encoding="utf-8"
    )
    store = IngestCheckpointStore(state_file)

    assert store.get_last_completed_batch() == 4
    assert store.get_last_batch_size() is None
