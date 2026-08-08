# 🔬 Research & Quyết định kỹ thuật — Graph RAG Legal QA

## 🗒️ ADR-001: Chọn graph store — Neo4j Community

**Status:** Accepted
**Date:** 2026-08-03
**Deciders:** Khang

### Context

Cần lưu trữ node (Document/Chapter/Article/Clause/Term/Organization) và relationship (BELONGS_TO/REFERENCES/DEFINES/...) để traverse multi-hop lúc query. Project cá nhân, mục tiêu module hoàn chỉnh cho CV trong vài tuần, không có yêu cầu production scale.

### Decision

Dùng **Neo4j Community Edition** chạy qua Docker Compose, local.

### Options Considered

**Option A: Neo4j Community**
| Dimension | Assessment |
|---|---|
| Complexity | Trung bình — cần chạy thêm 1 service Docker, học Cypher |
| Cost | Miễn phí (Community), chạy local |
| Scalability | Đủ cho scope demo (2k-10k văn bản); không cần HA |
| Team familiarity | Chưa dùng trước đây — nhưng đây chính là giá trị học/CV muốn có |

**Pros:** Cypher trực quan cho multi-hop query, Neo4j Browser cho demo trực quan (giá trị lớn khi trình bày CV/phỏng vấn), driver Python chính thức ổn định, ecosystem GraphRAG (LangChain, LlamaIndex) hỗ trợ sẵn.
**Cons:** Thêm 1 service phải quản lý (so với NetworkX không cần server), learning curve Cypher.

**Option B: NetworkX (in-memory)**
| Dimension | Assessment |
|---|---|
| Complexity | Thấp — không cần server, load thẳng vào Python |
| Cost | Miễn phí |
| Scalability | Giới hạn RAM, không phù hợp nếu mở rộng dữ liệu |
| Team familiarity | Quen thuộc (dùng thư viện Python thuần) |

**Pros:** Nhanh setup, không cần Docker, dễ debug bằng Python thuần.
**Cons:** Không thể hiện được kỹ năng "graph database" thật cho CV, không có query language chuẩn ngành, không demo trực quan bằng Neo4j Browser, khó mở rộng nếu sau này muốn ghép vào hệ thống doanh nghiệp thật (đúng định hướng Agentic RAG dài hạn của Khang — xem lại phần "hướng phát triển" đã thảo luận).

**Option C: Microsoft GraphRAG (framework trọn gói)**
Đã loại ở bước brainstorming trước đó — chi phí index bằng LLM quá cao cho hạ tầng local (Ollama 7B), không phù hợp "vài tuần".

### Trade-off Analysis

Neo4j thêm độ phức tạp vận hành (1 service Docker, học Cypher) nhưng đổi lại: (1) đúng công nghệ thị trường dùng cho GraphRAG doanh nghiệp — khớp định hướng dài hạn Agentic RAG/AI Engineering của Khang, (2) demo trực quan tốt hơn hẳn cho CV/phỏng vấn, (3) không giới hạn RAM như NetworkX nếu sau này mở rộng corpus. Đánh đổi hợp lý vì mục tiêu chính là portfolio, không phải tốc độ dựng nhanh nhất.

### Consequences

- Cần thêm `docker-compose.yml` service Neo4j, connection pooling trong `graph_store/neo4j_client.py`.
- Team (chỉ Khang) cần học Cypher — rủi ro thời gian, giảm bằng cách giới hạn query pattern cần dùng (traversal N-hop, upsert) thay vì học toàn bộ Cypher.
- Cần backup/restore Neo4j data nếu muốn giữ demo qua nhiều lần — dùng `neo4j-admin dump/load`, ghi vào `docs/van-hanh.md` khi implement.

### Action Items

1. [ ] Thêm Neo4j service vào `docker-compose.yml`, bật auth qua `.env`
2. [ ] Viết `graph_store/neo4j_client.py` + constraint/index từ `data-model.md`
3. [ ] Viết script `neo4j-admin dump` để backup demo data trước khi thử nghiệm phá schema

---

## 🗒️ ADR-002: Batch ingest + savepoint cho quy mô 67k văn bản

**Status:** Accepted
**Date:** 2026-08-03
**Deciders:** Khang

