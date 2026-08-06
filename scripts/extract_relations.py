"""extract_relations.py (T013): CLI mot lan de trich AMENDS/SUPERSEDES/
CONFLICTS_WITH (data-model.md) tu toan bo corpus da ingest va ghi vao
Neo4j - phan orchestration goi `app/extraction/relation_llm.py` (candidate
narrowing + LLM confirmation da xong).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): CLI parsing +
dieu phoi qua toan bo corpus (doc file -> candidate narrowing -> LLM
confirm -> ghi Neo4j) - KHONG chua logic regex/LLM (goi
`app.extraction.relation_llm`, tai dung CHINH XAC), khong chua logic doc
file/dedup (goi `app.ingest`'s `discover_documents`/
`detect_and_dedupe_collisions`/`parse_file` - dung CUNG logic da dung khi
ingest that vao Neo4j, Dieu 1, giong `scripts/extract_terms.py`), khong
chua Cypher (goi `app.graph_store.upsert`).

CACH DUNG:
    python -m scripts.extract_relations DATA_DIR [--limit N] [--batch-size N]

Vi du:
    python -m scripts.extract_relations data/raw
    python -m scripts.extract_relations data/raw --limit 500 --batch-size 200

=== Vi sao 1-pass (khac scripts/extract_terms.py's 2-pass) ===
Khong nhu DEFINES/USES_TERM (thuat ngu dinh nghia o van ban NAY, dung lai
o van ban KHAC - can biet TOAN BO dinh nghia truoc khi tinh usage), moi
candidate AMENDS/SUPERSEDES/CONFLICTS_WITH o day CHI phu thuoc vao noi
dung CUA CHINH Article dang xet (candidate narrowing + LLM deu chi doc
mot full_text duy nhat, khong can biet gi ve cac Article khac) - 1-pass
tuan tu qua tung file la du, khong co thu tu-phu-thuoc nao can giai quyet.

=== Chi phi LLM: candidate narrowing quyet dinh quy mo, khong phai so
Article ===
Phan lon Article se KHONG co candidate nao (khong co ca trigger phrase LAN
trich dan ro ten van ban trong CUNG mot cau - xem relation_llm.py module
docstring) -> `classify_candidate` (goi Ollama, cham) CHI duoc goi cho
candidate that su, khong phai cho toan bo 60k+ Article - day la ly do
candidate narrowing ton tai (giam chi phi LLM, data-model.md).

=== Khong can checkpoint/resume (giong extract_terms.py) ===
Neu bi ngat giua chung, chay lai TOAN BO lenh la an toan (upsert_relations
dung MERGE, idempotent) - LLM se duoc goi lai cho cac candidate DA xu ly
truoc do (lang phi thoi gian nhung KHONG sai du lieu). Neu quy mo candidate
that su lon toi muc can savepoint, day la cai tien co the lam sau (chua
can thiet o P1 - xem TIEN_DO.md).
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.extraction.relation_llm import classify_candidate, find_relation_candidates
from app.graph_store.neo4j_client import Neo4jClient
from app.graph_store.upsert import upsert_relations
from app.ingest import detect_and_dedupe_collisions, discover_documents, parse_file

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 200

_RELATION_TYPES = ("AMENDS", "SUPERSEDES", "CONFLICTS_WITH")


def _chunk(items: list, size: int) -> list[list]:
    """Chia `items` thanh cac list con toi da `size` phan tu - dung chung
    quy uoc voi scripts/extract_terms.py (Dieu 1, khong duplicate logic
    chia batch)."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_extract_relations(
    data_dir: str | Path,
    *,
    limit: int | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    client: Neo4jClient | None = None,
) -> None:
    """Vong lap orchestration chinh - tach rieng khoi `main()`/argparse de
    test truc tiep duoc, cung pattern voi
    `scripts.extract_terms.run_extract_terms`.

    `client`: injectable cho test (mock Neo4jClient) - mac dinh tao
    Neo4jClient() khi khong truyen (duong di CLI thuc te)."""
    owns_client = client is None
    client = client if client is not None else Neo4jClient()

    try:
        files = discover_documents(data_dir, limit=limit)
        # Tai dung CHINH XAC pre-flight dedup cua ingest that (T009e/ADR-003)
        # - dam bao tap file duoc trich quan he o day KHOP HET voi tap file
        # DA THUC SU duoc ingest vao Neo4j.
        files = detect_and_dedupe_collisions(files)

        relation_rows: dict[str, list[dict]] = {t: [] for t in _RELATION_TYPES}
        candidate_count = 0
        confirmed_count = 0

        for file_path in files:
            _text, parsed = parse_file(file_path)
            article = parsed.articles[0]

            candidates = find_relation_candidates(article.full_text, parsed.doc_id)
            candidate_count += len(candidates)

            for candidate in candidates:
                relation = classify_candidate(article.article_id, candidate)
                if relation is None:
                    continue
                confirmed_count += 1
                relation_rows[relation.relationship_type].append(
                    {
                        "source_article_id": article.article_id,
                        "target_article_id": relation.target_article_id,
                        "confidence": relation.confidence,
                        "ly_do": relation.ly_do,
                    }
                )

        logger.info(
            "candidate narrowing: %d candidate, %d duoc LLM xac nhan",
            candidate_count,
            confirmed_count,
        )

        for relationship_type in _RELATION_TYPES:
            rows = relation_rows[relationship_type]
            for batch in _chunk(rows, batch_size):
                upsert_relations(client, relationship_type, batch)
            if rows:
                logger.info(
                    "da ghi %d %s vao Neo4j", len(rows), relationship_type
                )
    finally:
        if owns_client:
            client.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Trich AMENDS/SUPERSEDES/CONFLICTS_WITH (candidate narrowing + "
            "LLM confirmation qua Ollama) tu corpus da ingest va ghi vao "
            "Neo4j."
        )
    )
    parser.add_argument(
        "data_dir",
        type=str,
        help="Thu muc chua cac file .md da fetch (vd data/raw).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Chi xet N file dau tien (sau khi sap xep theo ten) - test/debug.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=f"So row moi lan ghi Neo4j (mac dinh {_DEFAULT_BATCH_SIZE}).",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = build_arg_parser()
    args = parser.parse_args()
    run_extract_relations(args.data_dir, limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
