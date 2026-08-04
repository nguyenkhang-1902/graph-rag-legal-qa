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


def find_entry_points(query: str, top_k: int = 5) -> list[EntryPointResult]:
    """Tim toi da `top_k` Article lam diem bat dau graph traversal cho `query`.

    1. Embed `query` qua `embed_texts` (mot phan tu - CHI embed cau hoi,
       khong embed lai toan bo corpus).
    2. Query Chroma collection (`get_chroma_collection().query(...)`) de lay
       `top_k` ket qua gan nhat theo cosine distance.
    3. Chuyen distance -> similarity bang `similarity = 1 - distance` (da
       verify tren chromadb==1.5.9 that, xem module docstring o tren).
    4. Loc chi giu ket qua co `similarity >= config.SIMILARITY_THRESHOLD`.
    5. Sap xep tuong minh theo similarity giam dan (khong dua vao thu tu
       ngam dinh cua Chroma, du no thuong da dung thu tu nay).

    Chroma collection rong hoac khong co ket qua nao vuot threshold -> tra
    ve list rong (khong exception, khong None).
    """
    query_embedding = embed_texts([query])[0]

    collection = get_chroma_collection()
    raw = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    result_ids = (raw.get("ids") or [[]])[0]
    result_distances = (raw.get("distances") or [[]])[0]

    results = [
        EntryPointResult(article_id=article_id, similarity=1.0 - distance)
        for article_id, distance in zip(result_ids, result_distances)
        if (1.0 - distance) >= config.SIMILARITY_THRESHOLD
    ]

    results.sort(key=lambda r: r.similarity, reverse=True)
    return results
