# 📋 Báo cáo chi tiết phiên làm việc — Phase 1 (engine gốc, 2026-08-05 → 08-06)

> **File này là nhật ký TDD đỏ→xanh chi tiết theo từng bước** của 2 phiên làm
> việc dài (chẩn đoán GPU, T012/T013/T025/T026/T027) trên corpus Zalo 67k —
> **đã xoá khỏi đĩa** khi pivot sang BHXH (2026-08-20+). Nội dung đã được đúc
> kết ở mức cô đọng hơn tại `TIEN_DO.md` (dòng thời gian) và
> `specs/001-graph-rag-core/research.md` (ADR + sổ bẫy tổng quát hoá được) —
> đọc 2 file đó trước. File này chỉ còn giữ lại vài chi tiết narrative không
> lặp lại ở nơi khác, cho mục đích tham khảo quy trình làm việc.

## Điểm còn giá trị tham khảo, không lặp ở TIEN_DO.md/research.md

- **Quy trình chẩn đoán GPU chậm** (phiên 1, mục 2-6 bản gốc): dùng skill `systematic-debugging` + `cProfile` trên mẫu 128 file thật trước khi sửa bất kỳ dòng code nào — không đoán nguyên nhân rồi thử. Đây là ví dụ cụ thể áp dụng quy trình 4 pha (root cause → pattern → hypothesis → implementation) cho một bug hiệu năng, không phải bug logic.
- **Cách mở rộng `term_extractor.py` qua nhiều vòng** (phiên 1, mục 8-11): mỗi vòng đều bắt đầu bằng khảo sát dữ liệu thật (đếm file có mẫu X trước khi viết regex cho mẫu đó), không viết regex rồi mới kiểm tra độ phủ ngược lại.
- **T025/T026 (phiên 2, mục 2-7)**: trước khi thiết kế giải pháp, chạy 3 script khảo sát riêng (khảo sát mã hiệu, khảo sát độ phủ trích dẫn, thử-và-loại phương án từ điển tên→số hiệu) — quyết định kỹ thuật cuối cùng chỉ viết SAU khi có đủ số liệu khảo sát, không phải trước.
- **Thứ tự triển khai H1/H2 có chủ đích** (phiên 2, mục 12): làm H2 (sửa `doc_id` chữ `ð`) TRƯỚC H1 (chạy migration) dù không ai yêu cầu thứ tự — vì đổi `doc_id` sau migration sẽ cần re-ingest 2 lần thay vì 1 lần. Ví dụ về việc tự suy luận phụ thuộc giữa các task trước khi thực thi, không làm theo đúng thứ tự liệt kê máy móc.

## Số liệu/file đã tạo trong 2 phiên (tham khảo nhanh)

Toàn bộ đã đúc kết vào `TIEN_DO.md` ĐỢT 5-12. Các module chính tạo trong 2 phiên này: `app/extraction/term_extractor.py` (T012), `app/extraction/relation_llm.py` (T013), `app/extraction/doc_identity.py` (T025), `scripts/migrate_references.py` (T027), cùng các test TDD tương ứng.
