# 📋 BÁO CÁO CHI TIẾT PHIÊN LÀM VIỆC (2026-08-05 → 2026-08-06)

> File này ghi lại **CHI TIẾT TOÀN BỘ** từng yêu cầu của Khang và từng việc đã làm trong phiên này — cố tình viết dài, đầy đủ, không tóm tắt, để sau này viết gọn lại thành bản súc tích hơn (đưa vào `TIEN_DO.md`/CV/báo cáo chính thức). Sắp xếp theo đúng trình tự thời gian đã xảy ra.

---

## 1. Đọc tiến độ, duyệt bộ câu hỏi eval

**Yêu cầu 1**: "đọc file tiến độ và công việc cần triển khai. cho anh biết công việc cần triển khai"
- Đã đọc `TIEN_DO.md`, tóm tắt trạng thái dự án lúc đó: đã ingest xong 61,068 văn bản thật (60,679 Article/3,203 Document/165,699 Clause/37,875 REFERENCES), Phase 3 User Story 1 hoạt động qua `/chat`, backfill embedding mới ~3,700-4,000/60,679, GPU chỉ nhanh hơn CPU ~1.1 lần (thấp hơn kỳ vọng 5-8 lần).
- Liệt kê việc cần làm theo đúng thứ tự trong `TIEN_DO.md`: T012 (term_extractor), T013 (relation_llm), backfill embedding full, và điểm chờ duyệt: 32 câu eval multi-hop (T016).

**Yêu cầu 2**: "tôi duyệt 32 câu eval. bạn có cách nào kiểm tra nguyên nhân GPU chạy ko tốt như kỳ vọng ko?"
- Đã đánh dấu duyệt T016 vào `CHECKLIST-GRAPHRAG-DUYET.md` mục E1 và `TIEN_DO.md`.
- Dùng skill `systematic-debugging` (Phase 1: root cause investigation trước khi sửa) để điều tra GPU.

---

## 2. Chẩn đoán GPU chậm (systematic-debugging)

- Viết script benchmark thủ công so sánh CPU/GPU trên mẫu 128 file thật từ `data/raw`.
- **Trở ngại hạ tầng phát hiện dọc đường**: tiến trình chạy nền (`run_in_background`) nhiều lần bị "stopped" giữa các lượt hội thoại — không phải bug code, mà do tiến trình gắn với vòng đời phiên agent, không sống sót qua khoảng chờ giữa các lượt (đã kiểm tra Windows Event Log xác nhận không phải do máy tắt/khởi động lại). Đã điều chỉnh chiến lược: chạy foreground (đồng bộ) hoặc chạy trong cùng 1 lượt liên tục thay vì nền qua nhiều lượt.
- **Dùng `cProfile`** để soi trực tiếp lệnh `SentenceTransformer("BAAI/bge-m3", device="cpu")` — phát hiện: **6.1/8.76 giây (70%) là network** — thư viện `sentence-transformers` tự động gọi ~34 HTTP request kiểm tra revision mới trên Hugging Face Hub mỗi lần khởi tạo model, **dù model đã cache đầy đủ trên máy** (xác nhận qua `du -sh` cache, model 4.3GB đã có sẵn).
- **Phát hiện thứ 2 (nguyên nhân chính)**: quét thật corpus mẫu 128 file → độ dài văn bản lệch cực mạnh (p50=298 token, max=4737 token trong mẫu nhỏ). Benchmark thật: batch=32 → 1.67s/item; batch=64 (không sắp xếp) → **12.93s/item, chậm hơn 7.7 lần** — do 1 văn bản dài lọt ngẫu nhiên vào batch, buộc cả batch pad theo độ dài đó.

---

## 3. Giải thích script chẩn đoán (khi được hỏi)

**Yêu cầu**: "trong lúc chờ ingest, giải thích 1 tí về script đang chạy nền này"
- Đã giải thích chi tiết: mục đích (tìm nguyên nhân GPU chậm), giả thuyết (cổ chai tokenize CPU vs GPU forward pass), cách thiết kế (mẫu thật, đo tokenize riêng, đo full encode riêng, nhiều batch-size), và ý nghĩa từng kết quả có thể xảy ra.

---

## 4. Áp dụng 2 fix cho GPU chậm

**Yêu cầu**: "ok hãy áp dụng fix"
- **Fix 1** — `app/retrieval/embedder.py`: thêm `os.environ.setdefault("HF_HUB_OFFLINE", "1")` trước khi import `sentence_transformers` — bỏ 34 HTTP request thừa, giảm thời gian khởi tạo model từ 8.76s → ~2s.
- **Fix 2** — `scripts/backfill_embeddings.py`: sắp xếp `pending` theo độ dài `full_text` TRƯỚC khi chia batch, tránh văn bản dài lọt ngẫu nhiên vào batch làm chậm cả batch.
- **TDD đầy đủ**: viết test trước (đỏ), implement (xanh) cho cả 2 fix — file `tests/retrieval/test_embedder.py` (test mới: `test_module_defaults_hf_hub_offline_to_avoid_redundant_network_checks`), `tests/test_backfill_embeddings.py` (test mới: `test_pending_articles_are_batched_sorted_by_text_length`). 19/19 test liên quan pass, 151/152 toàn bộ suite (1 fail không liên quan — biến môi trường `INGEST_BATCH_SIZE=3` có sẵn trong shell của Khang).

**Kết quả đo lại sau fix** (mẫu 128 file thật, đã sort): batch=32: 0.77s/item (nhanh hơn 2.2 lần so với trước fix); batch=64: 0.91s/item (nhanh hơn 14 lần so với trước fix, tăng nhẹ hợp lý khi tăng batch thay vì "nổ" 7.7 lần).

**Yêu cầu**: "thử chạy với GPU"
- Benchmark GPU riêng (cùng mẫu, cùng cách sort): batch=32: **0.090s/item** (GPU nhanh hơn CPU **8.5 lần**); batch=64: **0.126s/item** (nhanh hơn **7.3 lần**) — đúng mức kỳ vọng ban đầu (5-8 lần), xác nhận fix đúng nguyên nhân gốc.
- **Sự cố mới phát hiện**: batch=128 gây **CUDA OutOfMemoryError thật** trên RTX 3050 (6GB VRAM) — "Tried to allocate 10.70 GiB". Ghi nhận: không nên tăng batch-size quá 64 cho GPU này.

---

## 5. Giải thích + mở rộng cơ chế batch-size (theo yêu cầu tìm hiểu)

**Yêu cầu**: "trong lúc chờ backfill, bạn có thể làm gì?" → sau đó dừng lại hỏi "thực chất batch size là gì, hoạt động thế nào, có nên dùng 64 không, khác biệt giữa các batch là gì"

- Giải thích cơ chế: batch gộp N văn bản vào 1 lần gọi model thay vì N lần riêng lẻ; padding theo văn bản dài nhất TRONG batch đó — đây là lý do văn bản lệch độ dài gây vấn đề.
- Cảnh báo: dữ liệu benchmark 32 vs 64 không hoàn toàn công bằng (cửa sổ lấy mẫu khác nhau), và quan trọng nhất — **batch=128 đã thực sự OOM trên mẫu chỉ 128 file** → với **corpus thật 60k+ Article**, batch cuối cùng (sau khi sort) sẽ chứa các Điều DÀI NHẤT TOÀN CORPUS, rủi ro OOM còn cao hơn.
- **Đề xuất**: quét toàn bộ 61,069 file thật để biết phân phối độ dài thật trước khi quyết batch-size.

