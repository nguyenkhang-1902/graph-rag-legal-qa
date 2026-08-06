"""relation_llm.py (T013): trich xuat AMENDS/SUPERSEDES/CONFLICTS_WITH
(data-model.md) - quan he kho nhat trong graph, LLM extraction voi
`confidence`/`ly_do` (spec.md FR-003).

Trach nhiem cua module nay (constitution Dieu 5): rule-based candidate
narrowing (`find_relation_candidates` - KHONG dung Neo4j/LLM) THEM LLM
confirmation (`classify_candidate`/`_call_ollama` - goi Ollama qua HTTP,
cung API shape da verify o `app/serving/api.py`). Hai phan gop chung mot
file (khac voi term_extractor.py/reference_extractor.py) vi candidate
narrowing o day CHI ton tai de giam chi phi goi LLM (data-model.md: "LLM
extraction"), khong dung doc lap - ten file "relation_llm" phan anh dung
dieu do.

=== Vi sao candidate narrowing can thiet (khong goi LLM cho MOI Article) ===
Khao sat tho corpus that (TIEN_DO.md, muc "Viec can lam tiep theo" #2):
quet tu khoa don thuan ("thay the", "bai bo"...) overcounted rat nang - day
la tu qua pho bien trong van ban phap ly, phan lon KHONG lien quan gi den
quan he AMENDS/SUPERSEDES/CONFLICTS_WITH giua 2 Dieu cu the. Candidate
narrowing CHI xem la ung vien khi CA HAI dieu kien dung trong CUNG mot cau:
(1) mot trigger phrase cho 1 trong 3 loai quan he, VA (2) mot trich dan
"Dieu X <ten van ban>" co TEN VAN BAN DICH RO RANG (tai dung nguyen
`reference_extractor.extract_references` - Dieu 1, khong duplicate regex
trich dan).

=== Gioi han pham vi da biet (KHONG chan T013, ghi ro theo brief) ===
Nhieu cau that dang "Dieu N duoc sua doi, bo sung nhu sau:" KHONG neu ten
van ban trong CHINH cau do (chi biet qua Document.title - hien dang RONG
trong Neo4j, gap tu structure_parser.py's parse_article_chunk, xem
TIEN_DO.md). `extract_references` se resolve nhung trich dan nay ve
`current_doc_slug` (tu tham chieu) - candidate narrowing loai BO CO CHU
DICH nhom nay (target doc slug == current_doc_slug), thay vi doan bua quan
he voi mot van ban khong xac dinh duoc. Day la GIOI HAN CAU TRUC da biet,
khong phai bug - can quyet dinh rieng (bo sung Document.title hay chap
nhan bo qua) truoc khi mo rong pham vi nay.

=== LLM la nguon quyet dinh CUOI CUNG, khong phai trigger keyword ===
`relationship_type_hint` tu candidate narrowing CHI la goi y (trigger nao
khop truoc theo thu tu uu tien AMENDS > SUPERSEDES > CONFLICTS_WITH khi
nhieu trigger cung xuat hien mot cau) - KHONG duoc ghi thang vao Neo4j.
`classify_candidate` luon goi LLM voi ca cau text that de LLM tu quyet
dinh loai quan he DUNG (co the khac hint, hoac "NONE" neu LLM xac nhan
day khong thuc su la mot trong 3 quan he) - khop dung data-model.md
"Nguon trich xuat: LLM extraction", candidate narrowing chi la buoc loc
chi phi.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from app import config
from app.extraction.reference_extractor import extract_references

logger = logging.getLogger(__name__)

# Cat cau o dau cau ket thuc gan nhat (".", ";") hoac xuong dong - cung
# quy uoc ranh gioi don gian voi term_extractor.py (P1 rule-based, ghi ro
# gia dinh thay vi ngam dinh). `(?<=[.;])\s+` giu lai dau cau o cuoi cau
# truoc, `\n+` tach theo dong khi khong co dau cau ro rang.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+|\n+")

# Thu tu uu tien khi nhieu trigger cung khop mot cau (hiem) - CHI dung de
# chon relationship_type_hint (goi y, khong phai ket qua cuoi - xem module
# docstring). AMANDS/SUPERSEDES truoc CONFLICTS_WITH vi "bai bo"/"het hieu
# luc" thuong la he qua duoc nhac kem, khong phai trong tam cau.
_TRIGGER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AMENDS", re.compile(r"sửa đổi|bổ sung", re.IGNORECASE)),
    ("SUPERSEDES", re.compile(r"thay thế", re.IGNORECASE)),
    (
        "CONFLICTS_WITH",
        re.compile(r"bãi bỏ|hết hiệu lực|trái với|mâu thuẫn với", re.IGNORECASE),
    ),
]

_VALID_RELATION_TYPES = {"AMENDS", "SUPERSEDES", "CONFLICTS_WITH"}

# Lan goi generate() dau tien mat ~12s (load model) - cung timeout voi
# app/serving/api.py (da verify that o do, dung chung hang so trien khai).
_OLLAMA_TIMEOUT_SECONDS = 120.0

_RELATION_PROMPT_TEMPLATE = (
    "Bạn là trợ lý phân tích văn bản pháp luật Việt Nam. Dưới đây là một câu "
    "trích từ Điều luật {source_article_id}, có khả năng thể hiện quan hệ "
    "với Điều luật khác ({target_article_id}):\n\n"
    '"{sentence}"\n\n'
    "Hãy xác định quan hệ ĐÚNG NHẤT giữa 2 Điều luật này, CHỈ được chọn một "
    "trong 3 loại: AMENDS (sửa đổi/bổ sung nội dung), SUPERSEDES (thay thế "
    "hoàn toàn), CONFLICTS_WITH (mâu thuẫn/bãi bỏ/hết hiệu lực). Nếu câu "
    'trên KHÔNG thực sự thể hiện một trong 3 quan hệ này, trả lời '
    '"NONE". CHỈ trả lời bằng JSON đúng định dạng sau, không thêm giải '
    "thích ngoài JSON:\n"
    '{{"relationship_type": "AMENDS|SUPERSEDES|CONFLICTS_WITH|NONE", '
    '"confidence": 0.0-1.0, "ly_do": "..."}}'
)


@dataclass
class RelationCandidate:
    """Mot ung vien quan he (rule-based candidate narrowing) - CHUA duoc
    LLM xac nhan (xem module docstring)."""

    target_article_id: str
    relationship_type_hint: str
    trigger_keyword: str
    sentence: str


@dataclass
class ExtractedRelation:
    """Mot quan he AMENDS/SUPERSEDES/CONFLICTS_WITH DA duoc LLM xac nhan
    (data-model.md: `confidence`, `ly_do`)."""

    target_article_id: str
    relationship_type: str
    confidence: float
    ly_do: str


def _split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _detect_trigger(sentence: str) -> tuple[str, str] | None:
    for relationship_type, pattern in _TRIGGER_PATTERNS:
        match = pattern.search(sentence)
        if match:
            return relationship_type, match.group(0)
    return None


def _target_doc_slug(target_article_id: str) -> str:
    """Suy doc_slug tu mot article_id (`f"{doc_slug}_dieu-{so_dieu}"` -
    dung nguyen scheme cua reference_extractor.py/structure_parser.py) -
    dung rsplit (khong phai split) vi doc_slug khong bao gio tu chua
    "_dieu-" (slugify_doc_name khong sinh ra cum nay tu ten van ban)."""
    return target_article_id.rsplit("_dieu-", 1)[0]


def find_relation_candidates(
    text: str, current_doc_slug: str
) -> list[RelationCandidate]:
    """Quet `text` theo tung cau, tim cau vua co trigger phrase (1 trong 3
    loai quan he) vua co trich dan "Dieu X <ten van ban>" CO TEN VAN BAN
    RO RANG (tai dung `extract_references` - loai tu dong ca trich dan tu
    tham chieu, xem module docstring).

    Loai bo candidate co target_article_id CUNG van ban voi
    `current_doc_slug` (tu tham chieu - gioi han da biet, xem module
    docstring). Neu nhieu cau cung tra ve CUNG target_article_id, chi giu
    candidate DAU TIEN (tranh goi LLM lap lai vo ich cho cung mot cap).

    Tra ve list rong (khong raise) khi khong co candidate nao."""
    candidates: list[RelationCandidate] = []
    seen_targets: set[str] = set()

    for sentence in _split_sentences(text):
        trigger = _detect_trigger(sentence)
        if trigger is None:
            continue
        relationship_type_hint, trigger_keyword = trigger

        for ref in extract_references(sentence, current_doc_slug):
            if _target_doc_slug(ref.target_article_id) == current_doc_slug:
                continue
            if ref.target_article_id in seen_targets:
                continue
            seen_targets.add(ref.target_article_id)
            candidates.append(
                RelationCandidate(
                    target_article_id=ref.target_article_id,
                    relationship_type_hint=relationship_type_hint,
                    trigger_keyword=trigger_keyword,
                    sentence=sentence.strip(),
                )
            )

    return candidates


def _build_relation_prompt(source_article_id: str, candidate: RelationCandidate) -> str:
    return _RELATION_PROMPT_TEMPLATE.format(
        source_article_id=source_article_id,
        target_article_id=candidate.target_article_id,
        sentence=candidate.sentence,
    )


def _parse_llm_response(raw_response: str) -> tuple[str, float, str] | None:
    """Parse JSON tu response cua LLM - xu ly thuc te ca truong hop Ollama
    boc JSON trong markdown code fence (```json ... ```) du prompt yeu cau
    khong lam vay (xac nhan qua thuc nghiem voi model khac trong
    app/serving/api.py's prompt style). Tra ve None (khong raise) tren bat
    ky loi parse/validate nao - LLM output khong dang tin cay 100%, coi
    nhu khong xac nhan duoc quan he thay vi crash ca pipeline batch."""
    text = raw_response.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        logger.warning(
            "relation_llm: khong tim thay JSON object trong LLM response: %r",
            raw_response,
        )
        return None

    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning(
            "relation_llm: LLM response khong phai JSON hop le: %r", raw_response
        )
        return None

    relationship_type = data.get("relationship_type")
    confidence = data.get("confidence")
    ly_do = data.get("ly_do")

    if relationship_type not in _VALID_RELATION_TYPES | {"NONE"}:
        logger.warning(
            "relation_llm: relationship_type khong hop le tu LLM: %r", relationship_type
        )
        return None
    if not isinstance(confidence, (int, float)):
        logger.warning(
            "relation_llm: confidence khong phai so tu LLM: %r", confidence
        )
        return None
    if not isinstance(ly_do, str):
        logger.warning("relation_llm: ly_do khong phai chuoi tu LLM: %r", ly_do)
        return None

    return relationship_type, float(confidence), ly_do


def _call_ollama(prompt: str) -> str:
    """Goi Ollama's `/api/generate` (khong stream) - cung API shape da
    verify that o `app/serving/api.py` (module docstring o do co chi tiet
    verify truc tiep tren Ollama that dang chay)."""
    response = httpx.post(
        f"{config.OLLAMA_BASE_URL}/api/generate",
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        },
        timeout=_OLLAMA_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()["response"]


def classify_candidate(
    source_article_id: str, candidate: RelationCandidate
) -> ExtractedRelation | None:
    """Goi LLM de XAC NHAN (khong phai chi dung hint) loai quan he that
    su giua `source_article_id` va `candidate.target_article_id`, kem
    `confidence`/`ly_do` (data-model.md).

    Tra ve None khi LLM xac nhan day KHONG phai mot trong 3 quan he
    ("NONE") HOAC khi response khong parse/validate duoc (xem
    `_parse_llm_response`) - ca hai truong hop deu la "khong xac nhan
    duoc quan he", khong phan biet o caller."""
    prompt = _build_relation_prompt(source_article_id, candidate)
    raw_response = _call_ollama(prompt)
    parsed = _parse_llm_response(raw_response)
    if parsed is None:
        return None

    relationship_type, confidence, ly_do = parsed
    if relationship_type == "NONE":
        return None

    return ExtractedRelation(
        target_article_id=candidate.target_article_id,
        relationship_type=relationship_type,
        confidence=confidence,
        ly_do=ly_do,
    )
