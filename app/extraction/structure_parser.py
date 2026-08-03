"""structure_parser.py (T008): parse cau truc phan cap Document -> Chapter
(optional) -> Article -> Clause (optional) tu raw text mot van ban luat.

Trach nhiem duy nhat cua module nay (constitution Dieu 5): parse cau truc
bang rule-based/regex (Dieu 1 - khong LLM), khong dung Neo4j/graph code o
day (do la upsert.py, T009), khong trich xuat "Dieu X" reference (do la
reference_extractor.py, T007 - da xong, KHONG duplicate regex cua no o
day du ca hai module deu xu ly "Dieu N").

=== GIA DINH VE INPUT FORMAT (chua verify voi corpus that - flag ro) ===
Chua co corpus that nao duoc fetch vao repo nay (viec do bi hoan lai co
chu dich sang mot checkpoint sau - xem research.md ADR-002, tai ve doi hoi
keo toan bo ~61k van ban HuggingFace bat ke giu lai bao nhieu, nen khong
lam giua chung task mot cach tuy tien). Module nay duoc xay dung dua tren
QUY UOC CAU TRUC CHUAN, DA DUOC TAI LIEU HOA RONG RAI cua van ban quy pham
phap luat Viet Nam (theo cach data-model.md, spec.md, va chinh Luat Ban
hanh van ban quy pham phap luat mo ta cau truc van ban):

  - Dong "text/*.md" dau tien la tieu de dang H1 markdown: "# {title}",
    theo dung format `scripts/fetch_zalo_legal_corpus.py` ghi ra
    (`# {title}\\n\\n{body text}\\n`).
  - Dong tieu de Chuong: "Chuong I", "Chuong II", "Chuong 1"... (so La Ma
    hoac A Rap), THUONG di ngay sau boi mot dong tieu de rieng, vd:
        Chuong I
        NHUNG QUY DINH CHUNG
  - Dong tieu de Dieu: bat dau bang "Dieu {N}." roi tieu de TREN CUNG MOT
    DONG, vd "Dieu 5. Pham vi dieu chinh". Noi dung Dieu la tat ca cho toi
    "Dieu {N+1}." tiep theo / "Chuong" tiep theo / het van ban.
  - Khoan: trong noi dung mot Dieu, mot dong bat dau BANG SO + DAU CHAM o
    dau dong (cot 0), vd "1. Noi dung khoan mot." - CHI coi day la ranh
    gioi Khoan khi dong do o dau dong VA nam trong noi dung mot Dieu,
    ngay sau tieu de Dieu hoac ngay sau mot dong-khoan khac (khong phai
    moi danh sach so o bat ky dau cung la khoan - can than, khong nham
    voi danh sach so nam giua doan van xuoi).
  - Khong phai van ban nao cung co Chuong (mot so di thang Document ->
    Article). Khong phai Dieu nao cung co Khoan (mot so chi la mot doan
    van). Ca hai deu la optional trong cau truc output.

Day la gia dinh SE duoc doi chieu voi du lieu corpus that o checkpoint du
an tiep theo (ingest vai van ban mau that). Neu format that khac di, module
nay se can dieu chinh luc do - do la ky vong binh thuong, khong phai loi
cua task nay.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.extraction.slugify import slugify_doc_name

# Dong tieu de Chuong: CHI "Chuong" + so La Ma/A Rap, KHONG co gi khac tren
# cung dong (tieu de Chuong nam o dong RIENG tiep theo - xem gia dinh o
# trên). Dung .strip() truoc khi match nen khong can \s* o dau/cuoi.
_CHAPTER_RE = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)$")

# Dong tieu de Dieu: "Dieu {N}." roi tieu de tren cung dong (co the rong).
_ARTICLE_RE = re.compile(r"^Điều\s+(\d+)\.\s*(.*)$")

# Dong-khoan: BAT BUOC o dau dong (khong strip truoc khi match - xem
# _extract_clauses, dung nguyen dong tho de ep cot 0).
_CLAUSE_RE = re.compile(r"^(\d+)\.\s+(.*)$")

_PREVIEW_MAX_CHARS = 200

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(numeral: str) -> int:
    """Doi so La Ma (vd "IV", "IX") sang int. Helper noi bo, khong dung o
    module khac (xem brief - giu local trong structure_parser.py)."""
    total = 0
    prev_value = 0
    for ch in reversed(numeral.upper()):
        value = _ROMAN_VALUES[ch]
        if value < prev_value:
            total -= value
        else:
            total += value
            prev_value = value
    return total


def _chapter_numeral_to_int(raw: str) -> int:
    """"I"/"IV"/... hoac "1"/"2"/... -> int. Dung cho chapter_id/so_chuong."""
    if raw.isdigit():
        return int(raw)
    return _roman_to_int(raw)


@dataclass
class Clause:
    """Node Khoan (data-model.md) - giu FULL text (khong truncate)."""

    clause_id: str
    so_khoan: int
    noi_dung: str


@dataclass
class Article:
    """Node Dieu (data-model.md). `noi_dung_preview` da bi truncate ~200 ky
    tu - full text KHONG duoc luu o day (thuoc trach nhiem component khac,
    xem module docstring / brief). `chroma_id` khong thuoc pham vi task nay
    (out of scope - se duoc gan sau boi component embed/upsert)."""

    article_id: str
    so_dieu: int
    noi_dung_preview: str
    clauses: list[Clause] = field(default_factory=list)


@dataclass
class Chapter:
    """Node Chuong (data-model.md)."""

    chapter_id: str
    so_chuong: int
    tieu_de: str
    articles: list[Article] = field(default_factory=list)


@dataclass
class ParsedDocument:
    """Node Document (data-model.md) - CHI `doc_id`/`title`, cac truong con
    lai (`so_hieu`, `loai_vb`, `ngay_hieu_luc`, `source_file`) khong thuoc
    pham vi task nay (khong suy ra duoc tu than van ban - den tu noi khac/
    sau nay, xem brief).

    `chapters`: cac Chuong theo thu tu xuat hien, moi Chuong biet cac Dieu
    con cua no (`Chapter.articles`).
    `articles`: cac Dieu nam TRUC TIEP duoi Document (khong thuoc Chuong
    nao) - vd van ban khong co Chuong, hoac cac Dieu xuat hien truoc
    Chuong dau tien (hiem, nhung khong crash).

    Quan he cha-con o day du de mot task sau (upsert.py, T009 - khong
    thuoc task nay) tao cac canh BELONGS_TO (Article->Chapter,
    Chapter->Document, Clause->Article).
    """

    doc_id: str
    title: str
    chapters: list[Chapter] = field(default_factory=list)
    articles: list[Article] = field(default_factory=list)


def _split_title_and_body(text: str) -> tuple[str, str]:
    """Dong dau "# {title}" -> (title, phan body con lai). Neu khong co
    dong "# " o dau (input mo ho/malformed) -> title rong, toan bo text
    duoc coi la body (khong raise - xem yeu cau "khong crash tren input
    bat thuong" trong brief)."""
    if not text:
        return "", ""
    lines = text.split("\n")
    first_line = lines[0]
    if first_line.startswith("# "):
        title = first_line[2:].strip()
        body = "\n".join(lines[1:])
        return title, body
    return "", text


def _extract_clauses(content_lines: list[str], article_id: str) -> list[Clause]:
    """Quet cac dong SAU dong tieu de Dieu (khong bao gom tieu de) de tim
    Khoan. Chi vao "che do khoan" khi dong khong-rong DAU TIEN trong noi
    dung nay la mot dong-khoan hop le (bat dau cot 0 bang "\\d+. ") - neu
    khong, Dieu nay KHONG co Khoan (dung theo gia dinh "conservative" trong
    brief). Mot khi da vao che do khoan, moi dong-khoan tiep theo (cot 0)
    mo mot Khoan moi; cac dong khac duoc noi vao noi_dung cua Khoan hien
    tai (cho phep khoan tran nhieu dong)."""
    clauses: list[Clause] = []
    current_so_khoan: int | None = None
    current_lines: list[str] = []
    started = False
    in_clause_mode = False

    def flush() -> None:
        if current_so_khoan is None:
            return
        text = "\n".join(current_lines).strip()
        clauses.append(
            Clause(
                clause_id=f"{article_id}_khoan-{current_so_khoan}",
                so_khoan=current_so_khoan,
                noi_dung=text,
            )
        )

    for raw_line in content_lines:
        if not started:
            if not raw_line.strip():
                continue
            started = True
            match = _CLAUSE_RE.match(raw_line)
            if not match:
                # Dong noi dung dau tien khong phai dong-khoan -> Dieu nay
                # khong co Khoan, dung quet (khong doan mo ho, xem brief).
                break
            in_clause_mode = True
            current_so_khoan = int(match.group(1))
            current_lines = [match.group(2)]
            continue

        if not in_clause_mode:
            break

        match = _CLAUSE_RE.match(raw_line)
        if match:
            flush()
            current_so_khoan = int(match.group(1))
            current_lines = [match.group(2)]
        else:
            current_lines.append(raw_line)

    flush()
    return clauses


def parse_document(text: str) -> ParsedDocument:
    """Parse raw text mot van ban (format `# {title}\\n\\n{body}\\n` - xem
    module docstring) thanh ParsedDocument. Khong bao gio raise tren input
    rong/bat thuong - tra ve cau truc rong/mot phan la sensible fallback."""
    title, body = _split_title_and_body(text)
    doc_id = slugify_doc_name(title) if title else ""

    lines = body.split("\n")
    n = len(lines)

    chapters: list[Chapter] = []
    top_level_articles: list[Article] = []
    current_chapter: Chapter | None = None

    # Trang thai Dieu dang mo (chua gap ranh gioi tiep theo).
    pending: dict | None = None  # {"article_id", "so_dieu", "heading_title", "content_lines", "owner"}

    def close_pending_article() -> None:
        nonlocal pending
        if pending is None:
            return
        heading_title = pending["heading_title"]
        content_lines: list[str] = pending["content_lines"]
        full_text_parts = []
        if heading_title:
            full_text_parts.append(heading_title)
        body_text = "\n".join(content_lines).strip()
        if body_text:
            full_text_parts.append(body_text)
        full_text = "\n".join(full_text_parts).strip()
        preview = full_text[:_PREVIEW_MAX_CHARS]
        clauses = _extract_clauses(content_lines, pending["article_id"])
        article = Article(
            article_id=pending["article_id"],
            so_dieu=pending["so_dieu"],
            noi_dung_preview=preview,
            clauses=clauses,
        )
        owner: Chapter | None = pending["owner"]
        if owner is not None:
            owner.articles.append(article)
        else:
            top_level_articles.append(article)
        pending = None

    i = 0
    while i < n:
        stripped = lines[i].strip()

        chapter_match = _CHAPTER_RE.match(stripped) if stripped else None
        if chapter_match:
            close_pending_article()
            so_chuong = _chapter_numeral_to_int(chapter_match.group(1))
            chapter_id = f"{doc_id}_chuong-{so_chuong}"
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            tieu_de = lines[j].strip() if j < n else ""
            current_chapter = Chapter(
                chapter_id=chapter_id, so_chuong=so_chuong, tieu_de=tieu_de
            )
            chapters.append(current_chapter)
            i = (j + 1) if j < n else n
            continue

        article_match = _ARTICLE_RE.match(stripped) if stripped else None
        if article_match:
            close_pending_article()
            so_dieu = int(article_match.group(1))
            article_id = f"{doc_id}_dieu-{so_dieu}"
            pending = {
                "article_id": article_id,
                "so_dieu": so_dieu,
                "heading_title": article_match.group(2).strip(),
                "content_lines": [],
                "owner": current_chapter,
            }
            i += 1
            continue

        if pending is not None:
            pending["content_lines"].append(lines[i])
        i += 1

    close_pending_article()

    return ParsedDocument(
        doc_id=doc_id, title=title, chapters=chapters, articles=top_level_articles
    )
