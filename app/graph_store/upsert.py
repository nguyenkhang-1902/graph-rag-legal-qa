"""upsert.py (T009): ghi cac cau truc da parse (structure_parser.py, T008)
va cac trich dan da extract (reference_extractor.py, T007) vao Neo4j qua
Neo4jClient (T005).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): "ghi cau truc da
parse vao Neo4j" - khong chua logic regex/extraction (da xong o cac module
khac), khong dieu phoi vong lap batch/ingest (do la app/ingest.py, T009d -
cac ham o day la building block ma no goi cho tung van ban).

Moi node/relationship deu duoc ghi bang MERGE (khong bao gio CREATE) de dam
bao idempotent - goi lai ham nay nhieu lan voi cung du lieu KHONG duoc tao
node/canh trung lap (research.md ADR-002 - batch ingest + savepoint resume
phu thuoc hoan toan vao tinh chat nay).

Tat ca Cypher deu tham so hoa qua Neo4jClient.run(query, **params)
(constitution Dieu 1) - khong bao gio string-format gia tri vao query. Nhan
node (Document/Chapter/Article/Clause) va ten thuoc tinh id dung de MATCH
node cha la MOT PHAN CO DINH cua cau truc query (khong phai gia tri tu du
lieu nguoi dung), nen viet literal vao chuoi query nhu binh thuong - chi
GIA TRI (id, ten, noi dung...) moi luon di qua $param.
"""
from __future__ import annotations

from app.extraction.doc_identity import DocIdentity
from app.extraction.reference_extractor import ExtractedReference
from app.extraction.structure_parser import Article, Chapter, ParsedDocument
from app.graph_store.neo4j_client import Neo4jClient

_DOCUMENT_QUERY = (
    "MERGE (d:Document {doc_id: $doc_id}) "
    "SET d.title = $title, d.batch_id = $batch_id"
)

# Bien the T025: ghi them so_hieu/loai_vb khi caller truyen `DocIdentity`
# (suy tu TEN FILE - xem app/extraction/doc_identity.py). PHAI la mot query
# RIENG, khong phai them "SET d.so_hieu = $so_hieu" vao _DOCUMENT_QUERY voi
# gia tri null: mot lan chay KHONG co identity se AM THAM XOA so_hieu/
# loai_vb da ghi dung o lan chay truoc (SET x = null trong Cypher = xoa
# thuoc tinh). Xem test_upsert_document_without_identity_does_not_touch_...
_DOCUMENT_WITH_IDENTITY_QUERY = (
    "MERGE (d:Document {doc_id: $doc_id}) "
    "SET d.title = $title, d.batch_id = $batch_id, "
    "d.so_hieu = $so_hieu, d.loai_vb = $loai_vb, "
    "d.ngay_hieu_luc = $ngay_hieu_luc, d.ngay_het_hieu_luc = $ngay_het_hieu_luc, "
    "d.trang_thai = $trang_thai, d.che_do = $che_do"
)

_CHAPTER_QUERY = (
    "MATCH (parent:Document {doc_id: $doc_id}) "
    "MERGE (c:Chapter {chapter_id: $chapter_id}) "
    "SET c.so_chuong = $so_chuong, c.tieu_de = $tieu_de "
    "MERGE (c)-[:BELONGS_TO]->(parent)"
)

# Hai bien the cua Article MERGE: owner la Chapter hoac Document truc tiep
# (Chapter la optional trong phan cap - xem ParsedDocument docstring trong
# structure_parser.py). is_external = false duoc SET VO DIEU KIEN (KHONG
# phai ON CREATE) - day la diem mau chot de "nang cap" mot external
# reference placeholder (tao boi upsert_references, xem duoi) thanh Article
# that neu van ban chua no sau nay duoc ingest that su (xem task-2d-brief.md,
# muc "Ordering guarantee to preserve" - crux cua ca thiet ke placeholder).
_ARTICLE_UNDER_CHAPTER_QUERY = (
    "MATCH (parent:Chapter {chapter_id: $parent_id}) "
    "MERGE (a:Article {article_id: $article_id}) "
    "SET a.so_dieu = $so_dieu, a.noi_dung_preview = $noi_dung_preview, "
    "a.is_external = false "
    "MERGE (a)-[:BELONGS_TO]->(parent)"
)

