# ✅ CHECKLIST CHỜ DUYỆT — Graph RAG Legal QA

## A. 👀 Nhìn nhanh mỗi tài liệu (render, đọc lướt)
- [x] A1. `constitution.md` — ✅ Khang xác nhận ổn (2026-08-03)
- [x] A2. `data-model.md` — ✅ Khang xác nhận ổn (2026-08-03)
- [x] A3. `tasks.md` — ✅ Khang xác nhận ổn (2026-08-03)

## B. 🧩 Quyết định kỹ thuật cần chốt
- [x] B1. `MAX_HOP` mặc định = **2** — ✅ đã giải thích & chốt (spec.md FR-005)
- [x] B2. Article node: **rút gọn + `chroma_id`** trỏ Chroma (không lưu full text trong Neo4j) — ✅ đã giải thích & chốt (data-model.md)
- [x] B3. AMENDS/SUPERSEDES/CONFLICTS_WITH — ✅ chốt: làm ngay từ đầu ở P1, không dời P2
- [x] B4. Tập câu hỏi multi-hop (SC-001) — ✅ chốt: Claude soạn từ corpus thật, Khang duyệt lại trước khi dùng chính thức

## C. 📥 Quyết + đầu vào
- [x] C1. Quy mô dữ liệu — ✅ chốt: **toàn bộ 67k văn bản**, ingest theo batch + savepoint (không phải 2k/10k như đề xuất ban đầu)
- [x] C2. UI — ✅ chốt: **API + Neo4j Browser là đủ**, không làm Streamlit ở P1

## 🆕 Điểm mới phát sinh khi triển khai quy mô 67k (cần theo dõi, không phải chờ duyệt ngay)
- [ ] D1. `INGEST_BATCH_SIZE` khởi điểm đề xuất 200 văn bản/batch (`research.md` ADR-002) — sẽ điều chỉnh sau khi đo throughput thật trên 100-200 văn bản đầu, báo Khang số liệu trước khi chạy full 67k.
- [ ] D2. Nếu baseline Hybrid+Reranker project trước chưa từng đo ở quy mô 67k (chỉ có số liệu 2k/10k) — cần chạy lại baseline ở 67k trước khi so sánh (SC-002/SC-003), không so lệch quy mô. Xác nhận với Khang khi tới Phase 4.

**Tất cả mục A/B/C đã chốt — sẵn sàng bắt đầu `tasks.md` Phase 1 (T001).**

## 🆕 Điểm phát sinh khi triển khai Phase 3 (2026-08-04, chưa chặn tiến độ)
- [ ] E1. **32 câu hỏi multi-hop trong `data/eval/multihop_eval_set.json`** (T016) — do Claude soạn trực tiếp từ nội dung thật trong corpus đã ingest (đọc-hiểu thủ công, không dùng LLM/API tự động sinh câu hỏi). Chưa dùng chính thức cho SC-001/Phase 4 cho tới khi Khang xem lại — đặc biệt các `expected_article_ids` có đúng là điều luật cần thiết để trả lời hay không. Không chặn việc tiếp tục code (T012/T013) — chỉ cần duyệt trước khi dùng số liệu này làm tiêu chí nghiệm thu.
- [ ] E2. Backfill embedding GPU chỉ nhanh hơn CPU ~1.1 lần (không như kỳ vọng 5-8x) — nếu muốn tăng tốc thêm để chạy full 60k nhanh hơn, cần Khang quyết có đáng thử nghiệm `--batch-size` lớn hơn hay chấp nhận tốc độ hiện tại (ước tính still ~13-15 giờ cho phần còn lại ở GPU so với ~25h thuần CPU).
