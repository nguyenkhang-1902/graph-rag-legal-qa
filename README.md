# Graph RAG — Hỏi đáp Bảo hiểm xã hội cho người lao động

Hệ hỏi–đáp pháp luật **Bảo hiểm xã hội (BHXH)** tiếng Việt trên nền **Graph RAG**: hỏi bằng ngôn ngữ đời thường → truy xuất đúng Điều/Khoản luật **hiện hành** → trả lời có **trích dẫn** để kiểm chứng.

> Trọng tâm: **luật hiện hành** (Luật BHXH 2024 số 41/2024/QH15, hiệu lực 01/7/2025) + các Nghị định/Thông tư 2025 hướng dẫn. Dữ liệu crawl từ CSDL quốc gia [vbpl.vn](https://vbpl.vn).

---

## 📊 Số liệu đánh giá (2026-08-22)

### Dữ liệu (corpus)
| Chỉ số | Giá trị |
|---|---|
| Văn bản | **16** (Luật BHXH 2024, Bộ luật Lao động 2019, Luật Việc làm, Luật ATVSLĐ, Luật BHYT + các NĐ/TT 2025) |
| Điều | **839** |
| Khoản | **2.314** |

### Truy xuất (retrieval) — bộ 30 câu, gold Điều xác minh từ tiêu đề
| Chỉ số | Giá trị |
|---|---|
| **recall@5** | **100%** |
| recall@10 | 100% |
| MRR | 0.889 |

### Chất lượng câu trả lời (QA kiểu ALQAC) — bộ 92 câu
| Loại | Accuracy |
|---|---|
| Đúng/Sai (25 câu) | **100%** |
| Trắc nghiệm A/B/C/D (23 câu) | 82.6% |
| Tự luận – key facts (29 câu) | 79.3% |
| **Ngoài phạm vi – từ chối đúng (15 câu)** | **100%** |
| Truy xuất đúng gold (in-scope) | 93.5% |
| **TỔNG accuracy** | **89.1%** (82/92) |

*Model: `qwen2.5:7b-instruct` (Ollama) + cross-encoder reranker. Test suite: **417 pass**.*

> **Trung thực về giới hạn:** con số trên là bộ eval **92 câu curated** — đủ để chứng minh POC, chưa phải chỉ số production (cần bộ lớn/đa dạng hơn để khoảng tin cậy hẹp). 5 lỗi tự luận còn lại là LLM 7b viện dẫn văn bản ngoài corpus — đã được **guardrail hậu xử lý gắn cảnh báo** thay vì để trót lọt.

---

## 🏗️ Kiến trúc

```
Câu hỏi → [Embed truy vấn bge-m3] → [Entry point: ChromaDB dense search]
        → [Traversal: Neo4j theo REFERENCES] → [Rerank: cross-encoder]
        → [Sinh câu trả lời: Ollama + prompt guardrail]
        → [Guardrail hậu xử lý: chặn trích dẫn ngoài ngữ cảnh] → Trả lời + trích dẫn
```

**3 lớp phòng thủ chống bịa (hallucination):**
1. **Prompt guardrail** — buộc chỉ dùng ngữ cảnh, từ chối khi không đủ căn cứ.
2. **Reranker** (`BAAI/bge-reranker-v2-m3`) — đẩy Điều đúng trọng tâm lên đầu.
3. **Post-hoc guardrail** — quét trích dẫn; văn bản không có trong ngữ cảnh → gắn cảnh báo ⚠️ + trả `hallucinated_citations`.

**Metadata temporal-first:** mỗi văn bản mang `ngay_hieu_luc`, `trang_thai` (active/superseded), `che_do` → sẵn sàng phân biệt luật cũ/mới.

## 🧰 Stack
- **Vector:** ChromaDB (embedding `BAAI/bge-m3`)
- **Graph:** Neo4j (Document → Chương → Điều → Khoản, quan hệ `REFERENCES`)
- **Rerank:** `BAAI/bge-reranker-v2-m3` (cross-encoder, CPU)
- **LLM:** Ollama `qwen2.5:7b-instruct`
- **API:** FastAPI (`POST /chat`)
- **Crawler:** Playwright (vbpl.vn là Next.js RSC, cần render JS)

## ▶️ Chạy thử

```bash
docker compose up -d neo4j        # Neo4j
# đảm bảo Ollama đang chạy (ollama serve) + đã pull qwen2.5:7b-instruct

# 1) Crawl + ingest corpus BHXH vào Neo4j (Playwright)
python -m scripts.fetch_bhxh_corpus

# 2) Embed vào ChromaDB + trích dẫn chéo (multi-hop)
python -m scripts.fetch_bhxh_corpus --out-dir data/raw/bhxh
python -m scripts.embed_bhxh
python -m scripts.extract_bhxh_references

# 3) Demo hỏi-đáp
python -m scripts.smoke_bhxh_chat

# 4) Đánh giá
python -m scripts.eval_bhxh_retrieval    # retrieval recall@k
python -m scripts.eval_bhxh_qa           # QA accuracy (Đúng/Sai, trắc nghiệm, tự luận, guardrail)
```

## 📁 Cấu trúc
- `app/` — engine (extraction, graph_store, retrieval, reranker, serving) — domain-agnostic
- `scripts/` — crawler, embed, references, eval
- `data/eval/` — bộ eval retrieval (30 câu) + QA (92 câu), gold verified
- `docs/design/` — thiết kế & kế hoạch

## 🚧 Lộ trình
Chi tiết định hướng phát triển: **[ROADMAP.md](ROADMAP.md)**.
- [x] Nền dữ liệu BHXH temporal-first + retrieval + QA có trích dẫn
- [x] Reranker + guardrail chống bịa + bộ eval QA kiểu ALQAC
- [ ] Validate kiến trúc (dense-only vs có-graph)
- [ ] Mở rộng corpus sang **lao động – tiền lương**
- [ ] Cập nhật luật tự động → Cross-doc multi-hop → Giao diện + cảnh báo pháp lý

> ⚠️ Đây là công cụ tham khảo, **không thay thế tư vấn pháp lý chính thức**. Luôn kiểm chứng với nguồn gốc tại [vbpl.vn](https://vbpl.vn).
