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

import logging
import re
from dataclasses import dataclass, field

from app.extraction.slugify import slugify_doc_name

logger = logging.getLogger(__name__)

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
    tu - day la thu duy nhat duoc GHI VAO NEO4J (xem upsert.py, T009).
    `chroma_id` khong thuoc pham vi task nay (out of scope - se duoc gan sau
    boi component embed/upsert).

    `full_text` la ca heading + body + clause text, KHONG truncate - them
    vao o T009 (xem task-2d-brief.md) CHI de lam input cho cac buoc
    extraction can toan bo noi dung Dieu (reference_extractor.py can full
    text de tim moi trich dan "Dieu X", 200 ky tu preview se bo sot gan het
    trich dan trong mot Dieu that). Truong nay KHONG bao gio duoc ghi vao
    Neo4j - `upsert.py` chi doc `noi_dung_preview`/`chroma_id` cho node
    Article (data-model.md: "KHONG luu full text trong Neo4j")."""

    article_id: str
    so_dieu: int
    noi_dung_preview: str
    full_text: str
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


def _build_full_text_and_preview(
    heading_title: str, content_lines: list[str]
) -> tuple[str, str]:
    """Ghep heading + noi dung than bai thanh full_text, va cat preview
    ~200 ky tu (_PREVIEW_MAX_CHARS) - dung chung boi parse_document (qua
    close_pending_article) va parse_article_chunk, tranh 2 ban sao lech
    nhau (bai hoc tu bug leading-zero article_id o task-2c review)."""
    full_text_parts = []
    if heading_title:
        full_text_parts.append(heading_title)
    body_text = "\n".join(content_lines).strip()
    if body_text:
        full_text_parts.append(body_text)
    full_text = "\n".join(full_text_parts).strip()
    preview = full_text[:_PREVIEW_MAX_CHARS]
    return full_text, preview


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


def parse_document(text: str, fallback_doc_id: str = "") -> ParsedDocument:
    """Parse raw text mot van ban (format `# {title}\\n\\n{body}\\n` - xem
    module docstring) thanh ParsedDocument. Khong bao gio raise tren input
    rong/bat thuong - tra ve cau truc rong/mot phan la sensible fallback.

    `fallback_doc_id`: dung lam `doc_id` khi van ban KHONG co dong tieu de
    "# {title}" (title rong) - thay vi de doc_id sup thanh
    `slugify_doc_name("") == ""`. Neu nhieu van ban malformed nhu vay deu
    thieu title, doc_id rong se khien chung MERGE chung mot Document node
    (hai van ban khong lien quan bi gop lam mot, khong loi/canh bao - xem
    task-2e-brief.md). Caller thuc te (app/ingest.py, T009d) truyen ten
    file (khong duoi) lam fallback - da dam bao duy nhat qua
    scripts/fetch_zalo_legal_corpus.py's slugify_id. Mac dinh "" giu
    nguyen hanh vi cu cho cac caller khong truyen tham so nay (vd test
    hien co)."""
    title, body = _split_title_and_body(text)
    doc_id = slugify_doc_name(title) if title else fallback_doc_id

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
        full_text, preview = _build_full_text_and_preview(heading_title, content_lines)
        clauses = _extract_clauses(content_lines, pending["article_id"])
        article = Article(
            article_id=pending["article_id"],
            so_dieu=pending["so_dieu"],
            noi_dung_preview=preview,
            full_text=full_text,
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
            candidate = lines[j].strip() if j < n else ""
            # Chi coi dong ke tiep la tieu_de rieng cua Chuong khi no KHONG
            # tu no la mot dong tieu de cau truc khac (Chuong khac / Dieu).
            # Neu khong kiem tra, hai Chuong lien tiep khong co dong tieu de
            # rieng (hoac mot Chuong di thang vao Dieu, khong co tieu de) se
            # bi nuot mat dong Chuong/Dieu tiep theo lam tieu_de, lam bien
            # mat ca Dieu/Chuong do khoi ket qua parse (xem task-2c review
            # finding 1). tieu_de o day de rong ("khong co") va viec parse
            # tiep tuc binh thuong tu chinh dong candidate (khong bi bo qua).
            if candidate and (
                _CHAPTER_RE.match(candidate) or _ARTICLE_RE.match(candidate)
            ):
                tieu_de = ""
                i = j
            else:
                tieu_de = candidate
                i = (j + 1) if j < n else n
            current_chapter = Chapter(
                chapter_id=chapter_id, so_chuong=so_chuong, tieu_de=tieu_de
            )
            chapters.append(current_chapter)
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


def parse_article_chunk(
    text: str, doc_id: str, fallback_so_dieu: int | None = None
) -> ParsedDocument:
    """Parse mot file "moi file = mot Dieu" (corpus that - xem task-2f-brief.md,
    KHAC voi `parse_document()` o tren, van duoc GIU NGUYEN cho input dang
    "mot file = mot van ban nhieu Dieu"). Dong dau tien khong-rong cua
    `text` LA chinh dong tieu de Dieu ("Dieu N. <tieu de>", co the co hoac
    khong co tien to "# " markdown) - KHONG phai tieu de van ban. Toan bo
    phan con lai la noi dung cua DUY NHAT Dieu do; khong bao gio co "Dieu
    N." long ben trong body, va "Chuong" (neu xuat hien) chi la trich dan
    trong prose cua mot Khoan (xem `reference_extractor.py`), KHONG phai
    tieu de cau truc - vi ham nay khong bao gio quet tim dong tieu de
    Chuong, `ParsedDocument.chapters` luon la [] mot cach tu nhien.

    Dung LAI `_ARTICLE_RE`/`_extract_clauses` (Dieu 1 constitution - khong
    duplicate regex/logic da co o `parse_document()`), va cung article_id
    scheme `f"{doc_id}_dieu-{so_dieu}"` (dong bo voi `reference_extractor.py`).

    `doc_id`: do CALLER truyen vao san (khac voi `parse_document()` - ham
    nay KHONG tu tinh doc_id, vi title van ban dep khong the suy ra tu mot
    file-mot-Dieu - xem brief, out of scope). Document `title` luon de rong.

    `fallback_so_dieu`: dung khi dong tieu de KHONG khop pattern "Dieu N."
    (input bat thuong) - neu duoc truyen, dung so nay lam so_dieu VA ghi
    log canh bao ro rang (khong im lang coi nhu khong co gi xay ra). Neu
    dong tieu de khong khop VA khong co fallback, ham nay RAISE ValueError
    ro rang - KHONG doan bua so Dieu (khac voi `parse_document()`, ham do
    "khong crash tren input bat thuong" vi no xu ly toan bo corpus multi-
    Dieu va mot Dieu loi khong duoc lam mat ca van ban; o day moi file CHI
    la mot Dieu, mot heading loi ma khong co fallback nghia la khong co
    cach nao xac dinh duoc article_id dung - crash ro rang tot hon la tao
    ra mot Article voi so_dieu sai/doan bua)."""
    lines = text.split("\n")
    n = len(lines)

    i = 0
    while i < n and not lines[i].strip():
        i += 1

    if i < n:
        heading_line = lines[i].strip()
        if heading_line.startswith("#"):
            heading_line = heading_line.lstrip("#").strip()
        body_lines = lines[i + 1 :]
    else:
        heading_line = ""
        body_lines = []

    article_match = _ARTICLE_RE.match(heading_line)
    if article_match:
        so_dieu = int(article_match.group(1))
        heading_title = article_match.group(2).strip()
    elif fallback_so_dieu is not None:
        so_dieu = fallback_so_dieu
        heading_title = heading_line
        logger.warning(
            "parse_article_chunk: dong tieu de khong khop pattern 'Dieu "
            "N.' (heading=%r, doc_id=%r) - dung fallback_so_dieu=%d, "
            "KHONG parse duoc tieu de Dieu tu heading nay",
            heading_line,
            doc_id,
            fallback_so_dieu,
        )
    else:
        raise ValueError(
            f"parse_article_chunk: khong parse duoc dong tieu de Dieu tu "
            f"heading={heading_line!r} (doc_id={doc_id!r}) va khong co "
            "fallback_so_dieu de dung thay the - khong the xac dinh so_dieu."
        )

    article_id = f"{doc_id}_dieu-{so_dieu}"

    full_text, preview = _build_full_text_and_preview(heading_title, body_lines)

    clauses = _extract_clauses(body_lines, article_id)

    article = Article(
        article_id=article_id,
        so_dieu=so_dieu,
        noi_dung_preview=preview,
        full_text=full_text,
        clauses=clauses,
    )

    return ParsedDocument(doc_id=doc_id, title="", chapters=[], articles=[article])
