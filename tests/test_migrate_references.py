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
    reconcile_chroma_with_neo4j,
    run_migration,
)


def _mock_client():
    """Neo4jClient mock tra ve SHAPE dung cho tung loai query.

    Khong dung mot `return_value` chung ([{"n": 0}]) cho moi query: cac cau
    `RETURN ... AS article_id` co shape KHAC cac cau `RETURN count(...) AS n`,
    va code that doc dung key tuong ung - mock mot shape duy nhat se lam test
    do vi KeyError chu khong phai vi hanh vi sai.
    """
    client = MagicMock()

    def run(query, **_params):
        if "article_id" in query and "DELETE" not in query.upper():
            return []
        if "d.doc_id AS doc_id" in query:
            return []
        return [{"n": 0}]

    client.run.side_effect = run
    return client


def _queries(client) -> list[str]:
    return [c.args[0] for c in client.run.call_args_list]


# --- An toan: dry-run la mac dinh ----------------------------------------


def test_dry_run_sends_no_delete_or_write():
    client = _mock_client()
    reingest = MagicMock()
    reset = MagicMock()

    run_migration(
        "data/raw",
        client=client,
        apply=False,
        reingest=reingest,
        reset_checkpoint=reset,
        reconcile_chroma=lambda _c: 0,
        real_doc_ids={"co-that"},
        stale_doc_ids=[],
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
        reconcile_chroma=lambda _c: 0,
        real_doc_ids={"co-that"},
        stale_doc_ids=[],
    )

    assert any("count(" in q for q in _queries(client))


# --- Thu tu bat buoc va noi dung cac lenh xoa ---------------------------


def _plausible_real_doc_ids(n: int = 100) -> set[str]:
    """Tap doc_id "that" du lon de mot doc_id cu KHONG vuot nguong chan tham
    hoa (_MAX_STALE_DOCUMENT_SHARE = 5%). Ty le that trong corpus la 4/3,203
    (0.12%) nen 1/101 (~1%) la mo phong hop ly."""
    return {f"doc-that-{i}" for i in range(n)}


def test_apply_runs_steps_in_required_order():
    client = _mock_client()
    calls: list[str] = []
    reingest = MagicMock(side_effect=lambda *a, **k: calls.append("reingest"))
    reset = MagicMock(side_effect=lambda *a, **k: calls.append("reset"))
    original_run = client.run

    def tracking_run(query, **params):
        upper = query.upper()
        if "DELETE" in upper:
            if "REFERENCES" in query:
                calls.append("delete-refs")
            elif "is_external" in query:
                calls.append("delete-orphan")
            else:
                calls.append("delete-stale-doc")
        return original_run(query, **params)

    client.run = tracking_run

    run_migration(
        "data/raw",
        client=client,
        apply=True,
        reingest=reingest,
        reset_checkpoint=reset,
        reconcile_chroma=lambda _c: 0,
        real_doc_ids=_plausible_real_doc_ids(),
        stale_doc_ids=["cu-khong-con"],
    )

    assert calls == [
        "delete-refs",
        "delete-orphan",
        "delete-stale-doc",
        "reset",
        "reingest",
    ]


# --- Xoa Document khong con suy ra duoc tu ten file (T027b, chu "eth") ----
# 4 van ban that dung "ð" (eth) co doc_id CU la "102-2017-n-cp"...; sau khi
# `slugify_doc_name` chuan hoa eth (2026-08-06) doc_id MOI la
# "102-2017-nd-cp". Node cu tro thanh RAC: re-ingest tao node moi ben canh
# chu khong doi ten node cu. Phai xoa node cu + xoa luon ban ghi cua chung
# trong Chroma (id = article_id), roi backfill embedding cho node moi.


def test_stale_documents_are_deleted_with_their_whole_subtree():
    client = _mock_client()

    run_migration(
        "data/raw",
        client=client,
        apply=True,
        reingest=MagicMock(),
        reset_checkpoint=MagicMock(),
        reconcile_chroma=lambda _c: 0,
        real_doc_ids=_plausible_real_doc_ids() | {"102-2017-nd-cp"},
        stale_doc_ids=["102-2017-n-cp"],
    )

    stale_queries = [
        q for q in _queries(client) if "DELETE" in q.upper() and "REFERENCES" not in q
        and "is_external" not in q
    ]
    assert stale_queries, "khong co lenh xoa Document cu"
    q = stale_queries[0]
    # Phai xoa CA cay con: Chapter/Article/Clause thuoc Document do.
    for label in ("Chapter", "Article", "Clause"):
        assert label in q, f"query xoa Document cu khong xu ly {label}"