_ARTICLE_UNDER_DOCUMENT_QUERY = (
    "MATCH (parent:Document {doc_id: $parent_id}) "
    "MERGE (a:Article {article_id: $article_id}) "
    "SET a.so_dieu = $so_dieu, a.noi_dung_preview = $noi_dung_preview, "
    "a.is_external = false "
    "MERGE (a)-[:BELONGS_TO]->(parent)"
)

_CLAUSE_QUERY = (
    "MATCH (parent:Article {article_id: $parent_id}) "
    "MERGE (cl:Clause {clause_id: $clause_id}) "
    "SET cl.so_khoan = $so_khoan, cl.noi_dung = $noi_dung "
    "MERGE (cl)-[:BELONGS_TO]->(parent)"
)

_REFERENCE_QUERY = (
    "MATCH (source:Article {article_id: $source_id}) "
    "MERGE (target:Article {article_id: $target_id}) "
    # ON CREATE SET: CHI ap dung khi MERGE nay vua tao node target MOI HOAN
    # TOAN (chua ton tai duoi bat ky dang nao). Neu target da ton tai
    # (Article that tu upsert_document HOAC placeholder tu mot lan goi
    # upsert_references truoc do), KHONG duoc ghi de is_external - dung
    # theo "external reference placeholder" trong data-model.md.
    "ON CREATE SET target.is_external = true "
    "MERGE (source)-[r:REFERENCES]->(target) "
    # ON CREATE cho raw_text: neu cung cap nguon->dich duoc trich dan nhieu
    # lan trong mot van ban voi raw_text khac nhau, giu lan xuat hien DAU
    # TIEN la du - luu moi lan la phuc tap khong can thiet cho P1 (xem brief).
    "ON CREATE SET r.raw_text = $raw_text"
)


# DEFINES/USES_TERM (T012 hoan thien): batch qua UNWIND (khong phai N loi
# goi client.run rieng le nhu upsert_references) - quy mo 60k+ Article,
# cung ly do backfill_embeddings.py's _update_chroma_ids dung UNWIND (xem
# TIEN_DO.md).
_UPSERT_TERMS_AND_DEFINES_QUERY = (
    "UNWIND $rows AS row "
    "MERGE (t:Term {term_id: row.term_id}) "
    # ON CREATE SET (khong phai SET vo dieu kien): neu nhieu Article cung
    # dinh nghia mot term_id trung nhau (hiem nhung co the), giu dinh
    # nghia cua lan MERGE DAU TIEN tao node - cung triet ly voi raw_text
    # trong _REFERENCE_QUERY o tren.
    "ON CREATE SET t.ten_thuat_ngu = row.ten_thuat_ngu, "
    "t.dinh_nghia = row.dinh_nghia "
    "WITH t, row "
    "MATCH (a:Article {article_id: row.article_id}) "
    "MERGE (a)-[:DEFINES]->(t)"
)

# Term PHAI da ton tai (tao boi upsert_definitions o tren, cung lan chay
# hoac lan chay truoc) - dung MATCH (khong phai MERGE) cho Term o day, giu
# dung nguyen tac "khong tu bia Term moi tu USES_TERM" (data-model.md:
# USES_TERM la Article dung LAI thuat ngu DA duoc dinh nghia, khong phai
# nguon tao Term).
_UPSERT_USES_TERM_QUERY = (
    "UNWIND $rows AS row "
    "MATCH (a:Article {article_id: row.article_id}) "
    "MATCH (t:Term {term_id: row.term_id}) "
    "MERGE (a)-[:USES_TERM]->(t)"
)


