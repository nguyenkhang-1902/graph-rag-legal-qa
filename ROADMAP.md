# Định hướng phát triển

> Từ hỏi-đáp **BHXH** → nền tảng hỏi-đáp **pháp luật lao động – tiền lương** cho người lao động Việt Nam, dựa trên Graph RAG, ưu tiên **đúng luật hiện hành** và **có trích dẫn kiểm chứng được**.

## Tầm nhìn
Một trợ lý pháp luật đáng tin cho **người lao động phổ thông**: hỏi bằng ngôn ngữ đời thường, nhận câu trả lời **đúng luật đang có hiệu lực**, luôn kèm trích dẫn Điều/Khoản, và **thà từ chối còn hơn bịa**.

Nguyên tắc xuyên suốt:
- **Temporal-first**: chỉ trả lời theo luật hiện hành; phân biệt được luật cũ/mới.
- **Chống bịa nhiều lớp**: prompt guardrail + reranker + hậu xử lý chặn trích dẫn ngoài ngữ cảnh.
- **Đo được**: mọi thay đổi phải qua bộ eval (retrieval + QA kiểu ALQAC), không "cảm tính".
- **Validate trước khi scale**: chứng minh giá trị kiến trúc trước khi mở rộng dữ liệu.

## Trạng thái hiện tại (2026-08)
| | |
|---|---|
| Domain | BHXH (5 chế độ + thất nghiệp + TNLĐ-BNN + y tế liên quan) |
| Corpus | 19 văn bản · 995 Điều · 3.193 Khoản — **luật hiện hành** |
| Retrieval | recall@5 = 100% (bộ 30 câu) |
| QA (110 câu, kiểu ALQAC) | TỔNG 89.1% · Đúng/Sai 100% · guardrail out-of-scope 100% (gồm 18 câu lao động–tiền lương) |
| Engine | ChromaDB (bge-m3) + Neo4j + reranker (bge-reranker-v2-m3) + Ollama (qwen2.5:7b) |

## Lộ trình

### ✅ Giai đoạn 0 — Nền tảng BHXH (xong)
- [x] Pivot từ corpus Zalo (2021, hết hiệu lực) → BHXH hiện hành, temporal-first
- [x] Crawler Playwright (vbpl.vn) + ingest graph + embed + trích dẫn chéo
- [x] Reranker + 3 lớp guardrail chống bịa
- [x] Bộ eval retrieval + QA kiểu ALQAC (92 câu) + đo guardrail

### ✅ Giai đoạn 0.5 — Validate kiến trúc (xong)
- [x] **Cross-doc name-alias**: trích "Điều X của Luật BHXH" (không kèm năm) trước đây bị gán nhầm cho văn bản hiện tại → thêm `doc_aliases` map tên luật → doc_id. Cross-doc NĐ→Luật resolve: **1 → 171 cạnh**.
- [x] **Ablation dense-only vs có-graph**: graph **thêm giá trị thật ở multi-hop** — recall@10 (câu multi-hop) **57% → 71%** khi bật graph; MRR 0.41 → 0.51 khi thêm reranker. → **Giữ graph** (xứng đáng, nhất là khi corpus nhiều tham chiếu chéo hơn).

### 🎯 Giai đoạn 1 — Mở rộng domain: lao động – tiền lương
- [x] Thêm văn bản lõi: NĐ 145/2020 (hướng dẫn Bộ luật Lao động), NĐ 293/2025 (lương tối thiểu vùng), NĐ 219/2025 (NLĐ nước ngoài) → corpus 16 → **19 văn bản**
- [x] Mở rộng bộ eval tương ứng (giữ chuẩn ALQAC): **+18 câu lao động–tiền lương** (92 → 110 câu) — TỔNG accuracy giữ **89.1%**
- [ ] Nâng bộ QA lên quy mô ~200–500 câu để chỉ số đáng tin ở mức trình bày/công bố
- [ ] **Known-issue:** NĐ 145/2020 `dieu-1..11` bị phụ lục "Mẫu HĐLĐ" ghi đè (structure parser bắt nhầm phụ lục là Điều) — cần lọc phụ lục "Mẫu số…"