### Context

Quy mô corpus tăng từ đề xuất ban đầu (2k/10k, để so sánh trực tiếp với benchmark project trước) lên **toàn bộ 67k văn bản** Zalo legal corpus. Ở quy mô này, bước LLM extraction (DEFINES/AMENDS/CONFLICTS_WITH — FR-003) sẽ chạy rất lâu (ước tính nhiều giờ với Ollama local, ngoại suy từ project trước: eval pipeline Hybrid+Reranker trên 2k đã mất 21 phút trên GPU sau tối ưu — 67k văn bản với nhiều lệnh gọi LLM hơn/văn bản chắc chắn mất nhiều giờ). Rủi ro: crash/mất điện/dừng tay giữa chừng làm mất toàn bộ thời gian đã chạy.

### Decision

Ingest chạy theo **batch** (kích thước cấu hình qua `INGEST_BATCH_SIZE`, khởi điểm đề xuất **200 văn bản/batch** — điều chỉnh sau khi đo throughput LLM extraction thật). Sau mỗi batch hoàn tất, ghi **savepoint** (batch cuối đã xong) vào state store riêng (`ingest_checkpoint/state_store.py`). Khi ingest khởi động lại, đọc savepoint và tiếp tục từ batch kế tiếp.

### Options Considered

**Option A: State store là file JSON đơn giản (`.state/ingest_checkpoint.json`)**
| Dimension | Assessment |
|---|---|
| Complexity | Thấp — đọc/ghi file, không cần thêm hạ tầng |
| Cost | Miễn phí |
| Scalability | Đủ cho single-process ingest (không có nhiều worker chạy song song) |
| Team familiarity | Cao — không cần học gì mới |

**Pros:** Đơn giản nhất (Điều 1 constitution), dễ debug bằng cách mở file xem trực tiếp, không phụ thuộc Neo4j còn sống để biết tiến độ.
**Cons:** Nếu sau này chạy nhiều worker song song thì file JSON dễ race condition (không phải lo ở scope hiện tại — single process).

**Option B: Node `IngestBatch` trong Neo4j**
| Dimension | Assessment |
|---|---|
| Complexity | Trung bình — thêm node type không thuộc domain model chính |
| Cost | Miễn phí (đã có Neo4j sẵn) |
| Scalability | Tốt nếu multi-worker (Neo4j transaction xử lý concurrency) |
| Team familiarity | Trung bình |

**Pros:** Một nơi duy nhất chứa cả graph + tiến độ ingest, xem được trực tiếp qua Neo4j Browser.
**Cons:** Trộn lẫn "metadata vận hành" với domain model đồ án (Document/Article...) — vi phạm nhẹ Điều 5 (kỷ luật cấu trúc, một trách nhiệm/module).

### Trade-off Analysis

Chọn **Option A (file JSON)** cho P1: project chạy single-process, không cần concurrency của Neo4j cho việc này. Giữ domain model Neo4j sạch, chỉ chứa dữ liệu pháp luật thật (đúng Điều 5). Nếu sau này cần multi-worker ingest (không nằm trong scope hiện tại), có thể migrate sang Option B — ghi lại như hướng mở rộng, không làm ngay.

### Consequences

- Cần đảm bảo `state_store.py` ghi savepoint **atomic** (viết file tạm rồi rename, không ghi trực tiếp đè file cũ) — tránh savepoint bị hỏng nếu crash đúng lúc đang ghi.
- Batch phải **idempotent theo `doc_id`** (Điều đã có trong `data-model.md` constraint) — vì nếu savepoint ghi lệch 1 batch (vd crash ngay sau khi Neo4j commit nhưng trước khi ghi savepoint), batch đó có thể bị chạy lại — upsert phải xử lý được việc này mà không tạo trùng.
- Cần log rõ tiến độ (`batch N/M hoàn tất, còn ~X giờ ước tính`) để Khang theo dõi tiến trình chạy nhiều giờ mà không cần đứng canh máy.

### Action Items

