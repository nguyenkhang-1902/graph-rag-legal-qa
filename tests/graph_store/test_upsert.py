"""Tests cho app/graph_store/upsert.py (T009).

Khong co Neo4j that chay trong moi truong nay - cung tinh huong nhu T005
(xem tests/graph_store/test_neo4j_client.py). Moi test o day mock
`Neo4jClient.run` va kiem tra Cypher + tham so DUOC GUI, khong phai
"Neo4j thuc thi dung hay khong" - hop ly de unit test bang mock (T005 da
lam theo cach nay, tiep tuc quy uoc do o day).

Cac case theo task-2d-brief.md:
  1. Upsert van ban co Chapter/Article/Clause -> gui MERGE cho moi loai
     node/canh BELONGS_TO (khong CREATE).
  2. Upsert CUNG mot ParsedDocument hai lan -> gui CUNG cac cau lenh ca
     hai lan (bang chung idempotent - khong the kiem tra graph that o day).
  3. Van ban KHONG co Chapter -> Article gan BELONGS_TO thang vao Document.
  4. upsert_references cho target chua ton tai: ON CREATE SET
     is_external = true, canh REFERENCES cung la MERGE.
  5. Goi upsert_references hai lan cho cung (source, target, raw_text) ->
     gui cung Cypher/tham so ca hai lan (idempotent).
  6. full_text KHONG BAO GIO xuat hien trong tham so gui cho Neo4j (chi
     noi_dung_preview) - day la test duy nhat co the kiem tra phan nay cua
     amendment T008 (structure_parser.py test khong biet gi ve Neo4j).
  7. "Nang cap" placeholder -> Article that: cau Article MERGE set
     is_external = false VO DIEU KIEN (khong phai ON CREATE), khac voi
     is_external = true tren target cua upsert_references (CO ON CREATE).
     Day la kiem tra CAU TRUC QUERY, khong mo phong MERGE semantics that
     cua Neo4j bang mock graph (khong the lam duoc voi mock don gian).
"""
from unittest.mock import MagicMock

from app.extraction.reference_extractor import ExtractedReference
from app.extraction.structure_parser import Article, Chapter, Clause, ParsedDocument
import pytest

from app.graph_store.upsert import (
    upsert_definitions,
    upsert_document,
    upsert_references,
    upsert_relations,
    upsert_term_usages,
)


def _make_mock_client():
    """Neo4jClient that co method `run(query, **params)` - upsert.py chi
    goi qua interface nay, nen mock don gian nay du (giong cach T005 mock
    driver/session, o day mock thang o muc Neo4jClient vi do la dependency
    truc tiep cua upsert.py)."""
    return MagicMock()


def _queries_sent(mock_client) -> list[str]:
    return [c.args[0] for c in mock_client.run.call_args_list]


# --- Fixtures: ParsedDocument voi Chapter/Article/Clause ------------------


def _build_parsed_with_chapters() -> ParsedDocument:
    clause = Clause(
        clause_id="luat-test_dieu-1_khoan-1",
        so_khoan=1,
        noi_dung="Noi dung khoan mot day du, khong truncate.",
    )
    article = Article(
        article_id="luat-test_dieu-1",
        so_dieu=1,
        noi_dung_preview="Preview ngan.",
        full_text="Day la full_text DAY DU cua Dieu 1 - TUYET DOI khong duoc"
        " xuat hien trong bat ky tham so nao gui cho Neo4j.",
        clauses=[clause],
    )
    chapter = Chapter(
        chapter_id="luat-test_chuong-1",
        so_chuong=1,
        tieu_de="NHUNG QUY DINH CHUNG",
        articles=[article],
    )
    return ParsedDocument(
        doc_id="luat-test", title="Luat Test", chapters=[chapter], articles=[]
    )


def _build_parsed_without_chapters() -> ParsedDocument:
    article = Article(
        article_id="nghi-dinh-test_dieu-1",
        so_dieu=1,
        noi_dung_preview="Preview ngan khong chuong.",
        full_text="Full text day du khong co chuong.",
        clauses=[],
    )
    return ParsedDocument(
        doc_id="nghi-dinh-test",
        title="Nghi Dinh Test",
        chapters=[],
        articles=[article],
    )


