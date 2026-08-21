# BHXH Phase 1 — Nền dữ liệu temporal-first — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nạp được văn bản BHXH (crawl từ vbpl.vn) vào graph Neo4j với đầy đủ metadata hiệu lực, sẵn sàng cho retrieval.

**Architecture:** Giữ nguyên engine hiện có (`app/extraction`, `app/graph_store`, `app/ingest`). Thêm một adapter parse nguồn vbpl (HTML → `ParsedDocument`) và mở rộng đường ghi Document để mang các field hiệu lực đã được engine dự trù sẵn (`ngay_hieu_luc` — xem docstring `upsert_document`). Không đụng tầng retrieval/serving ở phase này.

**Tech Stack:** Python 3, Neo4j (`app/graph_store/neo4j_client.py`), pytest, requests/httpx cho crawler, BeautifulSoup/lxml cho parse HTML.

**Spec:** [docs/design/2026-08-20-bhxh-nld-design.md](../2026-08-20-bhxh-nld-design.md)

## Global Constraints

- **Config-driven:** mọi hằng số/ngưỡng đọc qua `app/config.py`, KHÔNG `os.environ` trực tiếp nơi khác (constitution Điều 4).
- **doc_id = `slugify_doc_name("{so}_{nam}_{ma_hieu}")`**, giữ nguyên leading zero (xem `build_doc_identity`). Đổi doc_id = phải embed lại toàn bộ → không đổi.
- **KHÔNG đoán:** `loai_vb`/`ngay_hieu_luc`/`trang_thai` chỉ set khi có dữ liệu thật từ nguồn; thiếu thì để `None`, không bịa.
- **TDD bắt buộc:** test đỏ trước, code tối thiểu cho xanh, commit nhỏ và thường xuyên.
- **Idempotent ingest:** mọi ghi graph dùng `MERGE`, gọi lại không tạo node/cạnh trùng.
- **Commit message:** tiếng Việt không dấu, prefix `feat(BHXH-P1-Tn):`.

---

## File Structure

| File | Trách nhiệm | Trạng thái |
|---|---|---|
| `tests/fixtures/bhxh/*.html` | HTML thô 2 văn bản mẫu vbpl (fixture cố định) | Tạo (Task 1) |
| `tests/fixtures/bhxh/selectors.md` | Ghi chú selector nguồn vbpl | Tạo (Task 1) |
| `app/extraction/vbpl_parser.py` | HTML vbpl → `ParsedDocument` + metadata hiệu lực | Tạo (Task 2) |
| `app/extraction/doc_identity.py` | Thêm field hiệu lực vào `DocIdentity` | Sửa (Task 3) |
| `app/graph_store/upsert.py` | Query Document mang hiệu lực + quan hệ `SUPERSEDES` | Sửa (Task 3, 4) |
| `scripts/fetch_bhxh_corpus.py` | Crawler 3 chế độ từ vbpl | Tạo (Task 5) |
| `tests/extraction/test_vbpl_parser.py`, `tests/graph_store/test_temporal_upsert.py`, `tests/ingest/test_bhxh_ingest.py` | Test | Tạo |

---

## Task 1: Spike — xác định cấu trúc nguồn vbpl.vn

**Files:**
- Create: `tests/fixtures/bhxh/luat-bhxh-2024.html`, `tests/fixtures/bhxh/nd-huong-dan.html`
- Create: `tests/fixtures/bhxh/selectors.md`

**Đây là task điều tra** (nguồn ngoài, HTML chưa biết) — đầu ra là *sự thật* để các task sau code chính xác, không phải code sản phẩm.