1. [ ] Viết `ingest_checkpoint/state_store.py` — ghi/đọc file JSON atomic
2. [ ] Viết test resume-after-crash (T009c trong `tasks.md`) trước khi chạy ingest thật trên 67k
3. [ ] Đo throughput thật trên 100-200 văn bản đầu để tính lại `INGEST_BATCH_SIZE` và ước lượng tổng thời gian ingest 67k, báo Khang trước khi chạy full

---

## 🗒️ ADR-003: Xử lý ID trùng do dữ liệu nguồn không nhất quán (near-duplicate filenames)

**Status:** Accepted
**Date:** 2026-08-04
**Deciders:** Khang

### Context

Sau khi ingest thật toàn bộ 61,068 văn bản (checkpoint dữ liệu thật, xem `TIEN_DO.md`), số Article thật trong Neo4j là 60,679 — thiếu 389 so với số file. Điều tra trực tiếp (đọc + so sánh nội dung tất cả 389 cặp trùng) cho thấy nguyên nhân: **chính corpus gốc (Zalo AI Challenge/HuggingFace) chứa các bản ghi trùng lặp thật**, cùng một văn bản xuất hiện 2 lần dưới 2 cách viết filename khác nhau chỉ khác đúng 1 điểm bất nhất Unicode — ví dụ `03_2021_tt-bgddt_1.md` (không dấu) và `03_2021_tt-bgdđt_1.md` (có dấu `đ`). `slugify_doc_name()` (chuẩn hóa bỏ dấu cho `doc_id`) vô tình gộp 2 filename này thành cùng 1 `article_id`, và `upsert.py` (MERGE-based) âm thầm ghi đè bản sau lên bản trước.

Đã xác minh: **cả 389/389 cặp trùng có nội dung giống hệt byte-by-byte** (`noi_dung`/`full_text` giống hoàn toàn) — lần này an toàn, không mất thông tin thật. Nhưng đây là **may mắn của lần này, không phải đảm bảo cho tương lai**. Đây là lớp lỗi rất phổ biến khi làm việc với dữ liệu crawl/scrape thật (encoding không nhất quán, ID gần giống nhau do chuẩn hóa khác nhau giữa các lần thu thập) — **sẽ còn gặp lại** nếu mở rộng nguồn dữ liệu hoặc ingest tăng dần (User Story 3) từ nguồn khác. Nếu 2 file trùng `article_id` mà nội dung THỰC SỰ khác nhau (vd 2 văn bản pháp luật khác nhau vô tình cùng slug, hoặc corpus cập nhật 1 bản mà giữ bản cũ), việc âm thầm ghi đè sẽ **mất thật 1 Article** mà không có cảnh báo nào — vi phạm trực tiếp Điều 1/Điều 7 constitution (không được âm thầm làm sai khi gặp mơ hồ).

### Decision

Thêm bước **pre-flight collision detection** trong `app/ingest.py`, chạy trước khi bắt đầu batch loop (một lần, quét toàn bộ `data_dir`):

1. Tính `article_id` cho mọi file (tái dùng đúng logic tính `doc_id`/`so_dieu` đã có — không viết lại).
2. Gom các file có cùng `article_id`. Với mỗi nhóm ≥2 file:
   - **Nội dung giống hệt nhau** (so sánh full text) → coi là bản sao thật của corpus nguồn, tự động chỉ giữ 1 bản (file đầu tiên theo thứ tự sort), log **INFO** liệt kê các file bị bỏ qua (không phải lỗi, nhưng cần thấy được để audit).
   - **Nội dung KHÁC nhau** → đây là trường hợp nguy hiểm thật — **dừng ngay, raise lỗi rõ ràng** liệt kê đúng các file xung đột và `article_id` chung, **không tự đoán chọn bản nào** (đúng nguyên tắc "gặp mơ hồ → hỏi Khang, không đoán" của constitution). Khang xem xét thủ công (thường là 1 trong 2 file bị lỗi crawl/OCR, hoặc đúng là 2 văn bản khác nhau cần sửa cách tính `doc_id` để tách ra) rồi mới chạy lại.

### Options Considered

**Option A: Bỏ qua, chấp nhận rủi ro (giữ nguyên MERGE âm thầm ghi đè như hiện tại)**
Đơn giản nhất nhưng vi phạm trực tiếp nguyên tắc "không âm thầm làm sai" — loại ngay, không phù hợp cho dữ liệu domain pháp luật (sai thông tin pháp luật có hậu quả thật).

