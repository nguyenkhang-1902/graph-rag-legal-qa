"""reference_extractor.py (T007): trich xuat trich dan "Dieu {so}" bang regex.

Trach nhiem duy nhat cua module nay: nhan dien trich dan dieu luat trong
mot doan text va tra ve `target_article_id` da resolve (constitution Dieu
5 - khong dung Neo4j/graph code o day; Dieu 1 - rule-based/regex, khong
LLM).

Theo data-model.md, `REFERENCES` la `Article -> Article` (khong bao gio
`Article -> Clause`): khi trich dan co "khoan X Dieu Y", so khoan chi dung
de nhan dien cau trich dan, khong nam trong `target_article_id` - van chi
tro toi Dieu Y.

Module nay KHONG xac dinh Dieu duoc trich co thuc su ton tai trong corpus
hay khong (external-reference detection xay ra sau, o upsert.py T009).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.doc_identity import build_doc_identity
from app.extraction.slugify import slugify_doc_name

# Quyet dinh ranh gioi "ten van ban ket thuc o dau" (diem mo ho duoc phep
# tu quyet dinh theo brief - ghi lai gia dinh theo constitution "ghi gia
# dinh"): chi ho tro 2 DANG cu phap, moi dang ap dung cho mot tap hop dong,
# khep kin cac loai van ban quy pham phap luat Viet Nam (dung theo Dieu 4
# Luat Ban hanh van ban QPPL - Luat, Bo luat, Phap lenh, Nghi dinh, Nghi
# quyet, Quyet dinh, Thong tu, Chi thi la cac loai pho bien nhat trong
# corpus phap ly). Day la mot danh sach dong, khep kin (khong phai NLP
# toan dien - P1 rule-based) nen mo rong duoc an toan; truoc ban sua nay
# chi 2 tu khoa (Luat, Nghi dinh) duoc nhan dien, khien mot tu khoa khac
# (vd "Bo luat", "Thong tu", "Nghi quyet") bi coi la "khong co ten van
# ban" va bi doan nham thanh tu-trich-dan (target_article_id tro sai ve
# current_doc_slug thay vi van ban duoc trich dan that su - xem task-2b
# review finding: sai con te hon la khong trich xuat):
#   - "<Luat|Bo luat|Phap lenh> <ten...> <nam 4 chu so>", vd "Luat Doanh
#     nghiep 2020", "Bo luat Dan su 2015" - ten van ban ket thuc ngay sau
#     nam ban hanh 4 chu so.
#   - "<Nghi dinh|Nghi quyet|Quyet dinh|Thong tu|Chi thi> <so>/<nam 4 chu
#     so>/<ma hieu>", vd "Nghi dinh 123/2020/ND-CP", "Thong tu
#     01/2020/TT-BTC", "Nghi quyet 42/2017/QH14" - ket thuc ngay sau ma
#     hieu (chu/so/gach ngang, dung truoc khoang trang hoac dau cau tiep
#     theo).
#
# === T026 (2026-08-06): mo rong do phu + doc_id nhat quan ===
#
# Khao sat THAT toan bo 61,069 file cho thay pattern truoc ban sua nay bo
# sot gan het trich dan cheo van ban: 115,563 trich dan "Dieu N" bat duoc
# nhung CHI 547 (0.47%) resolve duoc sang van ban khac; 115,016 con lai bi
# coi la self-reference, trong do 14,621 (12.7%) tro toi mot Dieu KHONG TON
# TAI trong chinh van ban do - bang chung truc tiep cua resolve sai.
#
# Ba nguyen nhan (do duoc, khong phai gia dinh):
#   1. Doi ten van ban dung NGAY sau "Dieu N" - nhung cach viet pho bien
#      nhat trong corpus that la "Dieu N CUA <Loai>..." (10,745 lan /
#      5,889 file).
#   2. Khong cho chu "so" xen giua loai va so hieu - "Nghi dinh SO
#      99/2015/ND-CP" (6,417 lan / 3,623 file) khong khop.
#   3. Khong ho tro ten van ban giua loai va so hieu - "Luat Nha o so
#      65/2014/QH13" (252 lan / 151 file).
# Ngoai ra "Thong tu lien tich" (218 van ban that) chua bao gio duoc nhan
# dien - phai dat TRUOC "Thong tu" trong alternation, neu khong "Thong tu"
# khop truoc roi doi so hieu ngay va that bai o " lien tich".
_LOAI_VB_PATTERN = (
    r"Bộ luật|Luật|Pháp lệnh|Nghị định|Nghị quyết|Quyết định"
    r"|Thông tư liên tịch|Thông tư|Chỉ thị"
)

# So hieu van ban: "{so}/{nam 4 chu so}/{ma hieu}". Cho phep khoang trang
# quanh dau "/" (corpus that co ca hai cach viet).
_SO_HIEU_PATTERN = (
    r"(?P<so>\d+)\s*/\s*(?P<nam>\d{4})\s*/\s*(?P<ma_hieu>[\w\-]+)"
)

# HAI nhanh, thu theo DUNG thu tu nay (regex alternation co thu tu):
#
#   (1) CO SO HIEU: "<Loai> [ten van ban] [so] {so}/{nam}/{ma hieu}"
#       -> resolve thanh doc_id CHUAN qua doc_identity.build_doc_identity,
#          KHOP CHINH XAC doc_id ma app/ingest.py sinh tu TEN FILE. Day la
#          fix cho bug "external gia" (118/8,427 placeholder) VA cho phan
#          lon do phu bi bo sot: 6,767 trich dan, trong do 3,275 tro dung
#          tới Article DA CO trong corpus.
#
#   (2) CHI TEN + NAM: "<Loai> <ten van ban> {nam 4 chu so}" (vd "Luat
#       Doanh nghiep 2020") -> GIU NGUYEN hanh vi cu: slug ca cum ten
#       ("luat-doanh-nghiep-2020"). KHONG the resolve sang doc_id that vi
#       moi doc_id that deu la dang so hieu; da thu mine tu dien "ten ->
#       so hieu" tu chinh corpus va KET LUAN KHONG DUNG DUOC: chi 86 ten
#       don nghia khop doc that, va cac ten quan trong nhat THUC SU da
#       nghia ("Luat Chung khoan" co 3 phien ban 2019/2006/2010, "Luat
#       Doanh nghiep" co 2) - chon bua mot phien ban la sai ve phap ly.
#       Cac trich dan nay tro thanh external placeholder co ten (thong tin
#       trung thuc, khong tao edge sai).
#
# Ten van ban trong nhanh (1) dung `[^\d,.;]` (khong chua chu so) nen khong
# the "an" nham sang so hieu cua mot trich dan KE TIEP trong cung cau (xem
# test_doc_name_does_not_bleed_across_a_following_citation).
_DOC_NAME_PATTERN = (
    # (1) co so hieu
    r"(?:" + _LOAI_VB_PATTERN + r")"
    + r"(?:\s+[^\d,.;]{1,80}?)?"
    + r"\s*(?:số\s+)?"
    + _SO_HIEU_PATTERN
    # (2) chi ten + nam
    + r"|(?:" + _LOAI_VB_PATTERN + r")\s+[^\d,.;]+?\d{4}"
)

# "khoan {so}" phia truoc la tuy chon, chi dung de nhan dien cau trich dan
# (khong xuat hien trong output). "Dieu" phai viet hoa chu D - phan biet
# voi "dieu"/"Dieu luat" thuong dung theo nghia doi thuong khac, tranh
# false positive (xem test_lowercase_dieu_in_everyday_sense_does_not_match,
# test_dieu_without_trailing_number_does_not_match).
#
# "cua" (tuy chon) giua "Dieu N" va ten van ban - xem nguyen nhan 1 o tren.
_CITATION_RE = re.compile(
    r"(?:khoản\s+\d+\s+)?"
    r"Điều\s+(?P<article_num>\d+)"
    r"(?:\s+(?:của\s+)?(?P<doc_name>" + _DOC_NAME_PATTERN + r"))?"
)


@dataclass
class ExtractedReference:
    """Mot trich dan Dieu luat da resolve thanh article_id (data-model.md REFERENCES)."""

    target_article_id: str
    raw_text: str


def extract_references(text: str, current_doc_slug: str) -> list[ExtractedReference]:
    """Tim tat ca trich dan "Dieu {so}" trong `text`, theo thu tu xuat hien.

    `current_doc_slug` la slug cua van ban chua `text` - dung lam
    doc_slug khi trich dan khong neu ten van ban khac (tu trich dan / self
    reference, vd "...duoc quy dinh tai Dieu 10...").

    Tra ve list rong (khong phai None, khong raise) khi khong co trich dan
    nao.
    """
    references: list[ExtractedReference] = []
    for match in _CITATION_RE.finditer(text):
        article_num = match.group("article_num")
        doc_name = match.group("doc_name")
        # Nhanh (1) - trich dan CO so hieu: doc_id phai duoc dung tu so
        # hieu qua doc_identity (MOT noi duy nhat tinh doc_id tu so hieu,
        # dung chung voi app/ingest.py qua ten file - Dieu 1 constitution),
        # KHONG phai slugify ca cum ten: slugify("Thong tu 19/2016/TT-BXD")
        # cho "thong-tu-19-2016-tt-bxd" trong khi doc_id THAT la
        # "19-2016-tt-bxd" -> khong bao gio khop (bug "external gia").
        if match.group("so") is not None:
            doc_slug = build_doc_identity(
                match.group("so"), match.group("nam"), match.group("ma_hieu")
            ).doc_id
        elif doc_name:
            # Nhanh (2) - chi ten + nam: giu nguyen slug ca cum ten.
            doc_slug = slugify_doc_name(doc_name)
        else:
            doc_slug = current_doc_slug
        # Chuan hoa so Dieu qua int() (bo leading zero, vd "05" -> "5") de
        # dong bo CHINH XAC voi cach structure_parser.py xay dung article_id
        # (T008 - quyet dinh khong zero-pad). Neu khong, mot trich dan viet
        # "Dieu 05" se resolve thanh "..._dieu-05", khong bao gio khop voi
        # id "..._dieu-5" cua Article node that trong graph -> REFERENCES
        # edge treo (dangling) am tham luc ingest (xem task-2c review
        # finding 2).
        so_dieu = int(article_num)
        target_article_id = f"{doc_slug}_dieu-{so_dieu}"
        references.append(
            ExtractedReference(
                target_article_id=target_article_id,
                raw_text=match.group(0),
            )
        )
    return references