# AMENDS/SUPERSEDES/CONFLICTS_WITH (T013, app/extraction/relation_llm.py):
# Cypher relationship TYPE khong tham so hoa duoc qua $param - MOT query
# rieng cho MOI loai, sinh tu whitelist CO DINH (_RELATION_TYPES) tai thoi
# diem module load, khong bao gio tu gia tri chay-thoi-gian/du lieu nguoi
# dung (dung nguyen tac "chi gia tri di qua $param" cua module docstring,
# type la MOT PHAN CO DINH cua cau truc query giong nhan node). Cung co
# che external reference placeholder voi _REFERENCE_QUERY (ON CREATE SET
# is_external = true) - target co the ngoai pham vi corpus da ingest.
# Source PHAI da ton tai (MATCH, khong MERGE - cung gia dinh voi
# upsert_definitions/upsert_references). confidence/ly_do dung SET (khong
# phai ON CREATE SET) - LLM co the duoc chay lai voi ket qua tot hon sau
# nay, muon lan chay MOI NHAT thang the thay vi giu vinh vien gia tri lan
# dau (khac voi raw_text/dinh_nghia - noi dung do la trich dan/dinh nghia
# GOC khong doi, con confidence/ly_do la danh gia CO THE cai thien).
_RELATION_TYPES = ("AMENDS", "SUPERSEDES", "CONFLICTS_WITH")
_UPSERT_RELATION_QUERIES: dict[str, str] = {
    relationship_type: (
        "UNWIND $rows AS row "
        "MATCH (source:Article {article_id: row.source_article_id}) "
        "MERGE (target:Article {article_id: row.target_article_id}) "
        "ON CREATE SET target.is_external = true "
        f"MERGE (source)-[r:{relationship_type}]->(target) "
        "SET r.confidence = row.confidence, r.ly_do = row.ly_do"
    )
    for relationship_type in _RELATION_TYPES
}


def upsert_definitions(client: Neo4jClient, rows: list[dict]) -> None:
    """Ghi mot batch dinh nghia (data-model.md DEFINES: Article -> Term)
    trong MOT cau UNWIND duy nhat.

    Moi `row` trong `rows`: {"article_id", "term_id", "ten_thuat_ngu",
    "dinh_nghia"} - khop truc tiep voi `ExtractedDefinition`
    (term_extractor.py, T012) cong them `article_id` nguon (module do
    khong biet article_id - chi tra ve dinh nghia tu mot doan text don le,
    xem term_extractor.py docstring, Dieu 5).

    GIA DINH: moi `article_id` la mot Article DA duoc ghi that su truoc do
    (cung gia dinh voi `upsert_references`) - ham nay chi MATCH node
    Article (khong MERGE).

    `rows` rong -> khong goi Neo4j (tranh round-trip lang phi).
    """
    if not rows:
        return
    client.run(_UPSERT_TERMS_AND_DEFINES_QUERY, rows=rows)


def upsert_term_usages(client: Neo4jClient, rows: list[dict]) -> None:
    """Ghi mot batch canh USES_TERM (data-model.md: Article -> Term) trong
    MOT cau UNWIND duy nhat.

    Moi `row` trong `rows`: {"article_id", "term_id"} - khop voi
    `TermUsage.term_id` (term_extractor.py) cong `article_id` nguon.

    GIA DINH: ca Article VA Term da ton tai truoc do (Term duoc tao boi
    `upsert_definitions`, PHAI chay truoc trong cung mot lan orchestration
    - xem scripts/extract_terms.py) - ham nay chi MATCH ca hai, khong MERGE
    Term moi.

    `rows` rong -> khong goi Neo4j.
    """
    if not rows:
        return
    client.run(_UPSERT_USES_TERM_QUERY, rows=rows)


