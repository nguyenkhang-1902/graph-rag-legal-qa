"""backfill_embeddings.py (T009f): CLI mot lan de dien Chroma embeddings cho
cac Article DA ingest vao Neo4j (real ingest da chay xong: 60,679 Article
node, `chroma_id` con NULL - data-model.md thiet ke co chu dich KHONG luu
full_text trong Neo4j, Chroma la nguon su that duy nhat cho full_text +
embedding, xem task-3a-brief.md).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): CLI parsing +
dieu phoi vong lap batch (doc file -> parse -> embed+upsert Chroma -> ghi
chroma_id vao Neo4j) - KHONG chua logic doc file/dedup/parse (goi
`app.ingest`'s `discover_documents`/`detect_and_dedupe_collisions`/
`parse_file`, tai dung CHINH XAC logic da dung khi ingest that vao Neo4j -
Dieu 1, tranh drift giua tap file da ingest va tap file duoc embed), khong
chua logic "noi chuyen voi model/Chroma" (goi `app.retrieval.embedder`).

CACH DUNG:
    python -m scripts.backfill_embeddings DATA_DIR [--limit N] [--batch-size N]

Vi du:
    python -m scripts.backfill_embeddings data/raw/legal_real
    python -m scripts.backfill_embeddings data/raw/legal_real --limit 20 --batch-size 5

Resumable: moi lan chay, script chi query Neo4j MOT LAN de lay toan bo tap
article_id DA CO chroma_id (mot cau Cypher, khong phai N round-trip), loc
bo cac file da co khoi tap can embed - giet script (Ctrl+C) roi chay lai
CUNG lenh se tu bo qua cac Article da xong, khong can checkpoint file rieng
(khac voi app/ingest.py's IngestCheckpointStore - o day khong can vi trang
thai "da xong hay chua" da nam san trong chinh Neo4j qua chroma_id, khong
can luu them o noi khac)."""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from app import config
from app.graph_store.neo4j_client import Neo4jClient
from app.ingest import detect_and_dedupe_collisions, discover_documents, parse_file
from app.retrieval import embedder

logger = logging.getLogger(__name__)


def _fetch_already_embedded_article_ids(client: Neo4jClient) -> set[str]:
    """Mot truy van Neo4j DUY NHAT (khong phai N round-trip cho N file) de
    lay toan bo article_id DA co chroma_id - dung de loc tap file can embed
    (xem module docstring - day la co che resume cua script nay)."""
    records = client.run(
        "MATCH (a:Article) WHERE a.chroma_id IS NOT NULL "
        "RETURN a.article_id AS article_id"
    )
    return {record["article_id"] for record in records}


def _update_chroma_ids(client: Neo4jClient, article_ids: list[str]) -> None:
    """Ghi `chroma_id` cho ca mot batch article_id trong MOT cau Cypher
    (UNWIND), khong phai N loi goi `client.run()` rieng le - hieu qua o quy
    mo 60k+ Article (xem brief). `chroma_id` dung CHINH `article_id` lam gia
    tri (data-model.md - khong can mot scheme id thu hai)."""
    client.run(
        "UNWIND $ids AS aid "
        "MATCH (a:Article {article_id: aid}) "
        "SET a.chroma_id = aid",
        ids=article_ids,
    )


def run_backfill(
    data_dir: str | Path,
    *,
    limit: int | None = None,
    batch_size: int | None = None,
    client: Neo4jClient | None = None,
) -> None:
    """Vong lap batch chinh - tach rieng khoi `main()`/argparse de test truc
    tiep duoc (goi ham nay, khong can qua sys.argv/subprocess), cung pattern
    voi `app.ingest.run_ingest`.

    `client`: injectable cho test (mock Neo4jClient) - mac dinh tao
    Neo4jClient() khi khong truyen (duong di CLI thuc te)."""
    owns_client = client is None
    client = client if client is not None else Neo4jClient()
    effective_batch_size = (
        batch_size if batch_size is not None else config.EMBED_BATCH_SIZE
    )

    try:
        files = discover_documents(data_dir, limit=limit)
        # Tai dung CHINH XAC pre-flight dedup cua ingest that (T009e/ADR-003)
        # - dam bao tap file duoc embed o day KHOP HET voi tap file DA THUC
        # SU duoc ingest vao Neo4j (khong bi lech do 2 noi tinh dedup khac
        # nhau).
        files = detect_and_dedupe_collisions(files)

        already_embedded = _fetch_already_embedded_article_ids(client)
        logger.info(
            "tim thay %d Article da co chroma_id trong Neo4j (se bo qua)",
            len(already_embedded),
        )

        # Parse MOI file (article_id can duoc parse tu noi dung, khong chi
        # tu ten file - xem parse_article_chunk: so_dieu uu tien lay tu
        # dong tieu de "Dieu N." trong noi dung, chi fallback ve so trich
        # tu ten file khi dong tieu de khong khop) - ket qua parse duoc GIU
        # LAI, tai su dung cho buoc embed ben duoi (khong parse file 2 lan).
        pending: list[tuple[str, str, dict]] = []  # (article_id, full_text, metadata)
        for file_path in files:
            _text, parsed = parse_file(file_path)
            article = parsed.articles[0]
            if article.article_id in already_embedded:
                continue
            pending.append(
                (
                    article.article_id,
                    article.full_text,
                    {"doc_id": parsed.doc_id, "so_dieu": article.so_dieu},
                )
            )

        batches = [
            pending[i : i + effective_batch_size]
            for i in range(0, len(pending), effective_batch_size)
        ]
        total_batches = len(batches)
        logger.info(
            "bat dau backfill embedding: %d file kham pha, %d can embed "
            "(sau khi loc da co chroma_id), chia thanh %d batch",
            len(files),
            len(pending),
            total_batches,
        )

        batch_durations: list[float] = []
        for batch_index, batch in enumerate(batches):
            batch_start = time.monotonic()

            ids = [item[0] for item in batch]
            texts = [item[1] for item in batch]
            metadatas = [item[2] for item in batch]

            embedder.upsert_embeddings(ids=ids, texts=texts, metadatas=metadatas)
            _update_chroma_ids(client, ids)

            duration = time.monotonic() - batch_start
            batch_durations.append(duration)
            remaining = total_batches - (batch_index + 1)
            avg_duration = sum(batch_durations) / len(batch_durations)
            eta_seconds = avg_duration * remaining
            logger.info(
                "batch %d/%d hoan tat (%.1fs, con lai %d batch, ETA ~%.0fs)",
                batch_index + 1,
                total_batches,
                duration,
                remaining,
                eta_seconds,
            )
    finally:
        if owns_client:
            client.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Chroma embeddings cho cac Article da ingest vao Neo4j "
            "(dien chroma_id con NULL)."
        )
    )
    parser.add_argument(
        "data_dir",
        type=str,
        help="Thu muc chua cac file .md da fetch (vd data/raw/legal_real).",
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
        default=None,
        help="Ghi de config.EMBED_BATCH_SIZE cho lan chay nay.",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = build_arg_parser()
    args = parser.parse_args()
    run_backfill(args.data_dir, limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
