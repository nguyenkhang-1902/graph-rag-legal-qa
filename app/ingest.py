"""Entry point CLI cho ingest pipeline (batch + savepoint, 67k van ban).

T009d (Phase 2: Foundational) - noi cac module da xong (structure_parser.py
T008, reference_extractor.py T007, upsert.py T009, Neo4jClient T005,
IngestCheckpointStore T009b) thanh mot vong lap batch co the resume sau
crash (research.md ADR-002, spec.md FR-008/User Story 4, quickstart.md
Nhom 1 buoc 3).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): CLI parsing +
dieu phoi vong lap batch (doc file -> parse -> upsert -> checkpoint) -
khong chua logic parse/extract/upsert (goi vao cac module da co), khong
chua logic checkpoint (goi IngestCheckpointStore).

CACH DUNG:
    python -m app.ingest DATA_DIR [--limit N] [--batch-size N]

Vi du:
    python -m app.ingest data/raw/legal_real
    python -m app.ingest data/raw/legal_real --limit 20 --batch-size 5

`--incremental` (T020, Phase 5) CHUA duoc implement o day - out of scope
task nay (xem task-2e-brief.md).
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

from app import config
from app.extraction.reference_extractor import extract_references
from app.extraction.structure_parser import Article, ParsedDocument, parse_document
from app.graph_store.neo4j_client import Neo4jClient
from app.graph_store.upsert import upsert_document, upsert_references
from app.ingest_checkpoint.state_store import IngestCheckpointStore

logger = logging.getLogger(__name__)

# Duong dan mac dinh cho savepoint - da nam trong .gitignore (`.state/`).
DEFAULT_STATE_FILE = Path(".state") / "ingest_checkpoint.json"


class BatchSizeMismatchError(RuntimeError):
    """Raise khi resume voi `batch_size` KHAC voi luc checkpoint duoc ghi.

    Review finding sau T009d: checkpoint chi ghi "last_completed_batch=N"
    (mot INDEX) - N chi con dung neu file duoc chia batch theo CUNG mot
    batch_size nhu luc ghi checkpoint do. Doi batch_size (vd sua
    --batch-size hoac INGEST_BATCH_SIZE giua hai lan chay) lam "batch N+1"
    theo cach chia MOI tro thanh mot doan file HOAN TOAN KHAC voi doan file
    that su con thieu - im lang bo sot hang nghin van ban ma khong loi,
    khong canh bao (xem finding chi tiet).

    Theo constitution Dieu 1 (KISS - "tha crash con hon lam sai trong im
    lang") va brief T009c/task-2e-brief.md: KHONG tu dong hoa giai/di chuyen
    batch_size - chi phat hien va TU CHOI chay, bat operator tu quyet dinh
    (vd xoa checkpoint de bat dau lai tu dau neu co y doi batch_size).
    """


def _check_batch_size_matches_checkpoint(
    state_store: IngestCheckpointStore, effective_batch_size: int
) -> None:
    """Neu day la lan resume (da co checkpoint) VA checkpoint co ghi lai
    batch_size tung dung, so sanh voi `effective_batch_size` cua lan chay
    nay - khac nhau thi raise BatchSizeMismatchError (tu choi chay tiep),
    KHONG tu dong xu ly/di chuyen (xem docstring BatchSizeMismatchError).

    Checkpoint cu (ghi truoc khi truong `batch_size` ton tai) se khong co
    truong nay -> get_last_batch_size() tra ve None -> KHONG the so sanh,
    bo qua kiem tra nay (khong the phat hien mismatch tu du lieu khong co,
    va chan resume trong truong hop nay se pha vo moi checkpoint cu mot
    cach khong can thiet).
    """
    recorded_batch_size = state_store.get_last_batch_size()
    if recorded_batch_size is None:
        return
    if recorded_batch_size != effective_batch_size:
        message = (
            "batch_size KHONG khop voi checkpoint: checkpoint duoc ghi voi "
            f"batch_size={recorded_batch_size}, nhung lan chay nay dang "
            f"dung batch_size={effective_batch_size}. Resume voi batch_size "
            "khac se tinh sai boundary cua batch (batch N+1 se tro toi mot "
            "doan file HOAN TOAN KHAC), co the im lang bo sot hang nghin "
            "van ban. TU CHOI chay tiep - hay dung lai batch_size cu "
            f"({recorded_batch_size}), hoac neu that su muon doi batch_size "
            "thi xoa file checkpoint de bat dau ingest lai tu dau."
        )
        logger.error(message)
        raise BatchSizeMismatchError(message)

# `scripts/fetch_zalo_legal_corpus.py` ghi mot README.md (giay phep/nguon)
# vao CUNG thu muc voi cac file .md van ban that - khong phai mot van ban
# luat, phai loai khoi danh sach discover (khong lam vong lap crash, chi
# se tao mot Document node rac vo nghia neu khong loai).
_NON_DOCUMENT_FILENAMES = frozenset({"README.md"})


def discover_documents(data_dir: str | Path, limit: int | None = None) -> list[Path]:
    """Liet ke tat ca `DATA_DIR/*.md` (dung format `fetch_zalo_legal_corpus.py`
    ghi ra), sap xep theo TEN FILE de dam bao thu tu on dinh, tai lap duoc
    giua cac lan chay (bat buoc de logic resume/batch dung dan - batch phai
    la CUNG mot tap file qua cac lan restart, xem brief).

    `limit`: sau khi sap xep, chi giu N file DAU TIEN. None = khong gioi
    han (toan bo file trong thu muc).
    """
    data_dir = Path(data_dir)
    files = sorted(
        (p for p in data_dir.glob("*.md") if p.name not in _NON_DOCUMENT_FILENAMES),
        key=lambda p: p.name,
    )
    if limit is not None:
        files = files[:limit]
    return files


def make_batches(files: list[Path], batch_size: int) -> list[list[Path]]:
    """Chia danh sach file (da sap xep/gioi han) thanh cac batch lien tiep,
    kich thuoc `batch_size` (batch cuoi co the ngan hon). Batch index = vi
    tri trong danh sach tra ve (0, 1, 2, ...)."""
    return [files[i : i + batch_size] for i in range(0, len(files), batch_size)]


def _all_articles(parsed: ParsedDocument) -> list[Article]:
    """Tat ca Article cua mot ParsedDocument - ca Dieu truc tiep duoi
    Document LAN Dieu nam trong tung Chuong (khong duoc bo sot nhom nao,
    xem brief buoc 6a)."""
    articles: list[Article] = list(parsed.articles)
    for chapter in parsed.chapters:
        articles.extend(chapter.articles)
    return articles


def _ingest_one_file(client: Neo4jClient, file_path: Path, batch_index: int) -> None:
    """Doc + parse + upsert MOT van ban, roi extract + upsert cac trich dan
    REFERENCES cua tung Dieu (ca Dieu truc tiep lan Dieu trong Chuong)."""
    text = file_path.read_text(encoding="utf-8")
    # Ten file (khong duoi) lam fallback_doc_id: on dinh, duy nhat cho moi
    # file (scripts/fetch_zalo_legal_corpus.py dam bao qua slugify_id rieng
    # cua no) - dong logic hong doc_id="" khi van ban thieu dong "# {title}"
    # (xem structure_parser.py fix, task-2e-brief.md).
    fallback_doc_id = file_path.stem
    parsed = parse_document(text, fallback_doc_id=fallback_doc_id)

    batch_id = f"batch-{batch_index:04d}"
    upsert_document(client, parsed, batch_id=batch_id)

    for article in _all_articles(parsed):
        references = extract_references(
            article.full_text, current_doc_slug=parsed.doc_id
        )
        upsert_references(client, article.article_id, references)


def run_ingest(
    data_dir: str | Path,
    *,
    limit: int | None = None,
    batch_size: int | None = None,
    client: Neo4jClient | None = None,
    state_store: IngestCheckpointStore | None = None,
) -> None:
    """Vong lap batch chinh (T009d) - tach rieng khoi `main()`/argparse de
    test truc tiep duoc (goi ham nay, khong can qua sys.argv/subprocess).

    `client`/`state_store`: injectable cho test (mock Neo4jClient, temp-path
    IngestCheckpointStore) - mac dinh tao Neo4jClient()/IngestCheckpointStore
    tro vao DEFAULT_STATE_FILE khi khong truyen (duong di CLI thuc te).

    Neu mot van ban BAT KY trong mot batch raise exception: log ro file/
    batch nao loi, roi RE-RAISE (crash tien trinh) - KHONG bo qua van ban
    loi roi van danh dau batch hoan tat (se lam mat dau vet loi, nguoc lai
    voi chinh muc dich cua savepoint - xem brief buoc 7). Batch dang xu ly
    luc crash SE KHONG duoc mark_batch_done, nen lan chay lai se lam lai tu
    dau batch do (an toan vi upsert.py dung MERGE idempotent).

    Khi day la mot lan RESUME (checkpoint da co san): neu `batch_size` cua
    lan chay nay khac voi `batch_size` da ghi trong checkpoint, raise
    BatchSizeMismatchError va TU CHOI chay tiep - resume voi batch_size
    khac se tinh sai boundary batch, co the im lang bo sot van ban (xem
    review finding + BatchSizeMismatchError). Day la "phat hien va tu
    choi", KHONG tu dong hoa giai batch_size.
    """
    owns_client = client is None
    client = client if client is not None else Neo4jClient()
    if state_store is None:
        state_store = IngestCheckpointStore(DEFAULT_STATE_FILE)
    effective_batch_size = (
        batch_size if batch_size is not None else config.INGEST_BATCH_SIZE
    )

    try:
        # Idempotent (IF NOT EXISTS) - an toan goi lai moi lan chay/resume.
        client.ensure_constraints_and_indexes()

        files = discover_documents(data_dir, limit=limit)
        batches = make_batches(files, effective_batch_size)
        total_batches = len(batches)

        last_completed = state_store.get_last_completed_batch()
        start_batch = 0 if last_completed is None else last_completed + 1

        if last_completed is not None:
            _check_batch_size_matches_checkpoint(state_store, effective_batch_size)

        if start_batch > 0:
            logger.info(
                "resume tu batch %d/%d (da hoan tat batch 0..%d truoc do)",
                start_batch,
                total_batches,
                last_completed,
            )
        else:
            logger.info(
                "bat dau ingest tu batch 0/%d (khong co checkpoint truoc do)",
                total_batches,
            )

        batch_durations: list[float] = []
        for batch_index in range(start_batch, total_batches):
            batch_start = time.monotonic()
            for file_path in batches[batch_index]:
                try:
                    _ingest_one_file(client, file_path, batch_index)
                except Exception:
                    logger.exception(
                        "loi khi ingest file %s (batch %d) - dung lai, "
                        "KHONG danh dau batch nay hoan tat (se resume lai "
                        "tu batch %d o lan chay sau)",
                        file_path,
                        batch_index,
                        batch_index,
                    )
                    raise

            state_store.mark_batch_done(batch_index, effective_batch_size)
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
        description="Batch ingest van ban luat (.md) vao Neo4j, co savepoint/resume."
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
        help="Chi ingest N file dau tien (sau khi sap xep theo ten) - test/debug.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Ghi de config.INGEST_BATCH_SIZE cho lan chay nay.",
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = build_arg_parser()
    args = parser.parse_args()
    run_ingest(args.data_dir, limit=args.limit, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