**Option B: Disambiguate — đổi `article_id` để giữ cả 2 bản (vd thêm hậu tố `_dup2`)**
Không mất dữ liệu nhưng phá vỡ giả định "1 `article_id` = 1 Điều luật thật duy nhất" mà `reference_extractor.py` và toàn bộ retrieval dựa vào — REFERENCES trỏ tới bản nào trong 2 bản trùng sẽ tùy tiện, gây nhiễu graph. Loại.

**Option C (đã chọn): Pre-flight detect — tự dedup khi an toàn (nội dung giống), dừng + báo khi nguy hiểm (nội dung khác)**
Tận dụng đúng: nếu giống hệt thì dedup an toàn không cần hỏi; chỉ hỏi khi thực sự mơ hồ (nội dung khác nhau) — đúng tinh thần Điều 1 (đơn giản, không xử lý phức tạp hơn mức cần) và nguyên tắc "gặp mơ hồ → hỏi Khang" của constitution.

### Trade-off Analysis

Option C thêm 1 bước quét toàn bộ file trước khi ingest (chi phí: đọc từng file 1 lần, ước tính vài chục giây trên 61k file dựa trên benchmark thực tế lúc điều tra — chấp nhận được so với tổng thời gian ingest nhiều giờ). Đổi lại: loại hoàn toàn rủi ro mất dữ liệu âm thầm do trùng ID nội dung khác nhau — đúng nguyên tắc dữ liệu domain pháp luật không được sai lặng lẽ.

### Consequences

- `app/ingest.py` cần 1 bước quét trước batch loop — không ảnh hưởng logic batch/savepoint hiện có (T009b-d), vì bước này chạy độc lập trước khi checkpoint được đọc.
- Danh sách file "đã dedup" (bị bỏ qua vì trùng nội dung) nên log rõ để Khang có thể audit lại nếu nghi ngờ.
- Nếu raise lỗi (nội dung khác nhau thật), ingest dừng hoàn toàn — không có "bỏ qua và tiếp tục" ở bước này, khác với lỗi 1 file đơn lẻ (Điều 1 — thà dừng sớm còn hơn ingest sai một phần lớn rồi phải dọn dẹp graph sau).
- 389 file trùng đã phát hiện trong lần ingest 61k đầu tiên (2026-08-04) đều **an toàn (giống hệt nội dung)** — không cần sửa dữ liệu đã ingest, việc này áp dụng cho các lần ingest sau/ingest tăng dần.

### Action Items

1. [ ] Thêm bước pre-flight collision detection vào `app/ingest.py`, tái dùng logic tính `article_id` hiện có, không tạo bản sao logic thứ 2.
2. [ ] Test: 2 file cùng `article_id`, nội dung giống hệt → dedup, không raise, không lặp. 2 file cùng `article_id`, nội dung khác → raise lỗi rõ ràng, liệt kê đúng file.
3. [x] Ghi lại phát hiện 389 cặp trùng (2026-08-04, ingest 61k đầu tiên) — đã audit, an toàn, không cần sửa dữ liệu.

---

## 🗒️ ADR-004: Hiệu chỉnh SIMILARITY_THRESHOLD từ 0.75 → 0.65 bằng dữ liệu thật

**Status:** Accepted
**Date:** 2026-08-06
**Deciders:** Khang

### Context

`SIMILARITY_THRESHOLD=0.75` (mặc định trong `app/config.py`) chỉ là **giá trị khởi điểm đặt tạm lúc scaffold** (T004, xem `tasks.md`), chưa từng được hiệu chỉnh bằng dữ liệu thật. Khi chạy `scripts/eval_graph_recall.py` (T017) lần đầu trên bộ 32 câu hỏi multi-hop đã duyệt (`data/eval/multihop_eval_set.json`), kết quả baseline rất thấp:

- Strict recall (SC-001, "trích dẫn ĐỦ các điều luật liên quan"): **59.4%** — dưới mục tiêu ≥80% trong spec.
- MRR: 0.625.

