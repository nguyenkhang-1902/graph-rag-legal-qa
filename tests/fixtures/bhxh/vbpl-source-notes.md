# Ghi chú nguồn vbpl.vn (Task 1 spike — 2026-08-20)

## Kết luận then chốt
- vbpl.vn (CSDL quốc gia về pháp luật) là **Next.js App Router + React Server Components**.
- Trang chi tiết văn bản **render nội dung bằng JS** (client hydration). `curl`/`requests` thuần trả về **shell 59KB không có text luật** (0 khớp "Phạm vi điều chỉnh"/"Điều 2"/ngày hiệu lực).
- ⇒ **Crawler PHẢI dùng headless browser (Playwright)** để render rồi trích text. KHÔNG dùng `requests` thuần được. (Đây là sửa đổi so với plan gốc dự kiến requests + BeautifulSoup.)

## URL & định danh
- Trang chi tiết: `https://vbpl.vn/van-ban/chi-tiet/<id>` (id = UUID hoặc số).
- **Luật BHXH 2024 (41/2024/QH15) — bản gốc:** `https://vbpl.vn/van-ban/chi-tiet/f72d2940-8fe9-11f1-bc12-7960f397c73a`
- Bản hợp nhất (VBHN 19/VBHN-VPQH, chứa Luật BHXH hợp nhất): `.../van-ban-hop-nhat-so-19-vbhn-vpqh-2026-...--ff9cd9e0-97aa-11f1-a50f-4bcbcb89bfc0`
- Trang chủ có ô tìm kiếm (autocomplete theo nội dung). Bộ lọc "Số hiệu" tìm theo mã văn bản.

## Cấu trúc trang chi tiết (các tab)
- **Nội dung**: toàn văn — render đúng cấu trúc `Chương` → `Điều N. <tiêu đề>` → khoản `1.` `2.` → điểm `a)` `b)`. Khớp thẳng với `structure_parser.parse_document()` hiện có.
- **Thuộc tính**: bảng metadata nhãn→giá trị:
  - `Số hiệu`, `Loại văn bản`, `Ngày ký xác thực`, `Ngày có hiệu lực`, `Ngày hết hiệu lực`, `Cơ quan ban hành`, `Người ký`, `Ngành`, `Lĩnh vực`.
  - (VBHN không có "Ngày có hiệu lực" riêng → `--`; Luật gốc 41/2024 có "Ngày có hiệu lực" = 01/7/2025.)
- **Lược đồ**: quan hệ văn bản (sửa đổi/thay thế/hết hiệu lực) — nguồn cho quan hệ `SUPERSEDES`.
- **Văn bản gốc**, **Tải về**: có thể có bản tải (chưa khảo sát kỹ — subagent xác minh).
- Ngày hiệu lực cũng nằm trong **text mở đầu**: "…số 41/2024/QH15 ngày 29 tháng 6 năm 2024… có hiệu lực kể từ ngày 01 tháng 7 năm 2025".

## Ảnh hưởng tới plan
- **Task 2 (parser)**: input là **text đã render** (từ Playwright `page.inner_text` của vùng nội dung), KHÔNG phải HTML thô + BeautifulSoup selector. Vẫn đưa qua `parse_document()`.
- **Task 5 (crawler)**: dùng Playwright. Bước: mở URL → chờ render → tab "Nội dung" lấy text toàn văn; tab "Thuộc tính" lấy metadata; tab "Lược đồ" lấy quan hệ. Thêm dependency `playwright` vào `requirements`.
- Fixture parser: `tests/fixtures/bhxh/luat-bhxh-2024-excerpt.txt` (text thật Điều 1–2, đủ để TDD parser mà không phụ thuộc mạng).
