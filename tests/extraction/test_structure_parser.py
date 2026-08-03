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

from app.extraction.slugify import slugify_doc_name
from app.extraction.structure_parser import (
    Article,
    Chapter,
    Clause,
    ParsedDocument,
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


def test_returns_dataclass_instances():
    parsed = parse_document(_DOC_FOR_ID_FORMAT)

    assert isinstance(parsed, ParsedDocument)
    assert isinstance(parsed.chapters[0], Chapter)
    assert isinstance(parsed.chapters[0].articles[0], Article)
    assert isinstance(parsed.chapters[0].articles[0].clauses[0], Clause)
