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
- [x] **Việc tiếp theo (Khang tự chạy)**: xem hướng dẫn cuối phiên chat cho lệnh cụ thể — fetch full 67k (khá lâu, tải toàn bộ qua HuggingFace) rồi `python -m app.ingest data/raw`. Sau khi ingest xong mới sang Phase 3 (`tasks.md` T010+, User Story 1 — trả lời câu hỏi multi-hop).

## 2. 🔍 ĐỢT 4 — Ingest full thật + Phase 3 User Story 1 (2026-08-04)

- [x] Khang tự chạy fetch full + ingest 61,068 văn bản thật thành công (61,068 file → 60,679 Article/3,203 Document/165,699 Clause/37,875 REFERENCES — 389 file trùng do corpus gốc không nhất quán encoding, đã audit 100% an toàn giống hệt nội dung).
- [x] **T009e** 🆕: pre-flight collision detection trong `app/ingest.py` — dedup tự động khi nội dung giống hệt, dừng + báo lỗi rõ khi nội dung khác nhau (bảo vệ các lần ingest sau, xem ADR-003 `research.md`).
- [x] **T009f** 🆕 (gap phát hiện khi bắt đầu Phase 3 — không task nào ghi embedding vào Chroma): `app/retrieval/embedder.py` + `scripts/backfill_embeddings.py`. Phát hiện + fix 1 bug thật nghiêm trọng trước khi chạy full: Chroma collection tạo thiếu `hnsw:space=cosine` (mặc định L2) → sẽ làm `SIMILARITY_THRESHOLD` vô nghĩa. Bắt được sau ~96 Article test, dọn sạch, sửa, chạy lại đúng.
- [x] Benchmark thật: ~1.6s/Article trên CPU (không có GPU) → full 60k ước tính ~27h. Theo quyết định của Khang, chỉ backfill subset ~3000 Article trước để verify T010+, full 60k để sau (script resumable, có thể tiếp tục bất cứ lúc nào bằng lệnh y nguyên).
- [x] **T010** `retrieval/entry_point.py` — vector search Chroma, tự verify công thức distance→similarity (`1 - distance`) bằng smoke test thật trên chromadb thật, không đoán.
- [x] **T011 + T015** `retrieval/traversal.py` — BFS thủ công (không dùng Cypher variable-length pattern) để chống lặp vô hạn đúng yêu cầu spec. Review bắt lỗi thật: query `DEFINES` bị ràng buộc `(b:Article)` nhưng `DEFINES` trỏ tới `Term` — sẽ không bao giờ khớp dù T012 có populate sau. Đã sửa: phân loại đúng Article/Term, thêm `visited_term_ids`.
- [x] **T014** `serving/api.py` (`POST /chat`) — nối `entry_point` + `traversal` + Ollama thật (`/api/generate`, đã verify shape API thật). Xử lý đúng 3 nhóm content (embedded/chưa embedded/external), không bịa nội dung. Review bắt lỗi thật: `citation_path` thiếu field `is_preview` (người dùng không biết trích dẫn nào chỉ là preview rút gọn) — đã sửa.
- [x] **✅ Checkpoint Phase 3 đạt được — test thật qua API** (không mock): hỏi "Chế độ tuần tra canh gác đê khi báo động lũ cấp I được quy định như thế nào?" → trả lời đúng nội dung Điều 8 Thông tư 01/2009/TT-BNNPTNT (đối chiếu thủ công với Neo4j gốc, khớp chính xác), multi-hop traversal thật Điều 8 → Điều 1 → Điều 4 qua REFERENCES, citation_path/edges_used đúng.
- [ ] **Còn lại Phase 3**: T012 (`term_extractor.py` — DEFINES/USES_TERM), T013 (`relation_llm.py` — AMENDS/SUPERSEDES/CONFLICTS_WITH), T016 (bộ câu hỏi eval — cần Khang duyệt). Backfill embedding subset ~3000 Article đang chạy nền lúc kết thúc phiên này — kiểm tra `.state`/log hoặc chạy lại lệnh cũ để tiếp tục/mở rộng ra full 60k khi sẵn sàng.
