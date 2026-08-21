"""vbpl_parser.py (BHXH-P1-T2): adapter tu text da render cua trang chi
tiet vbpl.vn (CSDL quoc gia ve phap luat) sang `ParsedDocument` cua
`structure_parser.py`, cong them metadata van ban (so hieu, nam, ma hieu,
ngay hieu luc/het hieu luc).

Input KHONG phai HTML tho (xem Ruling 1, task-2-brief.md): crawler (T5,
Playwright) render trang roi lay text cua 2 tab:
  - `noi_dung_text`: tab "Noi dung" - toan van van ban, dung format ma
    `structure_parser.parse_document()` da ky vong (Chuong -> Dieu ->
    Khoan). Xem tests/fixtures/bhxh/vbpl-source-notes.md.
  - `thuoc_tinh_text`: tab "Thuoc tinh" - bang metadata dang nhan->gia
    tri ("So hieu", "Ngay co hieu luc", "Ngay het hieu luc", ...). Dinh
    dang chinh xac cua text sau khi Playwright render CHUA duoc xac minh
    voi corpus that (chua co crawler That, T5) - ham parse metadata o day
    du chiu duoc mot vai bien the pho bien ("Nhan: gia tri" tren cung
    dong, hoac "Nhan" roi gia tri o dong ke tiep khi render dang bang).

Constitution Dieu 1 (khong LLM o day - rule-based/regex) va "khong doan
bua": neu khong tim thay ngay hieu luc/het hieu luc o dau ca, tra ve
`None` - KHONG suy doan.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.structure_parser import ParsedDocument, parse_document

# "Luat Bao hiem xa hoi so 41/2024/QH15" / "So hieu: 41/2024/QH15" ->
# (so="41", nam="2024", ma_hieu="QH15"). Ma hieu co the co gach ngang
# (vd "102/2017/NĐ-CP") nen cho phep chu + so + gach ngang.
_SO_HIEU_RE = re.compile(r"[Ss][ốôo]\s+(\d+)/(\d{4})/([A-Za-zĐđ0-9\-]+)")

# "ngay DD thang MM nam YYYY" (co dau tieng Viet, khong phan biet hoa/thuong).
_DATE_LONG_RE = re.compile(
    r"ng[àa]y\s+(\d{1,2})\s+th[áa]ng\s+(\d{1,2})\s+n[ăa]m\s+(\d{4})",
    re.IGNORECASE,
)
# "DD/MM/YYYY".
_DATE_SLASH_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

_NGAY_HIEU_LUC_LABEL = "Ngày có hiệu lực"
_NGAY_HET_HIEU_LUC_LABEL = "Ngày hết hiệu lực"
_HIEU_LUC_ANCHOR_RE = re.compile(r"hi[ệe]u\s+l[ựu]c", re.IGNORECASE)

# Cua so ky tu quet sau mot nhan/anchor de tim ngay - du dai cho "ngay DD
# thang MM nam YYYY" hoac "DD/MM/YYYY" nam tren cung dong hoac dong ke tiep
# (bang thuoc tinh render dang "Nhan\nGia tri"), nhung khong qua dai de
# tranh vo tinh khop ngay cua nhan KHAC o gan do.
_LABEL_WINDOW = 60


@dataclass
class VbplDoc:
    """Ket qua adapter: `ParsedDocument` (T008) + metadata van ban rut ra
    tu 2 tab cua trang chi tiet vbpl.vn. `ngay_hieu_luc`/`ngay_het_hieu_luc`
    la `None` khi khong tim thay - khong bao gio doan bua."""

    parsed: ParsedDocument
    so: str
    nam: str
    ma_hieu: str
    ngay_hieu_luc: str | None
    ngay_het_hieu_luc: str | None


def _normalize_date(text: str) -> str | None:
    """"ngay DD thang MM nam YYYY" hoac "DD/MM/YYYY" (o bat ky dau trong
    `text`) -> ISO "YYYY-MM-DD". `None` neu khong tim thay dang nao."""
    if not text:
        return None
    match = _DATE_LONG_RE.search(text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    match = _DATE_SLASH_RE.search(text)
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return None


def _extract_labeled_date(text: str, label: str) -> str | None:
    """Tim `label` (vd "Ngay co hieu luc") trong `text`, roi chuan hoa ngay
    trong mot cua so ky tu ngay sau do (_LABEL_WINDOW). Dung cho
    `thuoc_tinh_text` dang bang nhan->gia tri; dinh dang render cu the
    chua duoc xac minh nen chi dua vao khoang cach ky tu, khong dua vao
    dau phan cach co dinh (":" / tab / xuong dong)."""
    if not text:
        return None
    idx = text.find(label)
    if idx == -1:
        return None
    window = text[idx + len(label) : idx + len(label) + _LABEL_WINDOW]
    return _normalize_date(window)


def _extract_ngay_hieu_luc(noi_dung_text: str, thuoc_tinh_text: str) -> str | None:
    """Uu tien `thuoc_tinh_text` ("Ngay co hieu luc"); neu khong co, roi
    thu cau mo dau trong `noi_dung_text` (vd "... co hieu luc ke tu ngay
    01 thang 7 nam 2025")."""
    from_thuoc_tinh = _extract_labeled_date(thuoc_tinh_text, _NGAY_HIEU_LUC_LABEL)
    if from_thuoc_tinh is not None:
        return from_thuoc_tinh

    anchor = _HIEU_LUC_ANCHOR_RE.search(noi_dung_text or "")
    if anchor is None:
        return None
    window = noi_dung_text[anchor.end() : anchor.end() + _LABEL_WINDOW]
    return _normalize_date(window)


def _extract_ngay_het_hieu_luc(thuoc_tinh_text: str) -> str | None:
    """Chi tu `thuoc_tinh_text` ("Ngay het hieu luc") - khong co nguon nao
    khac dang tin cay cho ngay het hieu luc. Gia tri "--" (van ban con
    hieu luc) chuan hoa tu nhien thanh `None` vi khong khop dang ngay nao."""
    return _extract_labeled_date(thuoc_tinh_text, _NGAY_HET_HIEU_LUC_LABEL)


def _parse_so_hieu(noi_dung_text: str, thuoc_tinh_text: str) -> tuple[str, str, str]:
    """Rut so/nam/ma_hieu tu "so hieu" dang "41/2024/QH15", uu tien
    `thuoc_tinh_text` (nguon metadata co cau truc) roi den `noi_dung_text`
    (cau mo dau van ban). Tra ("", "", "") neu khong tim thay o dau ca."""
    for text in (thuoc_tinh_text, noi_dung_text):
        if not text:
            continue
        match = _SO_HIEU_RE.search(text)
        if match:
            so, nam, ma_hieu = match.groups()
            return so, nam, ma_hieu
    return "", "", ""


def parse_vbpl_content(noi_dung_text: str, thuoc_tinh_text: str = "") -> VbplDoc:
    """Parse text da render cua trang chi tiet vbpl.vn thanh `VbplDoc`.

    `noi_dung_text`: text tab "Noi dung" (bat buoc) - dua qua
    `structure_parser.parse_document()` khong doi.
    `thuoc_tinh_text`: text tab "Thuoc tinh" (tuy chon, mac dinh rong) -
    nguon uu tien cho `so`/`nam`/`ma_hieu` va ngay hieu luc/het hieu luc.
    """
    so, nam, ma_hieu = _parse_so_hieu(noi_dung_text, thuoc_tinh_text)
    ngay_hieu_luc = _extract_ngay_hieu_luc(noi_dung_text, thuoc_tinh_text)
    ngay_het_hieu_luc = _extract_ngay_het_hieu_luc(thuoc_tinh_text)

    fallback_doc_id = f"{so}-{nam}-{ma_hieu}".strip("-") if so else ""
    parsed = parse_document(noi_dung_text, fallback_doc_id=fallback_doc_id)

    return VbplDoc(
        parsed=parsed,
        so=so,
        nam=nam,
        ma_hieu=ma_hieu,
        ngay_hieu_luc=ngay_hieu_luc,
        ngay_het_hieu_luc=ngay_het_hieu_luc,
    )
