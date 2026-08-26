"""Tests cho app/extraction/structure_parser.py (T008).

Fixtures la text tong hop (synthetic) mo phong quy uoc cau truc CHUAN cua
van ban quy pham phap luat Viet Nam - xem gia dinh ghi trong module docstring
cua structure_parser.py va task-2c-brief.md (chua doi chieu voi corpus that,
se lam o checkpoint sau).

Cac case theo brief:
  1. Van ban CO Chuong, nhieu Dieu/Chuong, mot so Dieu co Khoan mot so
     khong.
  2. Van ban KHONG co Chuong (Document -> Article truc tiep).
  3. Parse so La Ma cho Chuong: I, II, IV, IX.
  4. Chuan hoa so Dieu: "Dieu 05." -> so_dieu == 5, id "..._dieu-5" (khong
     zero-pad).
  5. doc_id/article_id/chapter_id/clause_id dung dinh dang - assert chuoi
     literal.
  6. noi_dung_preview bi truncate ~200 ky tu cho Dieu dai; full text KHONG
     duoc luu o dau trong Article.
  7. Input rong/malformed khong lam crash.
"""
import dataclasses

import pytest

from app.extraction.slugify import slugify_doc_name
from app.extraction.structure_parser import (
    Article,
    Chapter,
    Clause,
    ParsedDocument,
    parse_article_chunk,
    parse_document,
)


# --- Case 1: van ban CO Chuong -------------------------------------------


_DOC_WITH_CHAPTERS = """# Luật Test Cấu Trúc

Chương I
NHỮNG QUY ĐỊNH CHUNG

Điều 1. Phạm vi điều chỉnh

1. Nội dung khoản một của điều một.

2. Nội dung khoản hai của điều một.

Điều 2. Đối tượng áp dụng

Đây là nội dung điều hai không có khoản nào cả, chỉ là một đoạn văn duy nhất.

Chương II
TỔ CHỨC THỰC HIỆN

Điều 3. Trách nhiệm thi hành

1. Chính phủ quy định chi tiết thi hành.
"""


def test_document_with_chapters_multiple_articles_some_with_clauses():
    parsed = parse_document(_DOC_WITH_CHAPTERS)
    doc_id = slugify_doc_name("Luật Test Cấu Trúc")

    assert isinstance(parsed, ParsedDocument)
    assert parsed.doc_id == doc_id
    assert parsed.title == "Luật Test Cấu Trúc"
    assert parsed.articles == []  # khong co Dieu nao truc tiep duoi Document
    assert len(parsed.chapters) == 2

    chuong1, chuong2 = parsed.chapters
    assert isinstance(chuong1, Chapter)
    assert chuong1.so_chuong == 1
    assert chuong1.tieu_de == "NHỮNG QUY ĐỊNH CHUNG"
    assert len(chuong1.articles) == 2

    dieu1, dieu2 = chuong1.articles
    assert isinstance(dieu1, Article)
    assert dieu1.so_dieu == 1
    assert len(dieu1.clauses) == 2
    assert dieu1.clauses[0].so_khoan == 1
    assert dieu1.clauses[0].noi_dung == "Nội dung khoản một của điều một."
    assert dieu1.clauses[1].so_khoan == 2
    assert dieu1.clauses[1].noi_dung == "Nội dung khoản hai của điều một."

    assert dieu2.so_dieu == 2
    assert dieu2.clauses == []  # Dieu 2 khong co khoan

    assert chuong2.so_chuong == 2
    assert chuong2.tieu_de == "TỔ CHỨC THỰC HIỆN"
    assert len(chuong2.articles) == 1
    assert chuong2.articles[0].so_dieu == 3
    assert len(chuong2.articles[0].clauses) == 1


# --- Case 2: van ban KHONG co Chuong --------------------------------------


_DOC_WITHOUT_CHAPTERS = """# Nghị Định Không Chương

Điều 1. Quy định chung

Nội dung điều một không có chương, không có khoản.

Điều 2. Điều khoản thi hành

1. Nghị định này có hiệu lực kể từ ngày ký.
2. Các bộ, ngành liên quan chịu trách nhiệm thi hành.
"""


