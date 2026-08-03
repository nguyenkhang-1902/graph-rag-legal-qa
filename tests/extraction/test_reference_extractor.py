"""Tests cho app/extraction/reference_extractor.py va slugify.py (T006).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi
app/extraction/reference_extractor.py va app/extraction/slugify.py ton
tai. Chay `python -m pytest tests/extraction/ -v` luc nay phai FAIL vi
ModuleNotFoundError - do la bang chung "red" truoc khi implement "green".

Cac case bat buoc theo tasks.md T006 va task-2b-brief.md:
  1. Trich dan khac van ban, co ten van ban ("Dieu 5 Luat Doanh nghiep
     2020").
  2. Trich dan khac van ban qua khoan ("khoan 2 Dieu 5 Nghi dinh
     123/2020/ND-CP") - REFERENCES van la Article -> Article (khong phai
     Article -> Clause), so khoan chi la dau hieu nhan dien cau trich
     dan, khong nam trong article_id.
  3. Trich dan cung van ban (khong co ten van ban theo sau) - phai dung
     `current_doc_slug` duoc truyen vao.
  4. Khong co trich dan -> tra ve [] (khong phai None, khong exception).
  5. Nhieu trich dan trong mot doan -> tra ve dung thu tu xuat hien.
  6. slugify_doc_name test truc tiep voi 2 vi du trong brief.
  Them: false-positive guard - "Dieu" khong co so theo sau, va "dieu"
  thuong (khong viet hoa) dung trong nghia doi thuong khac hoan toan
  nghia phap ly - khong duoc match.
"""
from app.extraction.reference_extractor import ExtractedReference, extract_references
from app.extraction.slugify import slugify_doc_name


# --- slugify_doc_name (case 6) -----------------------------------------


def test_slugify_luat_doanh_nghiep():
    assert slugify_doc_name("Luật Doanh nghiệp 2020") == "luat-doanh-nghiep-2020"


def test_slugify_nghi_dinh_with_slashes_and_diacritics():
    assert (
        slugify_doc_name("Nghị định 123/2020/NĐ-CP") == "nghi-dinh-123-2020-nd-cp"
    )


# --- extract_references --------------------------------------------------


def test_cross_document_citation_with_doc_name(): # case 1
    text = "...theo quy định tại Điều 5 Luật Doanh nghiệp 2020..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "luat-doanh-nghiep-2020_dieu-5"


def test_khoan_qualified_cross_document_citation(): # case 2
    text = "...khoản 2 Điều 5 Nghị định 123/2020/NĐ-CP quy định..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "nghi-dinh-123-2020-nd-cp_dieu-5"


def test_same_document_implicit_self_reference(): # case 3
    text = "...được quy định tại Điều 10..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "luat-xyz_dieu-10"


def test_no_citation_returns_empty_list(): # case 4
    text = "Đây là một đoạn văn bản không chứa trích dẫn điều luật nào cả."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert refs == []


def test_multiple_citations_returned_in_order_of_appearance(): # case 5
    text = (
        "Điều 5 Luật Doanh nghiệp 2020 và Điều 10 Nghị định "
        "01/2021/NĐ-CP quy định các vấn đề liên quan."
    )
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert [r.target_article_id for r in refs] == [
        "luat-doanh-nghiep-2020_dieu-5",
        "nghi-dinh-01-2021-nd-cp_dieu-10",
    ]


def test_raw_text_captures_the_citation_substring():
    text = "...khoản 2 Điều 5 Nghị định 123/2020/NĐ-CP quy định..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert refs[0].raw_text == "khoản 2 Điều 5 Nghị định 123/2020/NĐ-CP"


def test_cross_document_citation_bo_luat():
    # Review finding (task-2b): "Bo luat" khong duoc nhan dien truoc day,
    # khien cau nay bi doan nham thanh tu-trich-dan (current_doc_slug) -
    # target_article_id PHAI tro toi "bo-luat-dan-su-2015", KHONG PHAI
    # "luat-xyz_dieu-8".
    text = "...được quy định tại Điều 8 Bộ luật Dân sự 2015..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "bo-luat-dan-su-2015_dieu-8"


def test_cross_document_citation_thong_tu():
    # Review finding: "Thong tu" khong duoc nhan dien truoc day.
    text = "...được quy định tại Điều 8 Thông tư 01/2020/TT-BTC..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "thong-tu-01-2020-tt-btc_dieu-8"


def test_cross_document_citation_nghi_quyet():
    # Review finding: "Nghi quyet" khong duoc nhan dien truoc day.
    text = "...được quy định tại Điều 8 Nghị quyết 42/2017/QH14..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "nghi-quyet-42-2017-qh14_dieu-8"


def test_article_number_normalization_strips_leading_zero(): # task-2c finding 2
    # structure_parser.py chuan hoa so Dieu qua int() khi xay dung
    # article_id (T008 - "Dieu 05" -> "..._dieu-5", khong zero-pad, xem
    # test cung ten trong test_structure_parser.py). Neu reference_extractor
    # khong lam dieu tuong tu, mot trich dan "Dieu 05" se resolve thanh
    # "..._dieu-05" va khong bao gio khop voi id Article node that trong
    # graph -> REFERENCES edge treo am tham luc ingest.
    text = "...được quy định tại Điều 05 Luật Doanh nghiệp 2020..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "luat-doanh-nghiep-2020_dieu-5"
    assert not refs[0].target_article_id.endswith("_dieu-05")


def test_returns_extracted_reference_dataclass_instances():
    text = "Điều 1 quy định..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert isinstance(refs[0], ExtractedReference)
    assert refs[0].target_article_id == "luat-xyz_dieu-1"


# --- False positive guards ------------------------------------------------


def test_dieu_without_trailing_number_does_not_match():
    text = "Điều luật này quy định về quyền và nghĩa vụ của các bên."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert refs == []


def test_lowercase_dieu_in_everyday_sense_does_not_match():
    # "dieu" (khong viet hoa) o day mang nghia thong thuong ("mot dieu
    # quan trong"), khong phai trich dan phap ly "Dieu {so}" - regex
    # phan biet hoa/thuong nen khong duoc match.
    text = "Một điều quan trọng là phải tuân thủ pháp luật."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert refs == []
