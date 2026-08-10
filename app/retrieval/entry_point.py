"""entry_point.py (T010): tim Article node(s) lam diem bat dau cho graph
traversal, tu mot cau hoi ngon ngu tu nhien cua nguoi dung.

Trach nhiem duy nhat cua module nay (constitution Dieu 5): embed cau hoi
(tai su dung `app.retrieval.embedder.embed_texts` - KHONG tao model instance
moi, xem T009f/so bay 12e), query Chroma collection (tai su dung
`app.retrieval.embedder.get_chroma_collection` - KHONG tao Chroma client
moi) de tim candidate `article_id`, loc theo `config.SIMILARITY_THRESHOLD`.
Khong chua logic traversal (do la `retrieval/traversal.py`, T011, chua lam),
khong goi LLM, khong serving HTTP.

=== Chroma distance -> similarity conversion (verified, khong doan) ===
Collection duoc tao voi `hnsw:space="cosine"` (embedder.py). Da verify TRUC
TIEP tren chromadb==1.5.9 that (smoke test thu cong, xem
tests/retrieval/test_entry_point.py::test_real_model_and_chroma... va
task-3c-report.md) rang `collection.query(...)` tra ve "distances" theo
dung cong thuc `distance = 1 - cosine_similarity`:
  - hai vector giong het nhau -> distance = 0.0 -> similarity = 1.0
  - hai vector truc giao (orthogonal) -> distance = 1.0 -> similarity = 0.0
  - hai vector doi huong (opposite) -> distance = 2.0 -> similarity = -1.0
Vay `similarity = 1 - distance` la cong thuc DUNG cho chromadb 1.5.9 voi
hnsw:space="cosine" - khong phai gia dinh, da verify bang code that.
"""
from __future__ import annotations

from dataclasses import dataclass

from app import config
from app.retrieval.embedder import embed_texts, get_chroma_collection


@dataclass
class EntryPointResult:
    article_id: str
    similarity: float  # cosine similarity, cao hon = giong hon (1.0 = giong het)


# === T028: vector cap KHOAN ben canh vector cap DIEU ===
# Collection chua CA HAI loai id:
#   `{article_id}`             -> vector ca Dieu (co san tu T009f)
#   `{article_id}#khoan-{n}`   -> vector tung Khoan (scripts/backfill_clause_
#                                 embeddings.py)
#
# VI SAO (do that 2026-08-08, khong phai gia dinh): mot vector cho ca Dieu lam
# LOANG tin hieu - Spearman(similarity, do dai Dieu) = -0.312, nhom Dieu DAI
# nhat trong 793 cau gold fail 37% so voi 15% o nhom NGAN nhat. Pilot tren 274
# cau: dung similarity cao nhat cua tung Khoan cuu duoc 39/81 cau dang fail
# (48%), uoc tinh +4.9 diem % Recall@4 ma KHONG doi SIMILARITY_THRESHOLD.
#
# GIU CA HAI loai vector co chu dich: gop bang `max` nen vector Dieu lam SAN -
# chi co the THEM, khong the MAT. (Pilot do duoc: neu CHI dung Khoan thi 10/193
# cau dang pass se tut xuong duoi nguong.)
_CLAUSE_ID_SEPARATOR = "#"

# Fetch RONG hon top_k truoc khi gop: nhieu Khoan cua CUNG mot Dieu co the
# chiem nhieu slot, neu chi fetch top_k thi mot Dieu dai se day cac Dieu khac
# ra khoi ket qua -> GIAM recall. He so 6 chon theo do that: p90 so Khoan/Dieu
# trong nhom Dieu dai la ~7, nen top_k=5 * 6 = 30 vector du de it nhat 5 Dieu
# PHAN BIET cung xuat hien trong hau het truong hop.
_FETCH_MULTIPLIER = 6


def _article_id_of(vector_id: str) -> str:
    """`{article_id}#khoan-{n}` -> `{article_id}`; id Dieu tra ve nguyen.

    Graph/traversal lam viec tren `article_id` - id Khoan tho ("...#khoan-3")
    KHONG ton tai trong Neo4j, tra ve no se lam traversal khong khop gi."""
    return vector_id.split(_CLAUSE_ID_SEPARATOR, 1)[0]


def find_entry_points(query: str, top_k: int = 5) -> list[EntryPointResult]:
    """Tim toi da `top_k` Article lam diem bat dau graph traversal cho `query`.

    1. Embed `query` qua `embed_texts` (mot phan tu - CHI embed cau hoi,
       khong embed lai toan bo corpus).
    2. Query Chroma lay `top_k * _FETCH_MULTIPLIER` VECTOR gan nhat - rong hon
       `top_k` co chu dich, vi collection chua ca vector cap Dieu LAN cap Khoan
       (xem ghi chu tren `_CLAUSE_ID_SEPARATOR`): nhieu Khoan cua cung mot Dieu
       co the chiem nhieu slot.
    3. Chuyen distance -> similarity bang `similarity = 1 - distance` (da
       verify tren chromadb==1.5.9 that, xem module docstring o tren).
    4. GOP ve `article_id` (id Khoan `...#khoan-N` -> Dieu cha), giu similarity
       CAO NHAT trong so cac vector cua cung mot Dieu.
    5. Loc `similarity >= config.SIMILARITY_THRESHOLD` - ap SAU khi gop, nen
       mot Khoan duoi nguong khong lam loai ca Dieu neu Khoan khac vuot nguong.
    6. Sap xep theo similarity giam dan roi cat ve `top_k` DIEU PHAN BIET
       (khong phai top_k vector - do la con so caller ky vong).

    Chroma collection rong hoac khong co ket qua nao vuot threshold -> tra
    ve list rong (khong exception, khong None).

    TUONG THICH NGUOC: khi collection CHUA co vector cap Khoan nao (truoc khi
    chay `scripts/backfill_clause_embeddings.py`), buoc gop la no-op va ham nay
    tra ve dung ket qua nhu ban truoc T028 - da verify bang cach chay lai T017
    truoc khi embed Khoan.
    """
    query_embedding = embed_texts([query])[0]

    collection = get_chroma_collection()
    raw = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k * _FETCH_MULTIPLIER,
    )

    result_ids = (raw.get("ids") or [[]])[0]
    result_distances = (raw.get("distances") or [[]])[0]

    # Gop ve article_id, giu similarity CAO NHAT (vector Dieu hoac Khoan nao
    # khop nhat). Ap nguong SAU khi gop - mot Khoan duoi nguong khong duoc lam
    # loai ca Dieu neu mot Khoan khac cua no vuot nguong.
    best_by_article: dict[str, float] = {}
    for vector_id, distance in zip(result_ids, result_distances):
        article_id = _article_id_of(vector_id)
        similarity = 1.0 - distance
        if similarity > best_by_article.get(article_id, float("-inf")):
            best_by_article[article_id] = similarity

    results = [
        EntryPointResult(article_id=article_id, similarity=similarity)
        for article_id, similarity in best_by_article.items()
        if similarity >= config.SIMILARITY_THRESHOLD
    ]

    results.sort(key=lambda r: r.similarity, reverse=True)
    # Cat ve top_k DIEU PHAN BIET (khong phai top_k vector) - day moi la con
    # so caller ky vong (`/chat` va eval deu truyen top_k theo nghia "so Dieu").
    return results[:top_k]
