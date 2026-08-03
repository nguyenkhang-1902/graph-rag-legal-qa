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
