"""eval_bhxh_ablation.py: do DONG GOP CUA GRAPH (va reranker) vao retrieval.

So sanh 3 cau hinh tren cung bo cau hoi co gold:
  A) dense-only        : chi entry-point (ChromaDB dense), KHONG traversal.
  B) dense + graph      : entry-point + traverse Neo4j (REFERENCES) + rank.
  C) dense + graph + rerank : them cross-encoder rerank (cau hinh production).

Muc dich: tra loi cau hoi cot loi "graph co THUC SU them gia tri khong?"
Tach rieng nhom MULTI-HOP (gold >= 2 Dieu) - noi graph dang le phat huy.

CACH DUNG: python -m scripts.eval_bhxh_ablation
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

EVAL_FILES = ["data/eval/bhxh_eval_set.json", "data/eval/bhxh_qa_set.json"]
TOP_K = 10
FETCH_K = 15


def _load_questions() -> list[dict]:
    out: list[dict] = []
    seen = set()
    for f in EVAL_FILES:
        for q in json.loads(Path(f).read_text(encoding="utf-8"))["questions"]:
            gold = q.get("gold_article_ids") or []
            key = q["question"]
            if gold and key not in seen:
                seen.add(key)
                out.append({"question": key, "gold": gold})
    return out


def _dense(question: str) -> list[str]:
    eps = find_entry_points(question, top_k=FETCH_K)
    return [e.article_id for e in eps][:TOP_K]


def _dense_graph(question: str, client: Neo4jClient) -> list[str]:
    eps = find_entry_points(question, top_k=FETCH_K)
    if not eps:
        return []
    entry_ids = [e.article_id for e in eps]
    tr = traverse(client, sorted(set(entry_ids)))
    return rank_article_ids(entry_ids, tr, limit=TOP_K)


def _dense_graph_rerank(question: str, client: Neo4jClient) -> list[str]:
    eps = find_entry_points(question, top_k=FETCH_K)
    if not eps:
        return []
    entry_ids = [e.article_id for e in eps]
    tr = traverse(client, sorted(set(entry_ids)))
    pool = rank_article_ids(entry_ids, tr, limit=FETCH_K)
    texts = embedder.get_texts(pool)
    return rerank_ids(question, pool, texts, TOP_K)


def _metrics(questions: list[dict], retrieve) -> dict:
    r5 = r10 = 0
    mrr = 0.0
    for q in questions:
        gold = set(q["gold"])
        ranked = retrieve(q["question"])
        rank = next((i + 1 for i, a in enumerate(ranked) if a in gold), None)
        r5 += rank is not None and rank <= 5
        r10 += rank is not None and rank <= 10
        mrr += (1.0 / rank) if rank else 0.0
    n = len(questions)
    return {"recall@5": r5 / n, "recall@10": r10 / n, "mrr": mrr / n, "n": n}


def _print(label: str, m: dict) -> None:
    print(f"  {label:26} recall@5={m['recall@5']:.1%}  recall@10={m['recall@10']:.1%}  MRR={m['mrr']:.3f}  (n={m['n']})")


def main() -> None:
    qs = _load_questions()
    mh = [q for q in qs if len(q["gold"]) >= 2]
    print(f"Bo cau hoi co gold: {len(qs)} cau (trong do {len(mh)} multi-hop >=2 Dieu).\n")

    with Neo4jClient() as client:
        configs = [
            ("A) dense-only", lambda q: _dense(q)),
            ("B) dense+graph", lambda q: _dense_graph(q, client)),
            ("C) dense+graph+rerank", lambda q: _dense_graph_rerank(q, client)),
        ]
        print("=== TAT CA cau hoi ===")
        for name, fn in configs:
            _print(name, _metrics(qs, fn))
        print("\n=== Rieng MULTI-HOP (gold >= 2 Dieu) ===")
        for name, fn in configs:
            _print(name, _metrics(mh, fn))


if __name__ == "__main__":
    main()
