"""eval_bhxh_retrieval.py (P2-T3): do recall@k / MRR cua retrieval tren bo
eval BHXH (`data/eval/bhxh_eval_set.json`, gold XAC MINH tu tieu de Dieu).

Chay CHINH luong retrieval cua chat() (find_entry_points -> traverse -> rank
-> [rerank]) nhung KHONG goi LLM - chi do truy xuat. So sanh 2 cau hinh:
KHONG rerank vs CO rerank, de thay dong gop cua cross-encoder.

hit@k = it nhat 1 gold_article_id nam trong top-k truy xuat.
MRR   = trung binh 1/(thu hang gold dau tien); 0 neu khong co gold nao.

CACH DUNG:
    python -m scripts.eval_bhxh_retrieval
(can Neo4j + Chroma da co corpus BHXH.)
"""
from __future__ import annotations

import json
from pathlib import Path

from app import config
from app.graph_store.neo4j_client import Neo4jClient
from app.retrieval import embedder
from app.retrieval.entry_point import find_entry_points
from app.retrieval.ranking import rank_article_ids
from app.retrieval.reranker import rerank_ids
from app.retrieval.traversal import traverse

EVAL_PATH = Path("data/eval/bhxh_eval_set.json")
TOP_K = 10  # do recall@5 va @10


def _retrieve(question: str, client: Neo4jClient, rerank: bool) -> list[str]:
    """Tra ve danh sach article_id da xep hang (toi da TOP_K)."""
    fetch_k = config.RERANK_FETCH_K if rerank else TOP_K
    entry_points = find_entry_points(question, top_k=fetch_k)
    if not entry_points:
        return []
    ranked_entry_ids = [ep.article_id for ep in entry_points]
    traversal_result = traverse(client, sorted(set(ranked_entry_ids)))
    pool = rank_article_ids(ranked_entry_ids, traversal_result, limit=fetch_k)
    if rerank:
        texts = embedder.get_texts(pool)
        return rerank_ids(question, pool, texts, TOP_K)
    return pool[:TOP_K]


def _score(ranked: list[str], gold: list[str]) -> tuple[bool, bool, float]:
    """(hit@5, hit@10, reciprocal_rank)."""
    gold_set = set(gold)
    rank = next((i + 1 for i, aid in enumerate(ranked) if aid in gold_set), None)
    hit5 = rank is not None and rank <= 5
    hit10 = rank is not None and rank <= 10
    rr = 1.0 / rank if rank else 0.0
    return hit5, hit10, rr


def _run(questions: list[dict], client: Neo4jClient, rerank: bool) -> dict:
    n = len(questions)
    h5 = h10 = 0
    mrr = 0.0
    misses: list[str] = []
    for q in questions:
        ranked = _retrieve(q["question"], client, rerank)
        hit5, hit10, rr = _score(ranked, q["gold_article_ids"])
        h5 += hit5
        h10 += hit10
        mrr += rr
        if not hit10:
            misses.append(f"{q['question']}  (gold {q['gold_article_ids']})")
    return {
        "recall@5": h5 / n,
        "recall@10": h10 / n,
        "mrr": mrr / n,
        "misses": misses,
    }


def main() -> None:
    data = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    questions = data["questions"]

    with Neo4jClient() as client:
        # Kiem tra gold ton tai (KHONG doan) - canh bao neu id gold khong co node.
        all_gold = {g for q in questions for g in q["gold_article_ids"]}
        existing = {
            r["id"]
            for r in client.run(
                "MATCH (a:Article) WHERE a.article_id IN $ids RETURN a.article_id AS id",
                ids=list(all_gold),
            )
        }
        missing_gold = all_gold - existing
        if missing_gold:
            print(f"[CANH BAO] gold khong ton tai trong graph: {sorted(missing_gold)}")

        print(f"Bo eval: {len(questions)} cau hoi, {len(all_gold)} gold Dieu.\n")
        for label, rerank in [("KHONG rerank", False), ("CO rerank", True)]:
            res = _run(questions, client, rerank)
            print(f"=== {label} ===")
            print(f"  recall@5  = {res['recall@5']:.1%}")
            print(f"  recall@10 = {res['recall@10']:.1%}")
            print(f"  MRR       = {res['mrr']:.3f}")
            if res["misses"]:
                print(f"  Miss (khong co gold trong top-10): {len(res['misses'])}")
                for m in res["misses"]:
                    print(f"    - {m}")
            print()


if __name__ == "__main__":
    main()