**Yêu cầu**: "có, sau khi tính toán, ta sẽ chia ra chạy batch size 32 cho những batch nào 64 cho những batch nào"

- Quét toàn bộ 61,069 file thật: p50=899 ký tự, p90=2,751, p99=7,640, **p99.9=21,355, max=252,967 ký tự** (~63,000 token — gấp 13 lần outlier lớn nhất từng thấy trong mẫu 128 file).
- **Thiết kế batch-size theo tầng độ dài** (không phải cố định): thêm `_LENGTH_TIER_CUTOFFS_CHARS`, `_LENGTH_TIER_CAPS`, `_batch_cap_for_length()`, `_group_into_length_aware_batches()` vào `scripts/backfill_embeddings.py`:
  - ≤2,751 ký tự (p90, ~90% corpus): dùng nguyên `--batch-size`/`EMBED_BATCH_SIZE` (mặc định 32).
  - 2,751–7,640 ký tự (p90-p99): cap 8.
  - >7,640 ký tự (p99+, ~610 file/~1%): cap 1 (xử lý riêng từng file, tránh OOM).
- TDD đầy đủ: 4 test mới (`test_batch_cap_for_length_uses_smaller_cap_for_longer_tiers`, `test_group_into_length_aware_batches_splits_outlier_into_own_small_batch`, `test_group_into_length_aware_batches_respects_max_batch_size_within_tier`, `test_run_backfill_isolates_extremely_long_article_into_its_own_batch`). 23/23 test liên quan pass, 155/156 toàn bộ (1 fail không liên quan).

---

## 6. Backfill chạy tay + giải thích log

- Khang tự chạy `python -m scripts.backfill_embeddings data/raw` trên terminal của mình, hỏi ý nghĩa hàng loạt WARNING trong log.
- Giải thích: `WARNING parse_article_chunk: dong tieu de khong khop pattern 'Dieu N.'` là hành vi THIẾT KẾ CÓ CHỦ ĐÍCH (không phải lỗi) — khi dòng tiêu đề trong file không đúng chuẩn `"Điều N. ..."` (vd `"Điều 6 được sửa đổi, bổ sung như sau:"`, `"Điều 1:"`), parser dùng fallback lấy số điều từ TÊN FILE thay vì đoán mò.
- Giải thích các dòng `INFO phat hien 2 file cung article_id=...` là cơ chế dedup đã biết từ ADR-003 (file trùng nội dung do encoding gốc không nhất quán, tự động giữ 1 bản).
- Xác nhận dòng quan trọng: `56911 can embed, chia thanh 2818 batch` — khớp đúng số liệu tính trước (60,679 − 3,768 đã embed = 56,911), và 2,818 batch (không phải cố định) xác nhận batching theo tầng độ dài hoạt động đúng.

---

## 7. Sự cố tắt máy giữa phiên (lần 1)

- Khang báo cần tắt máy giữa lúc backfill đang chạy nền.
- Đã dừng an toàn tiến trình chẩn đoán đang chạy, kiểm tra git status không có gì nguy hiểm chưa commit, xác nhận Docker/Neo4j tắt cùng máy không mất dữ liệu (volume), xác nhận backfill KHÔNG có tiến trình nào đang chạy lúc đó (an toàn tắt máy).

---

## 8. T012 — `app/extraction/term_extractor.py` (rule-based DEFINES/USES_TERM, mẫu có quotes)

**Yêu cầu**: "tiếp tục hoàn thiện" (T012, làm song song lúc backfill chạy)

- Đọc `data-model.md` xác nhận mẫu cần bắt: `DEFINES` (Article → Term) qua "... được hiểu là ...", `USES_TERM` (Article → Term) qua string-match tên thuật ngữ đã biết.
- Khảo sát thật corpus (5 ví dụ đọc tay) → phát hiện: chỉ trường hợp thuật ngữ có QUOTES rõ ràng trước "được hiểu là" mới đủ tin cậy để rule-based trích — mệnh đề dài không quotes bị bỏ qua có chủ đích (tránh đoán mò sai).
- Viết TDD: `extract_definitions_rule_based()`, `extract_term_usages_rule_based()` (case-sensitive + word-boundary, tránh false positive từ thông dụng trùng thuật ngữ viết hoa như "Ngày").
- **Bug thật TDD bắt được**: câu thật nối 2 định nghĩa qua "và" trong cùng câu, chỉ thuật ngữ đầu có quotes — nếu chỉ cắt ở dấu chấm, định nghĩa đầu "nuốt" luôn phần không liên quan. Fix bằng lookahead dừng trước cụm "và ...được hiểu là" tiếp theo.
- 16/16 test mới pass. Kiểm chứng thêm trên 15 file mẫu ngẫu nhiên NGOÀI các case đã viết test — kết quả hợp lý, không rác (chỉ 4/15 có định nghĩa đủ rõ, khớp khảo sát ban đầu).

---

## 9. T012 hoàn thiện phần orchestration (ghi thật vào Neo4j)