# --- T025: Document.title/so_hieu/loai_vb tu DocIdentity -------------------
# `Document.title` RONG tren toan bo graph (gap tu DOT 3) va corpus KHONG
# chua tieu de van ban - chi suy duoc tu ten file qua doc_identity.py (xem
# module docstring cua no). Cac test duoi ghim: khi truyen `identity`,
# upsert_document PHAI ghi ca so_hieu/loai_vb; khi KHONG truyen, hanh vi cu
# giu nguyen (khong ghi de gia tri cu bang null).


def _document_call(mock_client):
    """(query, params) cua lan goi Document (luon la lan goi DAU TIEN)."""
    call = mock_client.run.call_args_list[0]
    return call.args[0], call.kwargs


def test_upsert_document_with_identity_writes_so_hieu_and_loai_vb():
    from app.extraction.doc_identity import build_doc_identity

    client = _make_mock_client()
    parsed = _build_parsed_without_chapters()
    identity = build_doc_identity("19", "2016", "tt-bxd")

    upsert_document(client, parsed, batch_id="batch-001", identity=identity)

    query, params = _document_call(client)
    assert "d.so_hieu = $so_hieu" in query
    assert "d.loai_vb = $loai_vb" in query
    assert params["so_hieu"] == "19/2016/TT-BXD"
    assert params["loai_vb"] == "Thông tư"


def test_upsert_document_with_identity_falls_back_to_synthesized_title():
    # `parse_article_chunk` (duong ingest that) LUON de title rong - luc do
    # dung chi danh chuan tu identity ("Thông tư 19/2016/TT-BXD").
    from app.extraction.doc_identity import build_doc_identity

    client = _make_mock_client()
    parsed = ParsedDocument(doc_id="19-2016-tt-bxd", title="", chapters=[], articles=[])

    upsert_document(
        client,
        parsed,
        batch_id="batch-001",
        identity=build_doc_identity("19", "2016", "tt-bxd"),
    )

    _query, params = _document_call(client)
    assert params["title"] == "Thông tư 19/2016/TT-BXD"


def test_upsert_document_prefers_real_parsed_title_over_synthesized_one():
    # Neu mot ngay nao do co tieu de van xuoi THAT (vd `parse_document()`
    # tren input mot-file-mot-van-ban), tieu de do PHAI thang chi danh chuan
    # sinh ra tu so hieu - identity chi la fallback, khong ghi de du lieu
    # tot hon.
    from app.extraction.doc_identity import build_doc_identity

    client = _make_mock_client()
    parsed = _build_parsed_without_chapters()  # title = "Nghi Dinh Test"

    upsert_document(
        client,
        parsed,
        batch_id="batch-001",
        identity=build_doc_identity("19", "2016", "tt-bxd"),
    )

    _query, params = _document_call(client)
    assert params["title"] == "Nghi Dinh Test"


def test_upsert_document_with_unknown_loai_vb_sends_none_not_guess():
    # Ma hieu Quoc hoi (qh13) khong xac dinh duoc loai van ban - phai gui
    # None (Cypher xoa thuoc tinh) thay vi doan bua "Luật".
    from app.extraction.doc_identity import build_doc_identity

    client = _make_mock_client()
    parsed = ParsedDocument(doc_id="16-2012-qh13", title="", chapters=[], articles=[])

    upsert_document(
        client,
        parsed,
        batch_id="batch-001",
        identity=build_doc_identity("16", "2012", "qh13"),
    )

    _query, params = _document_call(client)
    assert params["loai_vb"] is None
    assert params["title"] == "16/2012/QH13"


def test_upsert_document_without_identity_does_not_touch_so_hieu_or_loai_vb():
    # Khong co identity -> KHONG duoc dua so_hieu/loai_vb vao query. Neu
    # dua vao voi gia tri null, mot lan chay khong co identity se AM THAM
    # XOA so_hieu/loai_vb da ghi dung o lan chay truoc.
    client = _make_mock_client()
    parsed = _build_parsed_without_chapters()

    upsert_document(client, parsed, batch_id="batch-001")

    query, params = _document_call(client)
    assert "so_hieu" not in query
    assert "loai_vb" not in query
    assert "so_hieu" not in params
    assert "loai_vb" not in params


