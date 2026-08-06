"""doc_identity.py (T025/T026): danh tinh mot van ban phap luat - doc_id,
so hieu, loai van ban, chi danh (title).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): chuyen doi giua
BA cach viet cung mot van ban, khong lam gi khac (khong doc file, khong
Neo4j, khong regex trich dan - do la reference_extractor.py):

    ten file        "19_2016_tt-bxd"     (app/ingest.py doc duoc)
    so hieu         "19/2016/TT-BXD"     (cach trich dan trong van ban that)
    doc_id          "19-2016-tt-bxd"     (khoa trong graph)

=== VI SAO CAN MODULE NAY (bang chung that, khong phai gia dinh) ===

(1) `Document.title` RONG tren toan bo graph (gap tu DOT 3). Khao sat that
    61,069 file cho thay corpus KHONG HE chua tieu de van ban o bat ky dau:
    moi file chi co heading "# Dieu N. <tieu de Dieu>" (HuggingFace dataset
    Zalo tra ve tung Dieu rieng le, khong co ban ghi cap van ban). Nguon
    DUY NHAT suy ra duoc danh tinh van ban la TEN FILE - 3,206/3,207
    doc_prefix khop dang "{so}_{nam}_{ma-hieu}".

    HAN CHE CO CHU DICH: `title` sinh ra o day la CHI DANH CHUAN ("Thong tu
    19/2016/TT-BXD"), KHONG phai tieu de van xuoi ("Thong tu quy dinh chi
    tiet ve phat trien nha o..."). Tieu de van xuoi KHONG TON TAI trong du
    lieu nguon - muon co phai lay tu nguon ngoai corpus (ngoai pham vi P1).
    Ghi ro o day thay vi de nguoi doc graph tuong da co title that.

(2) `reference_extractor.py` tinh doc_slug cua van ban DICH bang cach
    slugify CA CUM ten loai ("Thong tu 19/2016/TT-BXD" ->
    "thong-tu-19-2016-tt-bxd") trong khi `app/ingest.py` tinh doc_id tu TEN
    FILE ("19_2016_tt-bxd" -> "19-2016-tt-bxd"). Hai noi KHONG khop nhau ->
    trich dan cheo van ban bi coi la "external" du van ban DA duoc ingest
    (do that: 118/8,427 placeholder la "external gia"). Module nay la MOT
    noi duy nhat tinh doc_id tu so hieu, dung cho ca hai duong.

=== BANG MA HIEU -> LOAI VAN BAN ===
Phan phoi THAT (do 2026-08-06 tren 3,207 doc_prefix cua corpus): chi 12 tien
to ma hieu phan biet - `tt` (1,867), `nd` (842 + 4 + 3 bien the encoding
"nd"/"nd" do nguon crawl khong nhat quan), `ttlt` (218), `qd` (174), va
`qh10`..`qh14`/`qh` (98).

`qh*` tra ve None CO CHU DICH: ma hieu Quoc hoi dung CHUNG cho Luat / Bo
luat / Nghi quyet / Phap lenh - KHONG the phan biet tu ma hieu. Gan bua
"Luat" cho ca 98 van ban nay se sai voi mot phan trong so do, nen khong
doan (cung triet ly "sai con te hon khong trich" cua reference_extractor.py
va term_extractor.py).

`ct`/`nq`/`pl` KHONG xuat hien trong corpus hien tai nhung la ma hieu chuan
cua van ban QPPL Viet Nam - giu trong bang de corpus mo rong sau nay khong
sot, danh dau ro la CHUA GAP THAT.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.slugify import normalize_eth, slugify_doc_name

# Tien to ma hieu (phan truoc dau "-" DAU TIEN, ha chu, da chuan hoa "d"
# -> "d" qua slugify_doc_name) -> loai van ban. Cac khoa la slug ASCII nen
# moi bien the encoding cua "d" ("nd"/"nd"/"nd") deu quy ve mot khoa "nd".
_MA_HIEU_PREFIX_TO_LOAI_VB: dict[str, str] = {
    # --- Da gap that trong corpus (kem so luong Document do duoc) ---
    "tt": "Thông tư",  # 1,867
    "nd": "Nghị định",  # 849 (842 + 4 + 3 bien the encoding)
    "ttlt": "Thông tư liên tịch",  # 218
    "qd": "Quyết định",  # 174
    # --- Ma hieu chuan, CHUA gap trong corpus hien tai (xem docstring) ---
    "ct": "Chỉ thị",
    "nq": "Nghị quyết",
    "pl": "Pháp lệnh",
}

# doc_prefix cua ten file: "{so}_{nam 4 chu so}_{ma hieu}". Ma hieu la phan
# CON LAI sau 2 dau "_" dau tien - chinh no co the chua "-" (vd
# "ttlt-btnmt-bnv") nhung theo do that KHONG chua "_".
_DOC_PREFIX_RE = re.compile(r"^(?P<so>\d+)_(?P<nam>\d{4})_(?P<ma_hieu>.+)$")

# GHI CHU: chu "ð" (eth, U+00F0) - loi encoding nguon crawl thay cho "đ",
# xuat hien that trong 4 doc_prefix (102_2017_nð-cp, 146_2018_nð-cp,
# 81_2016_nð-cp, 89_2016_nð-cp = 119 Article) - da duoc xu ly o MOT NOI DUY
# NHAT: `slugify.normalize_eth`, goi tu dong trong `slugify_doc_name`. Nho
# vay doc_id suy tu TEN FILE va doc_id suy tu SO HIEU tu dong nhat quan
# (truoc ban sua: "102-2017-n-cp" vs "102-2017-nd-cp" -> 4 van ban nay khong
# bao gio duoc trich dan cheo tim thay). Module nay chi con can `normalize_eth`
# cho chuoi `so_hieu` HIEN THI - chuoi do khong di qua slugify.


@dataclass(frozen=True)
class DocIdentity:
    """Danh tinh mot van ban, ba cach viet + loai van ban.

    `doc_id`: khoa trong graph, LUON bang `slugify_doc_name("{so}_{nam}_
    {ma_hieu}")` - dam bao khop chinh xac doc_id ma `app/ingest.py` sinh tu
    ten file (xem test_doc_id_matches_slug_of_filename_prefix).

    `loai_vb`: None khi ma hieu khong xac dinh duoc loai (vd `qh13` - xem
    module docstring). KHONG doan.

    `title`: chi danh chuan "{loai_vb} {so_hieu}", hoac CHI `so_hieu` khi
    `loai_vb` la None (khong bia tien to). KHONG phai tieu de van xuoi -
    tieu de do khong ton tai trong corpus (xem module docstring).
    """

    doc_id: str
    so_hieu: str
    loai_vb: str | None
    title: str


def loai_vb_from_ma_hieu(ma_hieu: str) -> str | None:
    """Loai van ban suy ra tu ma hieu (vd "tt-bxd" -> "Thong tu"), hoac None
    khi khong xac dinh duoc (ma hieu Quoc hoi `qh*`, hoac ma hieu la).

    Khong phan biet hoa/thuong, chuan hoa dau tieng Viet qua
    `slugify_doc_name`, VA quy "d" (eth, U+00F0) ve "d" TRUOC khi tra bang -
    nho vay ca 3 bien the encoding cua "nd" trong corpus that ("nd" 842 van
    ban, "nd" 3, "nd" 4) deu tra ve "Nghi dinh".

    Vi sao phai xu ly "d" rieng: `slugify_doc_name` chi decompose duoc "d"
    (U+0111) thanh "d"; "d" la MOT CHU CAI KHAC (eth, khong decompose duoc)
    nen bi `_NON_ALNUM_RE` thay bang "-" -> "nd-cp" thanh "n-cp", tien to
    "n" khong co trong bang.
    """
    if not ma_hieu:
        return None
    prefix = slugify_doc_name(ma_hieu).split("-", 1)[0]
    return _MA_HIEU_PREFIX_TO_LOAI_VB.get(prefix)


def build_doc_identity(so: str, nam: str, ma_hieu: str) -> DocIdentity:
    """Dung `DocIdentity` tu ba thanh phan cua so hieu.

    `so` duoc giu NGUYEN VAN, KHONG bo leading zero: 592/3,203 doc_id that
    co so bat dau bang 0 (vd "05_2017_tt-btnmt"), va do that tren 6,767
    trich dan cho thay 0 truong hop can chuan hoa leading zero (corpus viet
    so hieu nhat quan voi ten file). Bo leading zero se sinh doc_id khong
    bao gio khop du lieu that - va vi `article_id` cung la id trong Chroma,
    doi doc_id nghia la phai embed lai toan bo 60,679 Article.

    `ma_hieu` duoc viet HOA trong `so_hieu` (dang trich dan chuan trong van
    ban phap luat), nhung `doc_id` van la slug ha chu.
    """
    doc_id = slugify_doc_name(f"{so}_{nam}_{ma_hieu}")
    # `normalize_eth` cho chuoi HIEN THI: khong di qua slugify nen phai goi
    # tuong minh, neu khong "102/2017/NĐ-CP" se hien ra "102/2017/NÐ-CP".
    so_hieu = f"{so}/{nam}/{normalize_eth(ma_hieu).upper()}"
    loai_vb = loai_vb_from_ma_hieu(ma_hieu)
    title = f"{loai_vb} {so_hieu}" if loai_vb else so_hieu
    return DocIdentity(
        doc_id=doc_id, so_hieu=so_hieu, loai_vb=loai_vb, title=title
    )


def identity_from_doc_prefix(doc_prefix: str) -> DocIdentity | None:
    """`DocIdentity` tu doc_prefix cua TEN FILE (vd "19_2016_tt-bxd"), hoac
    None khi doc_prefix khong khop dang "{so}_{nam 4 chu so}_{ma hieu}".

    Tra ve None (KHONG raise) cho input di thuong: 1/3,207 doc_prefix that
    khong khop dang nay ("21-lct_hdnn8") - mot van ban di thuong khong duoc
    lam do ca pipeline ingest 61k file. Caller giu hanh vi cu (title rong)
    khi nhan None.
    """
    match = _DOC_PREFIX_RE.match(doc_prefix)
    if not match:
        return None
    return build_doc_identity(
        match.group("so"), match.group("nam"), match.group("ma_hieu")
    )
