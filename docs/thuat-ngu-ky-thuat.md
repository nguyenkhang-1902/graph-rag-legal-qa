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

## 🏷️ 6. Định danh văn bản pháp luật (bổ sung 2026-08-06, T025/T026)

Ba cách viết cùng một văn bản, rất hay bị lẫn — đây chính là nguồn gốc bug T026:

| Cách viết | Ví dụ | Ai dùng |
|---|---|---|
| **Tên file** | `19_2016_tt-bxd` | corpus tải về (`data/raw/`), `app/ingest.py` đọc |
| **Số hiệu văn bản** | `19/2016/TT-BXD` | cách trích dẫn chuẩn *trong* nội dung văn bản |
| **`doc_id`** | `19-2016-tt-bxd` | khoá trong Neo4j |

- **Số hiệu văn bản**: mã định danh chính thức, gồm 3 phần `{số thứ tự}/{năm ban hành}/{mã hiệu}`. Ví dụ `99/2015/NĐ-CP` = văn bản số 99, ban hành năm 2015, mã hiệu NĐ-CP.
- **Mã hiệu**: phần cuối số hiệu, cho biết **loại văn bản** + **cơ quan ban hành**. `NĐ-CP` = Nghị định của Chính phủ; `TT-BXD` = Thông tư của Bộ Xây dựng; `QĐ-TTg` = Quyết định của Thủ tướng; `TTLT-...` = Thông tư liên tịch (nhiều cơ quan). Tiền tố (phần trước dấu `-` đầu tiên) là thứ dùng để suy ra loại văn bản — xem `_MA_HIEU_PREFIX_TO_LOAI_VB` trong `app/extraction/doc_identity.py`.
- **Mã hiệu Quốc hội (`QH13`, `QH14`...)**: `QH` + số khoá Quốc hội. ⚠️ Đây là ngoại lệ quan trọng: mã hiệu này dùng **chung** cho Luật / Bộ luật / Nghị quyết / Pháp lệnh, nên **không suy ra được loại văn bản** — 98 văn bản trong corpus thuộc nhóm này, `loai_vb` để `None` thay vì đoán.
- **`doc_id` vs `article_id`**: `doc_id` là văn bản (`19-2016-tt-bxd`), `article_id` là một Điều cụ thể trong đó (`19-2016-tt-bxd_dieu-5`). ⚠️ `article_id` **cũng chính là id trong Chroma** — nên đổi cách sinh `doc_id` đồng nghĩa với phải embed lại toàn bộ Article liên quan. Đây là lý do một số bất nhất nhỏ (4 văn bản dùng chữ `ð`) được ghi nhận là hạn chế chứ không sửa ngầm.
- **Chỉ danh chuẩn (canonical designation)**: cụm `"{loại văn bản} {số hiệu}"` — ví dụ `"Thông tư 19/2016/TT-BXD"`. Đây là thứ `Document.title` đang chứa sau T025. ⚠️ **Không phải** tiêu đề văn xuôi (`"Thông tư quy định chi tiết về phát triển nhà ở..."`) — tiêu đề đó **không tồn tại** trong corpus (dataset Zalo trả về từng Điều riêng lẻ, không có bản ghi cấp văn bản).

## 🔀 7. Các loại trích dẫn (T026)

Phân loại theo mức độ resolve được, quyết định `target_article_id` trỏ đi đâu:

1. **Self-reference (tự trích dẫn)**: `"...quy định tại Điều 10..."` hoặc `"Điều 5 của Luật này"` — trỏ tới một Điều **trong chính văn bản đang đọc**. `doc_slug` = `current_doc_slug`.
2. **Cross-document reference có số hiệu**: `"Điều 10 Nghị định số 16/2010/NĐ-CP"` — resolve chính xác thành `16-2010-nd-cp_dieu-10`. Đây là nhóm T026 sửa được.
3. **Cross-document reference chỉ có tên**: `"Điều 5 của Luật Doanh nghiệp"` — ⚠️ **không resolve tự động được**. Cùng một tên có thể ứng với nhiều phiên bản (`Luật Chứng khoán` có 3 phiên bản 2019/2006/2010) — chọn bừa một phiên bản là **sai về mặt pháp lý**. 30,024 lượt trong corpus thuộc nhóm này.

**Dangling reference (trích dẫn treo)**: edge REFERENCES trỏ tới một `article_id` **không tồn tại** trong graph. Dấu hiệu thường gặp nhất của resolve sai — đo được 14,621/115,016 self-reference (12,7%) trỏ tới Điều không có trong chính văn bản đó, chính là bằng chứng phát hiện bug T026.

