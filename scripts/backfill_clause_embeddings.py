"""backfill_clause_embeddings.py (T028 buoc 2/2): them vector cap KHOAN vao
Chroma cho cac Dieu DAI, de `find_entry_points` co gi ma gop.

=== VI SAO (do that 2026-08-08, khong phai gia dinh) ===
Mot vector cho ca Dieu lam LOANG tin hieu: Spearman(similarity, do dai Dieu)
= -0.312, va tren 793 cau Zalo gold nhom Dieu DAI nhat fail 37% so voi 15% o
nhom NGAN nhat (2.5x te hon).

Chan doan quyet dinh: trong 127 cau bi ZERO entry point o nguong 0.65, dap an
dung co median rank = 3 va 78% nam o rank 1-5 - retrieval DA TIM DUNG, chi
thieu median 0.045 similarity. Day la bai toan DO LON similarity chu khong
phai xep hang, nen tang top_k / tuning HNSW / them reranker deu vo ich.

PILOT (274 cau gold co dap an la Dieu dai co >=2 Khoan): dung similarity cao
nhat cua tung Khoan cuu duoc 39/81 cau dang fail (48%) -> uoc tinh +4.9 diem %
Recall@4 MA KHONG DOI `SIMILARITY_THRESHOLD` (Khang chot giu 0.65).

=== CHI EMBED KHOAN CUA DIEU DAI CO >=2 KHOAN ===
KHONG embed het 165,393 Khoan:
  - Dieu NGAN da co similarity tot (nhom ngan nhat chi fail 15%) - them vector
    Khoan cho chung ton GPU ma khong giai quyet van de gi.
  - Dieu chi co 1 Khoan: vector Khoan gan nhu trung voi vector ca Dieu.
Do that tu data/raw: 6,278 Dieu dai, trong do 5,494 co >=2 Khoan = 36,585
Khoan (~55 phut GPU), thay vi 165,393 (~4 gio).

CON LAI 784 Dieu dai KHONG co Khoan (parser khong tach duoc) - can chunk theo
CUA SO, KHONG thuoc pham vi script nay (ghi ro de khong ai tuong da phu het).

=== VECTOR DIEU VAN GIU NGUYEN ===
Script nay CHI THEM id `{article_id}#khoan-{n}`, khong xoa/sua vector
`{article_id}` da co. `find_entry_points` gop bang `max` nen vector Dieu lam
SAN - chi co the THEM, khong the MAT (pilot: neu CHI dung Khoan thi 10/193 cau
dang pass se tut xuong duoi nguong).

Resumable: bo qua id da co trong Chroma, chay lai lenh y nguyen se tiep tuc
(cung nguyen tac voi `backfill_embeddings.py` bo qua Article da co chroma_id).

CACH DUNG:
    python -m scripts.backfill_clause_embeddings data/raw
    python -m scripts.backfill_clause_embeddings data/raw --limit 100
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from app import config
from app.ingest import detect_and_dedupe_collisions, discover_documents, parse_file
from app.retrieval.embedder import embed_texts, get_chroma_collection
from scripts.backfill_embeddings import _group_into_length_aware_batches

logger = logging.getLogger(__name__)

# Nguong "Dieu dai" = 2,700 ky tu. Lay theo p90 do that o DOT 5 (p90 = 2,751)
# va dung lam moc phan nhom trong phan tich tu phan vi o DOT 16. KHONG doi
# thanh so tuy y ma khong doc lai so lieu (co test ghim).
LONG_ARTICLE_CHARS = 2700

_CLAUSE_ID_SEPARATOR = "#"


def clause_vector_id(article_id: str, so_khoan: int) -> str:
    """Id cua vector cap Khoan trong Chroma.

    PHAI khop dinh dang ma `app.retrieval.entry_point._article_id_of` tach
    nguoc lai - neu lech thi vector Khoan khong bao gio gop duoc ve Dieu cha
    va toan bo cong suc embed thanh vo nghia (co test round-trip)."""
    return f"{article_id}{_CLAUSE_ID_SEPARATOR}khoan-{so_khoan}"


def select_clauses_to_embed(articles, already_embedded: set[str]):
    """[(vector_id, noi_dung_khoan)] can embed, tu danh sach Article da parse.

    Bo qua (xem module docstring de biet ly do tung dieu kien):
      - Dieu ngan (`full_text` <= LONG_ARTICLE_CHARS),
      - Dieu co < 2 Khoan,
      - Khoan co noi dung rong/chi khoang trang,
      - vector_id DA co trong Chroma (resume).
    """
    rows: list[tuple[str, str]] = []
    for article in articles:
        if len(article.full_text) <= LONG_ARTICLE_CHARS:
            continue
        if len(article.clauses) < 2:
            continue
        # Dung VI TRI (1-based) chu KHONG dung `so_khoan`: bug co san do duoc
        # (2026-08-08) cho thay parser sinh `so_khoan` TRUNG trong 335/60,568
        # Article (Dieu sua doi trich lai nguyen van Dieu khac -> danh so lap
        # lai: [1, 1, 2, 2, 17, 18, 3, ...]). Dung so_khoan lam id se raise
        # DuplicateIDError o Chroma (da xay ra that o smoke test dau tien).
        # Vi tri thi duy nhat theo cau truc. Voi Dieu binh thuong (khong trung)
        # vi tri == so_khoan nen id doc van tu nhien.
        for position, clause in enumerate(article.clauses, start=1):
            if not clause.noi_dung.strip():
                continue
            vid = clause_vector_id(article.article_id, position)
            if vid in already_embedded:
                continue
            rows.append((vid, clause.noi_dung))
    return rows


def _fetch_existing_clause_ids(collection) -> set[str]:
    """Cac id Khoan DA co trong Chroma (de resume).

    `collection.get(include=[])` chi lay id, khong keo embedding ve (do that o
    T027: 60,679 id trong ~0.9s)."""
    all_ids = collection.get(include=[])["ids"]
    return {i for i in all_ids if _CLAUSE_ID_SEPARATOR in i}


def run_backfill(
    data_dir: str | Path,
    *,
    limit: int | None = None,
    batch_size: int | None = None,
    collection=None,
) -> None:
    """Vong lap batch chinh - tach khoi `main()` de test/goi truc tiep duoc,
    cung pattern voi `backfill_embeddings.run_backfill`."""
    effective_batch_size = (
        batch_size if batch_size is not None else config.EMBED_BATCH_SIZE
    )
    if collection is None:
        collection = get_chroma_collection()

    files = discover_documents(data_dir, limit=limit)
    # Tai dung CHINH XAC pre-flight dedup cua ingest that (T009e/ADR-003) - dam
    # bao tap file o day KHOP tap file da ingest, khong lech do 2 noi tinh dedup
    # khac nhau.
    files = detect_and_dedupe_collisions(files)
    logger.info("%d file sau dedup", len(files))

    already = _fetch_existing_clause_ids(collection)
    logger.info("da co %d vector Khoan trong Chroma (se bo qua)", len(already))

    articles = []
    for file_path in files:
        _text, parsed = parse_file(file_path)
        articles.append(parsed.articles[0])

    pending = select_clauses_to_embed(articles, already_embedded=already)
    if not pending:
        logger.info("khong co Khoan nao can embed - da xong tu truoc")
        return

    # Sap xep theo do dai TRUOC khi chia batch + chia batch theo tang do dai:
    # tai dung `_group_into_length_aware_batches` cua backfill_embeddings.py
    # (Dieu 1 - khong viet lai). Ly do goc: mot Khoan dai loi vao batch buoc CA
    # batch pad theo do dai do (do that o DOT 5: cham 7.7 lan). Khoan dai nhat
    # do duoc la 20,217 ky tu nen van can co che nay.
    pending.sort(key=lambda row: len(row[1]))
    # Tuple dang (id, text, metadata) - `_group_into_length_aware_batches` doc
    # do dai qua `item[1]`, nen thu tu nay bat buoc.
    batches = _group_into_length_aware_batches(
        [(vid, text, {}) for vid, text in pending],
        max_batch_size=effective_batch_size,
    )
    logger.info(
        "%d Khoan can embed, chia thanh %d batch", len(pending), len(batches)
    )

    durations: list[float] = []
    for i, batch in enumerate(batches, 1):
        t0 = time.monotonic()
        ids = [row[0] for row in batch]
        texts = [row[1] for row in batch]
        vectors = embed_texts(texts)
        collection.upsert(ids=ids, embeddings=vectors, documents=texts)
        durations.append(time.monotonic() - t0)
        remaining = len(batches) - i
        eta = sum(durations) / len(durations) * remaining
        logger.info(
            "batch %d/%d hoan tat (%.1fs, con %d batch, ETA ~%.0fs)",
            i, len(batches), durations[-1], remaining, eta,
        )

    logger.info("XONG: da embed %d vector Khoan", len(pending))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Them vector cap Khoan cho cac Dieu DAI (>2,700 ky tu, >=2 Khoan) "
            "vao Chroma. KHONG xoa/sua vector cap Dieu da co."
        )
    )
    parser.add_argument("data_dir", type=str, help="Thu muc .md (vd data/raw).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Chi xet N file dau - test/debug.")
    parser.add_argument("--batch-size", type=int, default=None,
                        help="Ghi de config.EMBED_BATCH_SIZE cho lan chay nay.")
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = build_arg_parser().parse_args()
    run_backfill(args.data_dir, limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
