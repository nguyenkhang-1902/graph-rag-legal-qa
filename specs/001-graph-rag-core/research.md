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

## 🪤 Sổ bẫy (pitfall log) — kế thừa từ `rag-chatbot-document-QA`

Các bài học từ project Hybrid RAG trước áp dụng được cho project này:

- **12a. BM25 cần chuẩn hóa bỏ dấu tiếng Việt** — nếu entry-point search dùng lại BM25 (không chỉ dense), phải áp dụng lại tokenizer bỏ dấu đã fix Recall@4 61.1%→100% ở project trước. Không viết lại từ đầu.
- **12b. Reranker/LLM 14B không đáng — chậm hơn 2.9-4.2 lần mà chất lượng không tăng rõ** — áp dụng tương tự cho LLM extraction quan hệ: bắt đầu với model nhỏ (Qwen2.5:7b), chỉ nâng cấp nếu đo được sai số extraction cao và có số liệu chứng minh.
- **12c. Confidence-gated reranker đã thử và bị bác bỏ (chậm hơn 4.2 lần, recall không đổi)** — cảnh báo tương tự cho việc thêm "confidence gate" vào graph traversal (vd chỉ traverse khi entry-point confidence thấp) — PHẢI đo trước khi thêm, không mặc định là tối ưu.
- **12d. `host.docker.internal` cần `extra_hosts` trên Linux** — áp dụng lại cấu hình này trong `docker-compose.yml` nếu Ollama chạy trên host, container Neo4j/FastAPI cần gọi ra ngoài.

## 📌 Quyết định khác (chưa đủ điều kiện thành ADR riêng)

- **LLM extraction chạy 1 lần lúc ingest, không cache lại theo mỗi query** — vì AMENDS/CONFLICTS_WITH là thuộc tính tĩnh của văn bản, không đổi theo câu hỏi người dùng.
- **Rule-based trước, LLM fallback sau** cho mọi loại extraction có thể — giữ chi phí ingest thấp, chỉ dùng LLM cho phần thực sự cần hiểu ngữ nghĩa (đúng Điều 1 constitution — đơn giản trước).