**Trigger phrase (cụm kích hoạt)**: cụm từ bắt buộc phải xuất hiện trong văn bản để một mẫu rule-based được **cho phép** chạy (`term_extractor.py`: `"được hiểu như sau"`, `"giải thích từ ngữ"`). Mục đích: cùng một cấu trúc cú pháp (`"N. X là Y"`) mang ngữ nghĩa hoàn toàn khác nhau tuỳ ngữ cảnh — 5,707 file có cấu trúc đó nhưng là danh sách điều kiện/thủ tục, không phải định nghĩa. Trigger là cách rẻ nhất để phân biệt mà không cần LLM.

## 🧹 8. Thuật ngữ về migration & vận hành dữ liệu (T027)

- **Dữ liệu dẫn xuất (derived data)**: dữ liệu tính ra được từ nguồn bằng code, nên xoá đi không mất mát thật. REFERENCES/placeholder là dẫn xuất từ `data/raw/*.md`; embedding trong Chroma thì **không** (tốn hàng giờ GPU để tạo lại) — đây là lý do migration được phép xoá cái đầu nhưng tuyệt đối không đụng cái sau.
- **Stale data (dữ liệu cũ đọng lại)**: hệ quả trực tiếp của **MERGE idempotent** — MERGE chỉ *thêm* chứ không bao giờ *xoá*, nên khi logic sinh dữ liệu được sửa, các edge sai cũ **vẫn nằm đó**. Chạy lại ingest không đủ: graph sẽ chứa cả edge đúng (mới) lẫn edge sai (cũ), tệ hơn trước khi sửa. Bắt buộc phải xoá tường minh.
- **Dry-run**: chạy để **báo cáo** những gì *sẽ* thay đổi mà không thay đổi gì. `scripts/migrate_references.py` mặc định dry-run, phải truyền `--apply` mới thực sự ghi — quy ước cho script duy nhất trong dự án xoá dữ liệu thật.
- **Orphan node (node mồ côi)**: node không còn quan hệ nào sau khi xoá edge. Migration chỉ xoá external placeholder **mồ côi** — placeholder vẫn đang là đích của AMENDS/SUPERSEDES/CONFLICTS_WITH (T013) phải được giữ. Đây là lý do dùng `COUNT { (a)--() } = 0` chứ **không** dùng `DETACH DELETE` (DETACH sẽ xoá luôn cả quan hệ còn lại).
- **`CALL ... IN TRANSACTIONS`**: cú pháp Cypher chia một thao tác lớn thành nhiều transaction nhỏ. Xoá 37,875 edge trong **một** transaction dễ làm hết heap của Neo4j Community — chia lô 10,000 dòng là đủ an toàn. Chỉ chạy được trong auto-commit transaction (`session.run`), không chạy được bên trong transaction tường minh.

## ⚡ 9. Thuật ngữ hiệu năng gặp thật trong dự án

- **Regex cache thrashing**: Python cache sẵn các pattern đã `re.compile` nhưng **chỉ 512 pattern**. Khi số pattern phân biệt vượt ngưỡng đó (dự án này: ~6,900 tên thuật ngữ), mỗi lần gọi lại bị recompile từ đầu → chậm gấp nhiều lần. Phát hiện thật 2026-08-06: `extract_terms.py` chạy hơn 50 phút chưa xong; sau khi thêm `lru_cache` cho `_compile_term_pattern` + tiền lọc `in` thì còn ~8,5 phút.
- **Tiền lọc (prefilter)**: kiểm tra rẻ trước khi làm phép đắt, với điều kiện **phép rẻ không bao giờ loại oan** kết quả mà phép đắt sẽ tìm được. Ở đây: `ten_thuat_ngu not in text` (so khớp chuỗi ở tầng C, rất nhanh) chạy trước regex word-boundary — an toàn vì regex chỉ *lọc hẹp thêm* những gì `in` đã tìm thấy, không bao giờ tìm ra thứ `in` không thấy.
- **Padding theo batch**: xem lại mục về `EMBED_BATCH_SIZE`/batching theo tầng độ dài trong `TIEN_DO.md` ĐỢT 5 — cùng một họ vấn đề "một phần tử ngoại lai làm chậm cả lô".

## 🧪 10. Thuật ngữ về chất lượng & an toàn khi sửa dữ liệu thật (bổ sung ĐỢT 12)

- **Mojibake / biến thể encoding**: cùng một chữ bị ghi thành ký tự khác do lỗi chuyển bảng mã. Gặp thật trong corpus: **`ð` (eth, U+00F0)** thay cho **`đ` (U+0111)** — nhìn gần giống nhưng là **hai chữ cái khác nhau**, `ð` không phải "d + dấu" nên `unicodedata.normalize("NFD", ...)` không tách được. Hệ quả: `slugify_doc_name` biến `nð-cp` thành `n-cp` (mất chữ) thay vì `nd-cp`. Bài học chung: khi chuẩn hoá tiếng Việt, đừng chỉ xử lý dấu — phải xử lý cả các chữ cái bị ghi sai bảng mã. Xem `normalize_eth` trong `app/extraction/slugify.py`.

