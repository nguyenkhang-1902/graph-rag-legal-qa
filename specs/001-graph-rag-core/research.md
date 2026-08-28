# 🔬 Research & Quyết định kỹ thuật — Graph RAG (Phase 1: engine gốc)

> **Bối cảnh**: các ADR dưới đây được đúc kết khi dự án còn ở giai đoạn corpus
> chung 67k văn bản pháp luật đa lĩnh vực (nguồn Zalo AI Challenge — đã xoá
> khỏi đĩa từ 2026-08-24 khi pivot sang domain **BHXH/lao động-tiền lương**,
> xem `README.md`/`ROADMAP.md` cho hệ thống hiện tại). Engine cốt lõi (Neo4j +
> Chroma + graph traversal + reranker) vẫn là nền cho hệ thống BHXH đang chạy —
> **phương pháp/bài học** ở đây vẫn dùng được, chỉ số liệu cụ thể (60k+ Article,
> 793 câu Zalo gold...) là bối cảnh lịch sử, không phải số liệu hiện hành.

## 🗒️ ADR-001: Chọn graph store — Neo4j Community

**Status:** Accepted · **Date:** 2026-08-03

**Quyết định:** Neo4j Community qua Docker Compose, local — vẫn đúng cho hệ thống BHXH hiện tại.

**Vì sao** (so với NetworkX in-memory / Microsoft GraphRAG framework): Cypher trực quan cho multi-hop, Neo4j Browser demo tốt cho CV/phỏng vấn, không giới hạn RAM như NetworkX nếu corpus tăng lại. Đánh đổi: thêm 1 service Docker + học Cypher — chấp nhận được vì mục tiêu chính là portfolio/học kỹ thuật GraphRAG doanh nghiệp thật, không phải tốc độ dựng nhanh nhất.

## 🗒️ ADR-002: Batch ingest + savepoint cho corpus lớn

**Status:** Accepted (áp dụng khi corpus đủ lớn) · **Date:** 2026-08-03

**Bối cảnh cũ:** ở quy mô 67k văn bản, LLM extraction chạy nhiều giờ — cần resume được nếu crash giữa chừng.

**Quyết định:** ingest theo batch (`INGEST_BATCH_SIZE`), ghi savepoint atomic (`.state/ingest_checkpoint.json`, ghi file tạm rồi rename) sau mỗi batch, batch phải idempotent theo `doc_id`.

**Ghi chú cho corpus nhỏ (BHXH, hiện 19 văn bản):** `scripts/build_corpus.py` không cần cơ chế này — wipe + rebuild toàn bộ trong vài phút là đủ rẻ. Giữ pattern này lại làm tham khảo **nếu corpus BHXH mở rộng lại lên quy mô lớn** (vd toàn bộ văn bản lao động-tiền lương-BHXH của VN).

**Bài học chung, không phụ thuộc quy mô:** checkpoint/savepoint phải ghi **đủ tham số ảnh hưởng tới cách chia việc** (không chỉ "đã xong tới đâu"). Hai lần gặp đúng lớp lỗi này ở 2 script khác nhau:
- `app/ingest.py`: checkpoint ban đầu chỉ ghi `last_completed_batch` (một index) — đổi `batch_size` giữa 2 lần chạy khiến resume tính sai vị trí, âm thầm bỏ sót hàng nghìn văn bản. Fix: `BatchSizeMismatchError` — phát hiện lệch và **từ chối chạy** thay vì tự hoà giải.
- `scripts/eval_hybrid_reranker_baseline.py` (T018, giai đoạn sau): checkpoint không ghi **số câu hỏi** đã dùng — resume với `--limit-queries` mặc định khác lần trước khiến 2 chiến lược đo trên 793 câu, chiến lược thứ 3 đo nhầm trên 50 câu, cả ba in cạnh nhau như thể so sánh được. Áp dụng lại đúng nguyên tắc: `QuestionCountMismatchError`.
- **Quy tắc rút ra**: mọi checkpoint chia việc theo tham số nào (batch size, số câu hỏi, độ dài shard...) đều phải **ghi lại chính tham số đó**, không chỉ ghi tiến độ — nếu không, đổi tham số giữa 2 lần chạy là bug im lặng, không phải lỗi rõ ràng.

## 🗒️ ADR-003: Xử lý ID trùng do dữ liệu nguồn không nhất quán

**Status:** Accepted · **Date:** 2026-08-04

