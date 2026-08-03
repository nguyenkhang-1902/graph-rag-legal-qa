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


def slugify_doc_name(name: str) -> str:
    """Chuyen ten van ban tieng Viet (co dau) thanh slug ASCII.

    Cac buoc (Dieu 11 constitution - phai xu ly dau tieng Viet dung, khong
    gia dinh format ASCII):
    - Ha chu.
    - "d" (Google/NFD khong decompose duoc thanh "d" + dau rieng) duoc xu
      ly rieng truoc khi decompose.
    - NFD-decompose de tach chu cai goc khoi dau (a/e/i/o/u/y va cac bien
      the co dau nhu a/a/a/e/e/o/o/u/u...), roi loai bo cac ky tu
      combining mark (category "Mn").
    - Thay moi day ky tu khong phai [a-z0-9] bang mot dau "-" duy nhat.
    - Bo "-" o dau/cuoi chuoi.
    """
    lowered = name.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    normalized = unicodedata.normalize("NFC", stripped)
    slug = _NON_ALNUM_RE.sub("-", normalized)
    return slug.strip("-")
