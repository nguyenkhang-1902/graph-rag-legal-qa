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
- [x] E1. **32 câu hỏi multi-hop trong `data/eval/multihop_eval_set.json`** (T016) — ✅ Khang duyệt (2026-08-04). Có thể dùng chính thức cho SC-001/Phase 4.
- [x] E2. Backfill embedding GPU chỉ nhanh hơn CPU ~1.1 lần — ✅ đã chẩn đoán + fix (2026-08-05, ĐỢT 5 trong TIEN_DO.md): nguyên nhân là HF Hub network overhead khi khởi tạo model + batch không sắp xếp theo độ dài (outlier dài làm cả batch pad theo, đo được chậm 7.7 lần). Sau fix: GPU nhanh hơn CPU **7.3-8.5 lần** (đúng kỳ vọng ban đầu). Batch-size giờ tự động theo tầng độ dài (32/8/1) thay vì cố định, tránh OOM cho ~1% file cực dài trong corpus thật (quét toàn bộ 61,069 file: max 252,967 ký tự). Chưa chạy full backfill 56,911 Điều còn lại với fix mới — Khang tự chạy khi sẵn sàng.

## ✅ ĐÃ CHỐT 2026-08-06 (Khang quyết cả 5 điểm)

- [x] **F1 → chọn (a): bổ sung trích `Document.title`.** Đã làm (T025, `app/extraction/doc_identity.py`). ⚠️ **Kết quả khác kỳ vọng ban đầu, cần biết**: corpus **KHÔNG chứa tiêu đề văn bản ở đâu cả** (dataset Zalo trả về từng Điều riêng lẻ) → chỉ suy được từ **tên file**, nên `title` là **chỉ danh chuẩn** ("Thông tư 19/2016/TT-BXD"), KHÔNG phải tiêu đề văn xuôi. 3,206/3,207 văn bản map được; 98 văn bản mã hiệu Quốc hội (`qh1x`) không xác định được `loai_vb` (mã hiệu dùng chung cho Luật/Bộ luật/Nghị quyết/Pháp lệnh) → để `None`, không đoán.
- [x] **F2 → T012 ĐÓNG, không đầu tư LLM fallback.** Tìm ra nguyên nhân thật của phần bỏ sót: trigger chỉ khớp `"được hiểu như sau"` nên bỏ sót 263 file có heading `"Giải thích từ ngữ"`. Sửa bằng **1 dòng regex** → Term 5,352→**6,104**, DEFINES 6,005→**6,872**, USES_TERM 108,723→**113,888**. Chi phí ~0 so với LLM fallback (ước tính 35–85 giờ GPU).
- [x] **Mục 2 (slug) + mục 3 (độ phủ) → sửa cả hai, gộp làm MỘT task (T026)** vì cùng nguyên nhân gốc. Quy mô bug **lớn hơn con số 1,4% đã báo cáo**: chỉ 547/115,563 trích dẫn (0,47%) resolve được cross-document; 14,621 self-reference (12,7%) trỏ tới Điều không tồn tại. Sau sửa: thu hồi **2,594 edge cross-doc đúng**, loại **2,912 edge self-ref sai**.
- [x] **G1 → chọn (b) + tự đo baseline mới.** So Graph RAG với baseline Hybrid+Reranker cũ **ở quy mô 10k**, ghi rõ lệch quy mô là hạn chế đã biết; đồng thời **tự đo baseline Hybrid+Reranker mới ở 67k trong dự án này**, ghi rõ số liệu đo ở dự án mới và trình bày là **phát triển thêm** so với dự án cũ.

## ✅ H1/H2/H3 — Khang chốt "làm theo đề xuất" (2026-08-06)

- [x] **H1 → CHẠY.** Đang chạy `INGEST_BATCH_SIZE=200 python -m scripts.migrate_references data/raw --apply`. Bước 1-3 xong (REFERENCES xoá sạch, 4 Document `ð` xoá, placeholder mồ côi xoá — giữ 2 placeholder là đích AMENDS). ETA ~1h50 (đo thật 552 file/phút).
- [x] **H2 → SỬA.** Fix tại gốc `slugify_doc_name` (`normalize_eth`) chứ không sửa ở caller — đó là điểm duy nhất biến tên văn bản thành slug nên cả 2 đường tự động nhất quán. Phát hiện thêm khi kiểm tra: fix này làm **2 cặp văn bản gộp lại** (`102-2017-nd-cp`, `146-2018-nd-cp`), đã xác nhận **0 trường hợp nội dung khác nhau** nên dedup an toàn. Số Article giảm 60,679 → **60,568** là đúng ý nghĩa (111 Article đó vốn đã có bản trùng y hệt). Chỉ **8 Article** cần backfill embedding, không phải 119.
- [x] **H3 → ĐO LẠI RỒI XÉT.** Chưa sửa gì cho `mh-014`/`mh-030`; sẽ chạy `eval_graph_recall.py` sau migration, chỉ can thiệp nếu thật sự fail.

## ⚠️ Ghi nhận lỗi của Claude trong đợt này (để rút kinh nghiệm, không cần Khang quyết)

- [x] **Sai tên hàm `get_or_create_collection` → hỏng thật trên dữ liệu thật.** Tên đúng là `get_chroma_collection`. Migration crash SAU khi xoá node Neo4j nhưng TRƯỚC khi xoá Chroma → để lại 119 bản ghi Chroma mồ côi. **Gốc rễ vì sao test không bắt được**: mọi test đều inject `delete_from_chroma` nên đường code mặc định chưa bao giờ được chạy (điểm mù dependency injection). Đã sửa bằng cách **đổi cơ chế** (đối chiếu Chroma↔Neo4j, idempotent, tự sửa mọi lệch) chứ không chỉ sửa tên, + thêm test kiểm chính đường mặc định bằng `inspect.getsource`. Chi tiết: `BAO_CAO_CHI_TIET_PHIEN_LAM_VIEC.md` mục 15.
- [x] Đã dừng tiến trình `--apply` Khang tự chạy lúc 15:45 (nó nạp code trước khi có fix `ð` nên không thể ra trạng thái cuối đúng; dừng+chạy lại = 2h thay vì 3h30). Ghi lại để lần sau **thống nhất ai chạy lệnh dài** trước khi bắt đầu, tránh 2 tiến trình cùng ghi.