Điều tra trực tiếp: với mỗi `expected_article_id` trong 32 câu hỏi, kiểm tra similarity thật của nó so với câu hỏi (dù có nằm trong top-20 gần nhất hay không). Kết quả:

- 58 lượt `expected_article_id` kiểm tra trên toàn bộ 32 câu.
- **30/58 (52%) có similarity NẰM TRONG TOP-20 gần nhất nhưng THẤP HƠN 0.75** — bị `find_entry_points()` lọc bỏ oan trước khi graph traversal có cơ hội chạy.
- Trung vị similarity của các `expected_article_id` ĐÚNG (nằm trong top-20): **0.7426** — gần như ngay dưới ngưỡng 0.75, không phải outlier hiếm.
- Chỉ 4/58 thực sự không nằm trong top-20 — và cả 4 đều thuộc case được thiết kế để tìm qua **graph traversal** (không phải trực tiếp qua vector search), nên "không nằm top-20" là đúng thiết kế, không phải lỗi.

### Decision

Hạ `SIMILARITY_THRESHOLD` mặc định từ **0.75 → 0.65**.

Trước khi chốt, đã tự đặt câu hỏi phản biện đúng tinh thần "không được chốt ngưỡng chỉ vì nó cho số đẹp nhất trên đúng tập test" (Khang yêu cầu trực tiếp) và làm 2 bước xác minh:

1. **Đọc tay 10/10 câu hỏi "lật" từ fail(0.75)→pass(0.65)** (toàn bộ, không phải mẫu con — vì tổng số case lật đúng bằng 10, nằm trong khoảng 10-15 case yêu cầu): lấy full text thật của từng Điều "được cứu" bởi ngưỡng mới, đối chiếu tay với câu hỏi. **10/10 khớp đúng nội dung thật — không có case nào "khớp giả" (similarity gần nhưng nội dung lệch)**. Xem `TIEN_DO.md` ĐỢT 9 để có bảng chi tiết từng case.
2. **Held-out split-half**: chia 32 câu thành 2 nửa bằng nhau (xen kẽ theo id, tránh thiên vị thứ tự), đo lại Recall@k riêng từng nửa để xác nhận cải thiện không phải do vài case ngoại lệ kéo số liệu:
   - Nửa A (16 câu): 75.0% → 93.8% (threshold 0.75 → 0.65).
   - Nửa B (16 câu): 43.8% → 87.5%.
   Cải thiện nhất quán ở CẢ HAI nửa, cả hai đều vượt mục tiêu 80% ở ngưỡng mới — không phải overfitting vào 1 tập con may mắn.

Kết quả cuối trên toàn bộ 32 câu ở threshold=0.65: **Strict recall 90.6%, Lenient recall 93.1%, MRR 0.917**.

### Options Considered

**Option A: Giữ nguyên 0.75**
Baseline gốc — bị loại vì có bằng chứng thật (không phải suy đoán) rằng ngưỡng này lọc oan hơn một nửa số kết quả đúng, khiến hệ thống không đạt mục tiêu SC-001 dù retrieval/traversal về bản chất hoạt động đúng.

**Option B: Hạ mạnh hơn nữa (0.60 hoặc thấp hơn)**
Đã thử 0.60 — cho kết quả GIỐNG HỆT 0.65 (90.6%/93.1%/0.917) trên bộ 32 câu này, vì không có `expected_article_id` nào có similarity nằm giữa 0.60-0.65. Chọn 0.65 (không phải 0.60) để giữ biên an toàn — thấp hơn mức tối thiểu quan sát được của kết quả đúng (0.6904) nhưng không hạ thấp tùy tiện hơn mức cần thiết, giảm rủi ro kéo theo nhiễu (false positive) cho các câu hỏi thật khác ngoài 32 câu benchmark này.

**Option C (đã chọn): 0.65**
Cân bằng giữa bằng chứng thật (có biên an toàn dưới ngưỡng tối thiểu quan sát 0.6904) và thận trọng (không hạ sâu hơn mức có bằng chứng ủng hộ).

### Trade-off Analysis

