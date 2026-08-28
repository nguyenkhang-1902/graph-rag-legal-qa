# 📜 Feature Specification: Graph RAG (Phase 1: engine gốc)

**Feature Branch**: `001-graph-rag-core` | **Created**: 2026-08-03 | **Status**: Superseded — xem ghi chú dưới

> **Đã pivot sang domain BHXH/lao động-tiền lương (2026-08-20+)**: spec này
> mô tả mục tiêu BAN ĐẦU (corpus 67k văn bản pháp luật đa lĩnh vực, nguồn
> Zalo — đã xoá khỏi đĩa). Corpus hiện tại là **19 văn bản BHXH/lao động**,
> temporal-first (chỉ luật hiện hành), xem `README.md`/`ROADMAP.md` cho spec
> đang sống. Giữ file này làm hồ sơ thiết kế gốc của engine (User Story
> 1/2 — multi-hop + benchmark — vẫn là năng lực cốt lõi đang dùng; User Story
> 4 — batch 67k — không còn áp dụng ở quy mô nhỏ hiện tại).

## 🎬 User Scenarios & Testing (mandatory)

### User Story 1 - Trả lời câu hỏi cần lần theo trích dẫn giữa các điều luật (Priority: P1)

Người dùng hỏi một câu mà câu trả lời đúng đòi hỏi phải hiểu quan hệ giữa nhiều điều khoản (vd "Điều 5 Luật ABC dẫn chiếu đến điều nào của Nghị định XYZ, và điều đó quy định gì?"). Hệ thống tìm điều luật liên quan trực tiếp, sau đó lần theo quan hệ REFERENCES/DEFINES trong graph để lấy đủ ngữ cảnh, rồi trả lời kèm đường đi trích dẫn (citation path) đã dùng.

**Why this priority**: Đây là năng lực khác biệt cốt lõi của Graph RAG so với Hybrid RAG cũ (chỉ retrieve theo similarity, không lần theo quan hệ) — nếu không làm được P1 thì project không chứng minh được giá trị của hướng đi.

**Independent Test**: Chạy độc lập bằng một tập câu hỏi multi-hop tự tạo (không cần các story khác), so kết quả graph traversal với ground truth trích dẫn thật trong văn bản.

**Acceptance Scenarios**:
1. **Given** graph đã được build từ corpus Zalo legal, **When** người dùng hỏi một câu multi-hop cần 2 điều luật liên quan qua REFERENCES, **Then** hệ thống trả về câu trả lời có trích dẫn cả hai điều, kèm đường đi quan hệ đã dùng để lấy ngữ cảnh.
2. **Given** một câu hỏi chỉ cần 1 điều luật (không cần traverse), **When** người dùng hỏi, **Then** hệ thống trả lời đúng mà không cần mở rộng graph không cần thiết (không lấy dư ngữ cảnh).

### User Story 2 - So sánh Graph RAG với baseline Hybrid+Reranker bằng số liệu thật (Priority: P1)

Chạy benchmark Recall@k/MRR trên cùng bộ câu hỏi Zalo (theo phương pháp `scripts/eval_zalo_recall.py` của project trước) cho cả hai cách tiếp cận, ra bảng so sánh.

**Why this priority**: Không có số liệu thì không chứng minh được Graph RAG có đáng làm hay không — đây là yêu cầu cứng của Quy tắc riêng #3 trong constitution.

**Independent Test**: Chạy script benchmark độc lập, không phụ thuộc UI/serving.

**Acceptance Scenarios**:
1. **Given** graph đã build xong trên cùng subset corpus (2k hoặc 10k văn bản) đã dùng ở project trước, **When** chạy benchmark, **Then** ra được Recall@4 và MRR của Graph RAG, đặt cạnh bảng số liệu Hybrid+Reranker cũ.

### User Story 3 - Ingest tăng dần khi có văn bản luật mới (Priority: P2)

Thêm văn bản mới vào corpus mà không cần build lại toàn bộ graph từ đầu.

**Why this priority**: Cần cho tính "hoàn chỉnh" của module nhưng không phải năng lực chứng minh giá trị cốt lõi — có thể làm sau P1/P2 chính.