# --- Case 1: MERGE cho moi loai node/canh, khong CREATE --------------------


def test_upsert_document_sends_merge_for_every_node_and_edge():
    client = _make_mock_client()
    parsed = _build_parsed_with_chapters()

    upsert_document(client, parsed, batch_id="batch-001")

    queries = _queries_sent(client)
    assert len(queries) == 4  # Document, Chapter, Article, Clause

    for query in queries:
        assert "MERGE" in query
        assert "CREATE" not in query  # khong bao gio dung CREATE (idempotent)

    document_query, chapter_query, article_query, clause_query = queries
    assert "MERGE (d:Document {doc_id: $doc_id})" in document_query

    assert "MERGE (c:Chapter {chapter_id: $chapter_id})" in chapter_query
    assert "MERGE (c)-[:BELONGS_TO]->(parent)" in chapter_query
    assert "MATCH (parent:Document {doc_id: $doc_id})" in chapter_query

    assert "MERGE (a:Article {article_id: $article_id})" in article_query
    assert "MERGE (a)-[:BELONGS_TO]->(parent)" in article_query
    assert "MATCH (parent:Chapter {chapter_id: $parent_id})" in article_query

    assert "MERGE (cl:Clause {clause_id: $clause_id})" in clause_query
    assert "MERGE (cl)-[:BELONGS_TO]->(parent)" in clause_query
    assert "MATCH (parent:Article {article_id: $parent_id})" in clause_query

    # Tham so dung: Document
    doc_call = client.run.call_args_list[0]
    assert doc_call.kwargs == {
        "doc_id": "luat-test",
        "title": "Luat Test",
        "batch_id": "batch-001",
    }

    # Tham so dung: Chapter
    chapter_call = client.run.call_args_list[1]
    assert chapter_call.kwargs == {
        "doc_id": "luat-test",
        "chapter_id": "luat-test_chuong-1",
        "so_chuong": 1,
        "tieu_de": "NHUNG QUY DINH CHUNG",
    }

    # Tham so dung: Article (chu y is_external duoc set qua trong query
    # string, khong phai tham so - kiem tra rieng o case 7 duoi)
    article_call = client.run.call_args_list[2]
    assert article_call.kwargs == {
        "parent_id": "luat-test_chuong-1",
        "article_id": "luat-test_dieu-1",
        "so_dieu": 1,
        "noi_dung_preview": "Preview ngan.",
    }

    # Tham so dung: Clause (noi_dung KHONG bi truncate)
    clause_call = client.run.call_args_list[3]
    assert clause_call.kwargs == {
        "parent_id": "luat-test_dieu-1",
        "clause_id": "luat-test_dieu-1_khoan-1",
        "so_khoan": 1,
        "noi_dung": "Noi dung khoan mot day du, khong truncate.",
    }


# --- Case 2: idempotency - goi hai lan gui cung cau lenh -------------------


def test_upsert_document_called_twice_sends_identical_calls():
    client = _make_mock_client()
    parsed = _build_parsed_with_chapters()

    upsert_document(client, parsed, batch_id="batch-001")
    first_call_list = list(client.run.call_args_list)

    upsert_document(client, parsed, batch_id="batch-001")
    second_call_list = list(client.run.call_args_list)[len(first_call_list) :]

    assert first_call_list == second_call_list


# --- Case 3: khong co Chapter -> Article gan thang vao Document ------------


def test_upsert_document_without_chapters_attaches_article_to_document():
    client = _make_mock_client()
    parsed = _build_parsed_without_chapters()

    upsert_document(client, parsed, batch_id="batch-002")

    queries = _queries_sent(client)
    assert len(queries) == 2  # Document, Article (khong Chapter, khong Clause)

    document_query, article_query = queries
    assert "MERGE (d:Document {doc_id: $doc_id})" in document_query
    assert "MATCH (parent:Document {doc_id: $parent_id})" in article_query
    assert "MERGE (a:Article {article_id: $article_id})" in article_query
    assert "MERGE (a)-[:BELONGS_TO]->(parent)" in article_query

    article_call = client.run.call_args_list[1]
    assert article_call.kwargs["parent_id"] == "nghi-dinh-test"
    assert article_call.kwargs["article_id"] == "nghi-dinh-test_dieu-1"


