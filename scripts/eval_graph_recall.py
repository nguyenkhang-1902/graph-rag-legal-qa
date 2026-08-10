"""eval_graph_recall.py (T017): do Recall@k/MRR THAT tren bo 32 cau hoi
multi-hop that (data/eval/multihop_eval_set.json, T016 - da Khang duyet
2026-08-04, xem CHECKLIST-GRAPHRAG-DUYET.md muc E1), dung DE SO SANH voi
baseline Hybrid+Reranker cua du an truoc (D:\\RAG Chatbot\\scripts\\
eval_zalo_recall.py, spec.md FR-007: "cung phuong phap project truoc").

Trach nhiem duy nhat cua module nay (constitution Dieu 5): dieu phoi eval
(doc bo cau hoi -> goi entry_point+traversal da co -> tinh Recall@k/MRR) -
KHONG chua logic vector search/graph traversal cua chung (goi
`app.retrieval.entry_point.find_entry_points`/`app.retrieval.traversal.
traverse`, tai dung CHINH XAC logic dung boi `/chat` that, T014 - dam bao
so do duoc phan anh dung he thong PRODUCTION, khong phai mot duong di rieng
chi de eval).

=== Khac biet CO CHU DICH so voi eval_zalo_recall.py (ban goc) ===
Ban goc (retrieval vector-only, 1 cau hoi -> 1 "expected_source_file" duy
nhat):
    - retrieved la list DA CO THU TU san tu similarity search.
    - hit/rank = vi tri (1-indexed) dau tien trong retrieved list ma
      source khop expected_source_file. Recall@k = % cau hoi co hit.
      MRR = trung binh 1/rank (0 neu khong hit).

O day (Graph RAG, multi-hop, 1 cau hoi CO THE can NHIEU
expected_article_ids de tra loi DU - xem spec.md SC-001 "trich dan DU cac
dieu luat lien quan"):
    1. "Retrieved list" khong con la mot list co san tu 1 vector search -
       ma la HOP cua {entry point (CO diem similarity, sap xep duoc) +
       Article Graph traversal tim them qua REFERENCES (KHONG co diem so
       rieng, chi co canh)}. `_ranked_retrieved_article_ids` dinh nghia
       RANH GIOI RO RANG cho "thu tu" o day: entry point xep truoc (theo
       similarity giam dan, giong het `find_entry_points`), Article ONLY
       tim them qua traversal xep SAU, theo thu tu LAN DAU xuat hien trong
       `edges` (thu tu tra ve tu Neo4j moi hop - deterministic, KHONG phai
       ngau nhien). Day la MOT quy uoc ro rang, khong phai "dung" duy
       nhat co the - ghi lai theo dung "ghi gia dinh" cua du an.
    2. Vi 1 cau hoi co THE can NHIEU expected_article_ids, dinh nghia 2
       loai Recall song song (khong chi 1 con so nhu ban goc):
       - `strict_recall` (khop SC-001 "trich dan DU"): % cau hoi ma
         TOAN BO expected_article_ids deu duoc tim thay trong retrieved
         list (ALL-OR-NOTHING moi cau hoi).
       - `lenient_recall` (bo sung, cho thay muc do "gan dung" khi khong
         dat strict): ty le article-level = tong so expected_article_id
         tim duoc / tong so expected_article_id yeu cau, GOP tren TOAN
         BO cau hoi (khong phai trung binh cong cua ty le tung cau - 2
         cach tinh nay khac nhau khi cau hoi co so luong expected khac
         nhau, o day dung cach GOP de moi expected_article_id co trong so
         bang nhau, khong phai moi CAU HOI co trong so bang nhau).
    3. MRR: dung rank TOT NHAT (nho nhat) trong so cac expected_article_ids
       tim duoc cho MOI cau hoi (0 neu khong tim duoc cai nao) - day la
       cach mo rong MRR chuan cho truong hop nhieu "relevant doc" moi
       truy van, khop dinh nghia MRR pho bien trong IR literature (khong
       phai tu nghi ra).

CACH DUNG:
    python -m scripts.eval_graph_recall
    python -m scripts.eval_graph_recall --limit 5        # test nhanh
    python -m scripts.eval_graph_recall --top-k 3 --max-hop 1
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from app import config
from app.graph_store.neo4j_client import Neo4jClient
from app.retrieval.entry_point import find_entry_points
from app.retrieval.ranking import rank_article_ids
from app.retrieval.traversal import traverse

logger = logging.getLogger(__name__)

_EVAL_SET_PATH = Path(__file__).parent.parent / "data" / "eval" / "multihop_eval_set.json"

# Mac dinh top_k=5 KHOP CHINH XAC voi `app/serving/api.py`'s `find_entry_
# points(request.question)` (khong truyen top_k -> dung default cua chinh
# ham do) - dam bao so do phan anh dung cau hinh production /chat that,
# khong phai mot gia tri rieng chon cho eval.
_DEFAULT_TOP_K = 5


def _ranked_retrieved_article_ids(
    question: str,
    *,
    client: Neo4jClient,
    top_k: int = _DEFAULT_TOP_K,
    max_hop: int | None = None,
) -> list[str]:
    """Tra ve danh sach article_id DA XEP HANG cho `question` - entry point
    (theo similarity giam dan) truoc, Article tim them qua traversal
    (REFERENCES) sau theo thu tu lan dau xuat hien trong `edges` (xem
    module docstring, muc 1). Canh DEFINES (tro toi Term, khong phai
    Article) bi bo qua o day - khong thuoc pham vi Recall@k/MRR cap do
    Article."""
    entry_points = find_entry_points(question, top_k=top_k)
    entry_ids = [ep.article_id for ep in entry_points]

    traversal_result = traverse(client, entry_ids, max_hop=max_hop)

    # T028: dung CHUNG `app.retrieval.ranking.rank_article_ids` voi
    # `serving/api.py` (Dieu 1). Truoc day day la ban sao THU HAI cua cung
    # logic - de vay thi `/chat` va so lieu eval se dan lech nhau ma khong ai
    # biet. `limit=None`: eval do TOAN BO danh sach (viec cat o
    # config.MAX_CONTEXT_ARTICLES la quyet dinh cua tang serving, khong phai
    # cua phep do).
    return rank_article_ids(entry_ids, traversal_result, limit=None)


def _evaluate_question(
    expected_article_ids: list[str], ranked_article_ids: list[str]
) -> dict:
    """Tinh ket qua cho MOT cau hoi (xem module docstring muc 2-3):
    `all_found` (strict), `found_count`/`expected_count` (cho lenient
    recall gop sau), `reciprocal_rank` (rank TOT NHAT trong so cac
    expected_article_ids tim duoc, 0.0 neu khong tim duoc cai nao)."""
    rank_by_id = {aid: i + 1 for i, aid in enumerate(ranked_article_ids)}

    found_ranks = [
        rank_by_id[aid] for aid in expected_article_ids if aid in rank_by_id
    ]

    return {
        "all_found": len(found_ranks) == len(expected_article_ids),
        "found_count": len(found_ranks),
        "expected_count": len(expected_article_ids),
        "reciprocal_rank": (1.0 / min(found_ranks)) if found_ranks else 0.0,
    }


def run_eval(
    questions: list[dict],
    *,
    client: Neo4jClient,
    top_k: int = _DEFAULT_TOP_K,
    max_hop: int | None = None,
) -> dict:
    """Chay eval tren `questions` (list cac dict tu multihop_eval_set.json,
    moi dict can "question" + "expected_article_ids"), tra ve dict tom tat
    (strict_recall/lenient_recall/mrr/total_questions) - xem module
    docstring."""
    per_question_results = []

    for item in questions:
        ranked = _ranked_retrieved_article_ids(
            item["question"], client=client, top_k=top_k, max_hop=max_hop
        )
        result = _evaluate_question(item["expected_article_ids"], ranked)
        result["id"] = item.get("id")
        per_question_results.append(result)

    total = len(per_question_results)
    strict_hits = sum(1 for r in per_question_results if r["all_found"])
    total_found = sum(r["found_count"] for r in per_question_results)
    total_expected = sum(r["expected_count"] for r in per_question_results)
    total_reciprocal_rank = sum(r["reciprocal_rank"] for r in per_question_results)

    return {
        "total_questions": total,
        "strict_recall": strict_hits / total if total else 0.0,
        "lenient_recall": total_found / total_expected if total_expected else 0.0,
        "mrr": total_reciprocal_rank / total if total else 0.0,
        "per_question": per_question_results,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Do Recall@k/MRR that tren bo 32 cau hoi multi-hop (T017)."
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Chi chay N cau hoi dau tien."
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=_DEFAULT_TOP_K,
        help=f"So entry point moi cau hoi (mac dinh {_DEFAULT_TOP_K}, khop /chat that).",
    )
    parser.add_argument(
        "--max-hop",
        type=int,
        default=None,
        help="So hop traversal toi da (mac dinh config.MAX_HOP).",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = build_arg_parser()
    args = parser.parse_args()

    with open(_EVAL_SET_PATH, encoding="utf-8") as f:
        questions = json.load(f)["questions"]
    if args.limit:
        questions = questions[: args.limit]

    logger.info(
        "dung %d cau hoi tu %s (top_k=%d, max_hop=%s)",
        len(questions),
        _EVAL_SET_PATH,
        args.top_k,
        args.max_hop if args.max_hop is not None else config.MAX_HOP,
    )

    with Neo4jClient() as client:
        summary = run_eval(
            questions, client=client, top_k=args.top_k, max_hop=args.max_hop
        )

    print(f"\n=== Graph RAG — Recall@{args.top_k}/MRR ({summary['total_questions']} cau hoi that) ===")
    print(
        f"Strict recall (SC-001, DU tat ca expected_article_ids): "
        f"{summary['strict_recall']:.1%}"
    )
    print(f"Lenient recall (article-level, gop toan bo): {summary['lenient_recall']:.1%}")
    print(f"MRR: {summary['mrr']:.3f}")

    out_path = Path(__file__).parent / "quality_fixtures" / "graph_recall_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\nDa ghi ket qua vao {out_path}")


if __name__ == "__main__":
    main()