def test_document_without_chapters_goes_straight_to_articles():
    parsed = parse_document(_DOC_WITHOUT_CHAPTERS)

    assert parsed.chapters == []
    assert len(parsed.articles) == 2

    dieu1, dieu2 = parsed.articles
    assert dieu1.so_dieu == 1
    assert dieu1.clauses == []

    assert dieu2.so_dieu == 2
    assert len(dieu2.clauses) == 2
    assert dieu2.clauses[0].noi_dung == "Nghị định này có hiệu lực kể từ ngày ký."
    assert dieu2.clauses[1].noi_dung == (
        "Các bộ, ngành liên quan chịu trách nhiệm thi hành."
    )


# --- Case 3: so La Ma cho Chuong (I, II, IV, IX) --------------------------


_DOC_ROMAN_CHAPTERS = """# Văn Bản Nhiều Chương

Chương I
CHUONG MOT

Điều 1. Một

Nội dung điều một.

Chương II
CHUONG HAI

Điều 2. Hai

Nội dung điều hai.

Chương IV
CHUONG BON

Điều 3. Ba

Nội dung điều ba.

Chương IX
CHUONG CHIN

Điều 4. Bốn

Nội dung điều bốn.
"""


def test_roman_numeral_chapter_parsing():
    parsed = parse_document(_DOC_ROMAN_CHAPTERS)

    assert [c.so_chuong for c in parsed.chapters] == [1, 2, 4, 9]
    doc_id = parsed.doc_id
    assert [c.chapter_id for c in parsed.chapters] == [
        f"{doc_id}_chuong-1",
        f"{doc_id}_chuong-2",
        f"{doc_id}_chuong-4",
        f"{doc_id}_chuong-9",
    ]


# --- Case 4: chuan hoa so Dieu (khong zero-pad) ---------------------------


_DOC_ZERO_PADDED_ARTICLE = """# Văn Bản Điều Zero

Điều 05. Quy định về số không

Nội dung điều được đánh số có số 0 phía trước.
"""


def test_article_number_normalization_strips_leading_zero():
    parsed = parse_document(_DOC_ZERO_PADDED_ARTICLE)

    assert len(parsed.articles) == 1
    dieu = parsed.articles[0]
    assert dieu.so_dieu == 5
    assert dieu.article_id == f"{parsed.doc_id}_dieu-5"
    assert not dieu.article_id.endswith("_dieu-05")


# --- Case 5: dinh dang id - assert chuoi literal --------------------------


_DOC_FOR_ID_FORMAT = """# Luật Doanh nghiệp 2020

Chương I
QUY ĐỊNH CHUNG

Điều 5. Phạm vi điều chỉnh

1. Nội dung khoản một.
"""


def test_id_formats_match_exact_literal_strings():
    parsed = parse_document(_DOC_FOR_ID_FORMAT)

    assert parsed.doc_id == "luat-doanh-nghiep-2020"

    chuong = parsed.chapters[0]
    assert chuong.chapter_id == "luat-doanh-nghiep-2020_chuong-1"

    dieu = chuong.articles[0]
    assert dieu.article_id == "luat-doanh-nghiep-2020_dieu-5"

    khoan = dieu.clauses[0]
    assert khoan.clause_id == "luat-doanh-nghiep-2020_dieu-5_khoan-1"


# --- Case 6: noi_dung_preview bi truncate, full text khong duoc luu ------


def test_noi_dung_preview_is_truncated_full_text_present_but_untruncated():
    # Tu task-2d amendment: Article co them truong `full_text` (day du,
    # KHONG truncate) - de lam input cho reference_extractor.py (can toan
    # bo noi dung Dieu de tim trich dan, 200 ky tu preview se bo sot gan
    # het). Dieu thuc su quan trong (duoc test o day) la `noi_dung_preview`
    # - thu DUY NHAT duoc ghi vao Neo4j (xem upsert.py, T009) - van bi
    # truncate dung nhu truoc. Viec `full_text` KHONG duoc ghi vao Neo4j la
    # trach nhiem cua upsert.py, duoc test o tests/graph_store/test_upsert.py
    # (khong the test tu day, module nay khong biet gi ve Neo4j).
    long_sentence = "Đây là một câu rất dài được lặp lại nhiều lần. " * 10
    text = f"# Văn Bản Dài\n\nĐiều 1. Điều khoản dài\n\n{long_sentence}\n"

    parsed = parse_document(text)
    dieu = parsed.articles[0]

    full_text = f"Điều khoản dài\n{long_sentence.strip()}"
    assert len(full_text) > 200
    assert len(dieu.noi_dung_preview) <= 200
    assert dieu.noi_dung_preview == full_text[:200]

    # full_text duoc giu day du, khong bi truncate, va khop chinh xac noi
    # dung day du cua Dieu (khac voi noi_dung_preview da bi cat).
    assert dieu.full_text == full_text
    assert len(dieu.full_text) > 200

    # Article dataclass co dung 5 truong (them full_text so voi truoc).
    field_names = {f.name for f in dataclasses.fields(Article)}
    assert field_names == {
        "article_id",
        "so_dieu",
        "noi_dung_preview",
        "full_text",
        "clauses",
    }


