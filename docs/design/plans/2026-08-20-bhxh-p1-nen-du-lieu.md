# BHXH Phase 1 — Nền dữ liệu temporal-first — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nạp được văn bản BHXH (crawl từ vbpl.vn) vào graph Neo4j với đầy đủ metadata hiệu lực, sẵn sàng cho retrieval.

**Architecture:** Giữ nguyên engine hiện có (`app/extraction`, `app/graph_store`, `app/ingest`). Thêm một adapter parse nguồn vbpl (HTML → `ParsedDocument`) và mở rộng đường ghi Document để mang các field hiệu lực đã được engine dự trù sẵn (`ngay_hieu_luc` — xem docstring `upsert_document`). Không đụng tầng retrieval/serving ở phase này.

**Tech Stack:** Python 3, Neo4j (`app/graph_store/neo4j_client.py`), pytest, **Playwright** (headless) cho crawler — vbpl.vn là Next.js RSC render bằng JS, `requests` thuần KHÔNG lấy được text (xác nhận ở Task 1, xem `tests/fixtures/bhxh/vbpl-source-notes.md`).

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

> **Cập nhật (Ruling 1):** input KHÔNG phải HTML thô. Crawler (Task 5, Playwright) trả về **text đã render** của tab "Nội dung" và text tab "Thuộc tính". Task 2 parse từ text đó, không dùng BeautifulSoup selector.

**Interfaces:**
- Consumes: `structure_parser.parse_document(text, fallback_doc_id)`, dataclass `ParsedDocument`; fixture text `tests/fixtures/bhxh/luat-bhxh-2024-excerpt.txt`.
- Produces: `parse_vbpl_content(noi_dung_text: str, thuoc_tinh_text: str = "") -> VbplDoc` với `VbplDoc(parsed: ParsedDocument, so: str, nam: str, ma_hieu: str, ngay_hieu_luc: str | None, ngay_het_hieu_luc: str | None)`. Ngày hiệu lực lấy từ `thuoc_tinh_text` ("Ngày có hiệu lực") HOẶC từ câu mở đầu trong `noi_dung_text` ("có hiệu lực kể từ ngày 01 tháng 7 năm 2025"); chuẩn hóa ISO `YYYY-MM-DD`; `None` nếu không có.

- [ ] **Step 1: Viết test đỏ** — parse text đã render

```python
# tests/extraction/test_vbpl_parser.py
from pathlib import Path
from app.extraction.vbpl_parser import parse_vbpl_content

FIX = Path(__file__).parent.parent / "fixtures" / "bhxh" / "luat-bhxh-2024-excerpt.txt"

def test_extracts_effective_date_and_articles():
    doc = parse_vbpl_content(FIX.read_text(encoding="utf-8"))
    assert doc.ngay_hieu_luc == "2025-07-01"      # từ câu "có hiệu lực kể từ ngày 01 tháng 7 năm 2025"
    assert doc.parsed.articles or doc.parsed.chapters  # tách được Điều 1, Điều 2
```

- [ ] **Step 2: Chạy để xác nhận đỏ**

Run: `pytest tests/extraction/test_vbpl_parser.py -v`
Expected: FAIL (`ModuleNotFoundError: app.extraction.vbpl_parser`)

- [ ] **Step 3: Viết `vbpl_parser.py` tối thiểu** — regex lấy `so/nam/ma_hieu` từ số hiệu (vd "41/2024/QH15"); lấy ngày hiệu lực từ `thuoc_tinh_text` hoặc câu mở đầu, đổi "ngày DD tháng MM năm YYYY" và "DD/MM/YYYY" → ISO; đưa `noi_dung_text` qua `parse_document()`. Trả `VbplDoc`.
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

> **Cập nhật (Ruling 2):** theo pattern `tests/graph_store/test_upsert.py` — **mock `Neo4jClient.run`** và assert Cypher+params GỬI ĐI (KHÔNG chạm Neo4j thật, KHÔNG có fixture `neo4j_client`).

- [ ] **Step 1: Viết test đỏ** — mock, kiểm params hiệu lực được gửi

```python
# tests/graph_store/test_temporal_upsert.py
from unittest.mock import MagicMock
from app.graph_store.upsert import upsert_document
from app.extraction.doc_identity import DocIdentity
from app.extraction.structure_parser import parse_document

def test_document_query_sends_effective_fields():
    client = MagicMock()
    parsed = parse_document("Điều 1. Phạm vi.\n1. Nội dung.", fallback_doc_id="41_2024_luat")
    ident = DocIdentity(doc_id="41_2024_luat", so_hieu="41/2024/QH15", loai_vb="Luật",
                        title="Luật 41/2024/QH15", ngay_hieu_luc="2025-07-01",
                        ngay_het_hieu_luc=None, trang_thai="active", che_do=["huu_tri"])
    upsert_document(client, parsed, batch_id="t3", identity=ident)
    # Câu Document (call đầu tiên) phải mang params hiệu lực + query chứa field mới
    q, kwargs = client.run.call_args_list[0].args[0], client.run.call_args_list[0].kwargs
    assert "ngay_hieu_luc" in q and "trang_thai" in q and "che_do" in q
    assert kwargs["ngay_hieu_luc"] == "2025-07-01" and kwargs["trang_thai"] == "active"
    assert kwargs["che_do"] == ["huu_tri"]
```

- [ ] **Step 2: Chạy để xác nhận đỏ** — `python -m pytest tests/graph_store/test_temporal_upsert.py -v` → FAIL (`DocIdentity.__init__` thiếu tham số).
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

- [ ] **Step 1: Viết test đỏ** (mock pattern — Ruling 2)

```python
def test_supersedes_sends_merge_query():
    from unittest.mock import MagicMock
    from app.graph_store.upsert import upsert_supersedes
    client = MagicMock()
    upsert_supersedes(client, "41_2024_luat_dieu_70", "58_2014_luat_dieu_60")
    q = client.run.call_args.args[0]
    kwargs = client.run.call_args.kwargs
    assert "SUPERSEDES" in q and "MERGE" in q
    assert kwargs["new"] == "41_2024_luat_dieu_70" and kwargs["old"] == "58_2014_luat_dieu_60"
```

- [ ] **Step 2: Chạy đỏ** → FAIL (`ImportError upsert_supersedes`).
- [ ] **Step 3:** Viết `upsert_supersedes` gọi `client.run(q, new=new_article_id, old=old_article_id)` với `q = "MERGE (a:Article {article_id:$new}) MERGE (b:Article {article_id:$old}) MERGE (a)-[:SUPERSEDES]->(b)"`.
- [ ] **Step 4: Chạy xanh.** Thêm test: query dùng toàn MERGE (không CREATE) ⇒ idempotent theo cấu trúc.
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
