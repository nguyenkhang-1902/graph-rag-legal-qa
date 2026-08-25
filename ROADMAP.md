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
| Corpus | 16 văn bản · 839 Điều · 2.314 Khoản — **luật hiện hành** |
| Retrieval | recall@5 = 100% (bộ 30 câu) |
| QA (92 câu, kiểu ALQAC) | TỔNG 89.1% · Đúng/Sai 100% · guardrail out-of-scope 100% |
| Engine | ChromaDB (bge-m3) + Neo4j + reranker (bge-reranker-v2-m3) + Ollama (qwen2.5:7b) |

## Lộ trình

### ✅ Giai đoạn 0 — Nền tảng BHXH (xong)
- [x] Pivot từ corpus Zalo (2021, hết hiệu lực) → BHXH hiện hành, temporal-first
- [x] Crawler Playwright (vbpl.vn) + ingest graph + embed + trích dẫn chéo
- [x] Reranker + 3 lớp guardrail chống bịa
- [x] Bộ eval retrieval + QA kiểu ALQAC (92 câu) + đo guardrail

### 🔬 Giai đoạn 0.5 — Validate kiến trúc (đang làm)
- [ ] **Ablation dense-only vs có-graph**: graph (traversal/multi-hop) có thật sự thêm giá trị? → quyết định giữ hay đơn giản hóa trước khi scale
- [ ] Nếu giữ graph: củng cố cross-doc reference (Nghị định → Luật theo tên)

### 🎯 Giai đoạn 1 — Mở rộng domain: lao động – tiền lương
- [ ] Thêm văn bản lõi: NĐ 145/2020 (hướng dẫn Bộ luật Lao động), NĐ lương tối thiểu vùng, Luật Công đoàn, thời giờ làm việc, kỷ luật lao động…
- [ ] Mở rộng bộ eval tương ứng (giữ chuẩn ALQAC)
- [ ] Nâng bộ QA lên quy mô ~200–500 câu để chỉ số đáng tin ở mức trình bày/công bố

### 🔄 Giai đoạn 2 — Cập nhật luật tự động
- [ ] Cơ chế phát hiện văn bản mới/sửa đổi trên vbpl.vn
- [ ] Tự động crawl + ingest + đánh dấu `superseded` cho văn bản hết hiệu lực
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
- Bộ eval 92 câu **curated** — đủ cho POC, chưa phải chỉ số production.
- Corpus 16 văn bản — nặng về BHXH, chưa phủ hết lao động–tiền lương.
- Cross-doc multi-hop còn yếu (trích theo tên chưa nối node).
- LLM 7b thiên vị nội tại (đôi khi viện dẫn văn bản ngoài corpus — đã bị guardrail flag).

---
*Tài liệu này cập nhật theo tiến độ. Thiết kế chi tiết ở [`docs/design/`](docs/design/).*