Hạ threshold luôn có đánh đổi lý thuyết: cho phép nhiều entry point "yếu" hơn lọt qua, có thể tăng nhiễu cho các câu hỏi mà top-5 gần nhất thực sự không liên quan. Nhưng đây là lo ngại **lý thuyết chưa có bằng chứng phản bác** — toàn bộ 10 case rescued đã đọc tay đều đúng thật, và held-out split-half không cho thấy dấu hiệu overfitting. Nếu sau này phát hiện case nhiễu thật (câu hỏi không liên quan nhưng vẫn được coi là entry point ở 0.65), cần quay lại đo lại — đây không phải quyết định vĩnh viễn, chỉ là hiệu chỉnh tốt nhất với bằng chứng hiện có.

### Consequences

- `app/config.py`'s `SIMILARITY_THRESHOLD` default đổi 0.75 → 0.65 — ảnh hưởng trực tiếp hành vi `/chat` production (T014) và mọi lần gọi `find_entry_points()` sau này, không chỉ eval script.
- Baseline T017 chính thức dùng cho so sánh với Hybrid+Reranker (Quy tắc riêng #3 — bắt buộc số liệu thật): **Strict recall 90.6%, MRR 0.917** ở threshold=0.65 — đây là con số sẽ đưa vào bảng so sánh Phase 4 (T018), không phải con số ở 0.75.
- Nếu D2 (research.md's action item cũ — baseline Hybrid+Reranker có cần đo lại ở quy mô 67k) chưa xong, so sánh vẫn cần đợi baseline đó đo đúng quy mô trước khi công bố chính thức.

### Action Items

1. [x] Đo baseline thật ở threshold=0.75 (T017 lần đầu) — 59.4%/0.625.
2. [x] Điều tra nguyên nhân bằng dữ liệu thật (similarity distribution của expected_article_ids) — không đoán.
3. [x] Đọc tay 10/10 case lật fail→pass — xác nhận không có "khớp giả".
4. [x] Held-out split-half — xác nhận cải thiện nhất quán, không do overfitting.
5. [ ] Cập nhật `SIMILARITY_THRESHOLD` mặc định trong `app/config.py`/`.env` thành 0.65 (đang chờ Khang xác nhận cuối cùng trước khi sửa file production).

## 🪤 Sổ bẫy (pitfall log) — kế thừa từ `rag-chatbot-document-QA`

Các bài học từ project Hybrid RAG trước áp dụng được cho project này:

- **12a. BM25 cần chuẩn hóa bỏ dấu tiếng Việt** — nếu entry-point search dùng lại BM25 (không chỉ dense), phải áp dụng lại tokenizer bỏ dấu đã fix Recall@4 61.1%→100% ở project trước. Không viết lại từ đầu.
- **12b. Reranker/LLM 14B không đáng — chậm hơn 2.9-4.2 lần mà chất lượng không tăng rõ** — áp dụng tương tự cho LLM extraction quan hệ: bắt đầu với model nhỏ (Qwen2.5:7b), chỉ nâng cấp nếu đo được sai số extraction cao và có số liệu chứng minh.
- **12c. Confidence-gated reranker đã thử và bị bác bỏ (chậm hơn 4.2 lần, recall không đổi)** — cảnh báo tương tự cho việc thêm "confidence gate" vào graph traversal (vd chỉ traverse khi entry-point confidence thấp) — PHẢI đo trước khi thêm, không mặc định là tối ưu.
- **12d. `host.docker.internal` cần `extra_hosts` trên Linux** — áp dụng lại cấu hình này trong `docker-compose.yml` nếu Ollama chạy trên host, container Neo4j/FastAPI cần gọi ra ngoài.
- **12e. BGE-m3 (`sentence-transformers`) tải lại nhiều lần xen kẽ với gọi Ollama trong cùng 1 process từng gây crash native trên Windows** (access violation `0xC0000005`, xác nhận thực nghiệm ở project trước — xem `app/vectorstore.py` comment gốc). Bắt buộc cache 1 instance model duy nhất/process (module-level singleton), không tạo `SentenceTransformer(...)` mới mỗi lần gọi. Áp dụng cho `T009f` (backfill embedding) và mọi chỗ sau này gọi cả embedding lẫn Ollama trong cùng tiến trình (`T010`, `T014`).

## 🪤 Sổ bẫy mới phát hiện trong project này

- **13a. Dữ liệu crawl/scrape thật luôn có khả năng chứa bản ghi gần-trùng do encoding/chuẩn hóa không nhất quán** (vd tên file lệch nhau đúng 1 ký tự dấu tiếng Việt, ID sinh ra từ 2 lần thu thập khác thời điểm) — khi hệ thống có bước chuẩn hóa ID (slugify, bỏ dấu, lowercase...) để tạo khóa duy nhất, các bản ghi gần-trùng này SẼ va vào nhau. **Không mặc định coi là an toàn hay nguy hiểm** — phải so sánh nội dung thật: giống hệt thì dedup tự động (an toàn), khác nhau thì dừng lại hỏi người, không bao giờ để ghi đè âm thầm (đặc biệt nguy hiểm với domain có hậu quả thật như văn bản pháp luật). Xem ADR-003 (giải pháp) và `TIEN_DO.md` (số liệu điều tra thật: 389/389 cặp trùng phát hiện lúc ingest 61k đều an toàn, nhưng đây là may mắn của lần này, không phải đảm bảo).

## 🗒️ ADR-005: Phương pháp so sánh T018 — chọn benchmark, backend BM25, và cách trình bày số liệu cũ

**Status:** Accepted
**Date:** 2026-08-08
**Deciders:** Khang

### Context

Phát biểu ban đầu của G1 ("so Graph RAG với baseline Hybrid+Reranker cũ ở quy mô 10k, ghi rõ lệch quy mô là hạn chế") **chứa một lỗi phương pháp không được nhận ra lúc chốt**: số 93.3% của dự án trước đo trên **793 câu Zalo gold set** (mỗi câu MỘT đáp án, Recall@4), còn 90.6% của T017 đo trên **32 câu multi-hop tự soạn** (mỗi câu NHIỀU đáp án, strict/lenient recall). Đặt hai số cạnh nhau là so **hai bộ câu hỏi khác nhau** *và* **hai metric khác nhau** *và* **hai quy mô corpus khác nhau** — ba biến gây nhiễu cùng lúc, con số không nói lên điều gì.

Ba phát hiện thực nghiệm làm rõ bức tranh (đo 2026-08-08):

1. **793/793 câu Zalo gold map được sang `article_id` có thật** trong corpus 61k → chạy được đúng benchmark cũ trên Graph RAG, loại bỏ biến "bộ câu hỏi".
2. **Backend BM25 không phải thay thế trong suốt**: `rank_bm25` vs `bm25s` chỉ khớp ~66% thứ hạng top-4 và lệch 6.3 điểm % Recall@4 khi dùng một mình (58.0% vs 64.3%). Tốc độ: 351ms/truy vấn vs ~1ms (~360x).
3. **Hybrid KÉM HƠN Dense-only ở 67k** (79.2% vs 82.1%) — ngược hẳn dự án cũ ở 10k. Nguyên nhân khớp với (2): BM25 yếu ở quy mô lớn nên RRF gộp nhánh yếu vào nhánh dense mạnh thành ra kéo xuống.

### Decision

**1. Benchmark: chạy MỌI hệ thống trên cùng 793 câu Zalo gold, cùng metric Recall@4/MRR.** Bộ 32 câu multi-hop giữ nguyên nhưng báo ở **bảng RIÊNG** (SC-001), không đặt cạnh Recall@4.

**2. Backend BM25 cho baseline: `bm25s`** (không phải `rank_bm25` như chốt ban đầu ở ĐỢT 14). Hai lý do: (a) chính README dự án cũ viết *"cần đổi backend nếu scale vượt 10k văn bản"* — chạy `rank_bm25` ở 61k là chạy đúng cấu hình mà dự án cũ đã tự tuyên bố không phù hợp; (b) `bm25s` cho BM25 **mạnh hơn**, nên kết luận "Hybrid kéo xuống" trở thành phát biểu **thận trọng hơn** (với `rank_bm25` thì Hybrid còn tệ hơn nữa). Kèm theo: báo **thêm** một dòng Hybrid dùng `rank_bm25` để **lượng hoá** ảnh hưởng backend thay vì để nó thành biến gây nhiễu ẩn.

**3. Số 2k/10k của dự án cũ = BỐI CẢNH LỊCH SỬ, không phải dòng so sánh.** Ghi ở khối riêng, nêu rõ: đo trên corpus nhỏ hơn, backend BM25 khác, và trong repo khác. Mọi so sánh có ý nghĩa đều nằm trong nhóm "đo mới ở 67k trong dự án này".

**4. Graph RAG phải báo HAI con số recall, không được báo một.** Danh sách xếp hạng của Graph RAG là entry point (dense, tối đa `top_k`) trước, traversal sau — nên với `top_k=5`, `k=4` thì **4 slot đầu luôn là entry point**, traversal không thể chen vào top-4. Hệ quả: `Recall@4` của Graph RAG **theo cấu trúc** không thể cao hơn dense-only. Vì vậy báo cả `recall_at_k` (so sánh trực tiếp được) **và** `recall_expanded` (đáp án nằm bất kỳ đâu trong tập entry+traversal — cho thấy traversal thêm được gì, nhưng KHÔNG so được với Recall@4 vì tập ứng viên lớn hơn nhiều).

### Options Considered

- **Giữ nguyên G1 nguyên văn** (so 32 câu multi-hop với 93.3% ở 10k) — bị loại: ba biến gây nhiễu cùng lúc, và người đọc CV có kinh nghiệm sẽ phát hiện ngay.
- **Chỉ đo lại baseline cũ ở 67k bằng `rank_bm25`** cho trung thành tuyệt đối — bị loại: chạy đúng cấu hình mà dự án cũ đã tuyên bố không phù hợp ở quy mô này; vẫn giữ như một dòng phụ để lượng hoá.
- **Chỉ báo `recall_expanded` cho Graph RAG** (số cao hơn, dễ kể chuyện) — **bị loại vì không trung thực**: tập ứng viên lớn hơn nhiều nên không cùng thang đo với Recall@4.

### Trade-off Analysis

Đánh đổi chính: bảng kết quả **phức tạp hơn** (nhiều dòng, nhiều chú thích) và có khả năng cho ra kết luận **kém hấp dẫn hơn** cho Graph RAG (xem ADR này mục 4 + `CHECKLIST-GRAPHRAG-DUYET.md` mục I1). Chấp nhận, vì một bảng đơn giản nhưng so sai thì không có giá trị nào — kể cả giá trị CV.

### Consequences

- Cần thêm `scripts/eval_graph_on_zalo_gold.py` (Graph RAG trên 793 câu Zalo) — trước đó KHÔNG tồn tại, nên trước ADR này **chưa từng có so sánh nào hợp lệ**.
- Bảng T018 sẽ có 2 khối: "đo mới ở 67k trong dự án này" (so sánh được với nhau) và "bối cảnh lịch sử 2k/10k" (không so trực tiếp).
- Luận điểm giá trị của Graph RAG cần phát biểu lại — không dựa vào Recall@4 (xem mục I1 chờ Khang quyết).

### Action Items

- [x] Đo `793/793` câu gold map được sang `article_id` thật.
- [x] Đo so sánh backend BM25 ở 61k (`scripts/quality_fixtures/bm25_backend_bench_61k.txt`).
- [x] Viết `scripts/eval_graph_on_zalo_gold.py` (báo cả 2 con số recall).
- [x] Thêm dòng "2b. Hybrid (rank_bm25 + dense, RRF)" vào script baseline.
- [ ] Chạy xong Hybrid+Reranker trên 793 câu, rồi dựng bảng cuối cùng.
- [ ] Quyết I1 (cách phát biểu giá trị Graph RAG) trước khi viết README/T022.

## 📌 Quyết định khác (chưa đủ điều kiện thành ADR riêng)

- **LLM extraction chạy 1 lần lúc ingest, không cache lại theo mỗi query** — vì AMENDS/CONFLICTS_WITH là thuộc tính tĩnh của văn bản, không đổi theo câu hỏi người dùng.
- **Rule-based trước, LLM fallback sau** cho mọi loại extraction có thể — giữ chi phí ingest thấp, chỉ dùng LLM cho phần thực sự cần hiểu ngữ nghĩa (đúng Điều 1 constitution — đơn giản trước).
