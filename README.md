# Graph RAG — Hỏi đáp pháp luật lao động cho người lao động

Hệ hỏi–đáp pháp luật **lao động – tiền lương – bảo hiểm xã hội** tiếng Việt trên nền **Graph RAG**: hỏi bằng ngôn ngữ đời thường → truy xuất đúng Điều/Khoản luật **hiện hành** → trả lời có **trích dẫn** để kiểm chứng.

> Trọng tâm: **luật hiện hành** (Luật BHXH 2024 số 41/2024/QH15, hiệu lực 01/7/2025) + các Nghị định/Thông tư 2025 hướng dẫn. Dữ liệu crawl từ CSDL quốc gia [vbpl.vn](https://vbpl.vn).

---

## 📊 Số liệu đánh giá (2026-08-22)

### Dữ liệu (corpus)
| Chỉ số | Giá trị |
|---|---|
| Văn bản | **19** (Luật BHXH 2024, Bộ luật Lao động 2019 + NĐ 145/2020, lương tối thiểu vùng, Luật Việc làm, ATVSLĐ, BHYT, NLĐ nước ngoài + các NĐ/TT 2025) |
| Điều | **995** |
| Khoản | **3.193** |

### Truy xuất (retrieval) — bộ 30 câu, gold Điều xác minh từ tiêu đề
| Chỉ số | Giá trị |
|---|---|
| **recall@5** | **100%** |
| recall@10 | 100% |
| MRR | 0.889 |

### Chất lượng câu trả lời (QA kiểu ALQAC) — bộ 110 câu
| Loại | Accuracy |
|---|---|
| Đúng/Sai (31 câu) | **100%** |
| Trắc nghiệm A/B/C/D (29 câu) | 86.2% |
| Tự luận – key facts (35 câu) | 77.1% |
| **Ngoài phạm vi – từ chối đúng (15 câu)** | **100%** |
| Truy xuất đúng gold (in-scope) | 94.7% |
| **TỔNG accuracy** | **89.1%** (98/110) |

*Model: `qwen2.5:7b-instruct` (Ollama) + cross-encoder reranker. Bộ 110 câu gồm 18 câu **lao động – tiền lương** (lương tối thiểu vùng, hợp đồng lao động, làm thêm giờ, giấy phép lao động nước ngoài); mở rộng eval **không làm giảm** tổng accuracy (reranker nâng 87.3% → 89.1%).*

### Ablation — graph có đáng giá không? (đo được, không cảm tính)
Câu hỏi **multi-hop** (cần ≥2 Điều, vd Luật + Nghị định), recall@10:
| Cấu hình | recall@10 (multi-hop) |
|---|---|
| dense-only | 57.1% |
| **dense + graph** | **71.4%** |
| dense + graph + reranker | 71.4% (recall@5 lên 71.4%, MRR 0.41→0.51) |

→ **Graph thêm +14 điểm recall ở multi-hop** sau khi fix cross-doc name-alias (NĐ→Luật resolve: 1 → 171 cạnh). Kết luận: **giữ graph**.

> **Trung thực về giới hạn:** con số trên là bộ eval **110 câu curated** — đủ để chứng minh POC, chưa phải chỉ số production (cần bộ lớn/đa dạng hơn để khoảng tin cậy hẹp). Phần lớn lỗi còn lại là LLM 7b **trích sai số cụ thể** ở câu trắc nghiệm hoặc **viện dẫn văn bản ngoài corpus** ở câu tự luận — loại sau đã được **guardrail hậu xử lý gắn cảnh báo** thay vì để trót lọt. Đây là trần năng lực của 7b (hướng cải thiện: model mạnh hơn — xem ROADMAP GĐ4), không phải lỗi kiến trúc.

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

# 1) Xây toàn bộ corpus bằng MỘT lệnh (idempotent + tự kiểm chứng):
#    wipe → ingest → embed → references → reconcile (Chroma == Article thật)
python -m scripts.build_corpus              # rebuild từ .txt đã có
python -m scripts.build_corpus --refresh    # crawl lại từ vbpl.vn (~10 phút)

# 2) Demo hỏi-đáp
python -m scripts.smoke_bhxh_chat

# 3) Đánh giá
python -m scripts.eval_bhxh_retrieval    # retrieval recall@k
python -m scripts.eval_bhxh_qa           # QA accuracy (Đúng/Sai, trắc nghiệm, tự luận, guardrail)
python -m scripts.eval_bhxh_ablation     # dense-only vs có-graph
```

> Toàn bộ pipeline gói trong `scripts/build_corpus.py` — chạy lại luôn cho ra cùng trạng thái sạch, tự fail nếu Chroma và Neo4j lệch nhau.

### Tìm văn bản mới (discovery — nền cho cập nhật luật tự động)
```bash
# Nhập số hiệu (hoặc từ khóa) → liệt kê ứng viên URL + trạng thái hiệu lực để DUYỆT
python -m scripts.discover_vbpl "145/2020/NĐ-CP"
```
> Resolver số hiệu → URL chi tiết vbpl.vn (human-in-the-loop, không tự ingest). Kèm `trạng_thái` (Còn/Hết hiệu lực) — tín hiệu để phát hiện văn bản bị thay thế. Crawler có retry cho lỗi tạm thời + bỏ nhanh trang "không tồn tại".

## 📁 Cấu trúc
- `app/` — engine (extraction, graph_store, retrieval, reranker, serving) — domain-agnostic
- `scripts/` — crawler, embed, references, eval
- `data/eval/` — bộ eval retrieval (30 câu) + QA (110 câu, gồm 18 câu lao động–tiền lương), gold verified
- `docs/design/` — thiết kế & kế hoạch

## 🚧 Lộ trình
Chi tiết định hướng phát triển: **[ROADMAP.md](ROADMAP.md)**.
- [x] Nền dữ liệu BHXH temporal-first + retrieval + QA có trích dẫn
- [x] Reranker + guardrail chống bịa + bộ eval QA kiểu ALQAC
- [x] Validate kiến trúc (dense-only vs có-graph) — graph +14đ recall multi-hop
- [x] Mở rộng corpus sang **lao động – tiền lương** (19 văn bản) + eval 110 câu
- [x] Nền discovery tìm văn bản mới (resolver số hiệu → URL)
- [ ] Cập nhật luật tự động → Cross-doc multi-hop → Giao diện + cảnh báo pháp lý

> ⚠️ Đây là công cụ tham khảo, **không thay thế tư vấn pháp lý chính thức**. Luôn kiểm chứng với nguồn gốc tại [vbpl.vn](https://vbpl.vn).
