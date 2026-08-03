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