def test_reconcile_deletes_chroma_ids_absent_from_neo4j():
    # Co che DOI CHIEU (thay cho xoa nham-dich): moi id trong Chroma khong
    # ung voi mot Article that trong Neo4j deu la rac -> xoa. Tu sua duoc
    # MOI kieu lech, ke ca lech do mot lan chay truoc bi crash giua duong.
    class FakeCollection:
        def __init__(self):
            self.deleted: list[list[str]] = []

        def get(self, include=None):
            return {"ids": ["con-dung_dieu-1", "rac_dieu-1", "rac_dieu-2"]}

        def delete(self, ids):
            self.deleted.append(list(ids))

    col = FakeCollection()
    client = _mock_client()
    client.run.side_effect = lambda q, **p: (
        [{"article_id": "con-dung_dieu-1"}] if "article_id" in q else [{"n": 0}]
    )

    n = reconcile_chroma_with_neo4j(client, collection=col)

    assert n == 2
    assert col.deleted == [["rac_dieu-1", "rac_dieu-2"]]


def test_reconcile_is_noop_when_chroma_and_neo4j_agree():
    class FakeCollection:
        def __init__(self):
            self.deleted = []

        def get(self, include=None):
            return {"ids": ["a_dieu-1"]}

        def delete(self, ids):
            self.deleted.append(list(ids))

    col = FakeCollection()
    client = _mock_client()
    client.run.side_effect = lambda q, **p: (
        [{"article_id": "a_dieu-1"}] if "article_id" in q else [{"n": 0}]
    )

    assert reconcile_chroma_with_neo4j(client, collection=col) == 0
    assert col.deleted == []


def test_reconcile_refuses_when_neo4j_returns_no_articles():
    # Neu Neo4j tra ve 0 Article (loi ket noi/query sai), MOI id trong Chroma
    # se bi coi la rac -> xoa sach 60k embedding (hang gio GPU de tao lai).
    # Phai tu choi.
    class FakeCollection:
        def get(self, include=None):
            return {"ids": ["a_dieu-1", "a_dieu-2"]}

        def delete(self, ids):  # pragma: no cover - khong duoc goi
            raise AssertionError("khong duoc xoa gi")

    client = _mock_client()
    client.run.side_effect = lambda q, **p: [] if "article_id" in q else [{"n": 0}]

    with pytest.raises(RuntimeError, match="khong co Article nao"):
        reconcile_chroma_with_neo4j(client, collection=FakeCollection())


def test_default_chroma_collection_getter_exists_in_embedder():
    # BUG THAT tu gay ra (2026-08-06): `_delete_from_chroma` cu import
    # `get_or_create_collection` tu app.retrieval.embedder - TEN KHONG TON
    # TAI (ten dung la `get_chroma_collection`). Moi test deu inject
    # `delete_from_chroma`/`collection` nen implementation THAT chua bao gio
    # duoc chay -> loi chi lo ra khi chay migration tren du lieu that, SAU khi
    # da xoa node Neo4j nhung TRUOC khi xoa ban ghi Chroma (de lai 119 ban ghi
    # mo coi). Test nay ghim: ten ham mac dinh phai ton tai that.
    import app.retrieval.embedder as embedder

    from scripts.migrate_references import _default_chroma_collection

    import inspect

    # Ten ham PHAI ton tai that trong embedder.
    assert callable(embedder.get_chroma_collection)
    # Va `_default_chroma_collection` phai tro dung toi ten do. Kiem tra bang
    # doc source (khong GOI ham) - goi that se mo Chroma tren dia, khong phu
    # hop cho unit test.
    src = inspect.getsource(_default_chroma_collection)
    assert "get_chroma_collection" in src
    assert "get_or_create_collection" not in src


def test_no_stale_documents_means_no_stale_delete_query():
    client = _mock_client()

    run_migration(
        "data/raw",
        client=client,
        apply=True,
        reingest=MagicMock(),
        reset_checkpoint=MagicMock(),
        reconcile_chroma=lambda _c: 0,
        real_doc_ids={"102-2017-nd-cp"},
        stale_doc_ids=[],
    )

    stale_queries = [
        q
        for q in _queries(client)
        if "DELETE" in q.upper() and "REFERENCES" not in q and "is_external" not in q
    ]
    assert stale_queries == []


# --- Chan tham hoa: khong bao gio xoa toan bo graph ----------------------


