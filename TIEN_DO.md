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
- [x] **T016** `scripts/build_multihop_eval_set.py` (dò ứng viên chuỗi REFERENCES thật, không LLM) + `data/eval/multihop_eval_set.json` (32 câu hỏi thật do Claude soạn từ nội dung thật, đọc trực tiếp — **CHƯA DUYỆT chính thức**, xem `spec.md` Assumptions). Đã xác nhận: 44/44 article_id cần dùng đều đã có embedding, test được ngay. Lưu ý: đây chỉ là bộ kiểm tra định tính cho Phase 3, KHÔNG phải benchmark chính thức (đó là Phase 4 — T017/T018/T019, Recall@k/MRR trên toàn bộ 67k).
- [x] **GPU acceleration**: phát hiện máy có RTX 3050 nhưng torch cài bản CPU-only → cài lại `torch==2.13.0+cu126`, xác nhận CUDA hoạt động (`torch.cuda.is_available()==True`). **Benchmark thật (21 batch, 672 Article, batch-size=32): ~1.44s/Article trên GPU vs ~1.6s/Article trên CPU — chỉ nhanh hơn ~1.1 lần, KHÔNG phải 5-8x như kỳ vọng ban đầu.** Nghi ngờ nguyên nhân: batch-size=32 quá nhỏ để GPU khấu hao hết overhead truyền dữ liệu CPU↔GPU; RTX 3050 (6GB, tier phổ thông) so với CPU 12 luồng đã khá mạnh sẵn. Chưa thử batch-size lớn hơn (64/128) để xác nhận giả thuyết — có thể cải thiện thêm nếu cần.
- [ ] **Còn lại Phase 3**: T012 (`extraction/term_extractor.py` — DEFINES/USES_TERM, rule-based trước, LLM fallback), T013 (`extraction/relation_llm.py` — AMENDS/SUPERSEDES/CONFLICTS_WITH qua Ollama, kèm `confidence`).
- [ ] **Backfill embedding**: đang chạy nền (GPU) lúc kết thúc phiên này, tự resume nếu bị dừng. Kiểm tra tiến độ: `MATCH (a:Article) WHERE a.chroma_id IS NOT NULL RETURN count(a)` trong Neo4j Browser (`localhost:7474`). Muốn tiếp tục/mở rộng full 60k: chạy lại `python -m scripts.backfill_embeddings data/raw` (tự bỏ qua phần đã xong).
- [x] **Khang đã duyệt** 32 câu hỏi trong `data/eval/multihop_eval_set.json` (T016, 2026-08-04) — `CHECKLIST-GRAPHRAG-DUYET.md` mục E1 chốt. Có thể dùng chính thức cho SC-001/Phase 4.

## 3. 🩺 ĐỢT 5 — Chẩn đoán + fix GPU embedding chậm (2026-08-05)

- [x] **Điều tra chênh lệch Article count** (60,679 ghi trong ĐỢT 4 vs 69,106 thực tế trong Neo4j): KHÔNG phải bug/ingest lần 2 — cơ chế "external reference placeholder" (T009e) tạo 8,427 node `:Article {is_external: true}` cho các trích dẫn tới điều luật ngoài phạm vi 61k corpus. 60,679 (thật) + 8,427 (placeholder) = 69,106 khớp chính xác. Backfill chỉ cần tính trên 60,679 (đọc từ file, không quét Neo4j).
- [x] **Chẩn đoán nguyên nhân GPU chỉ nhanh hơn CPU ~1.1x** (thay vì 5-8x kỳ vọng — dùng `systematic-debugging`, `cProfile`, benchmark thật trên mẫu 128 file thật): 2 nguyên nhân xác nhận bằng bằng chứng thật, không phải đoán —
  1. Mỗi lần `SentenceTransformer(...)` khởi tạo, sentence-transformers gọi ~34 HTTP request kiểm tra revision trên HF Hub dù model đã cache đủ (chiếm 6.1/8.76s = 70% thời gian init). Fix: `os.environ.setdefault("HF_HUB_OFFLINE", "1")` trong `app/retrieval/embedder.py` — giảm còn ~2s.
  2. Corpus có độ dài Điều lệch cực mạnh (quét thật 61,069 file: p50=899 ký tự, p90=2,751, p99=7,640, **max=252,967** — file `12_2017_qh14_1.md`). Không sắp xếp → 1 Điều dài lọt vào batch buộc CẢ batch pad theo độ dài đó (batch=64 đo được CHẬM HƠN 7.7 lần/item so với batch=32 do dính outlier ~4737 token). Fix: sort `pending` theo độ dài trước khi chia batch trong `scripts/backfill_embeddings.py`.