**Independent Test**: Ingest 1 văn bản mới vào graph đã có sẵn, kiểm tra node/relationship mới xuất hiện đúng mà không phá dữ liệu cũ.

**Acceptance Scenarios**:
1. **Given** graph đã có N văn bản, **When** ingest thêm 1 văn bản có điều khoản viện dẫn văn bản cũ, **Then** relationship REFERENCES trỏ đúng sang node cũ đã tồn tại (không tạo node trùng).

### User Story 4 - Ingest toàn bộ 67k văn bản theo batch, chịu được gián đoạn (Priority: P1)

✅ **Chốt 2026-08-03**: quy mô corpus tăng từ subset 2k/10k lên **toàn bộ 67k văn bản** Zalo legal corpus. Ingest chạy theo batch (kích thước cấu hình được), ghi savepoint sau mỗi batch — nếu tiến trình bị dừng giữa chừng (crash, mất điện, chủ động dừng), chạy lại phải tiếp tục từ batch cuối đã lưu, không xử lý lại từ đầu.

**Why this priority**: Ở quy mô 67k, LLM extraction (DEFINES/AMENDS/CONFLICTS_WITH) cho toàn bộ corpus sẽ chạy nhiều giờ — không có savepoint thì một lần lỗi giữa chừng là mất toàn bộ thời gian đã chạy. Đây là yêu cầu hạ tầng bắt buộc, không phải tính năng phụ.

**Independent Test**: Ingest 100 văn bản đầu, dừng cứng tiến trình (kill -9) ở batch thứ 3, chạy lại lệnh ingest — xác nhận batch 1-2 không bị xử lý lại, batch 3 chạy lại từ đầu batch (không half-broken), batch 4+ tiếp tục bình thường.

**Acceptance Scenarios**:
1. **Given** ingest đang chạy batch thứ N trên tổng M batch của 67k văn bản, **When** tiến trình bị dừng đột ngột, **Then** file/bảng savepoint ghi rõ batch cuối cùng đã hoàn tất (N-1), không phải batch đang xử lý (N).
2. **Given** savepoint ghi batch N-1 đã hoàn tất, **When** chạy lại lệnh ingest, **Then** hệ thống bắt đầu từ batch N, không ingest lại batch 1..N-1 (idempotent theo `doc_id`, không tạo node trùng dù có ingest lại nhầm).

### Edge Cases

- Điều luật viện dẫn một điều/luật không có trong corpus (văn bản ngoài phạm vi ingest) → node "external reference" placeholder, không crash, không bịa nội dung.
- Vòng lặp trích dẫn (Điều A → Điều B → Điều A) → traversal phải có giới hạn hop và chống lặp vô hạn.
- Văn bản có OCR lỗi khiến regex bắt sai số điều → có bước validate/log cảnh báo, không âm thầm tạo relationship sai.

## ✅ Requirements (mandatory)

### Functional Requirements

- **FR-001**: Hệ thống PHẢI trích xuất cấu trúc phân cấp Document → Chapter → Article (→ Clause nếu có) từ văn bản luật khi ingest.
- **FR-002**: Hệ thống PHẢI trích xuất quan hệ REFERENCES giữa các Article dựa trên cách viện dẫn chuẩn trong văn bản pháp luật Việt Nam (regex rule-based).
- **FR-003**: Hệ thống PHẢI trích xuất quan hệ DEFINES/USES_TERM và AMENDS/SUPERSEDES/CONFLICTS_WITH bằng LLM khi rule-based không đủ (chạy một lần lúc ingest, không chạy lại mỗi query). ✅ Chốt: làm ngay ở P1 cho toàn bộ corpus, không dời P2.
- **FR-004**: Hệ thống PHẢI cho phép tìm entry-point node bằng vector similarity search trên nội dung Article.
- **FR-005**: Hệ thống PHẢI traverse graph tối đa N hop (N cấu hình được qua `.env`, mặc định **N=2** ✅ đã chốt 2026-08-03 — cân bằng giữa đủ sâu cho chuỗi trích dẫn pháp luật thường 1-2 cấp, và tránh kéo dư ngữ cảnh không liên quan) từ entry-point để lấy ngữ cảnh mở rộng.
- **FR-006**: Hệ thống PHẢI trả về câu trả lời kèm đường đi trích dẫn (danh sách Article + relationship đã dùng) để người dùng kiểm chứng.
- **FR-007**: Hệ thống PHẢI có script benchmark đo Recall@k và MRR theo cùng phương pháp project trước, chạy trên cùng benchmark dataset.
- **FR-008**: Hệ thống PHẢI ingest theo batch với savepoint (checkpoint sau mỗi batch hoàn tất) — resume đúng từ batch cuối đã lưu nếu bị gián đoạn, idempotent theo `doc_id`/`article_id` (không tạo node trùng dù ingest lại). ✅ Chốt: bắt buộc cho quy mô 67k văn bản (xem User Story 4), không phải "nice to have".