**Phát hiện thật:** ingest 61,068 văn bản Zalo → thiếu 389 Article so với số file. Điều tra: corpus nguồn có bản ghi trùng thật (cùng văn bản, 2 filename lệch đúng 1 ký tự Unicode có dấu/không dấu, vd `bgddt` vs `bgdđt`) — `slugify_doc_name()` gộp 2 filename thành 1 `article_id`, `upsert.py` (MERGE-based) âm thầm ghi đè.

**Quyết định — pre-flight collision detection** (chạy 1 lần trước batch loop): gom file theo `article_id`, nội dung **giống hệt** → tự dedup + log INFO; nội dung **khác nhau** → dừng ngay, raise lỗi liệt kê rõ file xung đột, không tự đoán chọn bản nào.

**Bài học tổng quát (không phụ thuộc dataset):** dữ liệu crawl/scrape thật luôn có khả năng chứa bản ghi gần-trùng do encoding/chuẩn hoá không nhất quán. Khi hệ thống có bước chuẩn hoá ID (slugify, bỏ dấu, lowercase...) để tạo khoá duy nhất, các bản ghi gần-trùng SẼ va chạm. Không mặc định coi là an toàn hay nguy hiểm — luôn so sánh nội dung thật trước khi quyết định dedup hay dừng hỏi người.

## 🗒️ ADR-004: Hiệu chỉnh ngưỡng similarity bằng dữ liệu thật — và bài học về cỡ mẫu

**Status:** Accepted, sau đó **hiệu chỉnh lại lần 2** · **Date:** 2026-08-06, đính chính 2026-08-10

**Lần 1 (bộ 32 câu eval)**: `SIMILARITY_THRESHOLD` mặc định 0.75 cho Strict recall chỉ 59.4% — điều tra bằng dữ liệu thật cho thấy 52% `expected_article_id` đúng bị lọc oan vì similarity nằm ngay dưới ngưỡng (trung vị 0.7426). Hạ xuống 0.65 → 90.6%. Trước khi chốt đã tự phản biện + xác minh: đọc tay 10/10 case "lật" fail→pass (không có case "khớp giả"), held-out split-half (cả 2 nửa đều cải thiện nhất quán).

**Lần 2 (bộ 793 câu, quy mô lớn hơn nhiều — 2026-08-10)**: cùng ngưỡng 0.65 lại làm **mất 12.3 điểm % Recall@4** (81.8% → 69.5%) so với tắt lọc hoàn toàn. **Bài học quan trọng nhất của ADR này**: hiệu chỉnh ngưỡng trên tập 32 câu — dù đã làm đúng quy trình xác minh (đọc tay, held-out split-half) — **không suy rộng được** ra tập 793 câu. Cỡ mẫu nhỏ có thể vượt qua mọi bài kiểm tra thống kê hợp lý (không overfit theo nghĩa thông thường) mà vẫn không đại diện đủ cho phân phối thật của câu hỏi đa dạng hơn. **Áp dụng cho lần hiệu chỉnh ngưỡng sau này**: luôn đo lại trên tập lớn nhất có sẵn trước khi coi một ngưỡng là "đã chốt", không dừng ở tập nhỏ dù đã xác minh kỹ.

## 🪤 Sổ bẫy (pitfall log) — áp dụng được cho mọi dataset/project sau này

