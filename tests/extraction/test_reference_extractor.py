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
import pytest

from app.extraction.reference_extractor import ExtractedReference, extract_references
from app.extraction.slugify import slugify_doc_name


# --- slugify_doc_name (case 6) -----------------------------------------


def test_slugify_luat_doanh_nghiep():
    assert slugify_doc_name("Luật Doanh nghiệp 2020") == "luat-doanh-nghiep-2020"


def test_slugify_nghi_dinh_with_slashes_and_diacritics():
    assert (
        slugify_doc_name("Nghị định 123/2020/NĐ-CP") == "nghi-dinh-123-2020-nd-cp"
    )


@pytest.mark.parametrize("ma_hieu", ["nð-cp", "NÐ-CP"])
def test_slugify_treats_eth_as_mis_encoded_dj(ma_hieu):
    # BUG THAT (2026-08-06, Khang chot sua): 4 van ban trong corpus dung chu
    # "ð" (eth, U+00F0) thay cho "đ" (U+0111) - loi encoding cua nguon crawl:
    #   102_2017_nð-cp (69 file) · 146_2018_nð-cp (42) · 81_2016_nð-cp (2)
    #   · 89_2016_nð-cp (6)  = 119 Article
    # "ð" la MOT CHU CAI KHAC, khong decompose duoc thanh "d" + dau, nen
    # truoc ban sua nay bi _NON_ALNUM_RE thay bang "-": "102_2017_nð-cp" ->
    # "102-2017-n-cp". Hau qua: trich dan viet DUNG ("102/2017/NĐ-CP") sinh
    # "102-2017-nd-cp", KHONG BAO GIO khop doc_id that -> 4 van ban nay khong
    # the duoc trich dan cheo tim thay.
    #
    # Chuan hoa "ð" -> "đ" o day (mot noi duy nhat) thay vi o tung caller:
    # slugify_doc_name la diem DUY NHAT bien ten van ban thanh slug, nen ca
    # duong ten-file (app/ingest.py) va duong trich dan
    # (doc_identity.build_doc_identity) tu dong nhat quan.
    assert slugify_doc_name(f"102_2017_{ma_hieu}") == "102-2017-nd-cp"


# --- extract_references --------------------------------------------------


def test_cross_document_citation_with_doc_name(): # case 1
    text = "...theo quy định tại Điều 5 Luật Doanh nghiệp 2020..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "luat-doanh-nghiep-2020_dieu-5"