# --- Case 4: upsert_references, target chua ton tai ------------------------


def test_upsert_references_sets_is_external_via_on_create_and_merges_edge():
    client = _make_mock_client()
    references = [
        ExtractedReference(
            target_article_id="luat-khac_dieu-9", raw_text="Điều 9 Luật Khác"
        )
    ]

    upsert_references(client, article_id="luat-test_dieu-1", references=references)

    assert client.run.call_count == 1
    query = client.run.call_args_list[0].args[0]
    kwargs = client.run.call_args_list[0].kwargs

    assert "MATCH (source:Article {article_id: $source_id})" in query
    assert "MERGE (target:Article {article_id: $target_id})" in query
    assert "ON CREATE SET target.is_external = true" in query
    assert "MERGE (source)-[r:REFERENCES]->(target)" in query
    assert "CREATE" not in query.replace(
        "ON CREATE", ""
    )  # khong CREATE tran lan, chi ON CREATE SET

    assert kwargs == {
        "source_id": "luat-test_dieu-1",
        "target_id": "luat-khac_dieu-9",
        "raw_text": "Điều 9 Luật Khác",
    }


# --- Case 5: upsert_references idempotent cho cung mot triple --------------


def test_upsert_references_called_twice_for_same_triple_sends_identical_calls():
    client = _make_mock_client()
    references = [
        ExtractedReference(target_article_id="luat-khac_dieu-9", raw_text="Điều 9")
    ]

    upsert_references(client, article_id="luat-test_dieu-1", references=references)
    first_call = client.run.call_args_list[0]

    upsert_references(client, article_id="luat-test_dieu-1", references=references)
    second_call = client.run.call_args_list[1]

    assert first_call == second_call


# --- Case 6: full_text KHONG BAO GIO duoc gui cho Neo4j ---------------------


def test_full_text_is_never_sent_to_neo4j():
    client = _make_mock_client()
    parsed = _build_parsed_with_chapters()
    forbidden_value = parsed.chapters[0].articles[0].full_text
    assert forbidden_value  # sanity: fixture thuc su co full_text khac rong

    upsert_document(client, parsed, batch_id="batch-001")

    for call_args in client.run.call_args_list:
        query = call_args.args[0]
        kwargs = call_args.kwargs
        assert "full_text" not in query
        assert "full_text" not in kwargs
        for value in kwargs.values():
            assert value != forbidden_value


# --- Case 7: nang cap placeholder -> Article that ---------------------------


def test_article_upsert_sets_is_external_false_unconditionally():
    # Cau Article MERGE (ca hai bien the: duoi Chapter va duoi Document
    # truc tiep) phai SET is_external = false VO DIEU KIEN (khong dang sau
    # "ON CREATE") - de mot Article that co the "nang cap" mot placeholder
    # da duoc tao truoc do boi upsert_references (xem case 4/8 tren, va
    # "Ordering guarantee to preserve" trong brief). Day la test cau truc
    # query (string), khong phai mo phong MERGE semantics that cua Neo4j.
    client = _make_mock_client()

    parsed_with_chapter = _build_parsed_with_chapters()
    upsert_document(client, parsed_with_chapter, batch_id="batch-001")
    article_under_chapter_query = client.run.call_args_list[2].args[0]

    client2 = _make_mock_client()
    parsed_without_chapter = _build_parsed_without_chapters()
    upsert_document(client2, parsed_without_chapter, batch_id="batch-002")
    article_under_document_query = client2.run.call_args_list[1].args[0]

    for query in (article_under_chapter_query, article_under_document_query):
        assert "a.is_external = false" in query
        # Khong duoc co "ON CREATE SET a.is_external" hay bat ky bien the
        # nao gate is_external=false phia sau ON CREATE - phai la SET vo
        # dieu kien.
        assert "ON CREATE SET a.is_external" not in query

    # Doi chieu: target cua upsert_references (tinh huong placeholder) THI
    # PHAI duoc gate boi ON CREATE - khac han voi Article that o tren.
    ref_client = _make_mock_client()
    upsert_references(
        ref_client,
        article_id="luat-test_dieu-1",
        references=[
            ExtractedReference(target_article_id="luat-khac_dieu-9", raw_text="x")
        ],
    )
    reference_query = ref_client.run.call_args_list[0].args[0]
    assert "ON CREATE SET target.is_external = true" in reference_query


