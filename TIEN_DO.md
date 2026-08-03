# 📓 GRAPH RAG LEGAL QA — NHẬT KÝ TIẾN ĐỘ & HƯỚNG DẪN TIẾP TỤC
> Cập nhật: **2026-08-03**. Mở file này đầu tiên là biết đang ở đâu và làm gì tiếp.
> Mọi điểm chờ người quyết định đã gom về file `CHECKLIST-GRAPHRAG-DUYET.md`.

## 0. 🎨 ĐỢT 1 — Brainstorming & Spec-driven setup (2026-08-03)

- [x] Brainstorm hướng đi: đối chiếu 10 pattern RAG, chọn Graph RAG làm bước đệm trước Agentic RAG (lý do: legal domain có cấu trúc trích dẫn tự nhiên, hợp graph; Agentic RAG để dành cho quy mô doanh nghiệp sau này)
- [x] So sánh 3 approach xây Graph RAG (Microsoft GraphRAG / custom dựa trên citation structure / LightRAG) — chọn custom, lý do chi phí index thấp hơn Microsoft GraphRAG, tận dụng đúng đặc thù văn bản luật VN
- [x] Chọn Neo4j Community làm graph store (ADR-001 trong `research.md`) thay vì NetworkX — ưu tiên giá trị CV/demo trực quan
- [x] Thiết kế graph schema (6 node type, 7 relationship type) — `specs/001-graph-rag-core/data-model.md`
- [x] Viết `constitution.md`, `spec.md`, `plan.md`, `tasks.md`, `research.md`, `quickstart.md`, `checklists/requirements.md`

## 0b. ✅ ĐỢT 2 — Chốt các điểm treo, mở rộng quy mô (2026-08-03)

- [x] B1: `MAX_HOP=2` — chốt. B2: Article node rút gọn + `chroma_id` (không lưu full text Neo4j) — chốt.
- [x] B3: AMENDS/SUPERSEDES/CONFLICTS_WITH làm ngay ở P1 (không dời P2) — cập nhật `spec.md` FR-003, `data-model.md`.
- [x] B4: Claude soạn tập câu hỏi multi-hop (SC-001), Khang duyệt lại sau — cập nhật Assumptions.
- [x] C1: **Quy mô tăng lên toàn bộ 67k văn bản** (từ đề xuất ban đầu 2k/10k) — thêm User Story 4 + FR-008 (batch/savepoint) + SC-005, ADR-002 trong `research.md`, task T009b-d trong `tasks.md`.
- [x] C2: Không làm UI Streamlit — API + Neo4j Browser là đủ. Cập nhật `plan.md`, `spec.md` Assumptions.
- [x] Constitution nâng version 1.0 → 1.1 (MINOR — thêm quy mô/hạ tầng, không đổi nguyên tắc gốc).
- [x] Icon hóa toàn bộ heading trong các file .md cho dễ đọc.
- [ ] **Còn lại (theo dõi, không chặn)**: D1 — đo throughput thật để chốt `INGEST_BATCH_SIZE`; D2 — kiểm tra baseline Hybrid+Reranker cũ có số liệu ở 67k chưa, nếu chưa phải đo lại trước khi so sánh ở Phase 4.
- [ ] **Sẵn sàng bắt đầu**: `tasks.md` Phase 1 (T001) — khởi tạo code thật (hiện tại mới có `.specify/` + `specs/` + docs, chưa có `app/` code)

**Việc tiếp theo**: đọc `specs/001-graph-rag-core/tasks.md` Phase 1, bắt đầu từ T001. Nếu dùng subagent triển khai, đưa cả `constitution.md` (v1.1) + `plan.md` + `tasks.md` làm context. Lưu ý D1/D2 khi tới Foundational/Phase 4.

## 1. 🏗️ ĐỢT 3 — Triển khai Phase 1 + Phase 2 Foundational (2026-08-03)

- [x] Git repo khởi tạo, branch `001-graph-rag-core`, quy trình subagent-driven-development (implementer + reviewer riêng mỗi task, fix inline khi review tìm lỗi).
- [x] Phase 1 Setup hoàn tất: T001 (scaffold), T002 (docker-compose Neo4j), T003 (fetch script tái dùng, xác nhận mặc định đã là full 67k), T004 (`app/config.py`).
- [x] Phase 2 Foundational hoàn tất: T005 (`neo4j_client.py`), T006-T007 (`reference_extractor.py` + `slugify.py`, TDD đúng nghĩa — test trước, xác nhận red, rồi implement), T008 (`structure_parser.py`), T009 (`upsert.py`, idempotent + external-reference placeholder), T009b-d (`state_store.py` savepoint atomic, `app/ingest.py` batch CLI, test resume-after-crash mô phỏng bằng mock).
- [x] 83/83 test pass. Review tìm và fix inline nhiều lỗi thật đáng chú ý: thiếu `;` verbatim Cypher, doc-type Bộ luật/Thông tư/Nghị quyết bị gán nhầm trích dẫn nội bộ, Chapter nuốt mất Article khi không có dòng tiêu đề riêng, lệch `article_id` giữa 2 module khi số điều có số 0 ở đầu, `doc_id` trùng khi thiếu tiêu đề, và quan trọng nhất: **checkpoint không ghi `batch_size` → đổi batch size giữa 2 lần chạy sẽ âm thầm bỏ sót hàng nghìn văn bản khi resume** (đã fix: phát hiện + từ chối chạy).
- [x] **Điểm dừng theo hiến pháp — ĐÃ VERIFY với dữ liệu thật**: fetch 447 văn bản mẫu thật (Zalo corpus) → phát hiện **corpus thật KHÔNG phải Document→Chương→Điều→Khoản như giả định ban đầu** — mỗi file thực ra là **1 Điều đơn lẻ** (title = "Điều N. ..."), `Chương` chỉ xuất hiện như trích dẫn trong nội dung, không bao giờ là heading thật. Đã sửa: thêm `parse_article_chunk()` (giữ nguyên `parse_document()` cũ), `app/ingest.py` lấy `doc_id`/số điều từ tên file. Cũng phát hiện + sửa 1 bug hạ tầng thật: `docker-compose.yml` dùng `env_file: .env` khiến Neo4j image tự hiểu nhầm biến app (`NEO4J_URI`) thành config server → crash loop; đã xóa `env_file`.
- [x] **Test kill -9 THẬT (không mock)**: chạy `python -m app.ingest data/raw --limit 60 --batch-size 5` trên Neo4j thật, `kill -9` tiến trình thật giữa batch 6/12 → checkpoint đúng `last_completed_batch: 5` → chạy lại y nguyên lệnh → log "resume từ batch 6/12" → hoàn tất, **60 Article thật = đúng 60 file, 0 document trùng, 0 article trùng**, 15 external-reference placeholder tạo đúng cơ chế. ✔ SC-005/FR-008/User Story 4 xác nhận đầy đủ.
- [x] Đã dọn sạch Neo4j + checkpoint sau test, sẵn sàng cho Khang tự chạy ingest thật quy mô lớn hơn.
- [ ] **Việc tiếp theo (Khang tự chạy)**: xem hướng dẫn cuối phiên chat cho lệnh cụ thể — fetch full 67k (khá lâu, tải toàn bộ qua HuggingFace) rồi `python -m app.ingest data/raw`. Sau khi ingest xong mới sang Phase 3 (`tasks.md` T010+, User Story 1 — trả lời câu hỏi multi-hop).
