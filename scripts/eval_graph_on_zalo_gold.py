"""eval_graph_on_zalo_gold.py (T018): chay GRAPH RAG tren DUNG 793 cau Zalo
gold set - manh con thieu de co mot bang so sanh thuc su hop le.

=== VI SAO CAN SCRIPT NAY ===
Truoc do KHONG co so lieu nao cho phep so sanh Graph RAG voi baseline:
  - `eval_graph_recall.py` (T017): Graph RAG tren **32 cau multi-hop** tu soan,
    metric strict/lenient recall (moi cau NHIEU dap an).
  - `eval_hybrid_reranker_baseline.py` (T018): baseline tren **793 cau Zalo
    gold**, metric Recall@4 (moi cau MOT dap an).
Dat 90.6% canh 82.1% la so sanh HAI BO CAU HOI KHAC NHAU tren HAI METRIC KHAC
NHAU - dung loi phuong phap da phat hien o DOT 13 (va suyt tai pham o DOT 15
voi bug tron 50/793 cau). Script nay chay Graph RAG tren DUNG bo cau hoi cua
baseline, voi DUNG metric cua baseline.

=== HAI CON SO, VA VI SAO PHAI BAO CA HAI ===
Danh sach xep hang cua Graph RAG (xem `eval_graph_recall._ranked_retrieved_
article_ids`) la: entry point (dense, toi da `top_k`) TRUOC, roi Article tim
them qua traversal REFERENCES SAU.

He qua toan hoc quan trong, PHAI noi ro thay vi de nguoi doc tu phat hien:
voi `top_k=5` va `k=4`, **4 slot dau LUON la entry point** - traversal KHONG
BAO GIO chen duoc vao top-4. Nen `recall_at_k` cua Graph RAG **theo cau truc**
khong the cao hon dense-only (chi co the THAP hon, do SIMILARITY_THRESHOLD loc
bo mot so entry point). Bao mot minh con so nay se khien Graph RAG trong nhu
"khong hon gi dense", va bao mot minh con so mo rong se khien no trong nhu
"hon han" - ca hai deu gay nham lan.

Vi vay bao CA HAI:
  1. `recall_at_k`      - cat danh sach con k. SO SANH TRUC TIEP duoc voi
                          baseline Dense-only / Hybrid / Hybrid+Reranker.
  2. `recall_expanded`  - dap an nam BAT KY DAU trong tap mo rong. Cho thay
                          traversal them duoc gi, nhung KHONG so sanh duoc voi
                          Recall@4 (tap ung vien lon hon nhieu).
  3. `mrr`              - tinh tren danh sach DAY DU (khong cat), de phan biet
                          "tim thay o vi tri 5" voi "khong tim thay".

Tai dung (Dieu 1 - khong duplicate logic da co):
  - `eval_graph_recall._ranked_retrieved_article_ids`: DUNG duong retrieval
    production ma `/chat` dung (find_entry_points + traverse).
  - `bench_bm25_backends.load_gold`: doc gold set + doi expected_source_file
    sang article_id (da kiem: 793/793 map duoc).

CACH DUNG:
    python -m scripts.eval_graph_on_zalo_gold
    python -m scripts.eval_graph_on_zalo_gold --limit-queries 50 -k 4
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# k=4 de khop truc tiep bang "Recall@4" cua baseline va cua project truoc.
DEFAULT_K = 4

RESULT_PATH = (
    Path(__file__).parent / "quality_fixtures" / "graph_on_zalo_gold_result.json"
)


def evaluate_ranked_lists(
    ranked_lists: list[list[str]], expected: list[str], k: int
) -> dict:
    """Ba metric tu cac danh sach da xep hang (xem module docstring).

    `expected[i]` la article_id dap an DUY NHAT cho cau hoi i (dinh dang gold
    set Zalo - khac bo 32 cau multi-hop co nhieu dap an).

    Lech do dai = loi lap trinh (ghep sai cau hoi voi dap an) -> raise, khong
    am tham tinh sai. Tra ve `total` de moi ket qua LUON mang theo so cau hoi -
    bai hoc tu bug DOT 15 (92.0% do tren 50 cau bi in canh so do tren 793 cau).
    """
    if len(ranked_lists) != len(expected):
        raise ValueError(
            f"so cau hoi khong khop: ranked={len(ranked_lists)} nhung "
            f"expected={len(expected)}"
        )
    total = len(ranked_lists)
    if total == 0:
        return {
            "recall_at_k": 0.0,
            "recall_expanded": 0.0,
            "mrr": 0.0,
            "hits_at_k": 0,
            "hits_expanded": 0,
            "total": 0,
            "k": k,
        }

    hits_k = 0
    hits_expanded = 0
    rr_total = 0.0
    for ranked, want in zip(ranked_lists, expected):
        if want in ranked[:k]:
            hits_k += 1
        if want in ranked:
            hits_expanded += 1
            rr_total += 1.0 / (ranked.index(want) + 1)
    return {
        "recall_at_k": hits_k / total,
        "recall_expanded": hits_expanded / total,
        "mrr": rr_total / total,
        "hits_at_k": hits_k,
        "hits_expanded": hits_expanded,
        "total": total,
        "k": k,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Chay Graph RAG tren 793 cau Zalo gold set (CUNG bo cau hoi + CUNG "
            "metric voi baseline Hybrid+Reranker) - de bang so sanh T018 thuc "
            "su hop le."
        )
    )
    parser.add_argument(
        "--limit-queries",
        type=int,
        default=None,
        help="Chi do N cau dau (mac dinh: TOAN BO gold set) - chi dung de debug.",
    )
    parser.add_argument("-k", type=int, default=DEFAULT_K,
                        help=f"top-k cho recall_at_k (mac dinh {DEFAULT_K}).")
    parser.add_argument("--top-k-entry", type=int, default=None,
                        help="So entry point (mac dinh: giong /chat that).")
    parser.add_argument("--max-hop", type=int, default=None,
                        help="So hop toi da (mac dinh: config.MAX_HOP).")
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = build_arg_parser().parse_args()

    from app.graph_store.neo4j_client import Neo4jClient
    from scripts.bench_bm25_backends import load_gold
    from scripts.eval_graph_recall import (
        _DEFAULT_TOP_K,
        _ranked_retrieved_article_ids,
    )

    top_k_entry = args.top_k_entry if args.top_k_entry is not None else _DEFAULT_TOP_K

    questions, expected = load_gold(limit=args.limit_queries)
    logger.info(
        "%d cau hoi Zalo gold | k=%d | top_k entry=%d | max_hop=%s",
        len(questions), args.k, top_k_entry, args.max_hop or "config",
    )

    client = Neo4jClient()
    ranked_lists: list[list[str]] = []
    t0 = time.monotonic()
    try:
        for i, question in enumerate(questions, 1):
            ranked_lists.append(
                _ranked_retrieved_article_ids(
                    question, client=client, top_k=top_k_entry, max_hop=args.max_hop
                )
            )
            if i % 100 == 0 or i == len(questions):
                logger.info("  %d/%d cau", i, len(questions))
    finally:
        client.close()
    elapsed = time.monotonic() - t0

    result = evaluate_ranked_lists(ranked_lists, expected, args.k)
    result["elapsed_s"] = elapsed
    result["top_k_entry"] = top_k_entry
    avg_len = sum(len(r) for r in ranked_lists) / max(len(ranked_lists), 1)
    result["avg_ranked_len"] = avg_len

    print()
    print(f"=== Graph RAG tren {result['total']} cau Zalo gold (k={args.k}) ===")
    print(f"Recall@{args.k} (cat top-{args.k}, SO SANH DUOC voi baseline): "
          f"{result['recall_at_k']:.1%} ({result['hits_at_k']}/{result['total']})")
    print(f"Recall mo rong (bat ky dau trong tap entry+traversal): "
          f"{result['recall_expanded']:.1%} ({result['hits_expanded']}/{result['total']})")
    print(f"MRR (tren danh sach day du): {result['mrr']:.3f}")
    print(f"Do dai danh sach trung binh: {avg_len:.1f} article "
          f"({top_k_entry} entry point + traversal)")
    print(f"Thoi gian: {elapsed:.0f}s")
    print()
    print(
        f"LUU Y BAT BUOC khi doc: voi top_k entry={top_k_entry} va k={args.k}, "
        f"{min(top_k_entry, args.k)} slot dau LUON la entry point (dense) - "
        "traversal khong the chen vao top-k. Nen Recall@k cua Graph RAG THEO CAU "
        "TRUC khong the cao hon dense-only. Con so cho thay traversal them duoc "
        "gi la 'Recall mo rong', nhung no KHONG so sanh duoc voi Recall@4 (tap "
        "ung vien lon hon nhieu)."
    )

    RESULT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("da ghi ket qua vao %s", RESULT_PATH)


if __name__ == "__main__":
    main()
