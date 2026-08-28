# ✅ CHECKLIST CHỜ DUYỆT — Phase 1 (engine gốc, corpus Zalo 67k)

> **Lịch sử, không còn là checklist sống.** Corpus Zalo 67k đã xoá khi pivot
> sang BHXH (2026-08-20+). Điểm chờ duyệt hiện tại của giai đoạn BHXH nằm
> trong `ROADMAP.md` (mục "Giới hạn đang có") — không dùng file này nữa.

## Đã chốt trong Phase 1 (tóm tắt)
- `MAX_HOP=2`, Article rút gọn + `chroma_id` trỏ Chroma, quy mô 67k + batch/savepoint, không làm UI riêng (API + Neo4j Browser đủ).
- 32 câu multi-hop eval — Khang duyệt (2026-08-04).
- 5 điểm treo (T025 `Document.title`, T012 đóng không cần LLM fallback, T026 sửa slug, G1 cách so baseline) — Khang chốt 2026-08-06, chi tiết đầy đủ ở `TIEN_DO.md`.
- H1/H2/H3 (chạy migration T027, sửa `doc_id` cho 4 văn bản chữ `ð`, xử lý 2 câu eval có edge sai) — Khang chốt "làm theo đề xuất" 2026-08-06, đã chạy xong 2026-08-07.

## ⚠️ Lỗi thật của Claude (rút kinh nghiệm, chi tiết ở `research.md` sổ bẫy)
Sai tên hàm `get_or_create_collection` (đúng: `get_chroma_collection`) làm hỏng 119 bản ghi Chroma thật khi chạy migration — test không bắt được vì mọi test đều inject/mock đúng hàm đó (đường code mặc định chưa từng chạy). Sửa bằng cách đổi hẳn cơ chế sang reconcile 2 chiều (idempotent) thay vì chỉ sửa tên hàm.

## Các câu hỏi CHƯA được trả lời trước khi pivot (giờ đã moot, ghi lại để không lặp lại nhầm lẫn)

Ba điểm dưới đây (I1/J1-J2/K1-K2) đang chờ Khang quyết thì dự án pivot sang BHXH — **không bao giờ được đóng chính thức trên corpus Zalo**. Ghi lại nguyên trạng vì bài học vẫn dùng được:

- **I1 — Graph traversal chỉ đóng góp +3.1 điểm % (1/58 câu) vào Recall** trên bộ 32 câu — nghi vấn trực tiếp luận điểm cốt lõi "Graph RAG hơn Hybrid nhờ multi-hop". **Cập nhật quan trọng**: câu hỏi này **đã được trả lời lại trên corpus BHXH** ở giai đoạn sau — `ROADMAP.md` "Giai đoạn 0.5" đo ablation multi-hop cho kết quả graph **thêm giá trị thật** (recall@10 57%→71% khi bật graph, sau khi fix cross-doc name-alias resolve 1→171 cạnh). Bài học giữ lại: **một bộ câu hỏi eval soạn từ chuỗi trích dẫn thật KHÔNG tự động kiểm tra được khả năng multi-hop** nếu câu hỏi chứa đủ manh mối để dense tìm thẳng ra đáp án — phải cố tình lọc/soạn câu mà dense-only thất bại.
- **J1 — `SIMILARITY_THRESHOLD=0.65` làm mất 12.3 điểm % Recall trên tập lớn** (789 câu) dù đã qua xác minh nghiêm ngặt trên tập nhỏ (32 câu). Bài học đã chuyển vào `research.md` ADR-004.
- **K1 — Bug `clause_id` trùng làm mất 4,149 Clause (2.4%)** do parser coi mọi dòng đánh số là Khoản mới kể cả khi Điều trích lại nguyên văn Điều khác. Không ảnh hưởng chức năng lúc đó (Clause không dùng trong retrieval) nhưng là nợ kỹ thuật chưa trả trước khi corpus bị xoá.
- **K2 — Chưa từng đo precision/chất lượng câu trả lời qua `/chat`** trong toàn bộ Phase 1 — mọi quyết định (ngưỡng similarity, giới hạn ngữ cảnh) đều dựa thuần trên recall. Giai đoạn BHXH đã lấp khoảng trống này bằng `eval_bhxh_qa.py` (QA kiểu ALQAC, có LLM chấm điểm) — bài học được áp dụng đúng ở giai đoạn sau.
