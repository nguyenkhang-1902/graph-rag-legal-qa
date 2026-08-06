"""Tests cho app/extraction/doc_identity.py (T025).

TDD (constitution Dieu 2): file nay duoc viet TRUOC khi
app/extraction/doc_identity.py ton tai - chay pytest luc nay phai FAIL vi
ModuleNotFoundError (bang chung "red" truoc khi implement "green").

BOI CANH (khao sat that toan bo 61,069 file, 2026-08-06):
`Document.title` dang RONG tren TOAN BO graph (gap tu DOT 3) va corpus
KHONG HE chua tieu de van ban o bat ky dau - moi file chi co heading
"# Dieu N. <tieu de Dieu>" (HuggingFace dataset tra ve per-Article). Nguon
duy nhat suy ra duoc danh tinh van ban la TEN FILE: 3,206/3,207 doc_prefix
khop dang "{so}_{nam}_{ma-hieu}" (vd "19_2016_tt-bxd").

Vi vay `title` o day la CHI DANH CHUAN ("Thong tu 19/2016/TT-BXD"), KHONG
phai tieu de van xuoi ("Thong tu quy dinh chi tiet ve...") - do la han che
CO CHU DICH, duoc ghi ro trong module docstring va research.md.

Module nay dung CHUNG cho hai muc dich (Dieu 1 - khong duplicate logic):
  - T025: sinh title/so_hieu/loai_vb cho Document node luc ingest.
  - T026: resolve doc_id tu SO HIEU trong trich dan (vd "Nghi dinh so
    16/2010/ND-CP" -> "16-2010-nd-cp") de khop dung doc_id sinh tu ten file.
"""
import pytest

from app.extraction.doc_identity import (
    DocIdentity,
    build_doc_identity,
    identity_from_doc_prefix,
    loai_vb_from_ma_hieu,
)


# --- loai_vb_from_ma_hieu ------------------------------------------------
# Phan phoi THAT trong corpus (do 2026-08-06 tren 3,207 doc_prefix): chi co
# 12 tien to ma hieu phan biet - tt (1,867), nd (842+4+3 bien the encoding),
# ttlt (218), qd (174), va qh10-qh14/qh (98).


@pytest.mark.parametrize(
    "ma_hieu,expected",
    [
        ("tt-bxd", "Thông tư"),
        ("TT-BTC", "Thông tư"),  # khong phan biet hoa/thuong
        ("ttlt-btnmt-bnv", "Thông tư liên tịch"),
        ("nđ-cp", "Nghị định"),
        ("qđ-ttg", "Quyết định"),
    ],
)
def test_maps_ma_hieu_prefix_to_loai_vb(ma_hieu, expected):
    assert loai_vb_from_ma_hieu(ma_hieu) == expected


@pytest.mark.parametrize("ma_hieu", ["nđ-cp", "nd-cp", "nð-cp", "NÐ-CP"])
def test_maps_all_three_encoding_variants_of_nghi_dinh(ma_hieu):
    # Corpus that co 3 bien the encoding cua ma hieu Nghi dinh do nguon
    # crawl khong nhat quan: "nđ" (842 van ban), "nd" (3), "nð" (4 - chu
    # eth U+00F0, KHAC "đ" U+0111 nen slugify_doc_name strip mat thanh "n").
    # Ca ba phai tra ve "Nghị định", khong de sot thanh None.
    assert loai_vb_from_ma_hieu(ma_hieu) == "Nghị định"


def test_eth_variant_doc_id_intentionally_differs_from_so_hieu_doc_id():
    # HAN CHE DA BIET, DO DUOC, CHUA SUA (xem module docstring
    # doc_identity.py): 4 van ban that dung "nð" trong ten file (102_2017,
    # 146_2018, 81_2016, 89_2016 = 119 Article) co doc_id "102-2017-n-cp"
    # (eth bi strip), trong khi trich dan viet dung "102/2017/NĐ-CP" sinh
    # "102-2017-nd-cp" -> khong khop, 4 van ban nay luon thanh external
    # placeholder.
    #
    # Test nay GHIM hanh vi hien tai co chu dich: doi doc_id nghia la doi
    # article_id, ma article_id CHINH LA id trong Chroma -> phai embed lai.
    # Neu sau nay Khang quyet sua, test nay se do va bat buoc phai doc ghi
    # chu tren (khong am tham doi khoa dinh danh cua 119 Article that).
    from app.extraction.slugify import slugify_doc_name

    doc_id_tu_ten_file = slugify_doc_name("102_2017_nð-cp")
    doc_id_tu_so_hieu = build_doc_identity("102", "2017", "NĐ-CP").doc_id
    assert doc_id_tu_ten_file == "102-2017-n-cp"
    assert doc_id_tu_so_hieu == "102-2017-nd-cp"
    assert doc_id_tu_ten_file != doc_id_tu_so_hieu
    # loai_vb/title thi VAN dung cho ca hai duong (fix cua T025).
    assert identity_from_doc_prefix("102_2017_nð-cp").loai_vb == "Nghị định"


