# BHXH Phase 2 — Retrieval + QA trên corpus BHXH — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Làm retrieval + hỏi-đáp chạy end-to-end trên corpus BHXH (11 văn bản / 715 Điều đã ở Neo4j), trả câu trả lời có trích dẫn Điều/Khoản.

**Architecture:** Tái dụng nguyên engine retrieval/serving (corpus-agnostic, khớp bằng exact-string `article_id`). Việc thiếu: (1) BHXH chưa embed vào Chroma; (2) BHXH chưa có cạnh REFERENCES nên multi-hop không mở rộng. P2 lấp 2 khoảng này + eval.

**Tech Stack:** ChromaDB (`legal_articles`, bge-m3, `./chroma_db`), Neo4j, Ollama (qwen2.5), pytest.

**Spec:** dựa trên bản đồ pipeline (Explore 2026-08-21) — xem "Bối cảnh" dưới.

## Global Constraints
- **doc_id/article_id (Ruling 4 — RESOLVED):** GIỮ nguyên article_id un-slugified của BHXH (`41-2024-QH15_dieu-1`, `158-2025-NĐ-CP_dieu-5`). Retrieval khớp exact-string; điều kiện đúng là **cùng một chuỗi ở Chroma ID và Neo4j `article_id`** — đảm bảo bằng cách embed từ CÙNG `parse_vbpl_content`. KHÔNG normalize (Zalo sẽ bị xóa ở P4 nên scheme lẫn lộn chỉ tạm thời). *Chi phí nếu sai:* nếu sau này giữ Zalo, hai scheme lẫn lộn — chấp nhận, xử lý khi đó.
- Config-driven; KHÔNG đoán; idempotent (Chroma upsert, Neo4j MERGE).
- Không đụng code engine retrieval/serving trừ khi cần (corpus-agnostic).
- Commit prefix `feat(BHXH-P2-Tn):`.

## Bối cảnh (sự thật đã kiểm chứng)
- Chroma collection `legal_articles` = 93.375 vector (toàn Zalo, id slugified). ID vector = `article_id` verbatim; text embed = `article.full_text`; metadata `{doc_id, so_dieu}`.
- `full_text` KHÔNG lưu Neo4j (chỉ `noi_dung_preview`) → nguồn text là Chroma `documents` hoặc parse lại từ nguồn.
- Retrieval: `find_entry_points` (Chroma query) → `traverse` (Neo4j BFS theo REFERENCES/DEFINES, MAX_HOP=2) → `rank_article_ids` (cắt 10). Khớp Neo4j bằng exact `Article.article_id`.
- `serving/api.py chat()` chạy full chain + trích dẫn sẵn; corpus-agnostic; Ollama `qwen2.5` (config trỏ `7b-instruct`, máy đang có `14b-instruct` → xem T4).
- BHXH ingest (`ingest_vbpl_doc`) CHỈ gọi `upsert_document` → **không có REFERENCES/DEFINES** cho BHXH.
- **Temporal Resolver: HOÃN** — corpus hiện toàn `trang_thai=active`, không có văn bản `superseded` để lọc/cảnh báo. Xây khi có luật cũ (P4 hoặc khi cần trình bày chuyển tiếp).

---

## Task 1: Embed BHXH vào Chroma

**Files:**
- Create: `scripts/embed_bhxh.py`
- Test: `tests/ingest/test_embed_bhxh.py`

**Interfaces:**
- Consumes: `vbpl_parser.parse_vbpl_content`, `retrieval.embedder` (`embed_texts`/`upsert_embeddings`), `fetch_bhxh_corpus.fetch_vbpl_document` hoặc file `.txt` đã lưu.
- Produces: `embed_bhxh_txt(paths: list[Path]) -> int` — parse mỗi file, upsert `(article.article_id, article.full_text, {"doc_id", "so_dieu"})` vào `legal_articles`; trả số vector.

- [ ] **Step 1:** Persist nguồn BHXH ra đĩa: `python -m scripts.fetch_bhxh_corpus --out-dir data/raw/bhxh` (ghi 11 file `.txt`). Xác nhận 11 file.
- [ ] **Step 2 (test đỏ):** test mock `embedder.upsert_embeddings` (MagicMock) — `embed_bhxh_txt([fixture_txt])` gọi upsert với `ids` chứa `article_id` dạng `..._dieu-N` và `documents` = full_text. Chạy đỏ.
- [ ] **Step 3:** Viết `embed_bhxh.py`: đọc `.txt` → `parse_vbpl_content` → gom tất cả Article (kể cả trong Chapter) → `upsert_embeddings(ids, texts, metadatas)`. `main()` glob `data/raw/bhxh/*.txt`.
- [ ] **Step 4:** Test xanh. Chạy thật `python -m scripts.embed_bhxh` (embed 715 Điều BHXH).
- [ ] **Step 5 (smoke):** verify: `col.count()` tăng ~715; `find_entry_points("điều kiện hưởng bảo hiểm xã hội một lần")` trả về ≥1 article_id dạng BHXH (chứa `-QH15`/`-NĐ-CP`). Ghi kết quả vào report.
- [ ] **Step 6:** Commit `feat(BHXH-P2-T1): embed corpus BHXH vao Chroma`.