# --- upsert_definitions / upsert_term_usages (T012 hoan thien) -----------


def test_upsert_definitions_sends_one_batched_unwind_call_not_one_per_row():
    """Quy mo 60k+ Article (giong ly do backfill_embeddings.py's
    _update_chroma_ids dung UNWIND thay vi N loi goi rieng) - upsert_definitions
    PHAI gui MOT cau UNWIND duy nhat cho ca batch, khong phai N loi goi
    client.run rieng le cho tung dinh nghia."""
    client = _make_mock_client()
    rows = [
        {
            "article_id": "luat-a_dieu-1",
            "term_id": "ngay",
            "ten_thuat_ngu": "Ngày",
            "dinh_nghia": "ngày dương lịch",
        },
        {
            "article_id": "luat-b_dieu-2",
            "term_id": "don-pct",
            "ten_thuat_ngu": "Đơn PCT",
            "dinh_nghia": "đơn đăng ký sáng chế",
        },
    ]

    upsert_definitions(client, rows)

    assert client.run.call_count == 1
    query, kwargs = client.run.call_args
    assert "UNWIND $rows" in query[0]
    assert "MERGE (t:Term {term_id: row.term_id})" in query[0]
    assert "MERGE (a)-[:DEFINES]->(t)" in query[0]
    assert kwargs["rows"] == rows


def test_upsert_definitions_empty_rows_does_not_call_neo4j():
    client = _make_mock_client()
    upsert_definitions(client, [])
    client.run.assert_not_called()


def test_upsert_definitions_term_uses_on_create_set_not_overwrite_existing():
    """Nhieu Article co the (hiem, nhung co the) cung dinh nghia mot
    term_id trung nhau - ON CREATE SET giu dinh nghia DAU TIEN, khong ghi
    de moi lan MERGE lai (tuong tu triet ly raw_text trong upsert_references)."""
    client = _make_mock_client()
    upsert_definitions(
        client,
        [
            {
                "article_id": "luat-a_dieu-1",
                "term_id": "ngay",
                "ten_thuat_ngu": "Ngày",
                "dinh_nghia": "ngày dương lịch",
            }
        ],
    )
    query = client.run.call_args[0][0]
    assert "ON CREATE SET t.ten_thuat_ngu" in query


def test_upsert_term_usages_sends_one_batched_unwind_call_not_one_per_row():
    client = _make_mock_client()
    rows = [
        {"article_id": "luat-a_dieu-5", "term_id": "ngay"},
        {"article_id": "luat-a_dieu-6", "term_id": "ngay"},
    ]

    upsert_term_usages(client, rows)

    assert client.run.call_count == 1
    query, kwargs = client.run.call_args
    assert "UNWIND $rows" in query[0]
    assert "MATCH (t:Term {term_id: row.term_id})" in query[0]
    assert "MERGE (a)-[:USES_TERM]->(t)" in query[0]
    assert kwargs["rows"] == rows


def test_upsert_term_usages_empty_rows_does_not_call_neo4j():
    client = _make_mock_client()
    upsert_term_usages(client, [])
    client.run.assert_not_called()


# --- upsert_relations (T013: AMENDS/SUPERSEDES/CONFLICTS_WITH) -------------