- [ ] **Step 1:** Tải trang văn bản **Luật BHXH 2024 (41/2024/QH15)** trên vbpl.vn (bản "Thuộc tính" + "Toàn văn"). Lưu HTML thô vào `tests/fixtures/bhxh/luat-bhxh-2024.html`.
- [ ] **Step 2:** Tải thêm 1 Nghị định hướng dẫn (bất kỳ trong 3 chế độ), lưu `tests/fixtures/bhxh/nd-huong-dan.html`.
- [ ] **Step 3:** Ghi vào `selectors.md` các selector/vị trí lấy được: **số hiệu**, **loại văn bản**, **ngày ban hành**, **ngày hiệu lực**, **ngày hết hiệu lực (nếu có)**, và cấu trúc HTML của **Chương/Điều/Khoản** trong phần toàn văn. Ghi rõ selector nào KHÔNG có (vd không có ngày hết hiệu lực).
- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/bhxh/
git commit -m "feat(BHXH-P1-T1): fixture 2 van ban mau vbpl + ghi chu selector"
```

**Acceptance:** 2 file HTML + `selectors.md` liệt kê được vị trí của cả 5 trường metadata (hoặc ghi rõ trường nào nguồn không cung cấp).

---

## Task 2: Parser adapter vbpl → ParsedDocument

**Files:**
- Create: `app/extraction/vbpl_parser.py`
- Test: `tests/extraction/test_vbpl_parser.py`

**Interfaces:**
- Consumes: fixtures + selectors từ Task 1; `structure_parser.parse_document(text, fallback_doc_id)`, dataclass `ParsedDocument`.
- Produces: `parse_vbpl_html(html: str) -> VbplDoc` với `VbplDoc(parsed: ParsedDocument, so: str, nam: str, ma_hieu: str, ngay_hieu_luc: str | None, ngay_het_hieu_luc: str | None)`.

- [ ] **Step 1: Viết test đỏ** — trích metadata từ fixture

```python
# tests/extraction/test_vbpl_parser.py
from pathlib import Path
from app.extraction.vbpl_parser import parse_vbpl_html

FIX = Path(__file__).parent.parent / "fixtures" / "bhxh" / "luat-bhxh-2024.html"

def test_extracts_effective_date_and_number():
    doc = parse_vbpl_html(FIX.read_text(encoding="utf-8"))
    assert doc.so == "41"
    assert doc.nam == "2024"
    assert doc.ngay_hieu_luc == "2025-07-01"      # ISO, không đoán nếu thiếu
    assert doc.parsed.articles or doc.parsed.chapters  # có tách được Điều
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

Run: `pytest tests/extraction/test_vbpl_parser.py -v`
Expected: FAIL (`ModuleNotFoundError: app.extraction.vbpl_parser`)

- [ ] **Step 3: Viết `vbpl_parser.py` tối thiểu** — dùng selector từ Task 1: BeautifulSoup lấy metadata, chuẩn hóa ngày về ISO `YYYY-MM-DD` (trả `None` nếu nguồn không có), lấy phần toàn văn → `parse_document()` để ra `ParsedDocument`. Trả `VbplDoc` (dataclass).
- [ ] **Step 4: Chạy để xanh**

Run: `pytest tests/extraction/test_vbpl_parser.py -v`
Expected: PASS

- [ ] **Step 5:** Thêm test cho fixture NĐ (cấu trúc Chương) + case thiếu ngày hết hiệu lực trả `None`. Chạy xanh.
- [ ] **Step 6: Commit**

```bash
git add app/extraction/vbpl_parser.py tests/extraction/test_vbpl_parser.py
git commit -m "feat(BHXH-P1-T2): parser adapter vbpl HTML -> ParsedDocument + metadata hieu luc"
```

---

## Task 3: Mở rộng data model — field hiệu lực trên Document

**Files:**
- Modify: `app/extraction/doc_identity.py` (thêm field vào `DocIdentity`)
- Modify: `app/graph_store/upsert.py:232` (`upsert_document` + `_DOCUMENT_WITH_IDENTITY_QUERY`)
- Test: `tests/graph_store/test_temporal_upsert.py`

**Interfaces:**
- Consumes: `Neo4jClient.run`, `DocIdentity`, `_DOCUMENT_WITH_IDENTITY_QUERY`.
- Produces: `DocIdentity` có thêm `ngay_hieu_luc: str | None`, `ngay_het_hieu_luc: str | None`, `trang_thai: str` (`"active"`/`"superseded"`), `che_do: list[str]`; `upsert_document(...)` ghi các field này lên Document node.

- [ ] **Step 1: Viết test đỏ** — ghi rồi đọc lại field hiệu lực

