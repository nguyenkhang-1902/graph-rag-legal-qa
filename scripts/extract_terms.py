"""extract_terms.py (T012 hoan thien): CLI mot lan de trich DEFINES/
USES_TERM (data-model.md) tu toan bo corpus that da ingest va ghi vao
Neo4j - phan orchestration con thieu cua T012 sau khi
`app/extraction/term_extractor.py` (module extraction thuan, khong dung
Neo4j) da xong.

Trach nhiem duy nhat cua module nay (constitution Dieu 5): CLI parsing +
dieu phoi 2-pass qua toan bo corpus (doc file -> trich dinh nghia -> ghi
Term+DEFINES -> trich USES_TERM -> ghi USES_TERM) - KHONG chua logic
regex/extraction (goi `app.extraction.term_extractor`, tai dung
CHINH XAC), khong chua logic doc file/dedup (goi `app.ingest`'s
`discover_documents`/`detect_and_dedupe_collisions`/`parse_file`, tai
dung dung logic da dung khi ingest that vao Neo4j, Dieu 1), khong chua
Cypher (goi `app.graph_store.upsert`).

CACH DUNG:
    python -m scripts.extract_terms DATA_DIR [--limit N] [--batch-size N]

Vi du:
    python -m scripts.extract_terms data/raw
    python -m scripts.extract_terms data/raw --limit 500 --batch-size 200

=== Vi sao 2-pass (khong phai 1-pass duyet tuan tu) ===
Mot thuat ngu co the duoc DINH NGHIA o van ban A nhung duoc DUNG LAI o van
ban B - bat ke B duoc duyet TRUOC hay SAU A theo thu tu file tren dia.
Neu chi 1-pass (tich luy known_terms dan trong luc duyet), Article nao
duoc duyet TRUOC khi thuat ngu no dung duoc dinh nghia se BI BO SOT
USES_TERM (false negative am tham). Pass 1 thu thap TOAN BO dinh nghia
truoc, Pass 2 moi tinh USES_TERM cho MOI Article voi day du known_terms.

Article TU dinh nghia mot thuat ngu KHONG duoc tinh la "dung lai" chinh no
(loai truong hop nay khoi USES_TERM o Pass 2) - tranh ghi ca DEFINES lan
USES_TERM du thua cho cung mot cap (article_id, term_id).

=== Khong can checkpoint/resume (khac backfill_embeddings.py) ===
Khong nhu embedding (can GPU/CPU nang, co the chay hang gio), buoc nay
chi la regex tren van ban ngan (trung vi ~900 ky tu/Article) - toan bo
corpus 60k+ Article du kien chay xong trong vai chuc giay den vai phut,
khong can savepoint. Neu bi ngat giua chung, chay lai TOAN BO lenh la an
toan (MERGE-based, idempotent) du co lang phi tinh lai tu dau.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.extraction.term_extractor import (
    ExtractedDefinition,
    extract_definitions_rule_based,
    extract_term_usages_rule_based,
)
from app.graph_store.neo4j_client import Neo4jClient
from app.graph_store.upsert import upsert_definitions, upsert_term_usages
from app.ingest import detect_and_dedupe_collisions, discover_documents, parse_file

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 500


def _chunk(items: list, size: int) -> list[list]:
    """Chia `items` thanh cac list con toi da `size` phan tu - dung chung
    cho ca definition_rows va usage_rows (Dieu 1, khong duplicate logic
    chia batch)."""
    return [items[i : i + size] for i in range(0, len(items), size)]


def run_extract_terms(
    data_dir: str | Path,
    *,
    limit: int | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    client: Neo4jClient | None = None,
) -> None:
    """Vong lap orchestration chinh - tach rieng khoi `main()`/argparse de
    test truc tiep duoc (goi ham nay, khong can qua sys.argv/subprocess),
    cung pattern voi `app.ingest.run_ingest`/`scripts.backfill_embeddings.
    run_backfill`.

    `client`: injectable cho test (mock Neo4jClient) - mac dinh tao
    Neo4jClient() khi khong truyen (duong di CLI thuc te)."""
    owns_client = client is None
    client = client if client is not None else Neo4jClient()

    try:
        files = discover_documents(data_dir, limit=limit)
        # Tai dung CHINH XAC pre-flight dedup cua ingest that (T009e/ADR-003)
        # - dam bao tap file duoc trich terms o day KHOP HET voi tap file
        # DA THUC SU duoc ingest vao Neo4j.
        files = detect_and_dedupe_collisions(files)

        articles: list[tuple[str, str]] = []  # (article_id, full_text)
        for file_path in files:
            _text, parsed = parse_file(file_path)
            article = parsed.articles[0]
            articles.append((article.article_id, article.full_text))

        logger.info(
            "da doc %d Article that tu %d file kham pha", len(articles), len(files)
        )

        # Pass 1: thu thap TOAN BO dinh nghia trong corpus (xem module
        # docstring - ly do 2-pass).
        definitions_by_article: dict[str, list[ExtractedDefinition]] = {}
        known_terms: dict[str, str] = {}  # term_id -> ten_thuat_ngu (global)
        for article_id, full_text in articles:
            defs = extract_definitions_rule_based(full_text)
            if defs:
                definitions_by_article[article_id] = defs
                for d in defs:
                    known_terms.setdefault(d.term_id, d.ten_thuat_ngu)

        logger.info(
            "pass 1 xong: %d Article co dinh nghia, %d thuat ngu duy nhat",
            len(definitions_by_article),
            len(known_terms),
        )

        # Ghi Term + DEFINES TRUOC USES_TERM (USES_TERM can Term da ton
        # tai - xem upsert_term_usages docstring, upsert.py).
        definition_rows = [
            {
                "article_id": article_id,
                "term_id": d.term_id,
                "ten_thuat_ngu": d.ten_thuat_ngu,
                "dinh_nghia": d.dinh_nghia,
            }
            for article_id, defs in definitions_by_article.items()
            for d in defs
        ]
        for batch in _chunk(definition_rows, batch_size):
            upsert_definitions(client, batch)
        logger.info("da ghi %d DEFINES (+ Term) vao Neo4j", len(definition_rows))

        # Pass 2: USES_TERM cho MOI Article voi day du known_terms - loai
        # tru thuat ngu CHINH Article do dinh nghia (xem module docstring).
        usage_rows: list[dict] = []
        for article_id, full_text in articles:
            defined_term_ids = {
                d.term_id for d in definitions_by_article.get(article_id, [])
            }
            for usage in extract_term_usages_rule_based(full_text, known_terms):
                if usage.term_id in defined_term_ids:
                    continue
                usage_rows.append({"article_id": article_id, "term_id": usage.term_id})

        for batch in _chunk(usage_rows, batch_size):
            upsert_term_usages(client, batch)
        logger.info("da ghi %d USES_TERM vao Neo4j", len(usage_rows))
    finally:
        if owns_client:
            client.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Trich DEFINES/USES_TERM (rule-based) tu corpus da ingest va "
            "ghi vao Neo4j."
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
    run_extract_terms(args.data_dir, limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