# --- Case 7: input rong/malformed khong crash -----------------------------


def test_empty_string_input_does_not_crash():
    parsed = parse_document("")

    assert isinstance(parsed, ParsedDocument)
    assert parsed.doc_id == ""
    assert parsed.title == ""
    assert parsed.chapters == []
    assert parsed.articles == []


def test_whitespace_only_input_does_not_crash():
    parsed = parse_document("   \n\n\n   ")

    assert parsed.chapters == []
    assert parsed.articles == []


def test_missing_h1_title_line_does_not_crash():
    # Khong co dong "# {title}" o dau - dinh dang bi loi, van khong duoc
    # raise (xem brief - "sensible" fallback, khong bat buoc phai co title).
    text = "Đây không phải dòng tiêu đề markdown.\nĐiều 1. Một điều lạc lõng.\nNội dung.\n"

    parsed = parse_document(text)

    assert parsed.title == ""
    assert parsed.doc_id == ""
    # Dieu 1 van duoc parse nhu mot top-level article (owner = None).
    assert len(parsed.articles) == 1
    assert parsed.articles[0].so_dieu == 1


def test_chapter_with_no_following_title_line_does_not_crash():
    # Chuong o cuoi van ban, khong co dong tieu de theo sau.
    text = "# Văn Bản Ngắn\n\nChương I\n"

    parsed = parse_document(text)

    assert len(parsed.chapters) == 1
    assert parsed.chapters[0].so_chuong == 1
    assert parsed.chapters[0].tieu_de == ""


def test_chapter_immediately_followed_by_article_heading_no_title_line():
    # Review finding (task-2c #1): truoc day dong "Dieu 1. ..." bi nuot
    # nham lam tieu_de cua Chuong I (vi no la dong khong-rong dau tien sau
    # "Chuong I"), khien Dieu 1 va noi dung cua no bien mat hoan toan khoi
    # ket qua parse, khong co loi/canh bao nao ca. Chuong I trong truong
    # hop nay KHONG co dong tieu de rieng - di thang vao Dieu 1.
    text = (
        "# VBT\n\nChương I\nĐiều 1. Tieu de dieu mot\n\nNoi dung.\n"
    )

    parsed = parse_document(text)

    assert len(parsed.chapters) == 1
    chuong = parsed.chapters[0]
    assert chuong.so_chuong == 1
    assert chuong.tieu_de == ""  # khong co dong tieu de rieng -> rong

    assert len(chuong.articles) == 1
    dieu1 = chuong.articles[0]
    assert dieu1.so_dieu == 1
    assert "Tieu de dieu mot" in dieu1.noi_dung_preview
    assert "Noi dung." in dieu1.noi_dung_preview


def test_two_chapters_back_to_back_no_title_line_between_them():
    # Review finding (task-2c #1): hai Chuong lien tiep, khong co dong
    # tieu de nao giua chung - truoc day dong "Chuong II" bi nuot lam
    # tieu_de cua Chuong I, khien Chuong II hoan toan bien mat va Dieu cua
    # no bi gan nham vao Chuong I.
    text = "# VBT\n\nChương I\nChương II\nĐiều 1. Một điều\n\nNội dung.\n"

    parsed = parse_document(text)

    assert len(parsed.chapters) == 2
    chuong1, chuong2 = parsed.chapters
    assert chuong1.so_chuong == 1
    assert chuong1.tieu_de == ""
    assert chuong1.articles == []

    assert chuong2.so_chuong == 2
    assert chuong2.tieu_de == ""
    assert len(chuong2.articles) == 1
    assert chuong2.articles[0].so_dieu == 1


