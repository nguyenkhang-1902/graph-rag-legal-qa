# Thiết kế: Graph RAG Hỏi–Đáp BHXH cho Người lao động (BHXH v2)

| | |
|---|---|
| **Ngày** | 2026-08-20 |
| **Trạng thái** | Đề xuất — chờ duyệt để chuyển sang `writing-plans` |
| **Nhánh dự kiến** | `002-bhxh-nld` (tách từ `001-graph-rag-core`) |
| **Giai đoạn pipeline** | 2 — Định hình yêu cầu & kiến trúc |
| **Nguồn** | Chốt qua skill `brainstorming` (nhánh architectural) |

---

## 0. Bối cảnh & lý do

Dự án hiện dùng corpus Zalo AI Challenge (**61.069 mảnh**, mọi lĩnh vực, dừng ở **2021**). Với mục tiêu sản phẩm BHXH thực tế năm 2026, corpus này **không dùng được ở tầng dữ liệu** vì:

1. **Sai luật hiện hành**: **Luật BHXH 2024 (41/2024/QH15) hiệu lực 01/7/2025** đã thay Luật BHXH 2014. Corpus chỉ có luật cũ (NĐ 115/2015). Trả lời theo luật hết hiệu lực = sai pháp lý.
2. **Nhiễu domain**: BHXH lẫn trong 61k văn bản mọi ngành.
3. **Thiếu metadata hiệu lực**: không phân biệt được văn bản còn/hết hiệu lực.

**Quyết định:** KHÔNG đập toàn bộ. **Giữ code engine** (domain-agnostic, đã tune), **reset sạch tầng dữ liệu/spec/eval Zalo**, viết lại luồng data + spec theo **BHXH temporal-first**.

---

## 1. Quyết định đã chốt (brainstorming)

| # | Hạng mục | Quyết định |
|---|---|---|
| 1 | Đối tượng | Người lao động phổ thông — trả lời ngắn, dễ hiểu, không thuật ngữ, luôn dẫn Điều/Khoản |
| 2 | Phạm vi MVP | 3 chế độ: **hưu trí, BHXH một lần, thai sản** |
| 3 | Hiệu lực | Luật hiện hành (BHXH 2024) + **cờ cảnh báo** khi có chuyển tiếp |
| 4 | Nguồn corpus | Crawl chính thống (vbpl.vn ưu tiên / thuvienphapluat.vn) |
| 5 | Đầu ra | Sinh câu trả lời + **trích dẫn bắt buộc** + guardrail chống bịa |
| 6 | Chế độ rebuild | Giữ repo + code engine; reset sạch data/spec/eval Zalo; viết lại luồng data+spec temporal-first |

---

## 2. Kiến trúc tổng thể

Giữ nguyên **code engine** làm lõi domain-agnostic; reset tầng dữ liệu; bọc thêm 2 tầng mới (in đậm).

```
[Crawler vbpl] → [Structure Parser*] → [Graph Neo4j + Hiệu lực] → [Retrieval (giữ nguyên)]
                                                                          ↓
                                       [**Temporal Resolver**] → [**Answer Generator + Guardrail**] → API
```

`*` Parser cần bổ sung adapter cho format nguồn mới (vbpl khác format md của Zalo).

**Tái dụng từ engine hiện tại:**

| Module | Vai trò | Trạng thái |
|---|---|---|
| `app/extraction/*` | Tách Điều/Khoản, trích dẫn chéo, thuật ngữ | Giữ — parser thêm adapter |
| `app/graph_store/*` (Neo4j) | Đồ thị Điều↔Khoản↔tham chiếu | Giữ nguyên |
| `app/retrieval/*` | Entry point → traversal → rank + reranker | Giữ nguyên (tài sản chính, T018/T028) |
| `app/ingest.py` + checkpoint | Nạp có checkpoint | Giữ nguyên |
| Temporal Resolver | Lọc & gắn cờ hiệu lực | **Mới** |
| Answer Generator + Guardrail | Sinh văn + trích dẫn | **Mới** |

---

## 3. Corpus & nguồn (3 chế độ)

Crawl từ **vbpl.vn** (ưu tiên — CSDL quốc gia, chính thống), danh mục lõi:

- **Luật BHXH 2024 (41/2024/QH15)** — trục chính, cả 3 chế độ
- **Bộ luật Lao động 2019 (45/2019/QH14)** — thai sản, hợp đồng lao động
- **Các NĐ/TT 2025** hướng dẫn Luật BHXH 2024 (hưu trí: cách tính lương hưu; một lần: điều kiện & mức hưởng; thai sản: mức hưởng)
- **Văn bản hết hiệu lực dùng cho cờ cảnh báo**: Luật BHXH 2014 + NĐ 115/2015 — đánh dấu `superseded`, **chỉ để đối chiếu thay đổi**, không dùng làm câu trả lời chính

**Quy mô ước tính:** ~8–15 văn bản, vài trăm–~1.500 Điều (giảm mạnh từ 61k → dễ kiểm soát đúng/sai).

> ⚠️ **Cần xác nhận / kiểm chứng khi crawl:** danh mục văn bản còn hiệu lực chính xác (đặc biệt các NĐ/TT 2025 mới nhất) sẽ được kiểm chứng lại tại bước crawl, không chốt cứng từ trí nhớ.

---

## 4. Data model temporal-first

Mở rộng node hiện có, thêm chiều thời gian:

- **`Document`**: `+ so_hieu`, `loai_vb`, `ngay_ban_hanh`, `ngay_hieu_luc`, `ngay_het_hieu_luc` (null = còn hiệu lực), `trang_thai` (`active` / `superseded`), `che_do[]` (hưu trí / một lần / thai sản)
- **`Article`/Điều, `Clause`/Khoản**: kế thừa hiệu lực từ Document; `+ supersedes` / `superseded_by` (quan hệ tới Điều tương ứng ở luật cũ) để sinh cờ cảnh báo
- **Giữ nguyên** quan hệ `references` (trích dẫn chéo) — trục multi-hop, giá trị cốt lõi của Graph RAG

---

## 5. Temporal Resolver (module mới #1)

Khi retrieval trả các Điều:
1. **Lọc cứng**: bỏ node `superseded` khỏi câu trả lời chính.
2. **Sinh cờ cảnh báo**: nếu Điều hiện hành có quan hệ `superseded_by` từ luật cũ → chèn cờ: *"Quy định này áp dụng từ 01/7/2025; trước đó theo Luật BHXH 2014 có thể khác."*

Không suy luận thời điểm user hỏi (đã chốt phạm vi: chỉ hiện hành + cảnh báo, không phân biệt đầy đủ theo mốc thời gian).

---

## 6. Answer Generator + Guardrail (module mới #2)

- **Input**: câu hỏi + top-N Điều/Khoản (đã lọc hiệu lực ở §5)
- **Sinh văn**: LLM tạo câu trả lời **ngắn, ngôn ngữ đời thường**; mỗi ý **bắt buộc** kèm `(Điều X, Khoản Y — <số hiệu VB>)`
- **Guardrail**:
  - Chỉ dùng nội dung có trong context truy xuất (grounding).
  - Kiểm chứng mọi citation sinh ra có thật trong graph.
  - Không đủ căn cứ → trả *"Chưa tìm thấy quy định cụ thể cho trường hợp này, bạn nên tham khảo cơ quan BHXH…"* thay vì bịa.
  - Chèn cờ cảnh báo từ §5 vào cuối câu trả lời.

---

## 7. Xử lý lỗi & rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Parser vỡ trên format vbpl mới | Viết adapter riêng + test fixtures trên 2–3 văn bản mẫu trước khi crawl hàng loạt |
| LLM bịa điều luật | Guardrail bắt buộc citation + kiểm chứng citation tồn tại trong graph |
| Nhầm luật cũ/mới | `trang_thai` lọc cứng ở tầng retrieval; `superseded` không bao giờ là câu trả lời chính |
| Luật thay đổi trong tương lai | Crawler chạy lại được + cập nhật `ngay_het_hieu_luc` |
| Nguồn crawl chặn/đổi HTML | Tách adapter crawl khỏi parser; cache HTML thô để parse lại offline |

---

## 8. Chiến lược test & eval

- **Bộ eval mới 3 chế độ** (~30–50 câu hỏi NLĐ thật, có đáp án Điều/Khoản gold) — thay `data/eval/multihop_eval_set` của Zalo
- **Test guardrail**: câu hỏi ngoài phạm vi → phải từ chối, không bịa
- **Test temporal**: câu về BHXH một lần → phải xuất hiện cờ cảnh báo chuyển tiếp
- **Metric**: recall@k Điều đúng + tỷ lệ câu trả lời có citation hợp lệ (100% là mục tiêu) + tỷ lệ từ chối đúng khi thiếu căn cứ

---

## 9. Dọn dẹp Zalo (reset sạch tầng dữ liệu)

**Xóa/lưu trữ:** `data/raw` (61k), `data/eval/*` (Zalo), `scripts/fetch_zalo_legal_corpus.py`, `scripts/eval_*zalo*`, ChromaDB cũ, spec `specs/001-graph-rag-core`.
**Giữ:** toàn bộ `app/*`, `docker-compose.yml`, cấu trúc `tests/`, engine + ADR.

> Thực hiện trên **nhánh mới `002-bhxh-nld`**; nhánh `001` giữ nguyên làm mốc tham chiếu.

---

## 10. Lộ trình phase

| Phase | Nội dung | Đầu ra kiểm chứng được |
|---|---|---|
| **P1** | Crawler + parser adapter + ingest 3 chế độ vào graph (có hiệu lực) | Graph BHXH có node + quan hệ + metadata hiệu lực |
| **P2** | Temporal Resolver + eval retrieval trên bộ mới | Recall@k trên bộ eval 3 chế độ; cờ hiệu lực hoạt động |
| **P3** | Answer Generator + Guardrail + eval end-to-end | Câu trả lời có citation hợp lệ 100%; từ chối đúng khi thiếu căn cứ |
| **P4** | API serving + dọn dẹp Zalo | API trả lời được; repo sạch dấu vết Zalo |

---

## 11. Điểm cần xác nhận (chốt mặc định trong doc, chờ duyệt)

1. **§3 — giữ Luật BHXH 2014 (hết hiệu lực) trong corpus** chỉ để sinh cờ cảnh báo: *mặc định GIỮ* (cần cho tính năng cảnh báo đã chốt). Nếu muốn gọn tối đa có thể bỏ và cảnh báo chung chung hơn.
2. **§10 — thứ tự phase P1→P4**: *mặc định giữ nguyên*.

---

## 12. Bước tiếp theo

Sau khi duyệt design này → chuyển sang skill **`writing-plans`** để lập kế hoạch triển khai chi tiết (P1→P4), rồi `nk-project-conventions` để viết `constitution.md` + `spec/plan/tasks` cho nhánh `002-bhxh-nld`.