### 🗂️ Key Entities

- **Document**: một văn bản luật/nghị định/thông tư hoàn chỉnh — có tiêu đề, số hiệu, cơ quan ban hành, ngày hiệu lực.
- **Chapter**: một chương trong Document — có số chương, tiêu đề chương.
- **Article (Điều)**: đơn vị nội dung chính — có số điều, nội dung văn bản.
- **Clause (Khoản)**: đơn vị con của Article, khi văn bản chia nhỏ tới mức khoản.
- **Term**: một thuật ngữ được định nghĩa chính thức trong văn bản, dùng lại ở nhiều Article khác.
- **Organization**: cơ quan ban hành/thi hành văn bản.

## 🎯 Success Criteria (mandatory)

- **SC-001**: Trên tập câu hỏi multi-hop (tối thiểu 30 câu, Claude soạn từ corpus thật — xem Assumptions), Graph RAG trả lời đúng và trích dẫn đủ các điều luật liên quan trong ít nhất 80% trường hợp.
- **SC-002**: Recall@4 của Graph RAG trên **toàn bộ 67k văn bản** không thấp hơn quá 5 điểm % so với Hybrid+Reranker đo ở quy mô tương ứng (project trước đo 93.3% ở 10k — cần đo lại baseline ở 67k nếu chưa có số, ghi rõ trong bảng so sánh) — nếu thấp hơn nhiều hơn, phải có phân tích nguyên nhân trong `research.md`.
- **SC-003**: Có bảng so sánh số liệu (Recall@4, MRR, latency p95) giữa Graph RAG và Hybrid+Reranker ở cùng quy mô corpus, công khai trong README.
- **SC-004**: Ingest tăng dần 1 văn bản mới (sau khi đã có graph 67k) hoàn tất trong dưới 5 phút.
- **SC-005**: Ingest batch toàn bộ 67k văn bản chịu được gián đoạn giữa chừng — resume từ savepoint không mất tiến độ đã chạy, không tạo dữ liệu trùng/half-broken (đo bằng test kill -9 giữa batch, xem User Story 4).

## 💭 Assumptions

- Corpus Zalo legal 67k văn bản lấy qua `scripts/fetch_zalo_legal_corpus.py` (điều chỉnh `--subset-size` lên toàn bộ) hoặc nguồn tương đương.
- Batch size ingest mặc định cấu hình qua `.env` (`INGEST_BATCH_SIZE`), giá trị khởi điểm đề xuất trong `research.md` — điều chỉnh theo thực tế throughput LLM extraction đo được.
- Neo4j chạy local Docker, không cần cân nhắc HA/cluster dù dữ liệu tăng lên 67k (vẫn trong khả năng 1 instance Community).
- Không cần UI người dùng cuối ở scope hiện tại — API + Neo4j Browser demo là đủ cho "module hoàn chỉnh" mục tiêu CV. ✅ Chốt 2026-08-03.
- Tập câu hỏi multi-hop dùng để test SC-001 do Claude soạn dựa trên corpus thật, Khang duyệt lại trước khi dùng làm tiêu chí nghiệm thu chính thức. ✅ Chốt 2026-08-03.