def test_khoan_qualified_cross_document_citation(): # case 2
    # T026 (2026-08-06) DOI ky vong cua test nay tu "nghi-dinh-123-2020-nd-cp"
    # sang "123-2020-nd-cp": doc_id THAT trong graph sinh tu TEN FILE
    # ("123_2020_nđ-cp" -> "123-2020-nd-cp", KHONG co tien to loai van ban),
    # nen chuoi cu khong bao gio khop -> trich dan cheo bi coi la external du
    # van ban DA duoc ingest. Do that: 118/8,427 placeholder la "external
    # gia". Xem doc_identity.py.
    text = "...khoản 2 Điều 5 Nghị định 123/2020/NĐ-CP quy định..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "123-2020-nd-cp_dieu-5"


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

    # Trich dan 1 chi co TEN + NAM (khong so hieu) -> slug theo ten (giu
    # nguyen hanh vi cu). Trich dan 2 CO so hieu -> doc_id chuan (T026).
    assert [r.target_article_id for r in refs] == [
        "luat-doanh-nghiep-2020_dieu-5",
        "01-2021-nd-cp_dieu-10",
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
    # T026: doc_id bo tien to loai van ban (xem test_khoan_qualified_...).
    text = "...được quy định tại Điều 8 Thông tư 01/2020/TT-BTC..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "01-2020-tt-btc_dieu-8"


def test_cross_document_citation_nghi_quyet():
    # Review finding: "Nghi quyet" khong duoc nhan dien truoc day.
    text = "...được quy định tại Điều 8 Nghị quyết 42/2017/QH14..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "42-2017-qh14_dieu-8"


# --- T026: do phu "cua"/"so" + so hieu -> doc_id nhat quan ----------------
# Khao sat that toan bo 61,069 file (2026-08-06): regex cu bat 115,563 trich
# dan "Dieu N" nhung CHI 547 (0.47%) resolve duoc cross-document; 115,016
# con lai bi coi la self-reference, trong do 14,621 (12.7%) tro toi mot Dieu
# KHONG TON TAI trong chinh van ban do - bang chung resolve sai. Nguyen nhan:
# _DOC_NAME_PATTERN cu doi ten van ban dung NGAY sau "Dieu N", khong cho
# "cua"/"so" xen giua, va khong ho tro "<Loai> <ten> <so hieu>".
# Sau khi sua: 6,767 trich dan cross-doc co so hieu duoc resolve, trong do
# 3,275 tro dung tới Article DA CO trong corpus (edge that thay vi self-ref
# sai), 3,465 thanh external placeholder trung thuc.


def test_so_hieu_citation_resolves_to_doc_id_matching_filename():
    # Nguyen van tu data/raw/01_2012_ttlt-tandtc-vksndtc-btp_16.md.
    text = "...quy định tại Điều 10 Nghị định số 16/2010/NĐ-CP..."
    refs = extract_references(text, current_doc_slug="01-2012-ttlt-tandtc")

    assert len(refs) == 1
    # doc_id THAT sinh tu ten file "16_2010_nđ-cp" -> "16-2010-nd-cp".
    assert refs[0].target_article_id == "16-2010-nd-cp_dieu-10"


def test_cua_connector_between_dieu_and_doc_name_with_so_hieu():
    # Dang "Dieu N CUA <Loai> so ..." - 10,745 lan / 5,889 file trong corpus
    # that, truoc T026 bi bo sot HOAN TOAN (resolve thanh self-reference).
    text = "...sửa đổi Điều 5 của Nghị định số 99/2015/NĐ-CP ngày 20 tháng 10..."
    refs = extract_references(text, current_doc_slug="19-2016-tt-bxd")

    assert len(refs) == 1
    assert refs[0].target_article_id == "99-2015-nd-cp_dieu-5"


def test_cua_connector_with_name_and_year_only():
    # "cua" cung phai hoat dong voi dang TEN + NAM (khong so hieu).
    text = "...theo Điều 5 của Luật Doanh nghiệp 2020..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "luat-doanh-nghiep-2020_dieu-5"


def test_doc_name_between_loai_vb_and_so_hieu():
    # Dang "<Loai> <ten van ban> so <so hieu>" (vd "Luat Nha o so
    # 65/2014/QH13") - 252 lan / 151 file. Regex cu khong khop nhanh nao.
    text = "...quy định tại Điều 5 Luật Nhà ở số 65/2014/QH13..."
    refs = extract_references(text, current_doc_slug="19-2016-tt-bxd")

    assert len(refs) == 1
    assert refs[0].target_article_id == "65-2014-qh13_dieu-5"


def test_thong_tu_lien_tich_is_recognized_before_thong_tu():
    # 218 van ban that trong corpus la Thong tu lien tich. Neu "Thong tu"
    # duoc thu TRUOC trong alternation, no khop truoc roi doi ngay so hieu
    # -> that bai o " lien tich" va ca trich dan bi bo sot.
    text = "...tại Điều 16 Thông tư liên tịch số 01/2012/TTLT-TANDTC-VKSNDTC-BTP..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "01-2012-ttlt-tandtc-vksndtc-btp_dieu-16"


def test_so_hieu_leading_zero_is_preserved_in_doc_id():
    # 592/3,203 doc_id that co so bat dau bang 0 (vd "05_2017_tt-btnmt"), va
    # do that tren 6,767 trich dan cho thay 0 truong hop can chuan hoa
    # leading zero. Bo leading zero se sinh "5-2017-tt-btnmt" - khong bao gio
    # khop doc_id that. (Khac voi SO DIEU, van chuan hoa qua int() - xem
    # test_article_number_normalization_strips_leading_zero.)
    text = "...tại Điều 3 Thông tư số 05/2017/TT-BTNMT..."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert refs[0].target_article_id == "05-2017-tt-btnmt_dieu-3"


@pytest.mark.parametrize(
    "text",
    [
        "...được quy định tại Điều 5 của Luật này...",
        "...được quy định tại Điều 5 Nghị định này...",
        "...được quy định tại Điều 5 Thông tư này...",
    ],
)
def test_loai_vb_followed_by_nay_is_still_self_reference(text):
    # "Luat/Nghi dinh/Thong tu NAY" = chinh van ban dang doc -> self
    # reference DUNG, khong duoc coi la trich dan cheo. Ca hai nhanh moi deu
    # doi so hieu HOAC nam 4 chu so, nen "nay" tu nhien khong khop.
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert len(refs) == 1
    assert refs[0].target_article_id == "luat-xyz_dieu-5"


def test_doc_name_does_not_bleed_across_a_following_citation():
    # HAN CHE DA BIET, ghim co chu dich: "Dieu 5 Luat Nha o" (ten KHONG co
    # nam, KHONG co so hieu) khong resolve duoc -> roi ve self-reference
    # (van sai, nhung khong duoc "an" sang so hieu cua trich dan KE TIEP,
    # dieu do se tao edge sai NGHIEM TRONG hon).
    text = "Điều 5 Luật Nhà ở và Điều 10 Nghị định số 99/2015/NĐ-CP."
    refs = extract_references(text, current_doc_slug="luat-xyz")

    assert [r.target_article_id for r in refs] == [
        "luat-xyz_dieu-5",
        "99-2015-nd-cp_dieu-10",
    ]


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


# --- doc_aliases: resolve cross-doc theo TEN (khong nam/so hieu) -----------

def test_alias_resolves_cross_doc_by_name():
    from app.extraction.reference_extractor import extract_references
    aliases = {"bộ luật lao động": "45-2019-qh14", "luật bảo hiểm xã hội": "41-2024-qh15"}
    refs = extract_references(
        "Thực hiện theo khoản 1 Điều 139 của Bộ luật Lao động.",
        current_doc_slug="41-2024-qh15",
        doc_aliases=aliases,
    )
    assert [r.target_article_id for r in refs] == ["45-2019-qh14_dieu-139"]


def test_alias_self_reference_stays_current_doc():
    from app.extraction.reference_extractor import extract_references
    aliases = {"luật bảo hiểm xã hội": "41-2024-qh15"}
    refs = extract_references(
        "được quy định tại Điều 23 của Luật này",
        current_doc_slug="158-2025-nd-cp",
        doc_aliases=aliases,
    )
    assert [r.target_article_id for r in refs] == ["158-2025-nd-cp_dieu-23"]


def test_alias_ignored_when_so_hieu_present():
    from app.extraction.reference_extractor import extract_references
    aliases = {"luật bảo hiểm xã hội": "41-2024-qh15"}
    refs = extract_references(
        "theo Điều 70 của Luật Bảo hiểm xã hội số 41/2024/QH15",
        current_doc_slug="158-2025-nd-cp",
        doc_aliases=aliases,
    )
    assert [r.target_article_id for r in refs] == ["41-2024-qh15_dieu-70"]