### 🔄 Giai đoạn 2 — Cập nhật luật tự động
- [x] **Nền discovery** (`scripts/discover_vbpl.py`): resolver số hiệu → URL chi tiết vbpl.vn (tìm theo "Số hiệu" chính xác), kèm `trạng_thái` hiệu lực — human-in-the-loop. Crawler thêm retry/backoff + bỏ nhanh trang "không tồn tại" (`fetch_bhxh_corpus.py`).
- [x] **Phát hiện văn bản hết hiệu lực** (`scripts/check_corpus_freshness.py`): soát từng văn bản corpus ↔ trạng_thái LIVE vbpl.vn. **Chạy thật (2026-08-26): 3/19 hết hiệu lực TOÀN BỘ** — Luật Việc làm 38/2013, TT 20/2023, NĐ 75/2024 — + 5 hết hiệu lực một phần. → cần tìm văn bản thay thế.
- [ ] Tự động crawl + ingest + đánh dấu `superseded` cho văn bản hết hiệu lực (dùng freshness ở trên làm đầu vào)
- [ ] Temporal Resolver: cảnh báo khi có chuyển tiếp luật

### 🕸️ Giai đoạn 3 — Cross-doc multi-hop
- [ ] Name-alias resolution (trích "Luật Bảo hiểm xã hội" theo tên → nối đúng node)
- [ ] Đo lại đóng góp multi-hop sau khi cross-doc resolve tốt

### 🖥️ Giai đoạn 4 — Sản phẩm hóa
- [ ] Giao diện hỏi-đáp (hiển thị câu trả lời + trích dẫn + cảnh báo)
- [ ] Cảnh báo pháp lý rõ ràng ("không thay thế tư vấn chính thức")
- [ ] Cân nhắc nâng tầng LLM (Claude/GPT qua API) khi cần chất lượng cao hơn (7b bị giới hạn phần cứng 8GB VRAM)

## Quyết định kiến trúc đã chốt (rationale)
- **Thu hẹp domain thay vì 61k văn bản tả pí lù (Zalo)**: dữ liệu nhỏ + đúng > dữ liệu lớn + lỗi thời. recall@5 = 100% chứng minh hướng này.
- **doc_id slugified thống nhất**: để reference/embedding/graph cùng một khóa (giải quyết mismatch cross-doc).
- **Reranker chạy CPU**: GPU 8GB đã cạn với bge-m3 + Ollama; reranker CPU (~vài giây/câu) chấp nhận được.
- **Guardrail hậu xử lý**: LLM 7b vẫn bịa dù prompt cấm → cần lớp deterministic ngoài LLM cho sản phẩm luật.

## Giới hạn đang có (trung thực)
- Bộ eval 110 câu **curated** — đủ cho POC, chưa phải chỉ số production.
- Corpus 19 văn bản — đã có lõi lao động–tiền lương, chưa phủ hết (thiếu Luật Công đoàn, NĐ tuổi nghỉ hưu, thang bảng lương).
- Discovery vbpl.vn: resolver số-hiệu→URL đã chạy, nhưng **tìm văn bản MỚI diện rộng** vẫn thủ công (search theo từ khóa, chưa quét danh mục tự động).
- LLM 7b có trần năng lực: đôi khi **trích sai số** (trắc nghiệm) hoặc **viện dẫn văn bản ngoài corpus** (tự luận — đã bị guardrail flag).
- NĐ 145/2020 `dieu-1..11` lẫn phụ lục "Mẫu HĐLĐ" (xem GĐ1 known-issue).

---
*Tài liệu này cập nhật theo tiến độ. Thiết kế chi tiết ở [`docs/design/`](docs/design/).*
