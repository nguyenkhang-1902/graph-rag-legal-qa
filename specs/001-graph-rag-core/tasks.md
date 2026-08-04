# ✅ Tasks: Graph RAG cho văn bản pháp luật

**Input**: `spec.md`, `plan.md`, `data-model.md`, `research.md`
**Ký hiệu**: `[P]` = chạy song song được (khác file, không phụ thuộc) · `[Story]` = US1/US2/US3

## 🏗️ Phase 1: Setup

- **T001** Khởi tạo repo `graph-rag-legal-qa`: cấu trúc thư mục theo `plan.md`, `requirements/base.txt`, `.env.example`
- **T002** [P] `docker-compose.yml` — service Neo4j Community, auth bật qua `.env`, `extra_hosts` cho Ollama trên host (sổ bẫy 12d)
- **T003** [P] Lấy **toàn bộ 67k văn bản** qua `scripts/fetch_zalo_legal_corpus.py` (điều chỉnh `--subset-size` hoặc bỏ giới hạn) — tái sử dụng script từ `rag-chatbot-document-QA`, chỉ đọc không sửa project cũ
- **T004** `app/config.py` — `MAX_HOP=2`, `SIMILARITY_THRESHOLD`, `INGEST_BATCH_SIZE` (giá trị khởi điểm — xem `research.md`), model names, `.env` loader

## 🧱 Phase 2: Foundational (chặn mọi user story)

- **T005** `graph_store/neo4j_client.py` — kết nối, tạo constraint/index từ `data-model.md` (bao gồm `batch_id` cho savepoint)
- **T006** [P] Test trước (Điều 2 constitution): `tests/extraction/test_reference_extractor.py` — case mẫu "Điều 5 Luật ABC", "khoản 2 Điều 5 Nghị định XYZ" → expect đúng `article_id` đích
- **T007** `extraction/reference_extractor.py` — regex REFERENCES, làm cho pass T006
- **T008** [P] `extraction/structure_parser.py` — Document→Chapter→Article→Clause (rule-based, tái dùng pattern `metadata_schema`/`dept_classifier` ý tưởng từ project cũ nếu áp dụng được)
- **T009** `graph_store/upsert.py` — ghi node/relationship idempotent theo `article_id`/`doc_id` (FR-008 phần idempotent)
- **T009b** 🆕 `ingest_checkpoint/state_store.py` — ghi savepoint sau mỗi batch hoàn tất (batch cuối `batch_id` + timestamp), API `get_last_completed_batch()` / `mark_batch_done()`
- **T009c** 🆕 Test resume: `tests/ingest_checkpoint/test_resume_after_crash.py` — mô phỏng kill giữa batch 3, xác nhận `get_last_completed_batch()` trả về batch 2, batch 3 chạy lại không tạo node trùng (User Story 4, AS-1/AS-2)
- **T009d** 🆕 `app/ingest.py` — vòng lặp batch, gọi `mark_batch_done()` sau mỗi batch, đọc `get_last_completed_batch()` khi khởi động để resume
- **T009e** 🆕 (phát hiện lúc chạy checkpoint dữ liệu thật, xem `research.md` ADR-003) `app/ingest.py` — bước pre-flight quét `data_dir` trước batch loop, gom file theo `article_id` trùng: nội dung giống hệt → tự dedup + log INFO; nội dung khác nhau → raise lỗi rõ ràng liệt kê file xung đột, dừng ingest (không đoán, không ghi đè âm thầm)

**Checkpoint**: chạy `app/ingest.py` trên 100 văn bản mẫu (2-3 batch), `kill -9` giữa batch, chạy lại → xác nhận resume đúng (SC-005) trước khi mở rộng ra 67k thật.

**✅ Checkpoint dữ liệu thật đã chạy (2026-08-04)**: fetch 447 mẫu → phát hiện corpus thật là per-Article chunk (không phải Document→Chương→Điều đầy đủ như giả định ban đầu) → sửa bằng `parse_article_chunk()`. Ingest full 61,068 văn bản thật thành công: 60,679 Article/3,203 Document/165,699 Clause/37,875 REFERENCES. Kill -9 thật giữa batch → resume đúng, 0 trùng lặp. Phát hiện 389 file trùng `article_id` do corpus nguồn không nhất quán encoding — đã audit an toàn (100% nội dung giống hệt), T009e xử lý cho các lần ingest sau.

