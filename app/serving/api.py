"""serving/api.py (T014): FastAPI app voi `POST /chat` - noi cac module
retrieval da co (`entry_point.py` T010, `traversal.py` T011/T015,
`embedder.py` T009f) thanh mot endpoint tra loi cau hoi phap luat co
citation path (spec.md FR-006, User Story 1).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): dieu phoi
(orchestration) + serving HTTP - goi `find_entry_points`/`traverse`/
`embedder.get_texts` da co san, KHONG chua lai logic vector search/graph
traversal/embedding cua chung. Phan "goi Ollama qua HTTP" duoc tach rieng
thanh `_call_ollama` (khong inline trong route handler) de test duoc doc
lap voi phan dieu phoi con lai.

=== Ollama HTTP API (verify that, khong doan) ===
Da verify TRUC TIEP tren Ollama that dang chay o may nay (`curl
http://localhost:11434/api/tags` xac nhan reachable, models
qwen2.5:7b-instruct/qwen2.5:14b-instruct da pull san) - `POST /api/generate`
voi body `{"model": ..., "prompt": ..., "stream": false}` tra ve JSON co
truong "response" (chuoi cau tra loi day du, khong phai stream cac dong
rieng le) va "done": true. Day la API "generate" mot lan (khong phai
"/api/chat" theo dinh dang message list) - du cho nhu cau o day (mot prompt
don, khong can lich su hoi thoai nhieu luot).

Du an nay KHONG dung langchain/langchain-ollama (Dieu 1 - tranh lop
framework khong can thiet) - goi HTTP truc tiep qua `httpx`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app import config
from app.graph_store.neo4j_client import Neo4jClient
from app.retrieval import embedder
from app.retrieval.entry_point import find_entry_points
from app.retrieval.traversal import traverse

logger = logging.getLogger(__name__)

app = FastAPI()

# Cau tra loi khi khong tim duoc entry point nao - day la mot ket qua BINH
# THUONG (cau hoi khong lien quan gi den corpus da ingest), khong phai loi
# server, nen tra ve HTTP 200 voi answer giai thich ro, khong raise/500.
_NOT_FOUND_ANSWER = "Không tìm thấy điều luật liên quan trong dữ liệu đã ingest."

# Lan goi generate() dau tien tren may nay mat ~12s (phan lon la load model
# vao Ollama, xem "load_duration" trong response that da verify) - timeout
# du rong de khong cat ngang mot lan goi that dang chay binh thuong.
_OLLAMA_TIMEOUT_SECONDS = 120.0

# Danh dau ro trong prompt cho 2 truong hop noi dung KHONG day du (case 1/3
# trong task-3e-brief.md) - de model KHONG nham preview rut gon hoac
# external placeholder voi full text that, tranh bia them noi dung.
_EXTERNAL_MARKER = (
    "[Điều luật này KHÔNG có trong dữ liệu đã ingest - không có nội dung, "
    "không được suy đoán hay bịa nội dung của Điều này]"
)
_PREVIEW_MARKER = "[preview rút gọn, chưa có embedding đầy đủ]"

# Query batched (mot lan goi Neo4j cho TOAN BO id can bo sung, khong phai
# mot lan cho moi id) de lay is_external/noi_dung_preview cho cac
# article_id KHONG co trong ket qua cua `embedder.get_texts` (chua duoc
# embed vao Chroma, hoac la external placeholder - xem task-3e-brief.md
# muc "Current real-data state").
_MISSING_ARTICLE_INFO_QUERY = (
    "MATCH (a:Article) WHERE a.article_id IN $ids "
    "RETURN a.article_id AS article_id, a.is_external AS is_external, "
    "a.noi_dung_preview AS noi_dung_preview"
)


class ChatRequest(BaseModel):
    question: str


@dataclass
class _ArticleContext:
    """Ngu canh da phan loai cho mot article_id trong
    `traversal_result.visited_article_ids`, dung de dung prompt VA citation
    path - xem 3 nhom trong task-3e-brief.md:
      1. is_external=True -> content=None (khong co noi dung o dau ca).
      2. is_external=False, is_preview=False -> content la full text that
         (tu Chroma qua `embedder.get_texts`).
      3. is_external=False, is_preview=True -> content la
         `Article.noi_dung_preview` (rut gon, tu Neo4j - fallback khi chua
         duoc embed)."""

    article_id: str
    is_external: bool
    content: str | None
    is_preview: bool


def _fetch_missing_article_info(client: Neo4jClient, ids: list[str]) -> dict[str, dict]:
    """Mot loi goi Neo4j DUY NHAT (batched qua `IN $ids`) tra ve
    is_external/noi_dung_preview cho danh sach `ids`. `ids` rong -> tra ve
    dict rong, khong goi Neo4j."""
    if not ids:
        return {}
    rows = client.run(_MISSING_ARTICLE_INFO_QUERY, ids=sorted(ids))
    return {row["article_id"]: row for row in rows}


def _classify_articles(
    client: Neo4jClient, visited_article_ids: set[str], texts: dict[str, str]
) -> dict[str, _ArticleContext]:
    """Phan loai MOI id trong `visited_article_ids` vao 1 trong 3 nhom (xem
    `_ArticleContext` docstring). `texts` la ket qua da co san cua
    `embedder.get_texts(...)` (nhom 2 - full text that). Voi id KHONG co
    trong `texts`, dung MOT lan goi Neo4j batched (`_fetch_missing_article_info`)
    de phan biet nhom 1 (is_external) vs nhom 3 (preview fallback)."""
    missing_ids = [aid for aid in visited_article_ids if aid not in texts]
    missing_info = _fetch_missing_article_info(client, missing_ids)

    contexts: dict[str, _ArticleContext] = {}
    for article_id in visited_article_ids:
        if article_id in texts:
            contexts[article_id] = _ArticleContext(
                article_id=article_id,
                is_external=False,
                content=texts[article_id],
                is_preview=False,
            )
            continue

        info = missing_info.get(article_id)
        if info is None:
            # Khong mong doi voi du lieu that: traversal.py vua tra ve
            # article_id nay TU Neo4j o buoc truoc, nen Article node phai
            # ton tai. Xu ly an toan thay vi crash (Dieu 1 - tha bo sot
            # ngu canh con hon crash ca request) - coi nhu khong co noi
            # dung, log canh bao ro rang de dieu tra sau.
            logger.warning(
                "article_id %r tu traversal nhung khong tim thay Article "
                "node khi query bo sung is_external/noi_dung_preview - "
                "coi nhu khong co noi dung san co.",
                article_id,
            )
            contexts[article_id] = _ArticleContext(
                article_id=article_id,
                is_external=False,
                content=None,
                is_preview=False,
            )
            continue

        if info.get("is_external"):
            contexts[article_id] = _ArticleContext(
                article_id=article_id, is_external=True, content=None, is_preview=False
            )
        else:
            contexts[article_id] = _ArticleContext(
                article_id=article_id,
                is_external=False,
                content=info.get("noi_dung_preview"),
                is_preview=True,
            )

    return contexts


def _build_prompt(question: str, contexts: dict[str, _ArticleContext]) -> str:
    """Dung prompt tieng Viet: chi tra loi tu NGU CANH duoc cung cap, trich
    dan ro Dieu/article_id cho tung phan, va noi ro khi mot Dieu duoc nhac
    toi nhung khong co noi dung day du trong NGU CANH (case 1/3) - khop
    FR-006 va edge case "external reference" cua spec.md/data-model.md."""
    blocks: list[str] = []
    for article_id in sorted(contexts):
        ctx = contexts[article_id]
        if ctx.is_external:
            blocks.append(f"[Điều: {article_id}] {_EXTERNAL_MARKER}")
        elif ctx.is_preview:
            blocks.append(
                f"[Điều: {article_id}] {_PREVIEW_MARKER}\n{ctx.content or ''}"
            )
        else:
            blocks.append(f"[Điều: {article_id}]\n{ctx.content}")

    context_text = "\n\n".join(blocks) if blocks else "(không có ngữ cảnh)"

    return (
        "Bạn là trợ lý hỏi-đáp pháp luật. CHỈ được trả lời dựa trên phần "
        "NGỮ CẢNH dưới đây - không được bịa thêm bất kỳ nội dung pháp luật "
        "nào không có trong đó. Với mỗi ý trong câu trả lời, hãy nêu rõ "
        "đang dựa vào Điều/article_id nào để người đọc có thể kiểm chứng. "
        "Nếu một Điều được nhắc tới nhưng NGỮ CẢNH ghi rõ không có nội dung "
        "(nằm ngoài dữ liệu đã ingest, hoặc chỉ có preview rút gọn), hãy "
        "nói rõ điều đó thay vì suy đoán hay bịa nội dung của Điều đó.\n\n"
        f"CÂU HỎI: {question}\n\n"
        f"NGỮ CẢNH:\n{context_text}\n\n"
        "TRẢ LỜI:"
    )


def _call_ollama(prompt: str) -> str:
    """Goi Ollama's `/api/generate` (khong stream - mot cau tra loi day du
    trong mot response, xem module docstring ve API shape da verify that)
    voi `config.OLLAMA_BASE_URL`/`config.OLLAMA_MODEL` (Dieu 4 - khong
    hard-code). Tra ve chuoi "response" tu JSON tra ve."""
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


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    """POST /chat (spec.md FR-006, User Story 1): tra loi cau hoi phap luat
    tieng Viet, kem citation path (danh sach Article da dung + relationship
    da traverse) de con nguoi kiem chung duoc.

    Khong co entry point nao tim duoc -> tra ve som (HTTP 200, answer giai
    thich) - `traverse`/`_call_ollama`/Neo4jClient KHONG duoc goi (khong co
    gi de traverse/tra loi tu)."""
    entry_points = find_entry_points(request.question)
    if not entry_points:
        return {
            "answer": _NOT_FOUND_ANSWER,
            "citation_path": [],
            "edges_used": [],
        }

    entry_point_ids = {ep.article_id for ep in entry_points}

    with Neo4jClient() as client:
        traversal_result = traverse(client, sorted(entry_point_ids))
        texts = embedder.get_texts(sorted(traversal_result.visited_article_ids))
        contexts = _classify_articles(client, traversal_result.visited_article_ids, texts)

    prompt = _build_prompt(request.question, contexts)
    answer = _call_ollama(prompt)

    citation_path = [
        {
            "article_id": article_id,
            "is_entry_point": article_id in entry_point_ids,
            "is_external": contexts[article_id].is_external,
        }
        for article_id in sorted(contexts)
    ]
    edges_used = [
        {
            "from_article_id": edge.from_article_id,
            "to_id": edge.to_id,
            "relationship_type": edge.relationship_type,
        }
        for edge in traversal_result.edges
    ]

    return {
        "answer": answer,
        "citation_path": citation_path,
        "edges_used": edges_used,
    }
