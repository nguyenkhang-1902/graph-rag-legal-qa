# 📖 Giải nghĩa thuật ngữ kỹ thuật — Graph RAG Legal QA

> Giải thích lại các khái niệm hay gặp trong project này, đối chiếu trực tiếp với code thật (`app/`, `scripts/`) chứ không chỉ định nghĩa chung chung. Cập nhật thêm khi gặp thuật ngữ mới trong quá trình làm.

## 🧭 1. Vector, embedding, cosine similarity

**Embedding**: một đoạn văn bản (câu hỏi, hoặc nội dung 1 Điều luật) được mô hình (ở đây là `BAAI/bge-m3`, xem `app/config.py` dòng `EMBEDDING_MODEL`) chuyển thành một vector số thực (vd 1024 chiều). Hai đoạn văn có ý nghĩa gần nhau thì vector của chúng cũng "nằm gần nhau" trong không gian đó.

**Cosine similarity**: cách đo "hai vector giống nhau đến mức nào" bằng góc giữa chúng, không quan tâm độ dài vector — chỉ quan tâm hướng. Công thức: `cosine_similarity = (A · B) / (|A| × |B|)`. Giá trị chạy từ **-1 đến 1**:
- `1.0` = hai vector giống hệt hướng (nội dung gần như trùng ý nghĩa)
- `0.0` = vuông góc, không liên quan
- `-1.0` = ngược hướng hoàn toàn (hiếm gặp với embedding văn bản thật)

Ví dụ trực quan: câu hỏi "Điều nào quy định về thời hiệu khởi kiện?" sẽ có cosine similarity cao với Điều luật thực sự nói về thời hiệu khởi kiện, và thấp với một Điều luật về xử phạt vi phạm giao thông.

**Cosine distance (Chroma dùng cái này, không phải similarity trực tiếp)**: `distance = 1 - cosine_similarity`. Đây là lý do trong `app/retrieval/entry_point.py` (dòng 63) có phép chuyển đổi `similarity = 1.0 - distance` — đã verify bằng test thật (`tests/retrieval/test_entry_point.py`), không phải giả định suông:

| Quan hệ 2 vector | cosine similarity | Chroma distance |
|---|---|---|
| Giống hệt nhau | 1.0 | 0.0 |
| Vuông góc (không liên quan) | 0.0 | 1.0 |
| Ngược hướng hoàn toàn | -1.0 | 2.0 |

## 🎚️ 2. SIMILARITY_THRESHOLD (ngưỡng cosine similarity)

Định nghĩa trong `app/config.py`, dùng trong `app/retrieval/entry_point.py` hàm `find_entry_points()`:

1. Câu hỏi được embed thành vector.
2. Chroma trả về `top_k` (mặc định 5) Article có vector **gần nhất** với câu hỏi.
3. Trong 5 kết quả đó, chỉ **giữ lại** những Article có `similarity >= SIMILARITY_THRESHOLD` — cái nào thấp hơn ngưỡng bị loại, dù vẫn nằm trong top 5 gần nhất.

Đây là **bộ lọc chất lượng ở tầng retrieval thật** (hệ thống dùng chính logic này khi trả lời `/chat`, không phải logic riêng chỉ để eval — xem docstring `scripts/eval_graph_recall.py` dòng 9-13) — khác với việc "nới lỏng tiêu chí chấm điểm" trong benchmark. Hạ threshold từ 0.75 xuống 0.65 nghĩa là: chấp nhận Article có độ liên quan thấp hơn một chút cũng được tính là entry-point hợp lệ.

**Vì sao 0.75 có thể quá gắt**: câu hỏi người dùng viết bằng văn phong tự nhiên ("Điều nào nói về..."), còn Điều luật viết bằng văn phong hành chính — hai văn phong khác nhau khiến cosine similarity giữa chúng khó đạt mức rất cao dù nội dung đúng ý nhau. Ngưỡng 0.75 có thể đã loại bỏ nhầm nhiều Article đúng, khiến nhiều câu hỏi không tìm được entry-point nào → Strict/Lenient recall thấp (như bảng T017 bạn đo được: 59.4%/58.6%).

**Cách xác nhận 0.65 là hợp lý, không phải "chỉnh số cho đẹp"**: lấy vài case trước đây fail ở 0.75 nhưng pass ở 0.65, đọc tay nội dung Article được chọn — nếu nó thực sự trả lời đúng câu hỏi thì 0.65 là cải thiện thật.

## 📊 3. Các chỉ số đo retrieval (Recall, MRR)

**Recall@k**: trong số các "đáp án đúng" cần tìm, hệ thống tìm ra được bao nhiêu phần trăm khi chỉ xét `k` kết quả trả về đầu tiên. Recall cao = ít bỏ sót.

Project này **định nghĩa lại Recall theo 2 kiểu** vì một câu hỏi Graph RAG có thể cần **nhiều** Article để trả lời đủ (không như retrieval thường chỉ cần đúng 1 nguồn) — xem `scripts/eval_graph_recall.py` dòng 36-47:

- **Strict recall** (`all_found`, hàm `_evaluate_question` dòng 126): tính theo **từng câu hỏi trọn vẹn** — câu hỏi chỉ được tính "đúng" nếu **TẤT CẢ** Article cần thiết (`expected_article_ids`) đều được tìm thấy. Thiếu 1 trong số đó = câu hỏi đó tính là sai (all-or-nothing). Đây là chỉ số khớp đúng yêu cầu SC-001 trong `spec.md` ("trích dẫn ĐỦ các điều luật liên quan").
- **Lenient recall** (dòng 163, `total_found / total_expected`): tính theo **từng Article riêng lẻ**, gộp trên toàn bộ tập câu hỏi. Ví dụ câu hỏi cần 3 Article mà tìm được 2 → không tính "đúng" ở strict, nhưng vẫn đóng góp 2/3 vào lenient recall. Chỉ số này cho thấy hệ thống "gần đúng" tới đâu, dù không đạt chuẩn strict.

Ví dụ cụ thể để dễ hình dung: có 2 câu hỏi. Câu A cần [Điều 1, Điều 2] và tìm được cả 2. Câu B cần [Điều 5, Điều 6, Điều 7] và chỉ tìm được Điều 5.
- Strict recall = 1/2 = 50% (chỉ câu A đạt "đủ")
- Lenient recall = (2+1) / (2+3) = 3/5 = 60% (tính theo từng Article riêng)

**MRR (Mean Reciprocal Rank)**: đo hệ thống trả kết quả đúng ở **vị trí gần đầu danh sách** đến mức nào. Với 1 câu hỏi, "reciprocal rank" = `1 / vị trí` của kết quả đúng đầu tiên (vị trí 1 → 1.0, vị trí 2 → 0.5, vị trí 4 → 0.25, không tìm thấy → 0). MRR là trung bình cộng của các giá trị đó trên toàn bộ câu hỏi. Vì mỗi câu hỏi ở đây có thể cần nhiều Article, project dùng **rank tốt nhất** trong số các Article tìm được cho mỗi câu hỏi (`app/scripts/eval_graph_recall.py` dòng 129, đây là cách mở rộng MRR chuẩn trong tài liệu Information Retrieval khi có nhiều "relevant document" cho 1 truy vấn, không phải tự nghĩ ra).

**Vì sao không có "Precision" trong bảng T017**: Precision đo "trong số kết quả trả về, bao nhiêu % là đúng" — hữu ích khi lo hệ thống trả về quá nhiều kết quả rác. Ở P1, project ưu tiên đo recall trước (có tìm đủ được không) vì đó là năng lực cốt lõi cần chứng minh (SC-001/SC-002); precision là hướng đo thêm nếu sau này cần tối ưu độ "gọn" của ngữ cảnh trả về.

## 🕸️ 4. Thuật ngữ riêng của Graph RAG trong project

- **Entry point**: (các) Article được tìm thấy đầu tiên qua vector search (`find_entry_points`) — điểm khởi đầu để "đi" trên graph.
- **top_k**: số lượng entry point tối đa lấy ra từ Chroma trước khi lọc theo `SIMILARITY_THRESHOLD` (mặc định 5, xem `_DEFAULT_TOP_K` trong `eval_graph_recall.py`).
- **MAX_HOP / multi-hop traversal**: số bước tối đa hệ thống "nhảy" theo quan hệ `REFERENCES` trong graph từ entry point để lấy thêm ngữ cảnh (đã chốt = 2, xem `spec.md` FR-005). 1-hop = Article được trích dẫn trực tiếp; 2-hop = Article được trích dẫn bởi Article đó (A→B→C).
- **Citation path**: danh sách Article + quan hệ đã đi qua để tới được câu trả lời — hiển thị cho người dùng kiểm chứng (FR-006).
- **Confidence** (dùng trong quan hệ `AMENDS`/`SUPERSEDES`/`CONFLICTS_WITH`, `data-model.md`): độ tin cậy do LLM tự đánh giá khi suy luận ra một quan hệ ngữ nghĩa (không rule-based rõ ràng như REFERENCES) — dùng để lọc bớt quan hệ LLM đoán sai khi cần.

## 💾 5. Thuật ngữ về ingest & lưu trữ

- **Idempotent**: chạy lại nhiều lần cùng một thao tác vẫn ra kết quả giống hệt (không tạo dữ liệu trùng). Ví dụ: ingest lại cùng 1 văn bản không tạo thêm node `Article` mới, mà cập nhật node cũ theo `article_id`.
- **Savepoint / checkpoint** (`app/ingest_checkpoint/`, `.state/ingest_checkpoint.json`): điểm đánh dấu "đã xử lý xong tới đâu" trong một tiến trình dài (ingest 67k văn bản theo batch) — để nếu bị dừng giữa chừng, chạy lại có thể tiếp tục từ chỗ dở dang thay vì làm lại từ đầu.
- **Batch**: một nhóm văn bản được xử lý cùng lúc rồi mới ghi checkpoint, thay vì xử lý — ghi checkpoint cho từng văn bản một (đỡ tốn I/O, nhưng nếu crash giữa batch thì mất tiến độ của cả batch đó, không phải chỉ 1 văn bản).
- **Constraint / Index** (Neo4j, `data-model.md`): `CONSTRAINT ... UNIQUE` đảm bảo một thuộc tính (vd `article_id`) không trùng lặp trong toàn graph; `INDEX` giúp tra cứu nhanh theo thuộc tính đó thay vì quét toàn bộ node.

---

*File này để tra cứu nhanh khi đọc lại spec/code sau này. Thêm thuật ngữ mới vào đúng mục liên quan khi gặp — không cần tạo file mới trừ khi mục này quá dài.*