def test_missing_h1_title_uses_fallback_doc_id_for_all_ids():
    # task-2e-brief.md prerequisite fix: van ban khong co dong "# {title}"
    # (title rong) phai dung fallback_doc_id (khong phai slugify_doc_name("")
    # == "") lam doc_id, va MOI id phai sinh (chapter_id/article_id/
    # clause_id) phai dua tren fallback_doc_id nay - neu khong, hai van ban
    # malformed khac nhau se cung sup ve doc_id "" va bi MERGE chung lam mot
    # Document trong Neo4j (xem app/ingest.py, T009d).
    text = (
        "Không có dòng tiêu đề markdown ở đây.\n\n"
        "Chương I\nQUY ĐỊNH CHUNG\n\n"
        "Điều 1. Một điều lạc lõng\n\n"
        "1. Nội dung khoản một.\n"
    )

    parsed = parse_document(text, fallback_doc_id="file-abc-123")

    assert parsed.title == ""
    assert parsed.doc_id == "file-abc-123"
    assert len(parsed.chapters) == 1
    chuong = parsed.chapters[0]
    assert chuong.chapter_id == "file-abc-123_chuong-1"
    assert len(chuong.articles) == 1
    dieu = chuong.articles[0]
    assert dieu.article_id == "file-abc-123_dieu-1"
    assert len(dieu.clauses) == 1
    assert dieu.clauses[0].clause_id == "file-abc-123_dieu-1_khoan-1"


def test_missing_h1_title_without_fallback_keeps_old_behavior():
    # Caller khong truyen fallback_doc_id (mac dinh "") -> hanh vi cu khong
    # doi: doc_id rong.
    text = "Không có tiêu đề.\nĐiều 1. Một điều.\nNội dung.\n"

    parsed = parse_document(text)

    assert parsed.doc_id == ""
    assert parsed.articles[0].article_id == "_dieu-1"


def test_returns_dataclass_instances():
    parsed = parse_document(_DOC_FOR_ID_FORMAT)

    assert isinstance(parsed, ParsedDocument)
    assert isinstance(parsed.chapters[0], Chapter)
    assert isinstance(parsed.chapters[0].articles[0], Article)
    assert isinstance(parsed.chapters[0].articles[0].clauses[0], Clause)


# === parse_article_chunk (task-2f) =========================================
#
# Corpus that (447 file mau da fetch tu Zalo legal corpus) xac nhan: MOI
# file la DUY NHAT mot Dieu, dong "# {title}" CHINH LA dong tieu de Dieu
# ("Dieu N. <tieu de>"), khong phai tieu de van ban nhieu Dieu nhu
# `parse_document()` gia dinh. Cac fixture A/B/C duoi day la NGUYEN VAN vi
# du that tu task-2f-brief.md (khong phai synthetic nhu cac case tren).

# --- Example A: nhieu Khoan, co tu-trich-dan "khoan 1 Dieu nay" ------------

_ARTICLE_CHUNK_A = """# Điều 7. Giá trị pháp lý của giấy tờ, văn bản đã được chứng thực không đúng quy định pháp luật

1. Các giấy tờ, văn bản được chứng thực bản sao từ bản chính, chứng thực chữ ký không đúng quy định tại Nghị định số 23/2015/NĐ-CP  và Thông tư này thì không có giá trị pháp lý.
2. Chủ tịch Ủy ban nhân dân cấp huyện có trách nhiệm ban hành quyết định hủy bỏ giá trị pháp lý của giấy tờ, văn bản chứng thực quy định tại khoản 1 Điều này đối với giấy tờ, văn bản do Phòng Tư pháp chứng thực.
3. Người đứng đầu Cơ quan đại diện ngoại giao có trách nhiệm ban hành quyết định hủy bỏ giá trị pháp lý của giấy tờ, văn bản chứng thực quy định tại khoản 1 Điều này.
4. Việc ban hành quyết định hủy bỏ giá trị pháp lý và đăng tải thông tin thực hiện ngay sau khi phát hiện giấy tờ, văn bản đó được chứng thực không đúng quy định pháp luật.
"""