## 🔍 Phase 3: User Story 1 — Trả lời câu hỏi multi-hop (P1) 🎯 MVP

- **T010** [Story:US1] `retrieval/entry_point.py` — vector search Chroma → `article_id`
- **T011** [Story:US1] `retrieval/traversal.py` — Cypher traversal N-hop (mặc định 2, xem `[CẦN DUYỆT]` FR-005), chống lặp vô hạn (edge case trong `spec.md`)
- **T012** [Story:US1] [P] `extraction/term_extractor.py` — DEFINES/USES_TERM, rule-based trước LLM fallback
- **T013** [Story:US1] [P] `extraction/relation_llm.py` — AMENDS/SUPERSEDES/CONFLICTS_WITH, kèm `confidence`
- **T014** [Story:US1] `serving/api.py` — endpoint `/chat`, ghép context từ traversal → Ollama → trả lời + citation path (FR-006)
- **T015** [Story:US1] Xử lý external reference placeholder (edge case `spec.md`) trong `traversal.py`
- **T016** [Story:US1] `scripts/build_multihop_eval_set.py` — sinh ≥30 câu hỏi multi-hop từ corpus thật — **cần Khang duyệt trước khi dùng làm tiêu chí chính thức** (Assumption trong spec.md)

**Checkpoint**: US1 chạy độc lập — hỏi 1 câu multi-hop qua API, nhận câu trả lời có citation path đúng ≥1 case thủ công kiểm tra được.

## 📊 Phase 4: User Story 2 — Benchmark so với Hybrid+Reranker (P1)

- **T017** [Story:US2] `scripts/eval_graph_recall.py` — Recall@k/MRR, cùng phương pháp `eval_zalo_recall.py` project trước
- **T018** [Story:US2] Chạy benchmark trên **toàn bộ 67k**, ghi kết quả vào bảng so sánh (SC-002, SC-003) — nếu baseline Hybrid+Reranker cũ chưa từng đo ở 67k (project trước chỉ đo 2k/10k), chạy lại baseline ở 67k trước khi so sánh, không so lệch quy mô
- **T019** [Story:US2] [P] `scripts/bench_latency.py` — đo p95 latency, đối chiếu baseline project trước

**Checkpoint**: có bảng số liệu Recall@4/MRR/p95 latency Graph RAG vs Hybrid+Reranker **cùng quy mô 67k** — đủ để quyết định có đáng đưa vào README/CV không.

## 🔁 Phase 5: User Story 3 — Ingest tăng dần (P2)

- **T020** [Story:US3] `app/ingest.py` — mode `--incremental`, chỉ xử lý văn bản mới, upsert không phá node cũ (khác với batch/savepoint T009b-d — đây là thêm văn bản MỚI sau khi 67k đã ingest xong)
- **T021** [Story:US3] Test: ingest 1 văn bản mới có REFERENCES trỏ văn bản cũ → verify không tạo node trùng (Acceptance Scenario US3)

**Checkpoint**: SC-004 — ingest 1 văn bản mới < 5 phút, verify bằng đồng hồ thật.

## ✨ Phase 6: Polish

- **T022** [P] README — kiến trúc, kết quả benchmark 67k, hướng dẫn chạy (đồng bộ style với `rag-chatbot-document-QA`)
- **T023** [P] `docs/van-hanh.md` — lệnh Neo4j backup/restore, reset demo data, cách theo dõi tiến độ batch ingest (đọc savepoint)
- **T024** Review lại checklist `CHECKLIST-GRAPHRAG-DUYET.md` mục A — xác nhận không còn điểm treo trước khi coi P1 là "hoàn chỉnh"

## 🔗 Dependencies

```
Setup (T001-T004) → Foundational (T005-T009d) → US1 (T010-T016) → US2 (T017-T019)
                                                                  → US3 (T020-T021, độc lập với US2)
                                                 → Polish (T022-T024, sau khi ít nhất US1+US2 xong)
```

Foundational giờ bao gồm cả cơ chế batch/savepoint (T009b-d) — bắt buộc xong trước khi chạy ingest thật trên 67k. US1 là MVP bắt buộc trước. US2 và US3 độc lập với nhau, có thể làm song song sau khi US1 xong nếu muốn.
