# 🛠️ Implementation Plan: Graph RAG (Phase 1: engine gốc)

**Branch**: `001-graph-rag-core` | **Date**: 2026-08-03 | **Spec**: `spec.md`

> **Đã pivot sang BHXH/lao động-tiền lương** — cấu trúc thư mục `app/` dưới
> đây phần lớn vẫn đúng (`graph_store/`, `retrieval/`, `serving/api.py`), đã
> thêm mới `app/extraction/{doc_identity,vbpl_parser}.py` +
> `scripts/{build_corpus,fetch_bhxh_corpus,extract_bhxh_references,embed_bhxh,
> check_corpus_freshness,discover_vbpl}.py` cho domain BHXH. `ingest_checkpoint/`
> + `app/ingest.py`'s CLI batch/savepoint không còn được gọi ở luồng chính
> (corpus 19 văn bản, wipe+rebuild trực tiếp qua `build_corpus.py`) nhưng vẫn
> giữ vài helper dùng chung (`discover_documents`, `_all_articles`).

## 📋 Summary

Xây pipeline ingest trích xuất cấu trúc + quan hệ từ văn bản luật vào Neo4j, kết hợp entry-point search bằng vector (Chroma) với graph traversal (Cypher, 1-2 hop) để trả lời câu hỏi multi-hop kèm citation path. Benchmark bằng lại phương pháp Recall@k/MRR của project trước để so sánh có số liệu với Hybrid+Reranker.

## 🔧 Technical Context

- **Language/Version**: Python 3.11
- **Primary Dependencies**: `neo4j` (driver chính thức), `langchain` (orchestration, optional — chỉ dùng phần cần thiết, không kéo cả framework nếu không cần), `chromadb`, `sentence-transformers` (BGE-m3, tái dùng từ project trước), Ollama client (Qwen2.5)
- **Storage**: Neo4j Community (Docker) cho graph, Chroma cho vector embedding, `.state/ingest_checkpoint.json` (hoặc node `IngestBatch` trong Neo4j — xem `research.md` ADR-002) cho savepoint
- **Testing**: `pytest`, coverage ưu tiên `extraction/` và `graph_build/` (Điều 2 constitution)
- **Target Platform**: Local (Docker Compose), demo qua FastAPI + Neo4j Browser — ✅ chốt không cần Streamlit ở P1
- **Performance Goals**: SC-004 — ingest tăng dần 1 văn bản < 5 phút. SC-005 — ingest batch 67k chịu được gián đoạn, resume không mất tiến độ. Không có mục tiêu latency query cứng (đo thực tế rồi so với baseline).
- **Constraints**: không phụ thuộc API trả phí (nhất quán Điều 8 project trước), Neo4j auth luôn bật (Điều 10).
- **Scale/Scope**: ✅ **Chốt 2026-08-03 — toàn bộ 67k văn bản** Zalo legal corpus (tăng từ đề xuất ban đầu 2k/10k). Ingest bắt buộc theo batch + savepoint (FR-008, User Story 4) — không còn là "mở rộng nếu kịp" mà là yêu cầu hạ tầng cốt lõi ngay từ Phase Foundational.

## ⚖️ Constitution Check

| Điều | Đối chiếu | Kết quả |
|---|---|---|
| 1 — Đơn giản | Dùng driver Neo4j + LangChain graph component có sẵn, không tự viết traversal engine riêng | Pass |
| 2 — Nghiệm thu/TDD | `extraction/` có test trước khi build graph thật (regex REFERENCES) | Pass — xem `tasks.md` Phase Foundational |
| 3 — Đặt tên | Label/relationship theo `PascalCase`/`UPPER_SNAKE_CASE` đã chốt ở `data-model.md` | Pass |
| 4 — Hằng số | `MAX_HOP`, `SIMILARITY_THRESHOLD`, `LLM_BATCH_SIZE` trong `app/config.py` | Pass |
| 5 — Kỷ luật cấu trúc | Module tách theo `extraction/graph_store/retrieval/serving`, trần 700 dòng | Pass |
| 7 — Suy giảm duyên dáng | Ingest resume được (FR-008), index trên `article_id`/`chroma_id` | Pass |
| 10 — Bảo mật | Neo4j auth bật, `.env` cho credentials | Pass |

Không có vi phạm cần biện minh ở Complexity Tracking.

## 📁 Project Structure

### Documentation (this feature)

```
specs/001-graph-rag-core/
├── spec.md
├── plan.md               (file này)
├── tasks.md
├── research.md
├── data-model.md
├── quickstart.md
└── checklists/requirements.md
```

### Source Code (repository root)

```
graph-rag-legal-qa/
├── app/
│   ├── config.py              # MAX_HOP=2, SIMILARITY_THRESHOLD, INGEST_BATCH_SIZE, model names, .env loader
│   ├── extraction/
│   │   ├── structure_parser.py    # Document→Chapter→Article→Clause (rule-based)
│   │   ├── reference_extractor.py # REFERENCES (regex viện dẫn điều luật VN)
│   │   ├── term_extractor.py      # DEFINES/USES_TERM (rule-based trước, LLM fallback)
│   │   └── relation_llm.py        # AMENDS/SUPERSEDES/CONFLICTS_WITH (LLM, có confidence) — chạy P1 cho toàn bộ 67k
│   ├── graph_store/
│   │   ├── neo4j_client.py        # kết nối, constraint/index setup
│   │   └── upsert.py              # ghi node/relationship, idempotent theo article_id/doc_id
│   ├── ingest_checkpoint/
│   │   └── state_store.py         # 🆕 đọc/ghi savepoint (batch cuối hoàn tất), resume logic — xem research.md ADR-002
│   ├── retrieval/
│   │   ├── entry_point.py         # vector search Chroma → article_id
│   │   └── traversal.py           # Cypher multi-hop, giới hạn MAX_HOP, chống lặp
│   ├── serving/
│   │   └── api.py                 # FastAPI /chat — trả lời + citation path (không có UI riêng)
│   └── ingest.py                  # entry point CLI, chạy theo batch, gọi state_store mỗi batch
├── scripts/
│   ├── build_multihop_eval_set.py # Claude soạn câu hỏi multi-hop cho SC-001, Khang duyệt lại
│   └── eval_graph_recall.py       # Recall@k/MRR, cùng phương pháp project trước, chạy trên 67k
├── tests/
│   ├── extraction/
│   ├── graph_store/
│   ├── ingest_checkpoint/          # 🆕 test resume-after-crash (kill -9 giữa batch)
│   └── retrieval/
├── docker-compose.yml              # Neo4j service
├── requirements/
└── .env.example
```

## 🧩 Complexity Tracking

Không có mục nào cần biện minh — Constitution Check pass toàn bộ. Việc thêm `ingest_checkpoint/` không phải "phức tạp hóa không cần thiết" — là yêu cầu hạ tầng bắt buộc ở quy mô 67k (FR-008/SC-005), không phải lựa chọn thẩm mỹ.