def test_parse_article_chunk_example_a_multiple_clauses():
    parsed = parse_article_chunk(_ARTICLE_CHUNK_A, doc_id="01-2020-tt-btp")

    assert isinstance(parsed, ParsedDocument)
    assert parsed.doc_id == "01-2020-tt-btp"
    assert parsed.title == ""
    assert parsed.chapters == []
    assert len(parsed.articles) == 1

    dieu = parsed.articles[0]
    assert isinstance(dieu, Article)
    assert dieu.so_dieu == 7
    assert dieu.article_id == "01-2020-tt-btp_dieu-7"
    assert dieu.article_id.endswith("_dieu-7")
    assert len(dieu.clauses) == 4
    assert [c.so_khoan for c in dieu.clauses] == [1, 2, 3, 4]
    assert dieu.clauses[0].clause_id == "01-2020-tt-btp_dieu-7_khoan-1"
    assert "không có giá trị pháp lý" in dieu.clauses[0].noi_dung
    # tu-trich-dan "khoan 1 Dieu nay" nam TRONG prose cua Khoan 2/3, khong
    # phai o dau dong -> khong tao Khoan moi, van thuoc ve Khoan 2/3.
    assert "khoản 1 Điều này" in dieu.clauses[1].noi_dung
    assert "khoản 1 Điều này" in dieu.clauses[2].noi_dung


# --- Example B: mot doan van duy nhat, khong co Khoan nao ------------------

_ARTICLE_CHUNK_B = """# Điều 8. Tổ chức Kiểm lâm trung ương

Kiểm lâm trung ương là tổ chức hành chính thuộc cơ quan tham mưu, giúp Bộ trưởng Bộ Nông nghiệp và Phát triển nông thôn quản lý nhà nước về lâm nghiệp.
"""


def test_parse_article_chunk_example_b_no_clauses_still_creates_article():
    parsed = parse_article_chunk(_ARTICLE_CHUNK_B, doc_id="01-2019-nd-cp")

    assert len(parsed.articles) == 1
    dieu = parsed.articles[0]
    assert dieu.so_dieu == 8
    assert dieu.article_id == "01-2019-nd-cp_dieu-8"
    assert dieu.clauses == []  # khong bi skip chi vi khong co Khoan
    assert "Kiểm lâm trung ương" in dieu.full_text


# --- Example C: "Chuong IV" chi la trich dan trong Khoan, KHONG phai -------
# --- tieu de Chuong -> khong tao Chapter, khong pha vo Khoan detection -----

_ARTICLE_CHUNK_C = """# Điều 6. Giám định xây dựng

1. Nội dung giám định xây dựng:
a) Giám định chất lượng khảo sát xây dựng, thiết kế xây dựng;
b) Giám định nguyên nhân hư hỏng, sự cố công trình xây dựng theo quy định tại Chương IV Nghị định này;
2. Cơ quan có thẩm quyền chủ trì tổ chức giám định xây dựng.
"""


def test_parse_article_chunk_example_c_chuong_citation_not_a_chapter():
    parsed = parse_article_chunk(_ARTICLE_CHUNK_C, doc_id="06-2021-nd-cp")

    assert len(parsed.chapters) == 0  # "Chuong IV" trong Khoan b) KHONG tao Chapter
    assert len(parsed.articles) == 1

    dieu = parsed.articles[0]
    assert dieu.so_dieu == 6
    assert dieu.article_id == "06-2021-nd-cp_dieu-6"
    assert len(dieu.clauses) == 2
    assert dieu.clauses[0].so_khoan == 1
    # Khoan a)/b) van nam trong noi dung Khoan 1 (khong bi tach thanh Khoan
    # moi), va "Chuong IV" van con nguyen trong noi dung do (khong bi mat).
    assert "Chương IV" in dieu.clauses[0].noi_dung
    assert dieu.clauses[1].so_khoan == 2


# --- Fallback / error khi dong tieu de khong khop pattern "Dieu N." -------


def test_parse_article_chunk_uses_fallback_so_dieu_when_heading_unparseable():
    text = "# Mot dong tieu de khong dung dinh dang Dieu N.\n\nNoi dung.\n"

    parsed = parse_article_chunk(text, doc_id="doc-la", fallback_so_dieu=42)

    dieu = parsed.articles[0]
    assert dieu.so_dieu == 42
    assert dieu.article_id == "doc-la_dieu-42"


