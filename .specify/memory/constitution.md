# 📜 HIẾN PHÁP DỰ ÁN — GRAPH RAG LEGAL QA

> `constitution.md` · phiên bản 1.0 · theo Spec-Driven Development
> Nền tảng bất biến mọi spec/plan/task phải tuân. Xung đột → hiến pháp thắng.

## 🏛️ 0. Bối cảnh dự án

Project cá nhân (portfolio/CV), tách riêng khỏi `rag-chatbot-document-QA` (dự án Hybrid RAG đã hoàn thiện trước đó). Mục tiêu: xây một Graph RAG hoàn chỉnh trên domain văn bản pháp luật Việt Nam (dùng lại benchmark Zalo AI Challenge 2021 — Legal Text Retrieval), tận dụng cấu trúc trích dẫn tự nhiên của văn bản luật (Điều/Khoản/Chương viện dẫn lẫn nhau) làm graph, và so sánh có số liệu với baseline Hybrid+Reranker của project trước.

Không phải dự án công ty — không áp dụng RBAC nhiều role, không có "người duyệt cuối" khác ngoài Khang, không có hạ tầng công ty phải tránh đụng vào. Vì vậy bỏ qua mục 9 (8-mục xác nhận dự án công ty) của quy ước Nhân Kiệt; giữ lại toàn bộ phần cấu trúc file, quy trình specify→clarify→plan→tasks→analyze, và các điều hiến pháp còn phù hợp.

### Đọc trước khi dựng
1. Spec là nguồn sự thật — trình tự constitution → specify → clarify → plan → tasks → analyze → implement.
2. Làm từng phần, có điểm dừng để Khang xem lại trước khi sang phase tiếp.
3. Đọc `data-model.md` (graph schema) trước khi viết code ingest — không tự bịa thêm node/relationship type ngoài schema đã chốt.
4. Không bao giờ commit bí mật — Neo4j credentials, mọi secret nằm trong `.env`, đã `.gitignore`.
5. Không thí nghiệm phá schema Neo4j đang chạy demo — có script reset riêng, không sửa tay qua Neo4j Browser rồi quên đồng bộ lại code.
6. Gặp mơ hồ (vd ngưỡng số hop traverse, ngưỡng similarity) → hỏi Khang, không đoán. Ghi giả định vào `[CẦN DUYỆT]`.

## ⚖️ Core Principles (NON-NEGOTIABLE)

### Điều 1 — Đơn giản & dùng tính năng sẵn có
KISS/YAGNI. Ưu tiên driver/thư viện Neo4j chính thức, LangChain graph components có sẵn trước khi tự viết traversal logic riêng. Không tự implement lại thuật toán community detection — nếu cần, dùng thư viện đã kiểm chứng (networkx/graspologic), không phải mục tiêu của project này (đó là hướng Microsoft GraphRAG đã cân nhắc và loại).

### Điều 2 — Nghiệm thu theo tiêu chí; TDD cho logic quan trọng
Mọi user story có `quickstart.md` kịch bản nghiệm thu. Logic trích xuất quan hệ (regex viện dẫn điều luật, entity resolution) là logic nghiệp vụ quan trọng → viết test trước (`tests/`), coverage ưu tiên cho `extraction/` và `graph_build/`.

### Điều 3 — Đặt tên nhất quán
Code Python: `snake_case` cho hàm/biến, `PascalCase` cho class. Cypher: label `PascalCase` (`Article`, `Document`), relationship type `UPPER_SNAKE_CASE` (`REFERENCES`, `BELONGS_TO`). Một bộ thuật ngữ tiếng Việt cho domain pháp luật (Điều/Khoản/Chương/Mục) dùng nhất quán trong code comment, docstring, và README — không lẫn "Article/Clause" tiếng Anh với "Điều/Khoản" tiếng Việt trong cùng một chỗ.

### Điều 4 — Hằng số thay magic value
Ngưỡng similarity, số hop traverse tối đa, batch size khi gọi LLM extraction → tập trung trong `app/config.py`, đọc qua `.env`. Không hard-code `2` (số hop) hay `0.8` (ngưỡng) rải rác trong code.

### Điều 5 — Kỷ luật cấu trúc
Một trách nhiệm/module: `extraction/` (rule-based + LLM), `graph_store/` (Neo4j client, Cypher queries), `retrieval/` (entry-point search + traversal), `serving/` (FastAPI). Trần 700 dòng/file — file vượt ngưỡng phải tách.

### Điều 6 — Tài liệu hóa
Mỗi quyết định kỹ thuật không hiển nhiên (vd tại sao 2-hop chứ không phải 1 hoặc 3) ghi vào `research.md`, không chỉ nằm trong đầu lúc code.

### Điều 7 — Thiết kế cho quy mô & suy giảm duyên dáng
Neo4j query có index trên thuộc tính dùng để lookup entry point (`article_id`). Nếu Ollama/LLM extraction lỗi giữa chừng khi ingest — pipeline phải resume được, không ingest lại từ đầu toàn bộ corpus.

### Điều 8 — Ưu tiên nền tảng đã kiểm chứng
Neo4j Community (Docker), driver `neo4j` chính thức, LangChain cho orchestration nếu phù hợp — ghim version trong `requirements/`.