- [x] **Xác nhận GPU đạt đúng kỳ vọng sau fix**: benchmark thật (mẫu 128 file, đã sort) — batch=32: GPU 0.090s/item vs CPU 0.77s/item = **nhanh hơn 8.5 lần**; batch=64: GPU 0.126s/item vs CPU 0.91s/item = **nhanh hơn 7.3 lần**. batch=128 **OOM thật** trên RTX 3050 (6GB VRAM) — "Tried to allocate 10.70 GiB".
- [x] **Batch-size cố định không an toàn cho corpus thật** (outlier tới 252,967 ký tự, ~63k token, sẽ bị cắt ở `model.max_seq_length=8192`) — thêm `_group_into_length_aware_batches`/`_batch_cap_for_length` (`scripts/backfill_embeddings.py`): batch-size **thay đổi theo tầng độ dài** thay vì cố định — ≤2,751 ký tự (p90, ~90% corpus): dùng nguyên `--batch-size`/`EMBED_BATCH_SIZE` (mặc định 32); 2,751–7,640 ký tự (p90–p99): cap 8; >7,640 ký tự (p99+, ~610 file, ~1%): cap 1 (xử lý riêng từng file, tránh OOM). Ngưỡng 8/1 là **thận trọng, chưa kiểm chứng thật ở quy mô lớn hơn** — ưu tiên an toàn hơn tối ưu.
- [x] TDD đầy đủ cho cả 2 fix + batching theo tầng: 8 test mới (`tests/retrieval/test_embedder.py`, `tests/test_backfill_embeddings.py`), viết trước-đỏ-sau-xanh đúng quy ước dự án. 155/156 test pass (1 fail không liên quan — `INGEST_BATCH_SIZE=3` set sẵn trong shell của Khang, không phải regression).
- [ ] **Chưa chạy**: backfill full phần còn lại (56,911 Điều thật, = 60,679 − 3,768 đã embed) với 2 fix mới — Khang tự chạy `python -m scripts.backfill_embeddings data/raw` khi sẵn sàng (không cần chỉnh gì thêm, batch-size theo tầng tự động áp dụng).

## 4. 🔤 ĐỢT 6 — T012 term_extractor.py (2026-08-05, làm song song lúc backfill đang chạy)

- [x] **T012 (một phần)** `app/extraction/term_extractor.py` — rule-based DEFINES/USES_TERM, KHÔNG dùng Neo4j (constitution Điều 5), KHÔNG gọi Ollama (chưa làm LLM fallback, xem bên dưới).
  - `extract_definitions_rule_based(text)`: khớp mẫu `"<thuật ngữ>" được hiểu là <định nghĩa>` — CHỈ trích khi thuật ngữ có quotes rõ ràng (thẳng `"` hoặc cong `“ ”`, corpus dùng cả 2). Khảo sát thật 15 file mẫu ngẫu nhiên có chứa "được hiểu là": chỉ 4/15 có thuật ngữ đủ rõ để trích — phần lớn còn lại là mệnh đề mô tả dài không có ranh giới rõ ràng, **cố tình bỏ qua** (rule-based, "sai còn tệ hơn không trích", cùng triết lý `reference_extractor.py`).
  - Bug thật TDD bắt được trước khi implement xong: câu thật nối 2 định nghĩa qua "và" trong cùng câu nhưng chỉ thuật ngữ đầu có quotes (`"Ngày" được hiểu là ngày dương lịch và tháng được hiểu là tháng dương lịch.`) — nếu chỉ cắt ở dấu chấm, định nghĩa đầu sẽ "nuốt" luôn phần không liên quan. Fix: thêm lookahead dừng trước cụm `và ...được hiểu là` tiếp theo.
  - `extract_term_usages_rule_based(text, known_terms)`: string-match case-sensitive + word-boundary — cố tình phân biệt hoa/thường (thuật ngữ định nghĩa thường viết hoa như "Ngày", nhưng từ đó cũng là từ thông dụng viết thường xuất hiện khắp văn bản luật — không phân biệt sẽ bùng nổ false positive USES_TERM vô nghĩa).
  - 16/16 test mới pass (TDD đầy đủ), 171/172 toàn bộ suite (1 fail cũ không liên quan).