def test_parse_article_chunk_raises_when_heading_unparseable_and_no_fallback():
    text = "# Mot dong tieu de khong dung dinh dang Dieu N.\n\nNoi dung.\n"

    with pytest.raises(ValueError):
        parse_article_chunk(text, doc_id="doc-la")


# --- full_text/noi_dung_preview theo dung quy uoc nhu parse_document ------


def test_parse_article_chunk_preview_truncated_full_text_untruncated():
    long_sentence = "Đây là một câu rất dài được lặp lại nhiều lần. " * 10
    text = f"# Điều 1. Điều khoản dài\n\n{long_sentence}\n"

    parsed = parse_article_chunk(text, doc_id="vb-dai")
    dieu = parsed.articles[0]

    full_text = f"Điều khoản dài\n{long_sentence.strip()}"
    assert len(full_text) > 200
    assert dieu.full_text == full_text
    assert len(dieu.noi_dung_preview) <= 200
    assert dieu.noi_dung_preview == full_text[:200]


def test_parse_article_chunk_heading_without_markdown_hash_prefix():
    # Brief: "handle it whether or not the '#'/markdown prefix is present".
    text = "Điều 3. Không có dấu thăng đầu dòng\n\nNội dung không có tiêu đề markdown.\n"

    parsed = parse_article_chunk(text, doc_id="doc-no-hash")
    dieu = parsed.articles[0]

    assert dieu.so_dieu == 3
    assert dieu.article_id == "doc-no-hash_dieu-3"
    assert "Không có dấu thăng đầu dòng" in dieu.full_text


# --- Case: ranh gioi PHU LUC - "Dieu N" trong mau/bieu KHONG thanh Dieu ---


_DOC_WITH_APPENDIX = """# Nghị định mẫu

Điều 1. Phạm vi điều chỉnh

Nghị định này quy định abc.

Điều 2. Đối tượng áp dụng

Áp dụng cho xyz.

Phụ lục I

MẪU HỢP ĐỒNG LAO ĐỘNG

Hai bên thống nhất ký kết hợp đồng lao động với những điều khoản sau đây:

Điều 1. Thời hạn hợp đồng

Loại hợp đồng: ....

Điều 2. Tiền lương

Mức lương: ....
"""


def test_appendix_articles_not_parsed_as_document_articles():
    # Regression (bug ND 145/2020): mau HDLD trong Phu luc co "Dieu 1..N"
    # rieng nam SAU cac Dieu that -> truoc day GHI DE Dieu that. Sau fix:
    # gap standalone "Phu luc N" thi DUNG parse.
    parsed = parse_document(_DOC_WITH_APPENDIX)

    arts = parsed.articles + [a for ch in parsed.chapters for a in ch.articles]
    assert len(arts) == 2, "chi 2 Dieu THAT, khong tinh Dieu trong phu luc"
    by_no = {a.so_dieu: a for a in arts}
    # Dieu 1 THAT = "Pham vi dieu chinh", KHONG bi mau HDLD "Thoi han hop dong" de len.
    assert "Phạm vi điều chỉnh" in by_no[1].noi_dung_preview
    assert "Thời hạn hợp đồng" not in by_no[1].noi_dung_preview
    assert "Đối tượng áp dụng" in by_no[2].noi_dung_preview


def test_inline_appendix_reference_not_treated_as_boundary():
    # Tham chieu inline "...Phu luc III ban hanh kem..." GIUA cau KHONG duoc
    # coi la ranh gioi phu luc (chi standalone ca dong moi tinh).
    text = (
        "# Nghị định mẫu\n\n"
        "Điều 1. Cấp phép\n\n"
        "Hồ sơ theo Mẫu số 04 Phụ lục III ban hành kèm theo Nghị định này.\n\n"
        "Điều 2. Hiệu lực\n\nCó hiệu lực từ 2025.\n"
    )
    parsed = parse_document(text)
    arts = parsed.articles + [a for ch in parsed.chapters for a in ch.articles]
    assert len(arts) == 2, "tham chieu Phu luc inline khong duoc cat Dieu 2"
