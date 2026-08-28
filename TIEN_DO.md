# 📓 GRAPH RAG — NHẬT KÝ TIẾN ĐỘ PHASE 1 (engine gốc, 2026-08-03 → 08-10)

> **File này ghi lại giai đoạn xây ENGINE GỐC trên corpus Zalo 67k văn bản đa
> lĩnh vực** (đã xoá khỏi đĩa 2026-08-24 khi pivot sang domain **BHXH/lao
> động-tiền lương**). Muốn biết **tiến độ hiện tại**, đọc `ROADMAP.md` +
> `README.md` — hai file đó là nhật ký sống của giai đoạn BHXH. File này giữ
> lại làm hồ sơ: các quyết định/lỗi thật đã đúc kết thành ADR/sổ bẫy đọc ở
> `specs/001-graph-rag-core/research.md` (khuyến khích đọc research.md trước,
> vì phần lớn bài học "tổng quát hoá được" đã chuyển qua đó). File này chỉ
> còn narrative rút gọn theo mốc thời gian.

## Dòng thời gian rút gọn

**ĐỢT 1-2 (08-03)** — Brainstorm hướng đi (chọn Graph RAG thay Microsoft GraphRAG/NetworkX), viết constitution/spec/plan/tasks/data-model. Chốt: `MAX_HOP=2`, Article không lưu full text (chỉ preview + `chroma_id` trỏ Chroma), quy mô tăng từ đề xuất 2k/10k lên **toàn bộ 67k văn bản** kèm batch+savepoint (ADR-002).

**ĐỢT 3 (08-03)** — Triển khai Phase 1+2 (T001-T009d): scaffold, Neo4j client, `reference_extractor.py`/`structure_parser.py`/`upsert.py` (TDD, 83/83 test). Phát hiện quan trọng bằng dữ liệu thật (447 văn bản mẫu): **corpus thật là per-Article chunk** (1 file = 1 Điều), khác giả định ban đầu Document→Chương→Điều→Khoản đầy đủ — sửa bằng `parse_article_chunk()`. Test kill -9 thật xác nhận resume đúng (SC-005).

**ĐỢT 4 (08-04)** — Ingest full 61,068 văn bản thật (60,679 Article/3,203 Document/37,875 REFERENCES). Phát hiện gap: chưa task nào ghi embedding vào Chroma → thêm `embedder.py`+`backfill_embeddings.py` (T009f), bắt được bug Chroma thiếu `hnsw:space=cosine` trước khi chạy full. `entry_point.py`/`traversal.py`/`serving/api.py` (`POST /chat`) hoàn tất — checkpoint thật qua API xác nhận multi-hop hoạt động. 32 câu eval multi-hop (`build_multihop_eval_set.py`) — Khang duyệt chính thức.

**ĐỢT 5 (08-05)** — Chẩn đoán GPU embedding chỉ nhanh hơn CPU 1.1x (kỳ vọng 5-8x) — 2 nguyên nhân thật: HF Hub network check khi init model (fix `HF_HUB_OFFLINE=1`) + batch không sort theo độ dài khiến outlier kéo chậm cả batch (fix sort + cap batch theo tầng độ dài). Sau fix: GPU nhanh hơn CPU 7.3-8.5 lần, đúng kỳ vọng.

**ĐỢT 6-7 (08-05)** — `term_extractor.py` (T012, DEFINES/USES_TERM rule-based). Mở rộng độ phủ 2 lần bằng khảo sát dữ liệu thật (6→844 file có định nghĩa trích được, không cần LLM) — quyết định không đầu tư LLM fallback.

**ĐỢT 8 (08-06)** — Backfill embedding full 60,679 Article hoàn tất 100%, xác nhận khớp tuyệt đối Neo4j↔Chroma.

**ĐỢT 9 (08-06)** — `eval_graph_recall.py` (T017), baseline đầu 59.4% dưới mục tiêu 80%. Điều tra: ngưỡng similarity 0.75 lọc oan >50% kết quả đúng → hạ xuống 0.65 sau khi đọc tay 10/10 case lật + held-out split-half → 90.6%/93.1%/MRR 0.917 (ADR-004, sau này phát hiện lại không suy rộng được ra tập lớn hơn — xem research.md).

**ĐỢT 10 (08-06)** — `relation_llm.py` (T013, AMENDS/SUPERSEDES/CONFLICTS_WITH). Verify thật trên 3000 file. 2 phát hiện lớn: (1) độ phủ candidate rất thấp vì regex trích dẫn không khớp mẫu "của"/"số"; (2) bug thật ảnh hưởng TOÀN BỘ REFERENCES — slug từ tên trích dẫn không khớp `doc_id` từ tên file (~1.4% external placeholder là "giả").