def test_upsert_relations_sends_one_batched_unwind_call_per_type():
    """Cypher relationship TYPE khong the tham so hoa - moi loai quan he
    (AMENDS/SUPERSEDES/CONFLICTS_WITH) dung query rieng (literal type,
    CHON tu whitelist co dinh, khong bao gio string-format tu du lieu
    nguoi dung - xem upsert.py module docstring Dieu 1). Van UNWIND batch
    trong MOT loi goi, khong phai N loi goi rieng."""
    client = _make_mock_client()
    rows = [
        {
            "source_article_id": "luat-xyz_dieu-1",
            "target_article_id": "luat-doanh-nghiep-2020_dieu-5",
            "confidence": 0.9,
            "ly_do": "sửa đổi trực tiếp",
        }
    ]

    upsert_relations(client, "AMENDS", rows)

    assert client.run.call_count == 1
    query, kwargs = client.run.call_args
    assert "UNWIND $rows" in query[0]
    assert "MERGE (source)-[r:AMENDS]->(target)" in query[0]
    assert kwargs["rows"] == rows


def test_upsert_relations_supersedes_and_conflicts_with_use_own_relationship_type():
    client = _make_mock_client()
    row = [
        {
            "source_article_id": "luat-xyz_dieu-1",
            "target_article_id": "luat-abc_dieu-2",
            "confidence": 0.8,
            "ly_do": "x",
        }
    ]

    upsert_relations(client, "SUPERSEDES", row)
    assert "MERGE (source)-[r:SUPERSEDES]->(target)" in client.run.call_args[0][0]

    upsert_relations(client, "CONFLICTS_WITH", row)
    assert "MERGE (source)-[r:CONFLICTS_WITH]->(target)" in client.run.call_args[0][0]


def test_upsert_relations_sets_is_external_via_on_create_for_new_target():
    """Target Article co the chua ton tai trong corpus (ngoai pham vi da
    ingest) - cung co che external reference placeholder voi
    upsert_references (data-model.md), ON CREATE SET is_external = true."""
    client = _make_mock_client()
    rows = [
        {
            "source_article_id": "luat-xyz_dieu-1",
            "target_article_id": "luat-ngoai-pham-vi_dieu-9",
            "confidence": 0.7,
            "ly_do": "x",
        }
    ]

    upsert_relations(client, "AMENDS", rows)

    query = client.run.call_args[0][0]
    assert "ON CREATE SET target.is_external = true" in query
    assert "MERGE (target:Article {article_id: row.target_article_id})" in query


def test_upsert_relations_matches_existing_source_does_not_merge_it():
    """Source Article PHAI da ton tai truoc do (cung gia dinh voi
    upsert_references/upsert_definitions) - dung MATCH, khong MERGE."""
    client = _make_mock_client()
    rows = [
        {
            "source_article_id": "luat-xyz_dieu-1",
            "target_article_id": "luat-abc_dieu-2",
            "confidence": 0.7,
            "ly_do": "x",
        }
    ]

    upsert_relations(client, "AMENDS", rows)

    query = client.run.call_args[0][0]
    assert "MATCH (source:Article {article_id: row.source_article_id})" in query


def test_upsert_relations_sets_confidence_and_ly_do():
    client = _make_mock_client()
    rows = [
        {
            "source_article_id": "luat-xyz_dieu-1",
            "target_article_id": "luat-abc_dieu-2",
            "confidence": 0.7,
            "ly_do": "x",
        }
    ]

    upsert_relations(client, "AMENDS", rows)

    query = client.run.call_args[0][0]
    assert "r.confidence = row.confidence" in query
    assert "r.ly_do = row.ly_do" in query


def test_upsert_relations_empty_rows_does_not_call_neo4j():
    client = _make_mock_client()
    upsert_relations(client, "AMENDS", [])
    client.run.assert_not_called()


def test_upsert_relations_rejects_invalid_relationship_type():
    """Whitelist co dinh (AMENDS/SUPERSEDES/CONFLICTS_WITH) - relationship_type
    la INPUT tu caller (co the sai do loi lap trinh o scripts/extract_relations.py),
    khong duoc am tham chay Cypher sai/rong."""
    client = _make_mock_client()
    with pytest.raises(ValueError):
        upsert_relations(client, "FOO", [{"source_article_id": "a", "target_article_id": "b"}])
    client.run.assert_not_called()
