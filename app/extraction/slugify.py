"""slugify.py (T006/T007 shared building block).

Chuan hoa ten van ban tieng Viet thanh slug ASCII on dinh. Dung chung boi
reference_extractor.py (T007, module nay) va structure_parser.py (T008,
chua lam) de ca hai deu sinh ra cung mot `article_id` (vd
`luat-abc_dieu-5`) ma khong can phoi hop runtime - xem data-model.md va
task-2b-brief.md.

Constitution Dieu 5 - trach nhiem duy nhat cua module: chuoi -> slug, khong
lam gi khac.
"""
from __future__ import annotations

import re
import unicodedata

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# "ð"/"Ð" (eth, U+00F0/U+00D0) la LOI ENCODING cua nguon crawl thay cho
# "đ"/"Đ" (U+0111/U+0110). Do THAT tren corpus 2026-08-06: 4 van ban dung
# chu nay trong ten file - 102_2017_nð-cp (69 file), 146_2018_nð-cp (42),
# 81_2016_nð-cp (2), 89_2016_nð-cp (6) = 119 Article.
#
# Vi sao phai xu ly rieng: eth la MOT CHU CAI KHAC, khong phai "d" + dau,
# nen NFD khong decompose duoc -> bi `_NON_ALNUM_RE` thay bang "-", khien
# "102_2017_nð-cp" thanh "102-2017-n-cp". Hau qua truoc khi sua: trich dan
# viet DUNG ("Nghi dinh so 102/2017/NĐ-CP") sinh "102-2017-nd-cp", KHONG BAO
# GIO khop doc_id that -> 4 van ban nay khong the duoc trich dan cheo tim
# thay (luon thanh external placeholder).
_ETH_TO_DJ = {"ð": "đ", "Ð": "Đ"}


def normalize_eth(name: str) -> str:
    """Quy "ð"/"Ð" (eth) ve "đ"/"Đ" - chuan hoa loi encoding nguon crawl.

    Duoc `slugify_doc_name` goi tu dong. Export ra ngoai vi con mot cho nua
    can: `doc_identity.build_doc_identity` dung cho chuoi `so_hieu` HIEN THI
    (khong di qua slugify), de "102/2017/NĐ-CP" khong hien ra chu eth.
    """
    for eth, dj in _ETH_TO_DJ.items():
        name = name.replace(eth, dj)
    return name


def slugify_doc_name(name: str) -> str:
    """Chuyen ten van ban tieng Viet (co dau) thanh slug ASCII.

    Cac buoc (Dieu 11 constitution - phai xu ly dau tieng Viet dung, khong
    gia dinh format ASCII):
    - Quy "d"/"D" (eth - loi encoding nguon crawl) ve "d"/"D" truoc moi buoc
      khac (xem `normalize_eth`).
    - Ha chu.
    - "d" (Google/NFD khong decompose duoc thanh "d" + dau rieng) duoc xu
      ly rieng truoc khi decompose.
    - NFD-decompose de tach chu cai goc khoi dau (a/e/i/o/u/y va cac bien
      the co dau nhu a/a/a/e/e/o/o/u/u...), roi loai bo cac ky tu
      combining mark (category "Mn").
    - Thay moi day ky tu khong phai [a-z0-9] bang mot dau "-" duy nhat.
    - Bo "-" o dau/cuoi chuoi.
    """
    lowered = normalize_eth(name).lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    normalized = unicodedata.normalize("NFC", stripped)
    slug = _NON_ALNUM_RE.sub("-", normalized)
    return slug.strip("-")