- [x] **T012 hoàn chỉnh (phần orchestration)** — thêm `upsert_definitions`/`upsert_term_usages` (batch UNWIND, `app/graph_store/upsert.py`) + `scripts/extract_terms.py` (CLI 2-pass: pass 1 thu thập TOÀN BỘ định nghĩa trong corpus trước, pass 2 mới tính USES_TERM cho mọi Article — tránh bỏ sót khi Article dùng thuật ngữ được định nghĩa ở văn bản khác đọc SAU nó theo thứ tự file). Article tự định nghĩa 1 thuật ngữ KHÔNG bị tính là "dùng lại" chính nó (loại trừ khỏi USES_TERM). Không cần checkpoint/resume (khác backfill embedding) — chỉ regex trên văn bản ngắn, chạy lại từ đầu nếu bị ngắt là an toàn (MERGE-based).
- [x] **Chạy thật trên toàn bộ 60,679 Article** (song song lúc backfill embedding đang chạy, không đụng nhau — khác node/edge type): **10 Term, 10 DEFINES, 525 USES_TERM** — hoàn tất trong ~14s. Kiểm chứng trực tiếp trong Neo4j: 10 Term đều có định nghĩa hợp lý, không rác (vd "Ngày", "Đơn PCT", "Đơn Madrid", "Thường trú tại Việt Nam"...).
- [x] 7/7 test mới cho `extract_terms.py` (TDD), 5/5 test mới cho `upsert_definitions`/`upsert_term_usages`. Tổng 183/184 toàn bộ suite (1 fail cũ không liên quan).
- [ ] **Còn thiếu (không chặn)**: LLM fallback cho câu định nghĩa không có quotes (data-model.md dự tính nhưng chưa làm — rule-based hiện chỉ bắt được 6/60,679 Article có định nghĩa rõ ràng qua quotes; phần lớn "được hiểu là" trong corpus là mệnh đề mô tả dài, không đủ rõ ràng để rule-based trích an toàn). Cần Khang quyết có đáng đầu tư LLM fallback hay chấp nhận độ phủ hiện tại (10 Term là khá ít so với kỳ vọng ban đầu về DEFINES/USES_TERM).

## 📍 Việc cần làm tiếp theo (đọc phần này trước khi bắt đầu phiên mới)

1. **T012 đã xong** (rule-based, chạy thật vào Neo4j) — quyết định có làm LLM fallback cho câu định nghĩa không-quotes hay chấp nhận độ phủ hiện tại (chỉ 10 Term) trước khi coi T012 đóng hẳn.
2. **T013 — `app/extraction/relation_llm.py`**: trích AMENDS/SUPERSEDES/CONFLICTS_WITH bằng Ollama, kèm `confidence` + `ly_do`. Đây là quan hệ khó nhất, độ tin cậy thấp hơn REFERENCES — cần benchmark nhỏ với model 7b trước khi quyết có cần 14b không (sổ bẫy 12b: model to hơn từng không đáng ở project trước).
3. Chạy lại thử 1-2 câu hỏi qua `/chat` với thuật ngữ đã có (vd "Ngày", "Đơn PCT") để xác nhận DEFINES/USES_TERM thực sự hoạt động trong traversal, không chỉ tồn tại trên lý thuyết.
4. Backfill embedding full 60,679 vẫn cần chạy xong trước khi Phase 4 (T017 Recall@k/MRR) có ý nghĩa đầy đủ — xem ĐỢT 5 để biết trạng thái/lệnh chạy.