## 🗂️ Lịch sử: nội dung H1/H2/H3 nguyên văn (đã chốt ở trên)

- [x] **H1. Chạy migration T027 trên graph thật?** `python -m scripts.migrate_references data/raw --apply`. Cần thiết vì `upsert.py` dùng MERGE → edge sai cũ **không tự biến mất**; chạy lại ingest mà không migration sẽ cho graph chứa **cả** edge đúng lẫn edge sai (tệ hơn trước khi sửa). Sẽ xoá 37,875 REFERENCES + placeholder mồ côi rồi tạo lại. **Không mất dữ liệu nguồn** (tất cả tái tạo được từ `data/raw`); **KHÔNG đụng** Chroma/`chroma_id`, Term/DEFINES/USES_TERM, AMENDS/SUPERSEDES/CONFLICTS_WITH. Đã verify `EXPLAIN` trên Neo4j 5.26.28 + dry-run trên graph thật. Chưa rõ thời gian chạy (re-ingest 61k file). **Cho tới khi chạy, mọi số liệu đo được đều không phản ánh code hiện tại.**
- [x] **H2. 4 văn bản dùng chữ `ð` (eth) — sửa `doc_id` cho nhất quán hay chấp nhận?** `102_2017_nð-cp`, `146_2018_nð-cp`, `81_2016_nð-cp`, `89_2016_nð-cp` = **119 Article** (0,12% văn bản / 0,20% Article). `ð` (U+00F0) là chữ cái khác `đ` (U+0111) nên `slugify_doc_name` strip mất → `doc_id` thành `102-2017-n-cp`, trong khi trích dẫn viết đúng `102/2017/NĐ-CP` sinh `102-2017-nd-cp` → **4 văn bản này không bao giờ được trích dẫn chéo tìm thấy**. Chưa sửa vì đổi `doc_id` = đổi `article_id`, mà `article_id` **chính là id trong Chroma** → phải embed lại 119 Article (~11s GPU, rẻ) + cập nhật Neo4j. Rẻ nhưng là thao tác trên **khoá định danh** dữ liệu thật nên không làm ngầm. `loai_vb`/`title` của 4 văn bản này **đã đúng** (fix riêng phần nhận diện).
- [x] **H3. 2 câu eval (`mh-014`, `mh-030`) có `relationship_path` dựng trên edge sắp bị loại.** `mh-030` chính là chuỗi self-ref **sai** đã phát hiện → metadata của câu đó vốn mô tả edge **không tồn tại thật**. Đề xuất: **đo lại sau migration rồi mới xét** (T017 chấm theo `expected_article_ids`, không theo `relationship_path`, nên có thể vẫn pass) — chỉ sửa nếu thật sự fail, và ghi rõ nguyên nhân.

## 🗂️ Lịch sử: các điểm F1/F2/G1 nguyên văn (đã chốt ở trên, giữ để tra cứu)
- [x] F1. **T013 (relation_llm.py) — `Document.title` đang RỖNG trong Neo4j** (gap từ `structure_parser.py`, ĐỢT 3, chưa từng trích title thật). Case AMENDS/SUPERSEDES/CONFLICTS_WITH mà tên văn bản đích chỉ biết qua Document cha (không nêu trong chính nội dung Điều) → bế tắc thật với kiến trúc hiện tại (không rule-based, không LLM đọc 1 Điều đơn lẻ giải quyết được). Chọn 1: (a) bổ sung trích `Document.title` trước — tốn thêm thời gian nhưng phủ được nhóm case này; (b) chấp nhận bỏ qua nhóm case đó ở P1, ghi rõ hạn chế trong README/research.md.
- [x] F2. **T012 LLM fallback** — rule-based đã nâng độ phủ rất mạnh (6,065 định nghĩa). Có cần đầu tư thêm LLM fallback cho phần còn thiếu, hay chấp nhận độ phủ hiện tại và coi T012 đã đóng?
- [x] G1. **T018 — baseline Hybrid+Reranker cũ KHÔNG có số liệu ở 67k, và có khả năng KHÔNG ĐO ĐƯỢC dễ dàng ở quy mô đó**: README `rag-chatbot-document-QA` tự ghi nhận hạn chế "BM25 dùng `rank_bm25` (linear scan) — chi phí lookup tăng nhanh hơn tuyến tính theo quy mô (đo được: corpus tăng 4.86x, lookup tăng 8.6x). Cần đổi backend nếu scale vượt 10k văn bản." 67k = 6.7x so với 10k đã đo — nhiều khả năng baseline cũ chạy rất chậm hoặc cần sửa code (đổi backend BM25) trước khi đo được công bằng. 3 hướng: (a) đo lại baseline ở 67k dù chậm/cần sửa code trước; (b) so sánh Graph RAG (67k) với baseline cũ ở quy mô lớn nhất từng đo (10k), ghi rõ chênh lệch quy mô là hạn chế đã biết, không cố ép bằng nhau; (c) đo cả Graph RAG lẫn baseline ở cùng subset 10k trước cho công bằng tuyệt đối, sau đó báo cáo riêng Graph RAG ở 67k như một kết quả bổ sung (không so sánh trực tiếp).
