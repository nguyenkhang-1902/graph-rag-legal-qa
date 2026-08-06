"""Tests cho scripts/migrate_references.py (T027).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi
scripts/migrate_references.py ton tai.

BOI CANH: T025 (Document.title/so_hieu/loai_vb) va T026 (resolve trich dan
cheo van ban) chi co hieu luc voi du lieu ingest MOI. Graph that dang chua
37,875 REFERENCES + 8,427 external placeholder sinh ra boi extractor CU -
`upsert.py` dung MERGE nen edge SAI khong tu bien mat khi chay lai.

Day la script DUY NHAT trong project xoa du lieu that, nen cac test duoi
tap trung vao AN TOAN:
  - Mac dinh la dry-run: KHONG gui bat ky lenh xoa/ghi nao khi thieu --apply.
  - Chi xoa external placeholder MO CO (khong con quan he nao) - external
    placeholder van la dich cua AMENDS/SUPERSEDES/CONFLICTS_WITH phai duoc
    GIU (T013 da ghi 2 canh AMENDS that vao graph).
  - Xoa REFERENCES theo lo (CALL ... IN TRANSACTIONS) - mot transaction don
    cho 37,875 canh de gay het bo nho heap cua Neo4j Community.
  - Reset checkpoint TRUOC khi re-ingest, neu khong `run_ingest` se thay
    checkpoint cu ("da xong batch cuoi") va khong lam gi ca.
  - Thu tu BAT BUOC: xoa REFERENCES -> xoa placeholder mo coi -> reset
    checkpoint -> re-ingest. Dao thu tu se xoa mat chinh edge vua tao.
"""
from unittest.mock import MagicMock

import pytest

from scripts.migrate_references import (
    DELETE_ORPHAN_EXTERNAL_ARTICLES_QUERY,
    DELETE_REFERENCES_QUERY,
    run_migration,
)


def _mock_client():
    client = MagicMock()
    client.run.return_value = [{"n": 0}]
    return client


def _queries(client) -> list[str]:
    return [c.args[0] for c in client.run.call_args_list]


# --- An toan: dry-run la mac dinh ----------------------------------------


def test_dry_run_sends_no_delete_or_write():
    client = _mock_client()
    reingest = MagicMock()
    reset = MagicMock()

    run_migration(
        "data/raw", client=client, apply=False, reingest=reingest, reset_checkpoint=reset
    )

    for query in _queries(client):
        assert "DELETE" not in query.upper()
        assert "MERGE" not in query.upper()
        assert "SET " not in query.upper()
    reingest.assert_not_called()
    reset.assert_not_called()


def test_dry_run_still_counts_current_state_for_the_report():
    # Dry-run phai VAN doc so lieu hien tai (chi MATCH/count) de bao cao
    # "se xoa bao nhieu" - neu khong thi khong con la dry-run huu ich.
    client = _mock_client()

    run_migration(
        "data/raw",
        client=client,
        apply=False,
        reingest=MagicMock(),
        reset_checkpoint=MagicMock(),
    )

    assert any("count(" in q for q in _queries(client))


# --- Thu tu bat buoc va noi dung cac lenh xoa ---------------------------


def test_apply_runs_steps_in_required_order():
    client = _mock_client()
    calls: list[str] = []
    reingest = MagicMock(side_effect=lambda *a, **k: calls.append("reingest"))
    reset = MagicMock(side_effect=lambda *a, **k: calls.append("reset"))
    original_run = client.run

    def tracking_run(query, **params):
        if "DELETE" in query.upper():
            calls.append("delete-refs" if "REFERENCES" in query else "delete-orphan")
        return original_run(query, **params)

    client.run = tracking_run

    run_migration(
        "data/raw", client=client, apply=True, reingest=reingest, reset_checkpoint=reset
    )

    assert calls == ["delete-refs", "delete-orphan", "reset", "reingest"]


def test_delete_references_query_is_batched_to_avoid_heap_exhaustion():
    # 37,875 canh trong MOT transaction de lam het heap Neo4j Community.
    assert "CALL" in DELETE_REFERENCES_QUERY
    assert "IN TRANSACTIONS" in DELETE_REFERENCES_QUERY
    assert "REFERENCES" in DELETE_REFERENCES_QUERY


def test_delete_orphan_query_only_targets_external_articles_with_no_relationships():
    q = DELETE_ORPHAN_EXTERNAL_ARTICLES_QUERY
    # PHAI gioi han o is_external = true: KHONG bao gio duoc xoa Article that
    # (60,679 node co chroma_id - xoa la mat lien ket sang Chroma).
    assert "is_external" in q
    # PHAI yeu cau khong con quan he nao - external placeholder dang la dich
    # cua AMENDS/SUPERSEDES/CONFLICTS_WITH (T013) phai duoc GIU.
    assert "degree" in q or "COUNT { " in q or "size(" in q or "NOT (" in q
    assert "DETACH" not in q.upper(), (
        "DETACH DELETE se xoa ca quan he con lai - phai chi xoa node MO COI"
    )


def test_apply_passes_data_dir_through_to_reingest():
    client = _mock_client()
    reingest = MagicMock()

    run_migration(
        "duong/dan/rieng",
        client=client,
        apply=True,
        reingest=reingest,
        reset_checkpoint=MagicMock(),
    )

    assert reingest.call_args.args[0] == "duong/dan/rieng"


def test_run_migration_returns_before_and_after_counts():
    client = _mock_client()
    client.run.side_effect = lambda q, **p: [{"n": 111}]

    report = run_migration(
        "data/raw",
        client=client,
        apply=True,
        reingest=MagicMock(),
        reset_checkpoint=MagicMock(),
    )

    assert "truoc" in report and "sau" in report
    assert report["truoc"]["references"] == 111


def test_reingest_failure_propagates_and_is_not_swallowed():
    # Neu re-ingest that bai giua chung, KHONG duoc bao cao "migration xong":
    # luc do graph dang o trang thai da xoa REFERENCES nhung chua tao lai
    # het - phai crash lon tieng de operator biet phai chay lai.
    client = _mock_client()

    with pytest.raises(RuntimeError, match="ingest that bai"):
        run_migration(
            "data/raw",
            client=client,
            apply=True,
            reingest=MagicMock(side_effect=RuntimeError("ingest that bai")),
            reset_checkpoint=MagicMock(),
        )
