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

from app.extraction.slugify import slugify_doc_name

# Quyet dinh ranh gioi "ten van ban ket thuc o dau" (diem mo ho duoc phep
# tu quyet dinh theo brief - ghi lai gia dinh theo constitution "ghi gia
# dinh"): chi ho tro 2 dang cu the xuat hien trong tasks.md T006, khong co
# gang bao quat moi cach hanh van trich dan phap ly (P1 rule-based, khong
# phai NLP toan dien):
#   - "Luat <ten...> <nam 4 chu so>", vd "Luat Doanh nghiep 2020" - ten
#     van ban ket thuc ngay sau nam ban hanh 4 chu so.
#   - "Nghi dinh <so>/<nam 4 chu so>/<ma hieu>", vd
#     "Nghi dinh 123/2020/ND-CP" - ket thuc ngay sau ma hieu (chu/so/gach
#     ngang, dung truoc khoang trang hoac dau cau tiep theo).
_DOC_NAME_PATTERN = (
    r"Luật\s+[^\d,.;]+?\d{4}"
    r"|Nghị định\s+\d+/\d{4}/[\w\-]+"
)

# "khoan {so}" phia truoc la tuy chon, chi dung de nhan dien cau trich dan
# (khong xuat hien trong output). "Dieu" phai viet hoa chu D - phan biet
# voi "dieu"/"Dieu luat" thuong dung theo nghia doi thuong khac, tranh
# false positive (xem test_lowercase_dieu_in_everyday_sense_does_not_match,
# test_dieu_without_trailing_number_does_not_match).
_CITATION_RE = re.compile(
    r"(?:khoản\s+\d+\s+)?"
    r"Điều\s+(?P<article_num>\d+)"
    r"(?:\s+(?P<doc_name>" + _DOC_NAME_PATTERN + r"))?"
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
        doc_slug = slugify_doc_name(doc_name) if doc_name else current_doc_slug
        target_article_id = f"{doc_slug}_dieu-{article_num}"
        references.append(
            ExtractedReference(
                target_article_id=target_article_id,
                raw_text=match.group(0),
            )
        )
    return references