def upsert_relations(
    client: Neo4jClient, relationship_type: str, rows: list[dict]
) -> None:
    """Ghi mot batch canh AMENDS/SUPERSEDES/CONFLICTS_WITH (data-model.md,
    T013 - `app/extraction/relation_llm.py`) trong MOT cau UNWIND duy nhat.

    Moi `row`: {"source_article_id", "target_article_id", "confidence",
    "ly_do"} - khop `ExtractedRelation` (relation_llm.py) cong
    `source_article_id` nguon.

    `relationship_type` PHAI la mot trong `_RELATION_TYPES` (AMENDS/
    SUPERSEDES/CONFLICTS_WITH) - raise `ValueError` ro rang neu khong
    (bao ve chong loi lap trinh o caller, khong am tham bo qua/chay Cypher
    sai).

    GIA DINH: `source_article_id` la mot Article DA ton tai truoc do
    (cung gia dinh voi upsert_references/upsert_definitions) - chi MATCH,
    khong MERGE. `target_article_id` co the CHUA ton tai (ngoai pham vi
    corpus da ingest) - dung co che external reference placeholder giong
    upsert_references (ON CREATE SET is_external = true).

    `rows` rong -> khong goi Neo4j.
    """
    if relationship_type not in _UPSERT_RELATION_QUERIES:
        raise ValueError(
            f"relationship_type khong hop le: {relationship_type!r} - "
            f"phai la mot trong {_RELATION_TYPES}"
        )
    if not rows:
        return
    client.run(_UPSERT_RELATION_QUERIES[relationship_type], rows=rows)


def upsert_document(
    client: Neo4jClient,
    parsed: ParsedDocument,
    batch_id: str,
    identity: DocIdentity | None = None,
) -> None:
    """Ghi toan bo phan cap Document -> Chapter (optional) -> Article ->
    Clause (optional) cua mot ParsedDocument (structure_parser.py, T008)
    vao Neo4j.

    `batch_id` la id dot ingest hien tai (phuc vu savepoint resume o
    T009b - khong thuoc pham vi task nay), KHONG phai thuoc tinh cua
    ParsedDocument (structure_parser.py khong biet gi ve khai niem batch),
    nen truyen rieng o day thay vi doc tu `parsed`.

    `identity` (T025, tuy chon): `DocIdentity` suy tu TEN FILE (xem
    app/extraction/doc_identity.py) - khi duoc truyen, ghi them `so_hieu` va
    `loai_vb` cho Document node, va dung `identity.title` (chi danh chuan,
    vd "Thong tu 19/2016/TT-BXD") lam title KHI `parsed.title` rong.
    `parsed.title` khong rong thi THANG (tieu de van xuoi that - neu mot
    ngay nao do co - luon tot hon chi danh sinh ra tu so hieu).

    BHXH-P1-T3: khi co `identity`, cung ghi `ngay_hieu_luc`,
    `ngay_het_hieu_luc`, `trang_thai`, `che_do` tu chinh `identity` (cac
    field nay mac dinh None/"active"/[] tren `DocIdentity` - caller chua co
    du lieu hieu luc that se gui gia tri default do, khong phai bia).

    Khi KHONG truyen `identity`, query dung la `_DOCUMENT_QUERY` cu - KHONG
    gui so_hieu/loai_vb/ngay_hieu_luc/ngay_het_hieu_luc/trang_thai/che_do =
    null (se am tham xoa gia tri dung da ghi truoc do, xem ghi chu tren
    `_DOCUMENT_WITH_IDENTITY_QUERY`).

    Idempotent: goi lai ham nay nhieu lan voi CUNG mot ParsedDocument khong
    tao them node/canh BELONGS_TO trung lap (moi thao tac deu la MERGE,
    khong bao gio CREATE).
    """
    if identity is None:
        client.run(
            _DOCUMENT_QUERY,
            doc_id=parsed.doc_id,
            title=parsed.title,
            batch_id=batch_id,
        )
    else:
        client.run(
            _DOCUMENT_WITH_IDENTITY_QUERY,
            doc_id=parsed.doc_id,
            title=parsed.title or identity.title,
            batch_id=batch_id,
            so_hieu=identity.so_hieu,
            loai_vb=identity.loai_vb,
            ngay_hieu_luc=identity.ngay_hieu_luc,
            ngay_het_hieu_luc=identity.ngay_het_hieu_luc,
            trang_thai=identity.trang_thai,
            che_do=identity.che_do,
        )

    for chapter in parsed.chapters:
        _upsert_chapter(client, chapter, parsed.doc_id)
        for article in chapter.articles:
            _upsert_article(
                client, article, parent_label="chapter", parent_id=chapter.chapter_id
            )
            _upsert_clauses(client, article)

    for article in parsed.articles:
        _upsert_article(
            client, article, parent_label="document", parent_id=parsed.doc_id
        )
        _upsert_clauses(client, article)