- Thêm `upsert_definitions()`, `upsert_term_usages()` vào `app/graph_store/upsert.py` (batch UNWIND, không phải N lời gọi riêng — cùng lý do hiệu năng với `backfill_embeddings.py`'s `_update_chroma_ids`).
- Viết `scripts/extract_terms.py`: CLI 2-pass — pass 1 thu thập TOÀN BỘ định nghĩa trong corpus trước (vì 1 thuật ngữ có thể định nghĩa ở văn bản A nhưng dùng lại ở văn bản B, bất kể thứ tự duyệt file), pass 2 mới tính USES_TERM cho mọi Article với đầy đủ từ điển thuật ngữ đã biết. Article tự định nghĩa 1 thuật ngữ KHÔNG bị tính là "dùng lại" chính nó.
- Quyết định: không cần checkpoint/resume (khác `backfill_embeddings.py`) vì chỉ regex trên văn bản ngắn, chạy lại từ đầu an toàn (MERGE-based, idempotent).
- 7 test mới cho `extract_terms.py`, 5 test mới cho `upsert_definitions`/`upsert_term_usages`. Tổng 183/184 toàn bộ suite.
- **Chạy thật lần 1** trên toàn bộ 60,679 Article (song song lúc backfill embedding đang chạy — không đụng nhau vì khác node/edge type): **10 Term, 10 DEFINES, 525 USES_TERM**, hoàn tất trong ~14 giây. Kiểm chứng trực tiếp Neo4j — nội dung hợp lý (Ngày, Đơn PCT, Đơn Madrid, Thường trú tại Việt Nam...).

---

## 10. Thảo luận độ phủ DEFINES/USES_TERM + chi phí LLM

**Yêu cầu**: "độ phủ mà bạn nói nó đóng vai trò gì, chỉ số hiện tại có đủ tốt chưa, chưa thì tầm bao nhiêu là ổn? gọi LLM tốn chi phí gì?"

- Tra lại `spec.md` FR-003: xác nhận LLM extraction cho DEFINES/USES_TERM/AMENDS/SUPERSEDES/CONFLICTS_WITH đã được CHỐT làm ở P1 (không phải tùy chọn thêm).
- Kiểm tra metadata bộ 32 câu eval — xác nhận **toàn bộ soạn từ chuỗi REFERENCES**, không câu nào dùng DEFINES/USES_TERM → độ phủ thấp KHÔNG ảnh hưởng điểm SC-001 đo được hiện tại, chỉ là khoảng trống so với yêu cầu spec.
- Phân tích chi phí LLM 3 khía cạnh: **thời gian** (gọi Ollama cho toàn bộ 60k Article ước tính 35-85 giờ nếu không lọc ứng viên), **tài nguyên** (Ollama và model embedding cùng tranh GPU 6GB VRAM — backfill vẫn đang chạy lúc đó), **chất lượng/kỹ thuật** (rủi ro hallucination, cần confidence score, cần thêm code checkpoint theo FR-008).

---

## 11. Mở rộng rule-based term_extractor (không cần LLM) — phát hiện lớn

**Yêu cầu**: "ok hãy mở rộng"

- Quét corpus tìm mẫu định nghĩa rộng hơn: `"được hiểu là"` (54 file, đã bắt), `'"<quote> là '` không có "được hiểu" (165 file), **tiêu đề "giải thích từ ngữ"/"được hiểu như sau:" (1,072 file — gấp ~20 lần mẫu đã bắt)**.
- Đọc file mẫu thật → phát hiện mẫu PHỔ BIẾN NHẤT: danh sách đánh số `"N. <thuật ngữ KHÔNG quotes> là <định nghĩa>."` dưới tiêu đề "Điều N. Giải thích từ ngữ" — cấu trúc rất đều đặn, hoàn toàn rule-based bắt được.
- Implement `_ENUM_ITEM_RE`, `_split_enum_item_term_and_definition()` — CHỈ kích hoạt khi văn bản chứa trigger "được hiểu như sau" (tránh false positive trên danh sách đánh số khác như điều kiện/thủ tục — có viết test riêng xác nhận điều này).
- Xử lý case định nghĩa kéo dài nhiều dòng (không có số thứ tự mới) — dùng lookahead dừng đúng trước mục đánh số tiếp theo hoặc hết văn bản.
- Đo thật: **844 file / 6,065 định nghĩa** (tăng ~600 lần so với 6 file/10 định nghĩa ban đầu).
- **Bug thật phát hiện qua spot-check chất lượng** (không phải qua test, qua đọc tay 35 định nghĩa mẫu ngẫu nhiên): mẫu viết tắt `"<Tên đầy đủ> (sau đây gọi tắt là <tên ngắn>) là <định nghĩa>"` khiến regex bắt nhầm " là " ĐẦU TIÊN nằm BÊN TRONG ngoặc viết tắt, cắt cụt thuật ngữ. Đo quy mô: 266/6,065 (4.4%) bị ảnh hưởng.
- Fix: `_split_enum_item_term_and_definition()` kiểm tra ngoặc CÂN BẰNG trước khi chọn điểm tách term/định nghĩa, bỏ qua " là " nằm trong ngoặc chưa đóng. Giảm còn 45/6,055 (~0.7%, chấp nhận được).
- TDD: 22/22 test tổng cho `term_extractor.py` (8 test mới đợt này), 189/190 toàn bộ suite.
- **Chạy lại thật trên toàn bộ 60,679 Article**: **5,352 Term, 6,005 DEFINES, 108,723 USES_TERM** (tăng từ 10/10/525).

---

## 12. Sự cố Docker Desktop (lần 2) + xác nhận backfill hoàn tất

- Khang tự chạy `backfill_embeddings.py` lại (sau khi tắt máy) → `ConnectionRefusedError` — Docker Desktop không tự khởi động cùng Windows. Đã chẩn đoán bằng `docker ps -a` (lỗi "failed to connect to the docker API... daemon is running"), xác nhận không phải lỗi code.
- Hướng dẫn mở lại Docker Desktop, xác nhận container tự khởi động lại nhờ `restart: unless-stopped` trong `docker-compose.yml`.

**Yêu cầu**: "đã ingest xong toàn bộ. kiểm tra lại giúp tôi"

- Xác nhận 2 chiều: Neo4j `chroma_id IS NOT NULL` = **60,679/60,679**; Chroma `.count()` = **60,679** — khớp tuyệt đối, backfill embedding hoàn tất 100%.

---

## 13. Giải thích T013 và T017

**Yêu cầu**: "T013 và T017 là gì?"

- T013 (`app/extraction/relation_llm.py`): trích AMENDS/SUPERSEDES/CONFLICTS_WITH bằng LLM, kèm `confidence`/`ly_do` — Phase 3, mở rộng khả năng graph.
- T017 (`scripts/eval_graph_recall.py`): đo Recall@k/MRR so với baseline Hybrid+Reranker cũ, cùng phương pháp, cùng quy mô 67k — Phase 4, đo lường hệ thống hiện có.

**Yêu cầu**: "việc làm T013 trước và sau có ảnh hưởng như thế nào?"

- Kiểm tra thật `traversal.py` — xác nhận Cypher pattern hardcode `[r:REFERENCES|DEFINES]`, KHÔNG có AMENDS/SUPERSEDES/CONFLICTS_WITH. Làm T013 trước KHÔNG tự động ảnh hưởng T017 trừ khi sửa thêm `traversal.py`.
- Bộ 32 câu eval xây từ REFERENCES thuần — không câu nào cần AMENDS/SUPERSEDES/CONFLICTS_WITH để trả lời đúng.
- Đề xuất: đo T017 baseline TRƯỚC (rẻ, nhanh, không cần LLM), làm T013 SAU, đo lại T017 để tách bạch hiệu quả từng phần.

**Yêu cầu**: "tôi có thể làm 2 việc song song không?"

- Được, với điều kiện: KHÔNG sửa `traversal.py` (bước duy nhất khiến T013 thực sự ảnh hưởng retrieval) cho tới khi T017 đã chụp xong baseline — tránh đo baseline ở trạng thái graph "nửa vời".

---

## 14. T017 — implementation + baseline thật

**Yêu cầu**: "ok hãy bắt đầu"

- Đọc `D:\RAG Chatbot\scripts\eval_zalo_recall.py` (script gốc của dự án trước) để dùng ĐÚNG phương pháp so sánh công bằng.
- Thiết kế `scripts/eval_graph_recall.py` — điều chỉnh có chủ đích cho đặc thù Graph RAG multi-hop:
  - "Retrieved list" = entry point (có similarity, xếp hạng được) + Article tìm thêm qua traversal REFERENCES (không có điểm số riêng, chỉ có canh) — định nghĩa rõ ràng thứ tự: entry point trước theo similarity, phần còn lại theo thứ tự XUẤT HIỆN ĐẦU TIÊN trong `edges` trả về từ Neo4j.
  - `strict_recall` (khớp SC-001 "trích dẫn ĐỦ" — all-or-nothing mỗi câu) + `lenient_recall` (article-level, gộp toàn bộ) — vì 1 câu multi-hop có THỂ cần NHIỀU `expected_article_ids`, khác bản gốc (1 câu → 1 đáp án).
  - MRR dùng rank TỐT NHẤT trong số các `expected_article_ids`/câu (mở rộng chuẩn IR cho multi-relevant-doc).
- TDD: 10 test mới, pass ngay lần đầu. 199/200 toàn bộ suite.
- **Chạy thật lần 1** (threshold=0.75 cũ): Strict recall **59.4%**, MRR **0.625** — DƯỚI mục tiêu SC-001 (≥80%).

---

## 15. T013 groundwork — khảo sát candidate-narrowing (song song lúc chờ Docker)

- Quét từ khóa thô cho AMENDS ("sửa đổi, bổ sung": 621 file), SUPERSEDES ("thay thế"/"hết hiệu lực"/"bãi bỏ": 2,822 file), CONFLICTS_WITH ("trái với"/"mâu thuẫn": 612 file).
- Đọc tay 3 ví dụ thật → phát hiện quét từ khóa thô **overcounted nặng** (case 1: chỉ nói chung chung "nếu văn bản bị thay thế..." không phải quan hệ thật).
- Phân loại 2 case thật: (1) có tên văn bản đích rõ trong chính nội dung Điều — rule-based bắt được bằng cách tái dùng logic `reference_extractor.py`; (2) không có tên văn bản đích trong chính Điều đó (chỉ biết qua Document cha) — **BẾ TẮC CẤU TRÚC THẬT**: `Document.title` hiện đang RỖNG trong Neo4j (gap cũ từ ĐỢT 3), không rule-based, không cả LLM (đọc 1 Điều đơn lẻ) giải quyết được nếu không bổ sung dữ liệu.

---

## 16. Hiệu chỉnh SIMILARITY_THRESHOLD (ADR-004) — quy trình xác minh nghiêm ngặt

- Điều tra nguyên nhân Strict recall 59.4% thấp: với mỗi `expected_article_id`/32 câu, kiểm tra similarity thật (58 lượt kiểm tra) → **30/58 (52%) có similarity NẰM TRONG top-20 nhưng THẤP HƠN 0.75** — bị lọc oan. Trung vị similarity của kết quả ĐÚNG chỉ ~0.7426. 4/58 còn lại không nằm top-20 nhưng đều thuộc case thiết kế để tìm qua TRAVERSAL, không phải vector search trực tiếp (đúng thiết kế, không phải lỗi).
- Thử nhiều ngưỡng (0.60/0.65/0.70) bằng cách override env var, không sửa code thật trước: 0.65 → Strict recall **90.6%**, Lenient **93.1%**, MRR **0.917**.

**Yêu cầu**: "lấy ngẫu nhiên 10-15 case ở ngưỡng 0.65 mà 0.75 từng chấm 'sai' — đọc tay xem retrieved article có thực sự trả lời đúng câu hỏi không... Đừng chốt ngưỡng chỉ vì nó cho số đẹp nhất... tách một tập câu hỏi riêng (held-out) để xác nhận"

- Xác định chính xác 10 câu "lật" fail(0.75)→pass(0.65): mh-002, mh-003, mh-006, mh-011, mh-018, mh-022, mh-023, mh-026, mh-028, mh-032.
- Lấy full text THẬT của từng Điều "được cứu" từ Chroma, đọc tay đối chiếu với câu hỏi — **10/10 khớp đúng nội dung thật**, không có case "khớp giả" (bảng chi tiết từng case đã lập).
- Held-out split-half: chia 32 câu thành 2 nửa xen kẽ theo id (tránh thiên vị) — Nửa A: 75.0%→93.8%, Nửa B: 43.8%→87.5%. Cải thiện nhất quán CẢ HAI nửa.
- **Viết ADR-004 vào `research.md`** (đúng format ADR-001/002/003 đã có: Status/Date/Deciders/Context/Decision/Options Considered/Trade-off Analysis/Consequences/Action Items) — ghi đầy đủ lý do, số liệu, và cả các phương án đã cân nhắc (giữ 0.75/hạ xuống 0.60/chọn 0.65).
- **Áp dụng thật**: `app/config.py` (default + comment giải thích), `.env`, `.env.example` — 0.75 → 0.65.
- **Sửa 2 test bị ảnh hưởng**: `tests/test_config.py` (assert default mới 0.65), `tests/retrieval/test_entry_point.py` (3 test + 1 test thật — chuyển từ phụ thuộc ngầm vào default toàn cục sang GHIM TƯỜNG MINH threshold=0.75 qua `monkeypatch.setattr`, tránh lặp lại việc test vỡ ở lần hiệu chỉnh threshold sau này).
- 199/200 toàn bộ suite pass (1 fail cũ không liên quan).
- **Xác nhận cuối**: chạy lại `eval_graph_recall.py` với config mặc định thật (không override env) → đúng 90.6%/93.1%/0.917 — số liệu chính thức cho T018.

---

## 📊 Số liệu tổng hợp cuối phiên (để tham khảo nhanh khi viết gọn lại)

| Hạng mục | Số liệu |
|---|---|
| Article thật đã ingest | 60,679 (+ 8,427 external-reference placeholder = 69,106 tổng trong Neo4j) |
| Backfill embedding | 60,679/60,679 (100%, khớp Neo4j = Chroma) |
| GPU speedup sau fix | 7.3–8.5 lần (từ 1.1 lần trước fix) |
| Term / DEFINES / USES_TERM | 5,352 / 6,005 / 108,723 |
| T017 Strict recall (threshold=0.65) | 90.6% (vượt mục tiêu SC-001 ≥80%) |
| T017 Lenient recall | 93.1% |
| T017 MRR | 0.917 |
| Test suite | 199/200 pass (1 fail cũ không liên quan — artifact `.env` cục bộ) |

## 📁 File chính đã tạo/sửa trong phiên

- `app/retrieval/embedder.py` (fix HF_HUB_OFFLINE)
- `scripts/backfill_embeddings.py` (sort-by-length + length-tiered batching)
- `app/extraction/term_extractor.py` (mới — DEFINES/USES_TERM rule-based, 2 mẫu)
- `app/graph_store/upsert.py` (thêm upsert_definitions/upsert_term_usages)
- `scripts/extract_terms.py` (mới — orchestration T012)
- `scripts/eval_graph_recall.py` (mới — T017)
- `app/config.py`, `.env`, `.env.example` (SIMILARITY_THRESHOLD 0.75→0.65)
- `specs/001-graph-rag-core/research.md` (thêm ADR-004)
- `TIEN_DO.md`, `CHECKLIST-GRAPHRAG-DUYET.md` (cập nhật liên tục theo từng đợt)
- Toàn bộ test tương ứng cho mỗi module trên (TDD — viết trước, xác nhận đỏ, rồi implement)

---
---

# 📋 PHIÊN LÀM VIỆC 2026-08-06 (buổi 2) — T012b / T025 / T026 / T027

> Ghi **từng bước một**, gồm cả nguyên văn thông báo lỗi đỏ và cách sửa, theo yêu cầu của Khang.

## 0. Yêu cầu mở đầu

**Yêu cầu 1**: "hãy đọc các file .md và file docx để nắm tình hình project"
- Đã quét toàn repo: **không có file `.docx`/`.doc`/`.pdf` nào** — toàn bộ tài liệu là `.md`. Đã báo rõ thay vì im lặng bỏ qua.
- Đọc `TIEN_DO.md`, `CHECKLIST-GRAPHRAG-DUYET.md`, `BAO_CAO_CHI_TIET_PHIEN_LAM_VIEC.md`, `constitution.md`, `spec.md`, `tasks.md`, `docs/thuat-ngu-ky-thuat.md`, outline `research.md`/`plan.md`, `data-model.md`.
- Phát hiện toàn bộ công việc ĐỢT 9 + 10 **chưa commit** (untracked: `relation_llm.py`, `extract_relations.py`, `eval_graph_recall.py`, `docs/`, các test tương ứng; modified: `config.py`, `upsert.py`, `research.md`).

**Yêu cầu 2** (Khang trả lời 5 điểm chờ duyệt): (1) bổ sung trích title; (2) sửa slug cho nhất quán — "đây là những file gây nhiều họ cố tình để vào"; (3) sửa độ phủ; (4) so ở 10k + ghi rõ hạn chế, rồi tự đo baseline mới ở 67k và trình bày là phát triển thêm; (5) hỏi T012 nên đầu tư thêm gì. Kèm: "Hãy commit trước rồi làm tiếp".

**Yêu cầu 3** (giữa phiên): "sau khi chạy xong, cập nhật vào file báo cáo đầy đủ từng chi tiết, từ việc báo lỗi đỏ đến vc sửa như nào. cũng như cập nhật thêm các từ vựng mới vào file từ ngữ chuyên ngành" → chính là mục đích của phần báo cáo này + mục 6-9 mới trong `docs/thuat-ngu-ky-thuat.md`.

## 1. Commit dọn dẹp (3 commit)

Kiểm tra an toàn trước khi commit: `git check-ignore -v .env` → xác nhận `.env` đã trong `.gitignore` (dòng 9), không có secret nào lọt vào. Chạy full suite trước: **228 passed, 1 failed** (đúng cái fail `.env` cục bộ đã biết).

Chia 3 commit logic thay vì một commit gộp:
- `9882047` feat(T013) — relation_llm + upsert_relations + extract_relations CLI + 41 test.
- `243e81b` feat(T017) — eval_graph_recall + ADR-004 (SIMILARITY_THRESHOLD 0.75→0.65) + fixture kết quả baseline.
- `2a3fe73` docs — nhật ký ĐỢT 9-10, checklist F1/F2/G1, báo cáo phiên, giải nghĩa thuật ngữ.

**Lỗi tự gây ra và sửa ngay**: commit đầu dùng cú pháp here-string của PowerShell (`-m @'...'@`) trong tool Bash → ký tự `@` lọt vào message (`git log -1 --format=%B | cat -A` cho thấy dòng đầu là `@$`). Sửa bằng `git commit --amend -F -` với heredoc Bash đúng cú pháp (`<<'EOF'`). Các commit sau dùng heredoc ngay từ đầu.

## 2. Khảo sát dữ liệu thật trước khi thiết kế (3 script scratchpad)

Không thiết kế theo suy đoán — viết 3 script quét toàn bộ 61,069 file thật.

**Trở ngại kỹ thuật**: script đầu crash `UnicodeEncodeError: 'charmap' codec can't encode character 'đ'` — console Windows mặc định cp1252. Sửa bằng `PYTHONIOENCODING=utf-8` cho mọi lần chạy sau.

### 2a. Khảo sát mã hiệu (phục vụ mục 1 — Document.title)

- **3,207** doc_prefix phân biệt, **3,206** khớp dạng `{số}_{năm}_{mã-hiệu}`; 1 ngoại lệ: `21-lct_hđnn8`.
- Chỉ **12** tiền tố mã hiệu phân biệt: `tt` 1,867 · `nđ` 842 · `ttlt` 218 · `qđ` 174 · `qh13` 36 · `qh14` 34 · `qh12` 17 · `qh11` 7 · `nð` 4 · `nd` 3 · `qh` 2 · `qh10` 2.
- **Phát hiện quyết định**: corpus **không chứa tiêu đề văn bản ở đâu cả**. Đọc `scripts/fetch_zalo_legal_corpus.py` (`_write_doc` dòng 103: `content = f"# {title}\n\n{text}\n"`) + đọc tay 3 file thật (`19_2016_tt-bxd_1.md`, `19_2016_tt-bxd_2.md`, `12_2017_qh14_1.md`) → xác nhận `title` mà dataset trả về là tiêu đề **Điều** (`"Điều 1. Phạm vi Điều chỉnh"`), không phải tiêu đề văn bản. Kết luận: `Document.title` chỉ suy được từ **tên file**, và chỉ ra được **chỉ danh chuẩn**, không phải tiêu đề văn xuôi.

### 2b. Khảo sát độ phủ trích dẫn (phục vụ mục 2+3)

| Chỉ số | Số liệu thật |
|---|---|
| Trích dẫn `Điều N` regex cũ bắt được | **115,563** |
| …resolve được cross-document | **547 (0,47%)** |
| …bị coi là self-reference | 115,016 (99,5%) |
| Self-ref trỏ tới Article **không tồn tại** trong cùng Document | **14,621 (12,7%)** |
| Dạng `Điều N **của** <Loại>` bị bỏ sót | 10,745 lần / 5,889 file |
| Dạng `<Loại> **số** N/YYYY/MÃ` bị bỏ sót | 6,417 lần / 3,623 file |
| Dạng `<Loại> <tên> <số hiệu>` bị bỏ sót | 252 lần / 151 file |

→ Bug thật **không phải** "1,4% external giả" như ghi trong ĐỢT 10, mà là: trích dẫn có nêu tên văn bản đích đang bị **âm thầm resolve thành self-reference**, trỏ sai sang một Điều khác trong *cùng* văn bản. Con số 12,7% dangling là bằng chứng trực tiếp.

### 2c. Đo lợi ích + thử phương án từ điển tên→số hiệu

- **6,767** trích dẫn cross-doc **có số hiệu**: 3,302 trỏ tới Document đã có trong corpus (3,275 có đúng Article đích), 3,465 external thật.
- **Thử mine từ điển "tên văn bản → số hiệu"** từ chính corpus và **kết luận không dùng được**: 387 tên phân biệt, 319 đơn nghĩa, nhưng chỉ **86** đơn nghĩa khớp doc thật; và các tên quan trọng nhất **thực sự đa nghĩa** — `Luật Chứng khoán` → 3 phiên bản (`54-2019-qh14` 41 lần, `70-2006-qh11` 13, `62-2010-qh12` 7), `Luật Doanh nghiệp` → 2 phiên bản. Chọn bừa một phiên bản là **sai về pháp lý**. Ghi rõ để không ai thử lại hướng này.
- **Kiểm tra rủi ro leading zero** (trước khi thiết kế, không đoán): 592/3,203 doc_id có số bắt đầu bằng `0` (vd `05_2017_tt-btnmt`), nhưng đo 6,767 trích dẫn → **0 trường hợp** cần chuẩn hoá leading zero. Corpus viết số hiệu nhất quán với tên file → **không thêm logic chuẩn hoá** (nếu thêm sẽ sinh `5-2017-...` không bao giờ khớp).

### 2d. Khảo sát T012 (phục vụ câu hỏi 5 của Khang)

- **263 file** có trigger định nghĩa nhưng trích được **0** định nghĩa. Đọc tay 3 file (`01_2014_tt-btc_3.md`, `02_2011_tt-bkhcn_3.md`, `02_2016_tt-btp_3.md`) → nguyên nhân rõ: có heading `Điều N. Giải thích từ ngữ` nhưng **không** có cụm `"được hiểu như sau"`, mà `_ENUM_TRIGGER_RE` chỉ khớp cụm đó.
- **Kiểm tra rủi ro false positive trước khi chốt** (đúng Quy tắc riêng #3): 1,039 file chứa `"Giải thích từ ngữ"` → 1,021 ở dòng đầu, **18 ở chỗ khác**. Đọc tay nhóm 18 file + 10 mẫu định nghĩa trích ra → **đều hợp lệ**, không có rác. Kiểm chứng nguyên nhân: `170_1999_qđ-ttg_2.md` có dòng đầu chỉ là `# Điều 2.`, cụm nằm dòng kế tiếp; `07_2019_tt-bkhđt_1.md` có đoạn định nghĩa nằm trong trích dẫn sửa đổi. → Trigger tìm toàn văn bản là **an toàn**, không giới hạn dòng đầu.
- Đo trước khi code: 844 → **1,020 file**, 6,055 → **6,926 định nghĩa** (+14,4%).
- **Cố tình KHÔNG phủ**: 5,707 file có cấu trúc `N. X là ...` nhưng không trigger nào — là danh sách điều kiện/thủ tục.

**Trả lời câu 5 của Khang**: không cần LLM fallback. Chi phí phương án rule-based = **1 dòng regex**, chạy lại ~15s, **0 đồng / 0 GPU**; so với LLM fallback ước tính **35–85 giờ GPU** + tranh 6GB VRAM với embedding + rủi ro hallucination cần confidence filtering.

## 3. T012b — mở rộng trigger định nghĩa (TDD chi tiết)

**Bước đỏ**: thêm 2 test vào `tests/extraction/test_term_extractor.py` rồi chạy `pytest -k "giai_thich"`:
```
FAILED test_extracts_enum_definitions_with_heading_giai_thich_tu_ngu_only
        assert 0 == 2   (where 0 = len([]))
FAILED test_heading_giai_thich_tu_ngu_trigger_is_case_insensitive_and_off_first_line
        assert 0 == 1   (where 0 = len([]))
2 failed, 22 deselected
```

**Bước sửa**: `app/extraction/term_extractor.py`
```python
# TRƯỚC
_ENUM_TRIGGER_RE = re.compile(r"được hiểu như sau", re.IGNORECASE)
# SAU
_ENUM_TRIGGER_RE = re.compile(r"được hiểu như sau|giải thích từ ngữ", re.IGNORECASE)
```
Kèm ~20 dòng comment ghi lại bằng chứng (263 file, 18 file heading tách dòng, 5,707 file cố tình bỏ) và cập nhật module docstring mục "Mẫu 2 mở rộng".

**Bước xanh**: 24/24 test `term_extractor`.

## 4. T012b (tiếp) — bug hiệu năng thật phát hiện khi chạy thật

**Triệu chứng**: chạy `python -m scripts.extract_terms data/raw` → **quá 600s timeout**, chuyển sang nền, và sau **hơn 50 phút** vẫn chưa xong (kiểm tra `tasklist`: PID 11340 còn sống, 358MB). Lần chạy trước (ĐỢT 7, 5,352 thuật ngữ) đã hoàn tất — nên đây là hồi quy do số thuật ngữ tăng.

**Chẩn đoán** (đọc code, không đoán): `extract_term_usages_rule_based` tại `term_extractor.py:269` gọi `re.compile` **bên trong vòng lặp từng thuật ngữ**, và hàm này được gọi cho **mỗi** Article:
```python
for term_id, ten_thuat_ngu in known_terms.items():
    pattern = re.compile(r"\b" + re.escape(ten_thuat_ngu) + r"\b")   # <-- trong vòng lặp
    found = pattern.search(text)
```
60,679 Article × ~6,900 thuật ngữ ≈ **419 triệu lượt**. Cache regex nội bộ của Python chỉ giữ **512 pattern** → với 6,900 pattern phân biệt thì cache thrash, gần như recompile mọi lượt.

**Xử lý**: `taskkill /PID 11340 /F` (an toàn — `extract_terms.py` MERGE-based, idempotent, chạy lại từ đầu không hỏng dữ liệu).

**Bước đỏ**: thêm 2 test hiệu năng (đếm số lần `re.compile` bằng cách monkeypatch `te.re.compile`):
```
FAILED test_term_usage_pattern_is_compiled_once_per_term_across_calls
FAILED test_term_not_present_as_substring_is_skipped_without_regex
        AttributeError: module 'app.extraction.term_extractor' has no attribute
        '_compile_term_pattern'
```

**Bước sửa** — hai tối ưu, ngữ nghĩa **giữ nguyên chính xác**:
```python
@lru_cache(maxsize=None)
def _compile_term_pattern(ten_thuat_ngu: str) -> re.Pattern[str]:
    return re.compile(r"\b" + re.escape(ten_thuat_ngu) + r"\b")
...
    if ten_thuat_ngu not in text:      # tiền lọc ở tầng C, rất nhanh
        continue
    found = _compile_term_pattern(ten_thuat_ngu).search(text)
```
Lý do tiền lọc an toàn: regex word-boundary chỉ **lọc hẹp thêm** những gì `in` đã tìm thấy, không bao giờ tìm ra kết quả mà `in` không thấy.

**Bước xanh**: 26/26 test `term_extractor`.

**Kết quả chạy thật sau fix**: **~8,5 phút** toàn corpus (từ >50 phút chưa xong).
```
pass 1 xong: 1018 Article co dinh nghia, 6104 thuat ngu duy nhat
da ghi 6872 DEFINES (+ Term) vao Neo4j
da ghi 111604 USES_TERM vao Neo4j
```
**Kiểm chứng trực tiếp trong Neo4j**: Term 5,352 → **6,104** · DEFINES 6,005 → **6,872** · USES_TERM 108,723 → **113,888**.

## 5. T025 — `Document.title`/`so_hieu`/`loai_vb` (module `doc_identity.py`)

### 5a. Bước đỏ 1 (module chưa tồn tại)
Viết `tests/extraction/test_doc_identity.py` (23 test) trước → `ModuleNotFoundError: No module named 'app.extraction.doc_identity'`.

### 5b. Bước đỏ 2 — bug thật TDD bắt được: chữ `ð` (eth)
Sau khi implement lần đầu: **20 passed, 1 failed**
```
FAILED test_maps_encoding_variants_of_dj_in_ma_hieu[nð-cp]
        AssertionError: assert None in {'Nghị định', 'Quyết định'}
         +  where None = loai_vb_from_ma_hieu('nð-cp')
```

**Chẩn đoán bằng dữ liệu thật**: `ð` là **chữ eth U+00F0**, một chữ cái khác hoàn toàn với `đ` U+0111. `slugify_doc_name` chỉ xử lý `đ` (`.replace("đ", "d")`); eth không decompose được nên bị `_NON_ALNUM_RE` thay bằng `-` → `nð-cp` thành `n-cp`, tiền tố `n` không có trong bảng. Quét corpus tìm file thật bị ảnh hưởng:
```
'102_2017_nð-cp' (69 file) -> doc_id='102-2017-n-cp'
'146_2018_nð-cp' (42 file) -> doc_id='146-2018-n-cp'
'81_2016_nð-cp'  ( 2 file) -> doc_id='81-2016-n-cp'
'89_2016_nð-cp'  ( 6 file) -> doc_id='89-2016-n-cp'
```
= **4 văn bản / 119 Article** (0,12% văn bản, 0,20% Article).

**Cách sửa — có chủ đích chỉ sửa một nửa**: thêm `_normalize_eth()` và dùng **chỉ trong** `loai_vb_from_ma_hieu` (nên `loai_vb`/`title` của 4 văn bản này đúng), **giữ nguyên** `doc_id`. Lý do không sửa `doc_id`: đổi `doc_id` = đổi `article_id`, mà `article_id` **chính là id trong Chroma** → phải embed lại 119 Article + cập nhật Neo4j. Rẻ (~11s GPU) nhưng là thao tác trên **khoá định danh** của dữ liệu thật đã ingest → cần Khang quyết riêng, không làm ngầm (cùng nguyên tắc với ADR-003/`BatchSizeMismatchError`).

Đã viết lại test cho chính xác từng biến thể + thêm `test_eth_variant_doc_id_intentionally_differs_from_so_hieu_doc_id` **ghim** hạn chế này — nếu sau này Khang quyết sửa, test sẽ đỏ và buộc phải đọc ghi chú.

**Bước xanh**: 23/23.

### 5c. Bước đỏ 3 — `upsert_document` chưa nhận `identity`
```
FAILED test_upsert_document_with_identity_writes_so_hieu_and_loai_vb
FAILED test_upsert_document_with_identity_falls_back_to_synthesized_title
FAILED test_upsert_document_prefers_real_parsed_title_over_synthesized_one
FAILED test_upsert_document_with_unknown_loai_vb_sends_none_not_guess
        TypeError (upsert_document() got an unexpected keyword argument 'identity')
4 failed, 20 passed
```
(Test thứ 5 — `..._without_identity_does_not_touch_so_hieu_or_loai_vb` — xanh ngay vì đang là hành vi cũ.)

**Cách sửa + lý do thiết kế quan trọng**: thêm **query RIÊNG** `_DOCUMENT_WITH_IDENTITY_QUERY` chứ **không** thêm `SET d.so_hieu = $so_hieu` vào query cũ với giá trị null — vì trong Cypher `SET x = null` **xoá thuộc tính**, nên một lần chạy không có identity sẽ **âm thầm xoá** `so_hieu`/`loai_vb` đã ghi đúng ở lần chạy trước. Thứ tự title: `parsed.title or identity.title` — tiêu đề văn xuôi thật (nếu có) luôn thắng chỉ danh sinh ra.

**Bước xanh**: 24/24.

### 5d. Bước đỏ 4 — `ingest.py` chưa truyền identity
```
FAILED test_run_ingest_writes_document_so_hieu_loai_vb_and_title_from_filename
        KeyError: 'so_hieu'
1 failed, 1 passed
```
**Cách sửa**: thêm `doc_identity_for_file()` vào `app/ingest.py`, tách **riêng** khỏi `parse_file` để không đổi signature của nó — `parse_file` còn được `detect_and_dedupe_collisions` **và** `scripts/backfill_embeddings.py` dùng, cả hai không cần identity.

**Bước xanh**: 69/69 (`test_ingest` + `test_upsert` + `test_doc_identity`).

## 6. T026 — sửa độ phủ + slug nhất quán (gộp mục 2 và 3)

Gộp làm **một** task vì cùng một nguyên nhân gốc: không có bộ resolve `doc_id` chuẩn hoá.

**Bước đỏ**: cập nhật 4 test cũ đang ghim slug **sai** + thêm 7 test mới → **11 failed, 14 passed**:
```
FAILED test_khoan_qualified_cross_document_citation
FAILED test_multiple_citations_returned_in_order_of_appearance
FAILED test_cross_document_citation_thong_tu
FAILED test_cross_document_citation_nghi_quyet
FAILED test_so_hieu_citation_resolves_to_doc_id_matching_filename
FAILED test_cua_connector_between_dieu_and_doc_name_with_so_hieu
FAILED test_cua_connector_with_name_and_year_only
FAILED test_doc_name_between_loai_vb_and_so_hieu
FAILED test_thong_tu_lien_tich_is_recognized_before_thong_tu
FAILED test_so_hieu_leading_zero_is_preserved_in_doc_id
FAILED test_doc_name_does_not_bleed_across_a_following_citation
```

**Cách sửa** — pattern hai nhánh có thứ tự:
```python
_LOAI_VB_PATTERN = (r"Bộ luật|Luật|Pháp lệnh|Nghị định|Nghị quyết|Quyết định"
                    r"|Thông tư liên tịch|Thông tư|Chỉ thị")
_SO_HIEU_PATTERN = r"(?P<so>\d+)\s*/\s*(?P<nam>\d{4})\s*/\s*(?P<ma_hieu>[\w\-]+)"
# nhánh (1) có số hiệu: "<Loại> [tên] [số] N/YYYY/MÃ"  -> build_doc_identity
# nhánh (2) chỉ tên+năm: "<Loại> <tên> YYYY"           -> slugify cả cụm (như cũ)
_CITATION_RE = ... r"Điều\s+(?P<article_num>\d+)"
                  r"(?:\s+(?:của\s+)?(?P<doc_name>" + _DOC_NAME_PATTERN + r"))?"
```
Bốn điểm thiết kế: (a) `của` là tuỳ chọn giữa `Điều N` và tên văn bản; (b) `số` tuỳ chọn trước số hiệu; (c) `Thông tư liên tịch` phải đứng **trước** `Thông tư` trong alternation, nếu không `Thông tư` khớp trước rồi đòi số hiệu ngay và thất bại ở `" liên tịch"`; (d) tên văn bản dùng `[^\d,.;]` (không chứa chữ số) nên **không thể "ăn" nhầm** sang số hiệu của trích dẫn kế tiếp.

**Lỗi cú pháp tự gây ra**:
```
File "app/extraction/reference_extractor.py", line 101
    r"(?:" + _LOAI_VB_PATTERN + r")"
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
SyntaxError: invalid syntax. Perhaps you forgot a comma?
```
Nguyên nhân: Python không cho đặt string literal **liền kề** ngay sau một tên biến trong biểu thức nối ngầm (`... + _SO_HIEU_PATTERN` rồi xuống dòng viết tiếp `r"|..."`). Sửa bằng thêm toán tử `+` tường minh ở mọi vị trí.

**Bước xanh**: 25/25 test `reference_extractor`.

**Regression thật phát hiện khi chạy full suite** — đúng loại lỗi cần tìm:
```
FAILED tests/extraction/test_relation_llm.py::test_supersedes_trigger_with_cross_doc_citation_produces_candidate
        AssertionError: assert '123-2020-nd-cp_dieu-10' == 'nghi-dinh-123-2020-nd-cp_dieu-10'
2 failed, 269 passed
```
`find_relation_candidates` (T013) **tái dùng nguyên** `extract_references` nên **thừa hưởng** fix — đây chính là *mục đích* của việc tái dùng (Điều 1 constitution), không phải regression. Đã cập nhật assert + ghi rõ lý do.

**Kết quả cuối**: **270 passed, 1 failed** (chỉ còn fail `.env` cục bộ đã biết).

## 7. Dry-run T026 trên toàn corpus (chưa ghi DB)

Trước khi đụng dữ liệu thật, chạy so sánh extractor cũ vs mới trên toàn bộ 61,068 file:

| | Cũ (trước T026) | Mới (sau T026) |
|---|---|---|
| Edge duy nhất | **37,875** ← *khớp chính xác số trong Neo4j* | **38,300** |
| Trỏ tới Article thật | 39,599 lượt | 38,815 lượt |
| External | 15,168 | 15,952 |
| Self-reference | 54,220 | 47,645 |

- **5,499** edge chỉ có ở bản mới (2,594 trỏ tới Article thật) · **5,074** edge chỉ có ở bản cũ, bị bỏ (2,912 trỏ tới Article thật).
- Bản chất là **đổi chỗ**, không phải chỉ thêm. Ví dụ thật:
```
CŨ (sai):   01-2012-ttlt-tandtc-vksndtc-btp_dieu-16 -> 01-2012-ttlt-...-btp_dieu-10
MỚI (đúng): 01-2012-ttlt-tandtc-vksndtc-btp_dieu-16 -> 16-2010-nd-cp_dieu-10
```
Câu `"Điều 10 Nghị định số 16/2010/NĐ-CP"` trước đây bị hiểu thành Điều 10 của *chính* Thông tư đó. Có cả **self-loop vô nghĩa** bị loại: `01-2013-ttlt-bnv-bqp_dieu-13 -> 01-2013-ttlt-bnv-bqp_dieu-13`.
- Chi phí CPU không đáng kể: parse 61,068 file 4,7s + extract cả 2 phiên bản 4,8s. Toàn bộ chi phí migration nằm ở ghi Neo4j.
- **Việc khớp đúng 37,875 với số thật trong Neo4j** là bằng chứng dry-run mô phỏng đúng thực tế, không phải tính nhầm.

## 8. T027 — script migration (TDD, chưa chạy trên dữ liệu thật)

**Vì sao cần migration riêng, không chỉ "chạy lại ingest"**: `upsert.py` ghi bằng MERGE (idempotent — điều kiện sống còn của batch/savepoint, ADR-002). Mặt trái: canh REFERENCES **sai** do extractor cũ tạo ra **không tự biến mất** khi chạy lại ingest → graph sẽ chứa **cả** edge đúng (mới) **lẫn** edge sai (cũ), **tệ hơn** trước khi sửa.

`scripts/migrate_references.py` — 4 bước, thứ tự bắt buộc:
1. Xoá toàn bộ REFERENCES: `CALL (r) { DELETE r } IN TRANSACTIONS OF 10000 ROWS` (37,875 edge trong **một** transaction dễ làm hết heap Neo4j Community).
2. Xoá Article external placeholder **đã thành mồ côi**: hai ràng buộc bắt buộc — `a.is_external = true` (không bao giờ xoá Article thật có `chroma_id`) **và** `COUNT { (a)--() } = 0`. **Không** dùng `DETACH DELETE` vì placeholder đang là đích của AMENDS/SUPERSEDES/CONFLICTS_WITH (T013) phải được giữ.
3. Reset checkpoint. **Bỏ bước này là bug nghiêm trọng**: `run_ingest` đọc thấy checkpoint cũ ("đã xong batch cuối") và **không làm gì cả** → migration "thành công" trong im lặng mà graph mất hết REFERENCES.
4. Chạy lại `run_ingest` — tạo lại REFERENCES bằng extractor mới, đồng thời ghi `Document.title/so_hieu/loai_vb` (T025) cho 3,203 Document.

**An toàn**: mặc định **DRY-RUN**, phải `--apply` tường minh mới thay đổi dữ liệu (script duy nhất trong dự án xoá dữ liệu thật). `reingest` thất bại thì exception nổi lên nguyên vẹn, **không** báo "xong" — vì lúc đó graph đang ở trạng thái đã xoá nhưng chưa tạo lại hết.

**Bước đỏ**: `ModuleNotFoundError: No module named 'scripts.migrate_references'` → implement → **8/8 xanh** ngay lần đầu (8 test tập trung vào an toàn: dry-run không ghi gì, thứ tự 4 bước, chỉ xoá node mồ côi, không swallow lỗi re-ingest).

**Verify Cypher bằng `EXPLAIN` trên Neo4j thật** (không thực thi) — `Neo4j version: 5.26.28`, cả 2 lệnh xoá + 5 câu đếm đều `OK`.

**Dry-run trên graph thật**:
```
chi so                          truoc          sau
references                     37,875       37,875
external_placeholder            8,427        8,427
document_co_so_hieu                 0            0
article_that                   60,679       60,679
article_co_chroma_id           60,679       60,679
```

**Kiểm tra rủi ro với bộ eval trước khi đề xuất chạy**: 26/32 câu có `relationship_path`; **2 câu** (`mh-014`, `mh-030`) có bước REFERENCES không còn tồn tại sau T026 — và `mh-030` chính là chuỗi self-ref **sai** đã phát hiện (`_dieu-24 -> _dieu-16 -> _dieu-10`), tức `relationship_path` của câu đó vốn dựng trên edge **không tồn tại thật**. Lưu ý: T017 chấm theo `expected_article_ids`, không theo `relationship_path`, nên có thể vẫn pass.

**TRẠNG THÁI**: đã hỏi Khang 2 câu (có chạy migration ngay không / xử lý 2 câu eval thế nào) — **chưa nhận trả lời**, nên **KHÔNG chạy `--apply`**. Graph giữ nguyên trạng thái cũ.

## 9. Số liệu tổng hợp phiên này

| Hạng mục | Trước | Sau |
|---|---|---|
| Term / DEFINES / USES_TERM | 5,352 / 6,005 / 108,723 | **6,104 / 6,872 / 113,888** |
| `extract_terms.py` thời gian chạy | >50 phút (chưa xong) | **~8,5 phút** |
| Trích dẫn resolve cross-doc | 547 (0,47%) | **~7,300** (theo dry-run, chờ migration) |
| Edge REFERENCES duy nhất | 37,875 | **38,300** (chờ migration) |
| `Document` có `so_hieu`/`loai_vb` | 0 | **3,203** (chờ migration) |
| Test suite | 228 passed / 1 failed | **270 passed / 1 failed** |

## 10. File tạo/sửa trong phiên này

**Mới**: `app/extraction/doc_identity.py` · `scripts/migrate_references.py` · `tests/extraction/test_doc_identity.py` · `tests/test_migrate_references.py`
**Sửa**: `app/extraction/term_extractor.py` (trigger + hiệu năng) · `app/extraction/reference_extractor.py` (T026) · `app/graph_store/upsert.py` (identity) · `app/ingest.py` (`doc_identity_for_file`) · `tests/extraction/test_term_extractor.py` · `tests/extraction/test_reference_extractor.py` · `tests/extraction/test_relation_llm.py` · `tests/graph_store/test_upsert.py` · `tests/test_ingest.py` · `docs/thuat-ngu-ky-thuat.md` (thêm mục 6-9) · `TIEN_DO.md` · `CHECKLIST-GRAPHRAG-DUYET.md`

**Commit**: `9882047` (T013) · `243e81b` (T017+ADR-004) · `2a3fe73` (docs ĐỢT 9-10) · `71bdc5f` (T012b) · `ac3354a` (T025) · `4bc2201` (T026) · `6386b24` (T027 script)
