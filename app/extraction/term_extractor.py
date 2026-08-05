"""term_extractor.py (T012): trich xuat DEFINES/USES_TERM (data-model.md)
bang rule-based - KHONG dung Neo4j/graph code o day (constitution Dieu 5,
cung ranh gioi voi reference_extractor.py), KHONG goi Ollama trong module
nay (xem ghi chu "LLM fallback" o duoi).

=== DEFINES (Article -> Term): extract_definitions_rule_based ===
Theo data-model.md, mau nhan dien la "... duoc hieu la ...". Khao sat
corpus that (data/raw, xem TIEN_DO.md DOT 5) cho thay CHI mot phan cau
truc "X duoc hieu la Y" co the tin cay duoc bang rule-based: khi X la MOT
thuat ngu duoc trich dan ro rang trong dau ngoac kep (thang " hoac cong
"" "" - corpus dung ca hai), vd:
    1.19. "Ngay" duoc hieu la ngay duong lich...
Con lai - khi X la mot menh de mo ta DAI, khong co quotes, vd:
    San pham duoc dua ra thi truong ... quy dinh tai diem b khoan 2 Dieu
    125 cua Luat So huu tri tue duoc hieu la san pham do chinh chu so
    huu...
- rule-based KHONG the tach dung "thuat ngu" tu menh de nay (khong co
ranh gioi ro rang). Theo triet ly da dung o reference_extractor.py ("sai
con te hon la khong trich xuat"), CAC TRUONG HOP NAY BI BO QUA o day, de
lai cho LLM fallback (data-model.md: "chi goi LLM khi rule-based khong
match, de giam chi phi") - CHUA implement fallback nay trong T012, ghi
nhan la gap da biet (tuong tu cach T007/T013 tach rieng LLM-heavy logic
khoi rule-based logic).

Ranh gioi dinh nghia: cat o dau cau ket thuc gan nhat (".", ";", hoac
xuong dong) - gia dinh don gian, ghi lai theo dung quy uoc "ghi gia dinh"
cua du an (co the sai voi cau co dau "." trong so/viet tat, chap nhan o
P1 rule-based).

=== Mau 2: danh sach dinh nghia danh so (bo sung 2026-08-05) ===
Quet THAT toan bo 61,069 file (TIEN_DO.md DOT 6) phat hien mau nay PHO
BIEN HON NHIEU mau co quotes o tren: 1,072 file co cum "duoc hieu nhu
sau" (thuong ngay sau tieu de "Dieu N. Giai thich tu ngu"), so voi chi 54
file co "duoc hieu la". Cau truc RAT DEU DAN, KHONG co quotes quanh thuat
ngu:
    Trong Thong tu nay, cac tu ngu sau day duoc hieu nhu sau:
    1. Giay to co gia la bang chung xac nhan nghia vu tra no...
    2. Giay to co gia dai han la giay to co gia co thoi han...

Moi muc la "N. <thuat ngu KHONG quotes> la <dinh nghia>." - ranh gioi
thuat ngu la tu sau so thu tu den " la " DAU TIEN tren CUNG mot dong (khong
xuong dong). Dinh nghia co the KEO DAI QUA NHIEU DONG (vi du that: muc 2
trong 01_2011_qh13_2.md tiep tuc sang dong thu 2 khong co so thu tu moi) -
CHI ket thuc khi gap muc danh so TIEP THEO (dau dong, "N. ") hoac het van
ban.

CHI kich hoat khi van ban chua cum trigger "duoc hieu nhu sau" (tim trong
TOAN BO text, khong phan biet hoa/thuong) - neu khong co trigger nay,
KHONG ap dung mau danh sach danh so, tranh false positive tren cac danh
sach danh so KHAC khong phai dinh nghia (vd danh sach dieu kien/thu tuc
cung co the tinh co chua cau truc "N. X la Y" ve mat cu phap nhung khac
hoan toan ve ngu nghia - xem test_enum_list_pattern_requires_trigger_
phrase_to_avoid_false_positive).

Ket qua tu ca 2 mau (quotes + danh sach danh so) duoc GOP lai, loai trung
lap theo term_id (giu ket qua XUAT HIEN TRUOC neu 2 mau cung tra ve mot
term_id - hiem, nhung co the xay ra).

=== USES_TERM (Article -> Term): extract_term_usages_rule_based ===
Theo data-model.md: "string-match ten thuat ngu da co trong
Term.ten_thuat_ngu". Ham nay KHONG tu truy Neo4j de lay danh sach thuat
ngu da biet - nhan `known_terms` (dict term_id -> ten_thuat_ngu) lam tham
so, do caller (buoc ingest/orchestration, chua lam trong T012) truyen vao
- giu dung Dieu 5 (module nay khong biet Neo4j ton tai).

Match CASE-SENSITIVE + word-boundary (\\b, Python 3 Unicode-aware nen bat
dung ranh gioi voi ky tu co dau tieng Viet): nhieu thuat ngu phap ly viet
hoa (vd "Ngay") trung voi tu thong dung viet thuong xuat hien khap noi
trong van ban phap ly (vd "ngay" nghia thong thuong) - khong phan biet
hoa/thuong se bung no false positive USES_TERM tren tu thong dung, lam
graph vo nghia. Day la gia dinh ro rang, chap nhan bo sot truong hop
thuat ngu duoc nhac lai khong dung hoa/thuong goc (hiem trong van ban
phap ly, thuat ngu dinh nghia thuong duoc giu nguyen cach viet hoa khi
tai su dung).

Moi thuat ngu chi tra ve TOI DA MOT lan cho MOI van ban (mot canh
USES_TERM duy nhat, khong phai mot canh cho moi lan xuat hien) - khop voi
data-model.md (USES_TERM la mot canh Article -> Term, khong co thuoc tinh
dem so lan). Ket qua tra ve THEO THU TU XUAT HIEN dau tien trong text
(cung quy uoc voi extract_references cua reference_extractor.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.slugify import slugify_doc_name

# Ho tro ca quotes thang (") lan quotes cong ("" "") - corpus that dung ca
# hai (xem module docstring). Dinh nghia cat o dau cau ket thuc gan nhat:
# ".", ";", xuong dong, HOAC truoc cum "va ... duoc hieu la" tiep theo -
# bang chung that (TIEN_DO.md DOT 5): cau that thuong noi 2 dinh nghia qua
# "va" trong CUNG mot cau nhung CHI thuat ngu dau co quotes (vd '"Ngay"
# duoc hieu la ngay duong lich va thang duoc hieu la thang duong lich.') -
# khong co lookahead nay, dinh nghia dau se "nuot" ca phan noi tiep khong
# lien quan. Fallback cuoi cung ($) cho truong hop dinh nghia o cuoi text,
# khong co dau cau ket thuc.
_DEFINITION_RE = re.compile(
    r"[“\"](?P<term>[^”\"]+)[”\"]\s*được hiểu là\s+"
    r"(?P<definition>.+?)"
    r"(?=[.;\n]| và [^.;\n]*?được hiểu là|$)"
)

# Mau 2: danh sach dinh nghia danh so (xem module docstring). Buoc 1:
# CHI tim ranh gioi tung muc (khong tach term/dinh nghia o day, xem
# _split_enum_item_term_and_definition) - dung re.DOTALL de dinh nghia
# duoc phep chua xuong dong (keo dai qua nhieu dong, vi du that trong
# module docstring), lookahead dung dung TRUOC muc danh so tiep theo (dau
# dong, "N. ") hoac het van ban (\Z).
_ENUM_ITEM_RE = re.compile(
    r"(?:^|\n)[ \t]*\d{1,3}\.[ \t]+(?P<item>.+?)"
    r"(?=\n[ \t]*\d{1,3}\.[ \t]|\Z)",
    re.DOTALL,
)

_ENUM_TRIGGER_RE = re.compile(r"được hiểu như sau", re.IGNORECASE)

# " la " co the xuat hien NHIEU LAN tren dong dau cua mot muc - pho bien
# nhat la mau viet tat "<Ten day du> (sau day goi tat la <ten ngan>) la
# <dinh nghia>" (phat hien khi kiem chung tren toan bo corpus that,
# TIEN_DO.md DOT 6, anh huong ~4.4% dinh nghia truoc khi fix): " la " DAU
# TIEN nam BEN TRONG ngoac viet tat, khong phai ranh gioi that. Regex nay
# CHI dung de TIM vi tri ung vien - _split_enum_item_term_and_definition
# se loc bo vi tri nam trong ngoac chua dong.
_LA_SPLIT_RE = re.compile(r"\s+là\s+")


def _split_enum_item_term_and_definition(item_text: str) -> tuple[str, str] | None:
    """Tach `item_text` (noi dung MOT muc danh so, DA bo "N. " o dau)
    thanh (term, dinh_nghia) tai vi tri " la " DAU TIEN tren dong dau MA
    phan truoc no co ngoac tron CAN BANG (khong con ngoac mo chua dong) -
    tranh nham voi " la " ben trong ngoac viet tat (xem _LA_SPLIT_RE).
    Term luon nam tren DONG DAU (khong xuong dong); dinh nghia la phan con
    lai SAU vi tri tach, GOM CA cac dong tiep theo (neu co).

    Neu khong tim duoc vi tri nao co ngoac can bang (hiem), fallback ve vi
    tri " la " DAU TIEN (giu hanh vi don gian, thay vi bo qua ca muc).
    Tra ve None neu khong co " la " nao tren dong dau (muc khong dung mau
    dinh nghia, bo qua)."""
    newline_pos = item_text.find("\n")
    first_line = item_text if newline_pos == -1 else item_text[:newline_pos]
    rest = "" if newline_pos == -1 else item_text[newline_pos:]

    fallback_match = None
    for match in _LA_SPLIT_RE.finditer(first_line):
        prefix = first_line[: match.start()]
        if fallback_match is None:
            fallback_match = match
        if prefix.count("(") == prefix.count(")"):
            term = prefix.strip()
            definition = (first_line[match.end() :] + rest).strip()
            return term, definition

    if fallback_match is not None:
        term = first_line[: fallback_match.start()].strip()
        definition = (first_line[fallback_match.end() :] + rest).strip()
        return term, definition

    return None


@dataclass
class ExtractedDefinition:
    """Mot dinh nghia da trich (data-model.md DEFINES: Article -> Term)."""

    term_id: str
    ten_thuat_ngu: str
    dinh_nghia: str


@dataclass
class TermUsage:
    """Mot lan mot Article dung lai thuat ngu da biet (data-model.md
    USES_TERM: Article -> Term)."""

    term_id: str
    ten_thuat_ngu: str


def extract_definitions_rule_based(text: str) -> list[ExtractedDefinition]:
    """Tim tat ca dinh nghia trong `text` theo 2 mau (xem module docstring):
    (1) '"<thuat ngu>" duoc hieu la <dinh nghia>' (co quotes), (2) danh
    sach danh so 'N. <thuat ngu> la <dinh nghia>' - CHI khi `text` chua
    trigger "duoc hieu nhu sau".

    Ket qua tu ca 2 mau duoc gop, theo thu tu xuat hien, loai trung lap
    theo term_id (giu ket qua xuat hien TRUOC). Tra ve list rong (khong
    phai None, khong raise) khi khong co dinh nghia nao khop mau ro rang."""
    definitions: list[ExtractedDefinition] = []

    for match in _DEFINITION_RE.finditer(text):
        term = match.group("term").strip()
        definition = match.group("definition").strip()
        definitions.append(
            ExtractedDefinition(
                term_id=slugify_doc_name(term),
                ten_thuat_ngu=term,
                dinh_nghia=definition,
            )
        )

    if _ENUM_TRIGGER_RE.search(text):
        for match in _ENUM_ITEM_RE.finditer(text):
            split = _split_enum_item_term_and_definition(match.group("item"))
            if split is None:
                continue
            term, definition = split
            definitions.append(
                ExtractedDefinition(
                    term_id=slugify_doc_name(term),
                    ten_thuat_ngu=term,
                    dinh_nghia=definition,
                )
            )

    seen_term_ids: set[str] = set()
    deduped: list[ExtractedDefinition] = []
    for d in definitions:
        if d.term_id in seen_term_ids:
            continue
        seen_term_ids.add(d.term_id)
        deduped.append(d)
    return deduped


def extract_term_usages_rule_based(
    text: str, known_terms: dict[str, str]
) -> list[TermUsage]:
    """Tim cac thuat ngu trong `known_terms` (term_id -> ten_thuat_ngu)
    xuat hien (case-sensitive, word-boundary) trong `text`. Moi thuat ngu
    xuat hien it nhat 1 lan tra ve DUNG MOT LAN, theo thu tu xuat hien dau
    tien. `known_terms` rong hoac `text` rong -> tra ve list rong."""
    if not text or not known_terms:
        return []

    matches: list[tuple[int, TermUsage]] = []
    for term_id, ten_thuat_ngu in known_terms.items():
        pattern = re.compile(r"\b" + re.escape(ten_thuat_ngu) + r"\b")
        found = pattern.search(text)
        if found:
            matches.append((found.start(), TermUsage(term_id, ten_thuat_ngu)))

    matches.sort(key=lambda pair: pair[0])
    return [usage for _position, usage in matches]
