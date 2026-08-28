# Graph RAG — Hỏi đáp pháp luật lao động cho người lao động

Hệ hỏi–đáp pháp luật **lao động – tiền lương – bảo hiểm xã hội** tiếng Việt trên nền **Graph RAG**: hỏi bằng ngôn ngữ đời thường → truy xuất đúng Điều/Khoản luật **hiện hành** → trả lời có **trích dẫn** để kiểm chứng.

> Trọng tâm: **luật hiện hành** (Luật BHXH 2024 số 41/2024/QH15, hiệu lực 01/7/2025) + các Nghị định/Thông tư 2025 hướng dẫn. Dữ liệu crawl từ CSDL quốc gia [vbpl.vn](https://vbpl.vn).

---

## 📊 Số liệu đánh giá (2026-08-27)

### Dữ liệu (corpus)
| Chỉ số | Giá trị |
|---|---|
| Văn bản | **19** (Luật BHXH 2024, Bộ luật Lao động 2019 + NĐ 145/2020, lương tối thiểu vùng, **Luật Việc làm 2025 số 74/2025/QH15** + NĐ 374/2025 hướng dẫn, ATVSLĐ, BHYT, NLĐ nước ngoài + các NĐ/TT 2025) |
| Điều | **988** |
| Khoản | **3.205** |

> **Cập nhật 2026-08-26**: `scripts/check_corpus_freshness.py` phát hiện **Luật Việc làm 2013 (38/2013/QH13) đã hết hiệu lực toàn bộ** — đã thay bằng **Luật Việc làm 2025 (74/2025/QH15, hiệu lực 01/01/2026)**. Đây là lý do số liệu QA bên dưới thay đổi so với lần đo trước.

### Truy xuất (retrieval) — bộ 30 câu, gold Điều xác minh từ tiêu đề
| Chỉ số | Không rerank | Có rerank (production) |
|---|---|---|
| recall@5 | 100% | 100% |
| recall@10 | 100% | 100% |
| MRR | 0.872 | 0.836 |

### Chất lượng câu trả lời (QA kiểu ALQAC) — bộ 110 câu
| Loại | Accuracy |
|---|---|
| Đúng/Sai (31 câu) | 96.8% (30/31) |
| Trắc nghiệm A/B/C/D (29 câu) | 82.8% (24/29) |
| Tự luận – key facts (35 câu) | 74.3% (26/35) |
| **Ngoài phạm vi – từ chối đúng (15 câu)** | **100%** |
| Truy xuất đúng gold (in-scope) | 94.7% (90/95) |
| **TỔNG accuracy** | **86.4%** (95/110) |

*Model: `qwen2.5:7b-instruct` (Ollama) + cross-encoder reranker.*

> **Vì sao 89.1% (98/110) → 86.4% (95/110)** — đào sâu nguyên nhân bằng cách đọc từng câu trả lời đầy đủ (không chỉ số tổng), không đoán:
> 1. **Nguyên nhân thật, liên quan Luật Việc làm 2025**: Điều 38 luật mới gộp **4 điều kiện với 4 mốc thời gian khác nhau** (12 tháng/24 tháng, 03 tháng nộp hồ sơ, 10 ngày xét duyệt) vào **một Điều duy nhất** — cộng thêm Nghị định 374/2025 hướng dẫn (nhiều mốc ngày/tháng khác cho từng bước thủ tục) — khiến model dễ lẫn mốc thời gian nào trả lời cho câu nào (~3-4/18 câu sai).
> 2. **Bug chấm điểm đã sửa** (`scripts/eval_bhxh_qa.py::_score_mc`): regex cũ không nhận diện "đáp án **chính xác** là B" (chỉ nhận "đáp án là B") → 1 câu bị chấm sai oan dù nội dung đúng. Sửa xong đưa số liệu từ 83.6% lên 86.4%.
> 3. **Không liên quan đến việc đổi luật** (đã kiểm chứng bằng cách đọc ngữ cảnh truy xuất thật cho từng câu): phần lớn lỗi còn lại là hạn chế có sẵn từ trước — model đôi khi **bịa trích dẫn văn bản ngoài corpus** (vd "Nghị định 115/2015/NĐ-CP" không hề có trong 19 văn bản), và vài câu hỏi diễn đạt tự nhiên bị **retrieval miss hoàn toàn** (danh sách truy xuất rỗng) ở các chủ đề không liên quan luật việc làm (lương tối thiểu, trợ cấp hưu trí xã hội, xử phạt BHXH).
> 4. Đã thử siết prompt Đúng/Sai (thêm "KHÔNG giải thích") cho 1 case model viết cả đoạn văn không chứa từ "đúng"/"sai" — **không hiệu quả**, model 7B cục bộ vẫn bỏ qua ràng buộc khi ngữ cảnh phức tạp. Chấp nhận đây là trần năng lực model 7B, không phải lỗi kiến trúc.

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

### Discovery & cập nhật luật (nền Giai đoạn 2)
```bash
# a) Tìm văn bản: nhập số hiệu (hoặc từ khóa) → ứng viên URL + trạng thái để DUYỆT
python -m scripts.discover_vbpl "145/2020/NĐ-CP"     # tự tìm theo "Số hiệu" nếu là mã VB

# b) Kiểm tra corpus còn hiệu lực không → phát hiện văn bản đã bị thay thế
python -m scripts.check_corpus_freshness             # soát 19 VB trên vbpl.vn
```
> `discover_vbpl`: resolver số hiệu → URL chi tiết vbpl.vn (human-in-the-loop, không tự ingest). `check_corpus_freshness`: soát từng văn bản trong corpus, đối chiếu `trạng_thái` LIVE trên vbpl.vn → cảnh báo văn bản **Hết hiệu lực toàn bộ/một phần**. Crawler có retry cho lỗi tạm thời + bỏ nhanh trang "không tồn tại".

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