```python
# tests/graph_store/test_temporal_upsert.py
from app.graph_store.neo4j_client import Neo4jClient
from app.graph_store.upsert import upsert_document
from app.extraction.doc_identity import DocIdentity
from app.extraction.structure_parser import parse_document

def test_document_stores_effective_dates(neo4j_client: Neo4jClient):
    parsed = parse_document("Điều 1. Phạm vi.\n1. Nội dung.", fallback_doc_id="41_2024_luat")
    ident = DocIdentity(doc_id="41_2024_luat", so_hieu="41/2024/QH15", loai_vb="Luật",
                        title="Luật 41/2024/QH15", ngay_hieu_luc="2025-07-01",
                        ngay_het_hieu_luc=None, trang_thai="active", che_do=["huu_tri"])
    upsert_document(neo4j_client, parsed, batch_id="t3", identity=ident)
    row = neo4j_client.run(
        "MATCH (d:Document {doc_id:$id}) RETURN d.ngay_hieu_luc AS hl, d.trang_thai AS tt, d.che_do AS cd",
        id="41_2024_luat")[0]
    assert row["hl"] == "2025-07-01" and row["tt"] == "active" and "huu_tri" in row["cd"]
```

*(Fixture `neo4j_client` dùng Neo4j test/ephemeral — theo pattern có sẵn trong `tests/`; nếu chưa có, thêm trong conftest bằng `Neo4jClient()` + xóa `MATCH (n{doc_id:...}) DETACH DELETE` cuối test.)*

- [ ] **Step 2: Chạy để xác nhận đỏ** — `pytest tests/graph_store/test_temporal_upsert.py -v` → FAIL (`DocIdentity.__init__` thiếu tham số).
- [ ] **Step 3:** Thêm 4 field mới vào `DocIdentity` (mặc định: `ngay_hieu_luc=None, ngay_het_hieu_luc=None, trang_thai="active", che_do=()`), giữ `build_doc_identity` tương thích ngược. Cập nhật `_DOCUMENT_WITH_IDENTITY_QUERY` set thêm `d.ngay_hieu_luc`, `d.ngay_het_hieu_luc`, `d.trang_thai`, `d.che_do` từ params; truyền các param này trong nhánh `identity is not None` của `upsert_document`.
- [ ] **Step 4: Chạy để xanh** — `pytest tests/graph_store/test_temporal_upsert.py -v` → PASS.
- [ ] **Step 5:** Thêm test hồi quy: gọi `upsert_document` KHÔNG truyền `identity` vẫn chạy (nhánh `_DOCUMENT_QUERY` cũ không đổi). Chạy xanh.
- [ ] **Step 6: Commit**

```bash
git add app/extraction/doc_identity.py app/graph_store/upsert.py tests/graph_store/test_temporal_upsert.py
git commit -m "feat(BHXH-P1-T3): Document node mang metadata hieu luc + che do"
```

---

## Task 4: Quan hệ SUPERSEDES (luật mới → luật cũ)

**Files:**
- Modify: `app/graph_store/upsert.py` (thêm `upsert_supersedes`)
- Test: `tests/graph_store/test_temporal_upsert.py` (bổ sung)

**Interfaces:**
- Produces: `upsert_supersedes(client, new_article_id: str, old_article_id: str) -> None` — tạo `(new)-[:SUPERSEDES]->(old)` bằng MERGE.

- [ ] **Step 1: Viết test đỏ**

```python
def test_supersedes_edge(neo4j_client):
    from app.graph_store.upsert import upsert_supersedes
    neo4j_client.run("MERGE (:Article {article_id:'41_2024_luat_dieu_70'})")
    neo4j_client.run("MERGE (:Article {article_id:'58_2014_luat_dieu_60'})")
    upsert_supersedes(neo4j_client, "41_2024_luat_dieu_70", "58_2014_luat_dieu_60")
    n = neo4j_client.run(
        "MATCH (:Article {article_id:'41_2024_luat_dieu_70'})-[:SUPERSEDES]->"
        "(:Article {article_id:'58_2014_luat_dieu_60'}) RETURN count(*) AS c")[0]["c"]
    assert n == 1
```

- [ ] **Step 2: Chạy đỏ** → FAIL (`ImportError upsert_supersedes`).
- [ ] **Step 3:** Viết `upsert_supersedes` dùng `MERGE (a:Article {article_id:$new}) MERGE (b:Article {article_id:$old}) MERGE (a)-[:SUPERSEDES]->(b)`.
- [ ] **Step 4: Chạy xanh.** Thêm test gọi 2 lần không tạo cạnh trùng (idempotent).
- [ ] **Step 5: Commit**

```bash
git add app/graph_store/upsert.py tests/graph_store/test_temporal_upsert.py
git commit -m "feat(BHXH-P1-T4): quan he SUPERSEDES giua Dieu moi va Dieu cu"
```

---

## Task 5: Crawler 3 chế độ + ingest vào graph