### Điều 10 — Bảo mật & quyền riêng tư
Neo4j auth bật (không chạy `NEO4J_AUTH=none` kể cả local demo), credentials qua `.env` + `.env.example`. Không log toàn văn câu hỏi người dùng nếu chứa thông tin nhạy cảm (áp dụng lại `pii_guard` pattern từ project trước nếu tái sử dụng dữ liệu HR).

### Điều 11 — Bản địa hóa & bối cảnh Việt Nam
Toàn bộ regex/entity extraction phải xử lý đúng cách viết điều luật tiếng Việt ("Điều 5", "khoản 2 Điều 5", "Điều 5 Luật Doanh nghiệp 2020") — không giả định format tiếng Anh.

*(Bỏ Điều 9 — UI responsive/bản địa hóa giao diện: project này ưu tiên API + demo notebook/Neo4j Browser trước, chưa có UI người dùng cuối riêng ở scope hiện tại.)*

## 🧱 Nền tảng & hạ tầng (đã chốt)

- **Ngôn ngữ**: Python 3.11 (đồng bộ với `rag-chatbot-document-QA`).
- **Graph store**: Neo4j Community Edition, chạy qua Docker Compose, local.
- **Vector store**: Chroma (tái dùng pattern từ project trước) — chỉ dùng để tìm entry-point node, không phải nguồn context chính.
- **LLM**: Ollama (Qwen2.5) local — nhất quán với project trước, không phụ thuộc API trả phí.
- **Serving**: FastAPI (API) — Streamlit/UI là optional, không nằm trong scope P1.
- **Dữ liệu**: Zalo AI Challenge 2021 Legal Text Retrieval corpus, **toàn bộ 67k văn bản** (✅ chốt 2026-08-03, tăng từ đề xuất ban đầu 2k/10k) — tái sử dụng `scripts/fetch_zalo_legal_corpus.py` từ project trước. Ingest bắt buộc theo batch + savepoint (xem `research.md` ADR-002).
- **Không đụng**: project `rag-chatbot-document-QA` gốc — đây là repo/thư mục hoàn toàn tách biệt, không sửa code hay data của project cũ, chỉ tham chiếu đọc (vd copy script benchmark).

## 📐 Quy tắc riêng của dự án Graph RAG Legal QA

1. **Phạm vi**: chỉ xử lý domain legal (Zalo corpus). Không mở rộng sang HR/nội bộ doanh nghiệp ở P1 — đó là hướng mở rộng tương lai, không phải mục tiêu bản đầu.
2. **Không có multi-user/RBAC** — đây là demo single-user, không cần phân quyền.
3. **Benchmark bắt buộc**: mọi thay đổi ảnh hưởng retrieval phải đo lại bằng phương pháp tương tự `scripts/eval_zalo_recall.py` của project trước (Recall@k, MRR) để so sánh có số liệu với baseline Hybrid+Reranker — không nhận xét định tính "có vẻ tốt hơn" mà không có con số.
4. **Người quyết cuối**: Khang — mọi điểm mơ hồ (ngưỡng, phạm vi hop, có build UI hay không) gom vào `CHECKLIST-GRAPHRAG-DUYET.md`.
5. **Ràng buộc thời gian**: mục tiêu "module hoàn chỉnh" trong vài tuần — nếu một hướng kỹ thuật (vd LLM extraction quan hệ phức tạp) tốn quá nhiều thời gian so với giá trị đo được, ưu tiên cắt scope, ghi vào `research.md` lý do cắt, không cố làm cho "đẹp" mà trễ toàn bộ.

## 🔄 Quy trình Spec-Driven (cách dùng hiến pháp này)

```
constitution.md (file này)
   → specs/001-graph-rag-core/spec.md       (CÁI GÌ)
   → clarify (hỏi trực tiếp, không dùng tooling riêng)
   → specs/001-graph-rag-core/plan.md       (kỹ thuật, đối chiếu hiến pháp)
   → specs/001-graph-rag-core/tasks.md      (task rời, T00N)
   → analyze (đối chiếu spec/plan/tasks không mâu thuẫn)
   → implement
```

## 🏁 Governance

- Đứng trên mọi spec/plan/task/config của project này.
- Sửa đổi: ghi lý do, tăng version (MAJOR đổi/bỏ nguyên tắc · MINOR thêm · PATCH chỉnh chữ), cập nhật ngày.
- Phát hiện phải vi phạm 1 điều để khả thi → dừng, ghi vào `CHECKLIST-GRAPHRAG-DUYET.md`, hỏi Khang.

**Version**: 1.1 | **Ratified**: 2026-08-03 | **Last Amended**: 2026-08-03
> Changelog:
> v1.0 (2026-08-03) — khởi tạo constitution, lược Điều 9 (UI) và mục 9-quy-trình-công-ty (8-mục xác nhận) vì đây là project cá nhân.
> v1.1 (2026-08-03) — MINOR: chốt quy mô dữ liệu 67k văn bản (tăng từ 2k/10k), bổ sung yêu cầu batch+savepoint vào hạ tầng đã chốt; chốt AMENDS/SUPERSEDES/CONFLICTS_WITH làm ngay P1; chốt không có UI Streamlit.