def test_refuses_to_run_when_no_real_doc_ids_found():
    # Neu `data_dir` sai/rong, tap doc_id suy tu ten file se RONG -> MOI
    # Document deu bi coi la "cu" -> xoa sach graph. Phai tu choi chay.
    client = _mock_client()

    with pytest.raises(RuntimeError, match="khong tim thay doc_id nao"):
        run_migration(
            "duong/dan/sai",
            client=client,
            apply=True,
            reingest=MagicMock(),
            reset_checkpoint=MagicMock(),
            reconcile_chroma=lambda _c: 0,
            real_doc_ids=set(),
            stale_doc_ids=["a", "b"],
        )


def test_refuses_to_delete_an_implausibly_large_share_of_documents():
    # Do that: chi 4/3,203 van ban (0.12%) can xoa. Neu con so nay bat ngo
    # lon (vd doi cach sinh doc_id lam lech ca corpus), gan nhu chac chan la
    # loi lap trinh chu khong phai y dinh - dung lai, bat nguoi kiem tra.
    client = _mock_client()
    real = {f"doc-{i}" for i in range(100)}
    stale = [f"cu-{i}" for i in range(20)]  # 20/120 = 16.7%

    with pytest.raises(RuntimeError, match="qua nhieu Document"):
        run_migration(
            "data/raw",
            client=client,
            apply=True,
            reingest=MagicMock(),
            reset_checkpoint=MagicMock(),
            reconcile_chroma=lambda _c: 0,
            real_doc_ids=real,
            stale_doc_ids=stale,
        )


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
        reconcile_chroma=lambda _c: 0,
        real_doc_ids={"co-that"},
        stale_doc_ids=[],
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
        reconcile_chroma=lambda _c: 0,
        real_doc_ids={"co-that"},
        stale_doc_ids=[],
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
            reconcile_chroma=lambda _c: 0,
            real_doc_ids={"co-that"},
            stale_doc_ids=[],
        )


# --- --resume: tiep tuc mot migration bi dung giua chung ------------------
# BAY THAT (2026-08-06): buoc 1-4 la XOA + reset checkpoint. Neu migration bi
# dung giua buoc 5 (re-ingest) roi nguoi dung chay lai `--apply`, no se XOA
# SACH REFERENCES vua tao + reset checkpoint -> lam lai tu dau, mat toan bo
# tien do. `--resume` bo qua buoc 1-4, chi chay re-ingest (tu tiep tu
# checkpoint) + doi chieu Chroma.


def test_resume_skips_all_destructive_steps():
    client = _mock_client()
    reset = MagicMock()

    run_migration(
        "data/raw",
        client=client,
        apply=True,
        resume=True,
        reingest=MagicMock(),
        reset_checkpoint=reset,
        reconcile_chroma=lambda _c: 0,
        real_doc_ids=_plausible_real_doc_ids(),
        stale_doc_ids=["cu-khong-con"],
        checkpoint_exists=lambda: True,
    )

    for q in _queries(client):
        assert "DELETE" not in q.upper(), f"resume khong duoc xoa gi: {q}"
    reset.assert_not_called()


def test_resume_still_runs_reingest_and_reconcile():
    client = _mock_client()
    reingest = MagicMock()
    reconciled = []

    run_migration(
        "data/raw",
        client=client,
        apply=True,
        resume=True,
        reingest=reingest,
        reset_checkpoint=MagicMock(),
        reconcile_chroma=lambda _c: reconciled.append(1) or 0,
        real_doc_ids=_plausible_real_doc_ids(),
        stale_doc_ids=[],
        checkpoint_exists=lambda: True,
    )

    reingest.assert_called_once()
    assert reconciled == [1]


def test_resume_without_checkpoint_is_refused():
    # Khong co checkpoint = hoac migration chua tung chay, hoac da xong. Ca
    # hai truong hop `--resume` deu SAI: no bo qua buoc xoa, nen neu REFERENCES
    # cu van con thi graph se lan ca canh dung va canh sai.
    client = _mock_client()

    with pytest.raises(RuntimeError, match="khong co checkpoint"):
        run_migration(
            "data/raw",
            client=client,
            apply=True,
            resume=True,
            reingest=MagicMock(),
            reset_checkpoint=MagicMock(),
            reconcile_chroma=lambda _c: 0,
            real_doc_ids=_plausible_real_doc_ids(),
            stale_doc_ids=[],
            checkpoint_exists=lambda: False,
        )