- **Pinning test (test ghim hành vi)**: test viết ra để **cố định một hành vi đã biết là chưa lý tưởng**, kèm ghi chú "nếu sau này quyết sửa thì test này sẽ đỏ". Mục đích không phải khẳng định hành vi đó đúng, mà là **không cho ai đổi nó trong im lặng**. Đã hoạt động đúng ý định trong dự án này: test ghim hạn chế `doc_id` của 4 văn bản `ð` đã đỏ đúng lúc Khang quyết sửa, buộc phải đảo lại tường minh thay vì âm thầm đổi khoá định danh của 119 Article.

- **Điểm mù của dependency injection**: khi mọi test đều **truyền dependency thay thế** (mock/fake) vào, **đường code mặc định không bao giờ được chạy** — test xanh 100% mà implementation thật vẫn sai. Gặp thật: `_delete_from_chroma` import sai tên hàm (`get_or_create_collection` thay vì `get_chroma_collection`), 13/13 test xanh, lỗi chỉ lộ ra khi chạy trên dữ liệu thật. **Cách phòng**: viết thêm ít nhất một test nhắm vào chính đường mặc định — nếu gọi thật quá đắt (mở DB/tải model) thì kiểm bằng `inspect.getsource`/`assert callable(...)`, vẫn tốt hơn không kiểm gì.

- **Idempotent ≠ tự sửa được (self-healing)**: hai tính chất khác nhau, dễ lẫn.
  - *Idempotent*: chạy lại nhiều lần cho cùng kết quả (vd MERGE).
  - *Tự sửa được*: chạy lại **khôi phục được trạng thái đúng kể cả khi lần trước chết giữa đường**.
  Cơ chế "lấy id của Document cũ rồi xoá đúng những id đó khỏi Chroma" là idempotent nhưng **không** tự sửa được: một khi Document cũ đã bị xoá khỏi Neo4j thì lần chạy sau không còn cách nào biết id nào cần xoá. Đây là lý do đổi sang **đối chiếu**.

- **Reconcile (đối chiếu hai nguồn)**: thay vì ghi nhớ "cần xoá những gì", so trực tiếp hai nguồn rồi sửa phần lệch. `reconcile_chroma_with_neo4j`: mọi id trong Chroma không ứng với một Article thật trong Neo4j đều là rác → xoá. Tự sửa được **mọi** kiểu lệch, không phụ thuộc lịch sử. Nguyên tắc chung: **so trạng thái đích với trạng thái hiện tại** đáng tin hơn **ghi nhớ danh sách việc cần làm**.

- **Guard chống thảm hoạ (circuit breaker)**: điều kiện kiểm tra **trước** khi thực hiện thao tác không thể hoàn tác, dừng lại khi số liệu "vô lý" so với kỳ vọng đã đo. Ba guard trong `scripts/migrate_references.py`:
  1. `real_doc_ids` rỗng → từ chối (nếu không: mọi Document bị coi là cũ và bị xoá sạch).
  2. Tỉ lệ Document "cũ" > 5% → từ chối (đo thật chỉ 0,12%, nên con số lớn gần như chắc chắn là lỗi lập trình).
  3. Neo4j trả về 0 Article → từ chối `reconcile` (nếu không: xoá sạch 60k embedding, hàng giờ GPU để tạo lại).
  Điểm chung: guard so với **số đã đo thật**, không so với ngưỡng cảm tính — và **crash lớn tiếng** thay vì "xử lý tự động cho tiện" (cùng nguyên tắc với `BatchSizeMismatchError`, `ArticleIdCollisionError`).

- **Tính trước số liệu kỳ vọng (expected-state precomputation)**: trước khi chạy một thao tác dài trên dữ liệu thật, tính sẵn kết quả *phải* ra bằng đường độc lập (ở đây: quét tên file bằng Python) để sau đó **verify** thay vì "chạy xong rồi mới biết đúng hay sai". Ví dụ đợt này: tính trước 60,568 Article / 3,201 Document / 8 Article cần backfill — nếu số thật lệch thì biết ngay là có vấn đề.

- **Sửa ở gốc vs sửa ở caller**: khi một phép biến đổi có **một điểm duy nhất** (`slugify_doc_name` là nơi duy nhất biến tên văn bản thành slug), sửa tại đó làm **mọi** đường gọi tự động nhất quán; sửa ở từng caller chỉ sửa một nửa và để lại chính cái bất nhất đang cần sửa. Đây là lý do fix `ð` được đặt trong `slugify.py` chứ không trong `app/ingest.py`.

---

*File này để tra cứu nhanh khi đọc lại spec/code sau này. Thêm thuật ngữ mới vào đúng mục liên quan khi gặp — không cần tạo file mới trừ khi mục này quá dài.*