---

## Task 2: Reference extraction cho BHXH (multi-hop)

**Files:**
- Create: `scripts/extract_bhxh_references.py` (hoặc mở rộng `ingest_vbpl_doc` chạy references)
- Test: `tests/ingest/test_bhxh_references.py`

**Interfaces:**
- Consumes: `extraction.reference_extractor` (như `extract_relations.py`/`ingest.py:214-228` dùng), `graph_store.upsert.upsert_references`, `parse_vbpl_content`.
- Produces: cạnh `(:Article)-[:REFERENCES]->(:Article|placeholder)` cho các trích dẫn nội văn bản BHXH.

- [ ] **Step 1:** Đọc cách `app/ingest.py:_ingest_one_file` gọi reference extractor (bám đúng API thật).
- [ ] **Step 2 (test đỏ):** test mock — với text chứa "theo Điều 70 của Luật này", extractor sinh reference tới `article_id` đúng (un-slugified). Chạy đỏ.
- [ ] **Step 3:** Viết script: mỗi file BHXH → parse → `extract_references(full_text, source_article_id)` → `upsert_references`. Chú ý target-id phải khớp scheme un-slugified.
- [ ] **Step 4:** Test xanh. Chạy thật trên 11 văn bản.
- [ ] **Step 5 (smoke):** verify: `MATCH (:Article)-[:REFERENCES]->() WHERE ... che_do` count > 0; `traverse` từ 1 Điều BHXH mở rộng ≥1 hop. Ghi report.
- [ ] **Step 6:** Commit `feat(BHXH-P2-T2): trich dan chao (REFERENCES) cho corpus BHXH`.

---

## Task 3: Bộ eval BHXH + recall

**Files:**
- Create: `data/eval/bhxh_eval_set.json` (~20 câu, mỗi câu `{question, gold_article_ids[], che_do}`)
- Create: `scripts/eval_bhxh_retrieval.py`
- Test: `tests/eval/test_eval_bhxh.py`

- [ ] **Step 1:** Soạn ~20 câu hỏi NLĐ thật cho 3 chế độ + thất nghiệp, gán gold Điều (tra bằng nội dung Neo4j — KHÔNG đoán id; xác minh từng gold id tồn tại trong graph).
- [ ] **Step 2 (test đỏ):** test loader đọc eval set đúng schema. Đỏ → xanh.
- [ ] **Step 3:** Viết `eval_bhxh_retrieval.py`: mỗi câu → `find_entry_points` + `traverse` + `rank` → recall@k (gold nằm trong top-k?). In recall@5/@10.
- [ ] **Step 4:** Chạy thật, ghi recall vào report. (Mục tiêu tham chiếu, không phải cổng chặn.)
- [ ] **Step 5:** Commit `feat(BHXH-P2-T3): bo eval BHXH + do recall retrieval`.

---

## Task 4: QA end-to-end (chat) trên BHXH

**Files:**
- Modify (nếu cần): `app/config.py` (model Ollama khớp máy: có `qwen2.5:14b-instruct`, config trỏ `7b`)
- Create: `scripts/smoke_bhxh_chat.py` (gọi chain `chat()` cho vài câu, in answer + citation)

- [ ] **Step 1:** Xác nhận model Ollama: nếu `7b-instruct` chưa pull, đổi `OLLAMA_MODEL` (qua `.env`/config) sang `qwen2.5:14b-instruct` đang có. KHÔNG hard-code — qua config.
- [ ] **Step 2:** Viết smoke script gọi logic `chat()` cho 3–5 câu BHXH, in answer + `citation_path`.
- [ ] **Step 3:** Chạy thật; kiểm câu trả lời **chỉ dựa ngữ cảnh** + có trích dẫn Điều BHXH. Ghi 2–3 ví dụ vào report.
- [ ] **Step 4:** Commit `feat(BHXH-P2-T4): QA end-to-end co trich dan tren BHXH`.

---

## Self-Review
- Spec coverage: embed (T1) → references/multi-hop (T2) → eval (T3) → QA demo (T4). Temporal Resolver hoãn có chủ đích (không có superseded). doc_id giữ un-slugified (Ruling 4 resolved).
- Placeholder: eval gold ids phải xác minh tồn tại (T3 Step 1), không đoán.

## Bước tiếp theo sau P2
P3 = guardrail/citation cứng hơn trên `serving/api.py`. P4 = dọn Zalo (93k vector + 3201 doc) → lúc đó corpus thuần BHXH, cân nhắc normalize doc_id nếu cần.