@pytest.mark.parametrize("ma_hieu", ["qh13", "qh14", "qh", "qh10"])
def test_quoc_hoi_ma_hieu_is_ambiguous_returns_none(ma_hieu):
    # QUYET DINH CO CHU DICH: ma hieu Quoc hoi (QHnn) duoc dung CHUNG cho
    # Luat / Bo luat / Nghi quyet / Phap lenh - KHONG phan biet duoc tu ma
    # hieu. Tra ve None (khong doan) thay vi gan bua "Luat" cho ca 98 van
    # ban nhom nay - cung triet ly "sai con te hon khong trich" cua
    # reference_extractor.py/term_extractor.py.
    assert loai_vb_from_ma_hieu(ma_hieu) is None


def test_unknown_ma_hieu_returns_none():
    assert loai_vb_from_ma_hieu("xyz-abc") is None


# --- build_doc_identity -------------------------------------------------


def test_builds_identity_with_known_loai_vb():
    identity = build_doc_identity("19", "2016", "tt-bxd")
    assert identity == DocIdentity(
        doc_id="19-2016-tt-bxd",
        so_hieu="19/2016/TT-BXD",
        loai_vb="Thông tư",
        title="Thông tư 19/2016/TT-BXD",
    )


def test_builds_identity_without_loai_vb_title_is_so_hieu_only():
    # Khong biet loai van ban -> title CHI la so hieu, KHONG bia tien to.
    identity = build_doc_identity("16", "2012", "qh13")
    assert identity.loai_vb is None
    assert identity.so_hieu == "16/2012/QH13"
    assert identity.title == "16/2012/QH13"


def test_doc_id_preserves_leading_zero_to_match_filename():
    # Do THAT tren toan corpus: 592/3,203 doc_id co so bat dau bang 0 (vd
    # "05_2017_tt-btnmt"), va 0/6,767 trich dan can chuan hoa leading zero -
    # corpus viet so hieu NHAT QUAN voi ten file. Vi vay KHONG duoc bo
    # leading zero: lam vay se sinh "5-2017-tt-btnmt", khong bao gio khop
    # doc_id that "05-2017-tt-btnmt" (article_id cung la id trong Chroma -
    # doi doc_id nghia la phai embed lai toan bo 60,679 Article).
    assert build_doc_identity("05", "2017", "tt-btnmt").doc_id == "05-2017-tt-btnmt"
    assert build_doc_identity("05", "2017", "tt-btnmt").so_hieu == "05/2017/TT-BTNMT"


def test_doc_id_matches_slug_of_filename_prefix():
    # Rang buoc QUAN TRONG NHAT cua module: doc_id sinh tu SO HIEU trong
    # trich dan (T026) phai TRUNG KHOP doc_id sinh tu TEN FILE (app/ingest.py
    # dung slugify_doc_name(doc_prefix)). Day chinh la bug "external gia"
    # (118/8,427 placeholder) ma T026 sua.
    from app.extraction.slugify import slugify_doc_name

    for prefix in ["19_2016_tt-bxd", "05_2017_tt-btnmt", "16_2012_qh13"]:
        so, nam, ma = prefix.split("_", 2)
        assert build_doc_identity(so, nam, ma).doc_id == slugify_doc_name(prefix)


# --- identity_from_doc_prefix -------------------------------------------


def test_identity_from_doc_prefix_real_corpus_example():
    identity = identity_from_doc_prefix("19_2016_tt-bxd")
    assert identity is not None
    assert identity.doc_id == "19-2016-tt-bxd"
    assert identity.loai_vb == "Thông tư"


def test_identity_from_doc_prefix_handles_ma_hieu_containing_underscore():
    # Ma hieu chi duoc tach o 2 dau "_" DAU TIEN - phan con lai (co the
    # chua "_") thuoc ma hieu. Vi du that duy nhat trong corpus khong khop
    # dang chuan: "21-lct_hdnn8" (xem test ke tiep).
    identity = identity_from_doc_prefix("02_2013_ttlt-bnv-blđtbxh-btc-byt")
    assert identity is not None
    assert identity.loai_vb == "Thông tư liên tịch"


def test_identity_from_malformed_doc_prefix_returns_none():
    # 1/3,207 doc_prefix that KHONG khop dang "{so}_{nam}_{ma}":
    # "21-lct_hdnn8". Tra ve None (caller giu nguyen hanh vi cu: title
    # rong) - KHONG raise, mot van ban di thuong khong duoc lam do ca
    # pipeline ingest 61k file.
    assert identity_from_doc_prefix("21-lct_hđnn8") is None
    assert identity_from_doc_prefix("khong-co-dau-gach-duoi") is None
    assert identity_from_doc_prefix("") is None


def test_identity_from_doc_prefix_requires_4_digit_year():
    # "{so}_{nam}_{ma}" voi nam PHAI la 4 chu so - tranh khop bua vao cac
    # ten file dang khac.
    assert identity_from_doc_prefix("19_16_tt-bxd") is None
