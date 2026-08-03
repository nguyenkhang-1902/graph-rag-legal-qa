# 🚦 Quickstart — Nghiệm thu thủ công Graph RAG Legal QA

Chạy sau khi implement xong từng nhóm task trong `tasks.md`. Mỗi bước: hành động → kết quả mong đợi → mã tham chiếu.

## 🧱 Nhóm 1 — Sau Phase 2 (Foundational)

1. Chạy `python -m app.ingest data/raw --limit 10` → graph xuất hiện trong Neo4j Browser (`http://localhost:7474`) với đúng Document/Chapter/Article theo 10 văn bản mẫu. ✔ FR-001
2. Mở 1 Article có câu trích dẫn rõ ("theo quy định tại Điều 5...") → kiểm tra có relationship `REFERENCES` trỏ đúng node đích. ✔ FR-002
3. 🆕 Chạy `python -m app.ingest data/raw --limit 100`, `kill -9` tiến trình giữa batch thứ 2-3, chạy lại lệnh y nguyên → log báo "resume từ batch N", không ingest lại batch đã xong, không có `Article` trùng `article_id` trong Neo4j. ✔ FR-008, SC-005, User Story 4

## 🔍 Nhóm 2 — Sau Phase 3 (User Story 1)

1. Gọi `POST /chat` với 1 câu hỏi multi-hop đã biết trước đáp án (từ `build_multihop_eval_set.py`) → câu trả lời trích đúng cả 2 điều luật liên quan, kèm citation path hiển thị được. ✔ AS-1 US1
2. Gọi với câu hỏi chỉ cần 1 điều luật → câu trả lời không kéo dư ngữ cảnh không liên quan. ✔ AS-2 US1
3. Hỏi 1 câu có REFERENCES trỏ ra ngoài corpus → hệ thống báo rõ "không có trong corpus", không bịa nội dung. ✔ Edge case spec.md

## 📊 Nhóm 3 — Sau Phase 4 (User Story 2)

1. Chạy `python scripts/eval_graph_recall.py` trên **toàn bộ 67k** → có Recall@4, MRR ghi ra file/console, đối chiếu SC-002 (không thấp hơn Hybrid+Reranker cùng quy mô quá 5 điểm %). ✔ SC-002
2. Chạy `python scripts/bench_latency.py` → có p95 latency, đặt cạnh bảng cũ trong README. ✔ SC-003

## 🔁 Nhóm 4 — Sau Phase 5 (User Story 3)

1. Thêm 1 văn bản mới vào `data/raw`, chạy `python -m app.ingest data/raw --incremental`, bấm giờ → hoàn tất < 5 phút. ✔ SC-004
2. Kiểm tra Neo4j — không có node `Article` trùng `article_id` sau khi ingest tăng dần. ✔ AS-1 US3

Dự án không có RBAC/multi-role — bỏ qua bước tạo user test theo role. Không có UI riêng — nghiệm thu qua API (curl/Postman) + Neo4j Browser.