def _upsert_chapter(client: Neo4jClient, chapter: Chapter, doc_id: str) -> None:
    client.run(
        _CHAPTER_QUERY,
        doc_id=doc_id,
        chapter_id=chapter.chapter_id,
        so_chuong=chapter.so_chuong,
        tieu_de=chapter.tieu_de,
    )


def _upsert_article(
    client: Neo4jClient, article: Article, *, parent_label: str, parent_id: str
) -> None:
    query = (
        _ARTICLE_UNDER_CHAPTER_QUERY
        if parent_label == "chapter"
        else _ARTICLE_UNDER_DOCUMENT_QUERY
    )
    # `article.full_text` CO CHU DICH khong xuat hien trong params duoi day
    # - xem structure_parser.py Article docstring va task-2d-brief.md:
    # full_text CHI la input cho cac buoc extraction (reference_extractor.py
    # va cac extractor tuong lai), KHONG BAO GIO duoc ghi vao Neo4j
    # (data-model.md: node Article trong graph chi mang noi_dung_preview +
    # chroma_id, "mot nguon su that duy nhat" cho full text la Chroma).
    # `chroma_id` cung CHUA duoc set o day - embedding/Chroma upsert la mot
    # buoc sau, ngoai pham vi T009 (xem brief).
    client.run(
        query,
        parent_id=parent_id,
        article_id=article.article_id,
        so_dieu=article.so_dieu,
        noi_dung_preview=article.noi_dung_preview,
    )


def _upsert_clauses(client: Neo4jClient, article: Article) -> None:
    for clause in article.clauses:
        client.run(
            _CLAUSE_QUERY,
            parent_id=article.article_id,
            clause_id=clause.clause_id,
            so_khoan=clause.so_khoan,
            noi_dung=clause.noi_dung,
        )


def upsert_references(
    client: Neo4jClient, article_id: str, references: list[ExtractedReference]
) -> None:
    """Ghi cac canh REFERENCES tu Article `article_id` (van ban nguon) toi
    cac Article duoc `references` (reference_extractor.py, T007) tro toi.

    GIA DINH: `article_id` la mot Article DA duoc ghi that su (qua
    `upsert_document`) truoc khi ham nay duoc goi - ham nay chi MATCH node
    nguon (khong MERGE), dung theo trat tu goi thuc te (T009d se goi
    upsert_document cho van ban, roi extract_references tren full_text cua
    tung Article, roi upsert_references) - xem brief.

    Voi moi target CHUA ton tai trong graph (o bat ky dang nao), tao mot
    "external reference placeholder" (data-model.md): node Article moi voi
    `is_external = true`, khong co noi_dung_preview/chroma_id. Neu target
    da ton tai (Article that tu upsert_document HOAC placeholder tu mot lan
    goi upsert_references truoc do), gia tri hien co KHONG bi ghi de/flip
    is_external ve true (ON CREATE SET).

    Idempotent: goi lai ham nay voi cung (article_id, references) khong tao
    them Article/REFERENCES trung lap (MERGE, khong bao gio CREATE).
    """
    for reference in references:
        client.run(
            _REFERENCE_QUERY,
            source_id=article_id,
            target_id=reference.target_article_id,
            raw_text=reference.raw_text,
        )