**Files:**
- Create: `scripts/fetch_bhxh_corpus.py`
- Test: `tests/ingest/test_bhxh_ingest.py`

**Interfaces:**
- Consumes: `parse_vbpl_html` (T2), `build_doc_identity`/`DocIdentity` (T3), `upsert_document` (T3), `Neo4jClient`.
- Produces: `ingest_vbpl_doc(client, html: str, che_do: list[str]) -> str` (trả `doc_id`); `fetch_bhxh_corpus(urls: list[str], out_dir: Path)` lưu HTML thô.

- [ ] **Step 1: Viết test đỏ** (dùng fixture, KHÔNG gọi mạng)

```python
# tests/ingest/test_bhxh_ingest.py
from pathlib import Path
from app.graph_store.neo4j_client import Neo4jClient
from scripts.fetch_bhxh_corpus import ingest_vbpl_doc

FIX = Path("tests/fixtures/bhxh/luat-bhxh-2024.html")

def test_ingest_sets_effective_date_on_graph(neo4j_client: Neo4jClient):
    doc_id = ingest_vbpl_doc(neo4j_client, FIX.read_text(encoding="utf-8"), che_do=["huu_tri"])
    hl = neo4j_client.run("MATCH (d:Document {doc_id:$id}) RETURN d.ngay_hieu_luc AS hl",
                          id=doc_id)[0]["hl"]
    assert hl == "2025-07-01"
```

- [ ] **Step 2: Chạy đỏ** → FAIL (`ModuleNotFoundError scripts.fetch_bhxh_corpus`).
- [ ] **Step 3:** Viết `ingest_vbpl_doc`: `parse_vbpl_html` → `build_doc_identity(doc.so, doc.nam, doc.ma_hieu)` rồi gán `ngay_hieu_luc/ngay_het_hieu_luc/che_do` (dùng `dataclasses.replace`) → `upsert_document(client, doc.parsed, batch_id="bhxh", identity=ident)`. Trả `ident.doc_id`.
- [ ] **Step 4: Chạy xanh.**
- [ ] **Step 5:** Viết `fetch_bhxh_corpus(urls, out_dir)` (requests + lưu HTML thô, có `time.sleep` lịch sự đọc từ config) và một hàm `main()` argparse với danh mục URL 3 chế độ (điền từ Task 1). Không test mạng — chỉ smoke chạy tay.
- [ ] **Step 6: Chạy thật 1 lần** trên danh mục nhỏ, kiểm: `MATCH (d:Document) RETURN count(d)` > 0 và mọi Document có `ngay_hieu_luc` khác null (trừ văn bản nguồn thật sự không công bố).
- [ ] **Step 7: Commit**

```bash
git add scripts/fetch_bhxh_corpus.py tests/ingest/test_bhxh_ingest.py
git commit -m "feat(BHXH-P1-T5): crawler + ingest van ban BHXH vao graph co hieu luc"
```

---

## Self-Review (đã chạy)

- **Spec coverage:** §3 corpus → T1,T5; §4 data model temporal → T3,T4; §2 tái dụng engine → T2,T5 dùng `parse_document`/`upsert_document` thật. (§5 Temporal Resolver, §6 Answer Generator, §8 eval → thuộc **plan P2/P3**, không nằm ở đây — có chủ đích.)
- **Placeholder scan:** không có "TODO/xử lý lỗi chung"; các bước thiếu code là task điều tra T1 (đúng bản chất).
- **Type consistency:** `VbplDoc` (T2) → dùng ở T5; `DocIdentity` 4 field mới (T3) → dùng ở T5; `upsert_supersedes` (T4) tên nhất quán.

---

## Điều chỉnh so với design (phát hiện khi đọc code)

- **§6 Answer Generator không phải xây mới:** `app/serving/api.py` đã có `chat()`, `_build_prompt`, `_call_ollama`, `_classify_articles` (Ollama). Plan P3 sẽ **mở rộng** guardrail/citation trên tầng này, không viết lại.
- **`ngay_hieu_luc` đã được engine dự trù** (docstring `upsert_document`) — T3 chỉ hiện thực khe đã chừa.

---

## Bước tiếp theo

Sau khi P1 xanh: viết **plan P2** (Temporal Resolver + eval retrieval trên bộ BHXH), rồi **P3** (guardrail + citation trên `serving/api.py`), **P4** (dọn dẹp Zalo + serving hoàn chỉnh).