- **Chroma mặc định HNSW space là L2, không phải cosine** — nếu không set `metadata={"hnsw:space": "cosine"}` lúc tạo collection, `SIMILARITY_THRESHOLD` (giả định cosine 0..1) sẽ vô nghĩa. Chỉ áp dụng lúc **tạo mới** collection — `get_or_create_collection` im lặng bỏ qua nếu collection tên đó đã tồn tại với metric khác.
- **`SentenceTransformer(...)` load lại nhiều lần xen kẽ với gọi LLM khác trong CÙNG process** từng gây crash native trên Windows (access violation `0xC0000005`). Bắt buộc cache 1 instance/process (module-level singleton).
- **`sentence-transformers` tự gọi ~34 HTTP request kiểm tra revision trên HF Hub mỗi lần khởi tạo model**, dù model đã cache đủ — chiếm ~70% thời gian init. Fix: `HF_HUB_OFFLINE=1` khi model chắc chắn đã cache trước (đọc trong `quickstart.md`).
- **Batch embedding không sắp xếp theo độ dài trước khi chia batch** → 1 văn bản dài lọt vào 1 batch buộc CẢ batch pad theo độ dài đó, đo được chậm hơn 7.7 lần/item. Fix: sort theo độ dài trước khi chia batch + cap batch-size theo tầng độ dài (p90/p99) cho outlier cực dài.
- **Cross-encoder reranker cũng cần giới hạn `max_length`** — cùng bản chất với batch padding ở trên: không giới hạn thì 1 văn bản cực dài trong candidate set làm chi phí self-attention (O(n²) theo độ dài) tăng vọt. Đo thật: không giới hạn ~167s/8 cặp dài, `max_length=1024` ~1s/8 cặp.
- **Cypher relationship TYPE không tham số hoá được** — mỗi loại quan hệ cần 1 query riêng, sinh từ whitelist cố định tại thời điểm module load (không bao giờ string-format từ giá trị runtime/dữ liệu người dùng vào tên type).
- **`git add -A` quét luôn file chưa từng review** — từng lỡ commit kèm 1 file checkpoint tạm. Luôn `git add` có chọn lọc từng path, xem `git status` trước khi commit.
- **RRF (Reciprocal Rank Fusion) mù trước chênh lệch chất lượng giữa 2 retriever** — RRF chỉ dùng thứ hạng, không dùng độ tự tin. Khi một nhánh (vd BM25) yếu hơn hẳn nhánh kia (vd dense) trên một corpus cụ thể, việc fuse có thể kéo Hybrid xuống THẤP HƠN retriever mạnh đứng một mình — không phải bug, là hệ quả toán học của phương pháp rank-based khi 2 tín hiệu lệch chất lượng xa nhau. Luôn đo Hybrid so với từng nhánh riêng lẻ trước khi mặc định "kết hợp luôn tốt hơn".
- **Regex chấm điểm câu trả lời LLM (multiple-choice, true/false) dễ bỏ sót câu trả lời ĐÚNG nhưng khác định dạng** — LLM hay chèn thêm từ đệm ("đáp án **chính xác** là B" thay vì "đáp án là B"), hoặc diễn giải dài mà không dùng đúng từ khoá yêu cầu ("Đúng"/"Sai"). Regex chấm điểm nên cho phép một số từ chen giữa các cụm neo, và với model 7B cục bộ, **siết prompt (thêm "KHÔNG giải thích") không đảm bảo khắc phục được** — đã thử và thất bại trên `qwen2.5:7b-instruct` khi ngữ cảnh phức tạp.
- **Sai tên hàm import (`get_or_create_collection` thay vì `get_chroma_collection`) không bị test bắt vì MỌI test đều inject/mock đúng hàm đó** — điểm mù kinh điển của dependency injection: test xanh 100% mà nhánh code mặc định (không inject) chưa từng được chạy thật. Nên có ít nhất 1 test kiểm tra chính đường mặc định (vd `inspect.getsource` để xác nhận tên hàm/module tồn tại).
- **Cơ chế xoá dữ liệu cũ dựa trên "nhớ id cần xoá TRƯỚC khi xoá node cha"** tự nó không thể tự sửa nếu bị ngắt giữa chừng (mất luôn cách biết id nào cần xoá). Thay bằng **reconcile 2 chiều, idempotent** (so sánh trạng thái đích với trạng thái thật, xoá phần lệch) — tự sửa mọi kiểu lệch dù chạy lại bao nhiêu lần.
- **Guard chống thao tác huỷ diệt hàng loạt do lỗi lập trình**: khi một script có khả năng xoá dữ liệu theo điều kiện tính toán được (vd "văn bản cũ = không còn trong danh sách nguồn"), luôn thêm ngưỡng an toàn cứng (vd "nếu >5% dữ liệu bị coi là cũ thì từ chối chạy, in mẫu ra để người kiểm tra") — tỉ lệ cao bất thường gần như luôn là lỗi lập trình, không phải dữ liệu thật đổi nhiều đến vậy.

## 📌 Quyết định khác

- **LLM extraction chạy 1 lần lúc ingest, không cache lại theo mỗi query** — thuộc tính tĩnh của văn bản, không đổi theo câu hỏi người dùng.
- **Rule-based trước, LLM fallback sau** cho mọi loại extraction có thể — giữ chi phí ingest thấp, chỉ dùng LLM cho phần thực sự cần hiểu ngữ nghĩa.
- **Đo trên tập benchmark lớn nhất có sẵn trước khi chốt bất kỳ ngưỡng/tham số nào** — bài học trực tiếp từ ADR-004: một quyết định đã qua xác minh nghiêm ngặt trên tập nhỏ vẫn có thể sai trên tập lớn hơn.
- **So sánh 2 hệ thống chỉ có ý nghĩa khi cùng bộ câu hỏi, cùng metric, cùng quy mô corpus** — nếu một trong ba biến này khác nhau, đặt 2 con số cạnh nhau là so sai, dù mỗi con số riêng lẻ đều đo đúng.