**ĐỢT 11-12 (08-06)** — Khang chốt 5 điểm treo. `term_extractor` mở rộng thêm (T012 đóng hẳn). `doc_identity.py` (T025) suy `Document.title/so_hieu/loai_vb` từ tên file — phát hiện corpus không có tiêu đề văn bản ở đâu cả. Bug thật TDD bắt được: chữ `ð` (eth, khác `đ`) làm 119 Article không bao giờ được trích dẫn chéo tìm thấy. T026 sửa gốc rễ slug (bug ĐỢT 10 hoá ra nghiêm trọng hơn nhiều: chỉ 0.47% trích dẫn resolve đúng cross-document, không phải 1.4%). `migrate_references.py` (T027, script duy nhất xoá dữ liệu thật, mặc định dry-run). Lỗi thật của Claude: sai tên hàm `get_or_create_collection` làm hỏng 119 bản ghi Chroma — sửa bằng cách đổi cơ chế sang reconcile 2 chiều thay vì chỉ sửa tên hàm (chi tiết ở research.md sổ bẫy).

**ĐỢT 13 (08-07)** — Migration T027 chạy xong hoàn toàn, mọi số liệu khớp đúng bảng đã tính trước. **Phát hiện lớn**: graph traversal chỉ đóng góp +3.1 điểm % (đúng 1/58 câu) vào Strict recall trên bộ 32 câu — dense-only đã đạt 87.5%. Đặt câu hỏi trực tiếp vào luận điểm cốt lõi của dự án (đã giải quyết ở giai đoạn sau — xem ĐỢT 16-17).

**ĐỢT 14-15 (08-08)** — Đo backend BM25 thật ở 61k (`bm25s` nhanh hơn `rank_bm25` ~360x, Recall@4 cao hơn 6.3pp nhưng chỉ khớp thứ hạng ~66% — không phải thay thế trong suốt). T018 (so Graph RAG với Hybrid+Reranker baseline tự đo ở 67k) — bắt được 1 lỗi số liệu sai trước khi vào báo cáo (checkpoint không ghi số câu hỏi, y hệt lớp lỗi `BatchSizeMismatchError` cũ — xem research.md ADR-002). Phát hiện: Hybrid RRF kém hơn Dense-only ở 67k (ngược 10k của dự án trước) vì BM25 yếu ở quy mô lớn kéo dense mạnh xuống.

**ĐỢT 16 (08-08)** — T018 đủ số liệu, cùng 793 câu/cùng metric (ADR-005). **Phát hiện lớn nhất**: `SIMILARITY_THRESHOLD=0.65` (đã qua xác minh nghiêm ngặt ở ĐỢT 9) làm mất **12.3 điểm %** Recall@4 trên tập 793 câu lớn hơn — bài học về suy rộng cỡ mẫu (research.md ADR-004).

**ĐỢT 17 (08-10)** — T028: rà soát toàn tuyến embedding (theo yêu cầu, KHÔNG hạ thêm ngưỡng). Chẩn đoán đúng bản chất bài toán (độ lớn similarity, không phải xếp hạng) bằng tương quan Spearman với độ dài Điều. Thêm vector cấp Khoản cho Điều dài + giới hạn ngữ cảnh `MAX_CONTEXT_ARTICLES=10` theo đường cong bão hoà đo được. Kết quả nhỏ hơn dự đoán 3 lần (+1.6pp thay vì +4.9pp dự đoán) — bài học: pilot đo một chiều là giới hạn trên, không phải ước lượng (research.md ADR-006).

## 🔀 Bước ngoặt — Pivot sang BHXH (2026-08-20+)

Sau ĐỢT 17, dự án dừng mở rộng corpus 67k đa lĩnh vực và pivot sang domain hẹp hơn nhưng **luôn đúng luật hiện hành**: BHXH → mở rộng lao động-tiền lương. Lý do (đúc kết trong `ROADMAP.md`): "dữ liệu nhỏ + đúng > dữ liệu lớn + lỗi thời" — corpus Zalo 2021 đã lỗi thời, không phân biệt được luật còn/hết hiệu lực. Toàn bộ dữ liệu + phần lớn script đặc thù Zalo đã xoá; engine (Neo4j/Chroma/traversal/reranker) giữ lại làm nền.

**Từ đây, đọc `ROADMAP.md` (lộ trình + trạng thái hiện tại) và `README.md` (số liệu đánh giá mới nhất) — không cập nhật thêm vào file này.**
