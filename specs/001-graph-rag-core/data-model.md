# 🕸️ Data Model — Graph RAG Legal QA

**Feature**: `001-graph-rag-core` | **Store**: Neo4j Community

Ký hiệu: `✚` thêm mới (project mới, mọi entity đều ✚) · `⚠` cần verify khi implement · `[CẦN DUYỆT]` chờ Khang quyết.

## 🔵 Node types

| Label | Thuộc tính chính | Hành động | Ghi chú |
|---|---|---|---|
| `Document` | `doc_id` (unique), `title`, `so_hieu`, `loai_vb` (Luật/Nghị định/Thông tư), `ngay_hieu_luc`, `source_file` | ✚ | Gốc phân cấp. `doc_id` là khóa ổn định để upsert khi ingest lại. |
| `Chapter` | `chapter_id`, `so_chuong`, `tieu_de` | ✚ | Không phải văn bản nào cũng có Chapter — optional trong phân cấp. |
| `Article` (Điều) | `article_id` (unique, vd `luat-abc_dieu-5`), `so_dieu`, `noi_dung_preview` (rút gọn ~200 ký tự, chỉ để hiển thị nhanh), `chroma_id` (trỏ full text + embedding trong Chroma) | ✚ | Đơn vị trung tâm — hầu hết retrieval bắt đầu/kết thúc ở đây. ✅ **Đã chốt (2026-08-03)**: KHÔNG lưu full text trong Neo4j — chỉ preview + `chroma_id`. Lý do: một nguồn sự thật duy nhất (Chroma), tránh lệch dữ liệu khi update, Neo4j giữ nhẹ đúng vai trò graph structure. |
| `Clause` (Khoản) | `clause_id`, `so_khoan`, `noi_dung` | ✚ | Chỉ tạo khi văn bản thực sự chia tới khoản — không ép mọi Article phải có Clause con. |
| `Term` | `term_id`, `ten_thuat_ngu`, `dinh_nghia` | ✚ | Định nghĩa chính thức trích từ Article có dạng "... được hiểu là ...". |
| `Organization` | `org_id`, `ten`, `loai` (cơ quan ban hành/thi hành) | ✚ | Thường ít node, dùng để lọc theo cơ quan nếu cần mở rộng sau. |

## 🔗 Relationship types

| Type | From → To | Thuộc tính | Nguồn trích xuất | Ghi chú |
|---|---|---|---|---|
| `BELONGS_TO` | `Article → Chapter`, `Chapter → Document`, `Clause → Article` | — | Rule-based (parse cấu trúc heading) | Quan hệ phân cấp, bắt buộc, độ tin cậy cao. |
| `REFERENCES` | `Article → Article` (có thể khác Document) | `raw_text` (câu chứa trích dẫn gốc, để audit) | Rule-based (regex "Điều X", "khoản Y Điều X ... Luật/Nghị định ...") | Quan hệ cốt lõi cho multi-hop retrieval (User Story 1). |
| `ISSUED_BY` | `Document → Organization` | — | Rule-based (metadata đầu văn bản) | |
| `DEFINES` | `Article → Term` | — | LLM extraction (câu định nghĩa không luôn theo mẫu cố định) | ⚠ verify: fallback rule-based cho mẫu "... được hiểu là ..." trước, chỉ gọi LLM khi rule-based không match, để giảm chi phí. |
| `USES_TERM` | `Article → Term` | — | LLM extraction hoặc string-match tên thuật ngữ đã có trong `Term.ten_thuat_ngu` | String-match trước (rẻ), LLM chỉ dùng khi cần disambiguation. |
| `AMENDS` / `SUPERSEDES` / `CONFLICTS_WITH` | `Article → Article` hoặc `Document → Document` | `confidence`, `ly_do` (tóm tắt LLM sinh ra) | LLM extraction | Quan hệ khó nhất, độ tin cậy thấp hơn — luôn kèm `confidence` để retrieval có thể lọc theo ngưỡng. ✅ **Đã chốt**: làm ngay ở P1, không dời sang P2 (xem `spec.md` FR-003). |

## 🌐 External reference placeholder

Khi `REFERENCES` trỏ tới một Article không có trong corpus đã ingest (văn bản ngoài phạm vi):
- Tạo node `Article` với `article_id` suy từ text trích dẫn, thuộc tính `is_external = true`, `noi_dung = null`.
- Retrieval khi gặp node này: trả về trong citation path nhưng ghi rõ "không có trong corpus đã ingest", không bịa nội dung — tuân Điều 6/Assumption trong `spec.md`.

## ⚡ Index cần tạo (Điều 7 constitution — thiết kế cho quy mô)

```cypher
CREATE CONSTRAINT article_id_unique IF NOT EXISTS FOR (a:Article) REQUIRE a.article_id IS UNIQUE;
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (d:Document) REQUIRE d.doc_id IS UNIQUE;
CREATE INDEX article_chroma_id IF NOT EXISTS FOR (a:Article) ON (a.chroma_id);
CREATE INDEX document_batch_id IF NOT EXISTS FOR (d:Document) ON (d.batch_id);
```

`batch_id` trên `Document` phục vụ ingest theo batch + savepoint ở quy mô 67k văn bản — xem `plan.md` (Ingest checkpoint) và `tasks.md` T009b.

## 🔄 State machine

Không áp dụng cho nội dung pháp luật (không track "đang hiệu lực/hết hiệu lực" theo thời gian ở P1). Có state machine riêng cho **tiến trình ingest** ở quy mô 67k — xem `research.md` (ADR-002 — Batch ingest + savepoint).
