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

task-2f: corpus that xac nhan MOI file la DUY NHAT mot Dieu (khong phai
mot van ban nhieu Dieu nhu structure_parser.py's parse_document() gia
dinh ban dau) - module nay goi `parse_article_chunk()` thay vi
`parse_document()`, tach doc_id/so_dieu tu TEN FILE (xem
`parse_filename_doc_prefix_and_so_dieu()`).
"""
from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path

from app import config
from app.extraction.reference_extractor import extract_references
from app.extraction.slugify import slugify_doc_name
from app.extraction.structure_parser import (
    Article,
    ParsedDocument,
    parse_article_chunk,
)
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


# Ten file that (khong duoi): "{doc_prefix}_{so_dieu}.md" (task-2f-brief.md
# - corpus that xac nhan MOI file la DUY NHAT mot Dieu, doc_prefix la phan
# nhom cac file thuoc CUNG mot van ban cha). ".+" tham lam nen luon khop
# voi cum "_<so>" CUOI CUNG cua ten file, dung ke ca khi doc_prefix chinh no
# cung chua dau "_" (vd "01_2020_tt-btp_7" -> prefix "01_2020_tt-btp", so
# "7", KHONG bi cat nham o dau "_" dau tien).
_FILENAME_STEM_RE = re.compile(r"^(.+)_(\d+)$")


def parse_filename_doc_prefix_and_so_dieu(file_path: Path) -> tuple[str, int]:
    """Tach `(doc_prefix, filename_so_dieu)` tu TEN FILE (khong duoi) cua
    `file_path`, vd "01_2020_tt-btp_7.md" -> ("01_2020_tt-btp", 7).

    Neu ten file KHONG dung dinh dang mong doi "{prefix}_{digits}.md" ->
    raise ValueError ro rang, neu ten file (mention ro file nao) - KHONG
    im lang bo qua file nay (cung nguyen tac "crash lon tieng thay vi lam
    sai trong im lang" nhu BatchSizeMismatchError, xem docstring do)."""
    stem = file_path.stem
    match = _FILENAME_STEM_RE.match(stem)
    if not match:
        raise ValueError(
            "Ten file khong dung dinh dang mong doi '{doc_prefix}_{so_dieu}"
            f".md': {file_path} - khong the tach doc_prefix/so_dieu tu "
            f"stem={stem!r}."
        )
    doc_prefix = match.group(1)
    filename_so_dieu = int(match.group(2))
    return doc_prefix, filename_so_dieu


def _parse_file(file_path: Path) -> tuple[str, ParsedDocument]:
    """Doc + parse MOT file (= MOT Dieu, xem task-2f-brief.md) thanh
    `(text_tho, ParsedDocument)`.

    Ham DUNG CHUNG (T009e) giua `_ingest_one_file` (can ParsedDocument day
    du de upsert) VA pre-flight collision scan `_detect_and_dedupe_collisions`
    (can article_id + text tho de gom nhom/so sanh noi dung) - Dieu 1
    constitution: CHI mot noi tinh doc_id/so_dieu/article_id cho moi file,
    khong duplicate logic nay giua 2 noi goi (xem task-2g-brief.md)."""
    text = file_path.read_text(encoding="utf-8")
    doc_prefix, filename_so_dieu = parse_filename_doc_prefix_and_so_dieu(file_path)
    # slugify_doc_name (T006/T007, dung chung) thay vi doc_prefix tho - dam
    # bao doc_id dong dang dinh dang voi phan con lai cua he thong (vd
    # reference_extractor.py resolve trich dan qua cung ham nay).
    doc_id = slugify_doc_name(doc_prefix)
    parsed = parse_article_chunk(text, doc_id=doc_id, fallback_so_dieu=filename_so_dieu)
    return text, parsed


def _ingest_one_file(client: Neo4jClient, file_path: Path, batch_index: int) -> None:
    """Doc + parse + upsert MOT file (= MOT Dieu, xem task-2f-brief.md), roi
    extract + upsert cac trich dan REFERENCES cua Dieu do."""
    _text, parsed = _parse_file(file_path)

    batch_id = f"batch-{batch_index:04d}"
    upsert_document(client, parsed, batch_id=batch_id)

    for article in _all_articles(parsed):
        references = extract_references(
            article.full_text, current_doc_slug=parsed.doc_id
        )
        upsert_references(client, article.article_id, references)


class ArticleIdCollisionError(RuntimeError):
    """Raise khi 2+ file trong `data_dir` tinh ra CUNG article_id nhung noi
    dung THUC SU khac nhau (research.md ADR-003).

    Boi canh: corpus that (Zalo AI Challenge) chua cac ban ghi trung lap do
    2 cach viet ten file khac nhau chi lech 1 diem chuan hoa Unicode (vd
    dau tieng Viet bi/khong bi `slugify_doc_name` strip) - 2 filename khac
    nhau vo tinh tinh ra CUNG article_id. Neu noi dung 2 file GIONG HET
    nhau, day la ban sao that cua corpus nguon - an toan tu dong dedup (giu
    1 ban, xem `_detect_and_dedupe_collisions`). Nhung neu noi dung KHAC
    nhau, upsert.py (MERGE-based) se AM THAM ghi de ban truoc bang ban sau
    ma khong co canh bao nao - mat that 1 Dieu luat, vi pham truc tiep
    Dieu 1/Dieu 7 constitution ("khong duoc am tham lam sai khi gap mo
    ho" - du lieu domain phap luat, sai lang le co hau qua that).

    Theo ADR-003 (Option C): KHONG tu dong doan chon ban nao dung - day la
    quyet dinh CHI con nguoi moi lam duoc (xem lich su file, doi chieu
    nguon goc). Ham nay chi phat hien va TU CHOI chay tiep (crash lon
    tieng), giong nguyen tac da dung cho `BatchSizeMismatchError` o tren."""


def _detect_and_dedupe_collisions(files: list[Path]) -> list[Path]:
    """Pre-flight scan (T009e, ADR-003): tinh article_id cho MOI file trong
    `files` (qua `_parse_file` - tai dung dung logic da co, khong duplicate),
    gom nhom theo article_id trung nhau, roi xu ly tung nhom >= 2 file:

    - Noi dung (text tho, TOAN BO file - khong chi dong tieu de) giong het
      nhau giua TAT CA file trong nhom -> day la ban sao that cua corpus
      nguon, an toan: chi giu file DAU TIEN theo thu tu `files` (cung thu tu
      sort on dinh ma phan con lai cua pipeline da dua vao), log INFO liet
      ke cac file bi bo qua. KHONG phai loi.
    - Bat ky 2 file nao trong nhom co noi dung KHAC nhau -> nguy hiem that
      (xem ArticleIdCollisionError) - raise NGAY, liet ke article_id VA
      TOAN BO ten file xung dot trong nhom, KHONG tiep tuc quet/ingest gi
      them (dung ca vong lap batch truoc khi bat dau, dung nguyen tac da
      dung cho BatchSizeMismatchError).

    Tra ve danh sach file da dedup (thu tu nhu `files` goc, tru cac file bi
    bo qua vi trung noi dung) - day la danh sach THUC SU duoc dua vao batch
    loop/ingest, file bi drop khong bao gio duoc doc/parse/upsert lai lan
    nua trong `_ingest_one_file`."""
    article_id_to_files: dict[str, list[Path]] = {}
    file_contents: dict[Path, str] = {}

    for file_path in files:
        text, parsed = _parse_file(file_path)
        file_contents[file_path] = text
        article_id = parsed.articles[0].article_id
        article_id_to_files.setdefault(article_id, []).append(file_path)

    dropped: set[Path] = set()
    for article_id, group_files in article_id_to_files.items():
        if len(group_files) < 2:
            continue

        first_file = group_files[0]
        first_text = file_contents[first_file]
        conflicting = [
            f for f in group_files[1:] if file_contents[f] != first_text
        ]

        if conflicting:
            all_filenames = ", ".join(str(f) for f in group_files)
            message = (
                f"article_id trung nhau giua nhieu file NHUNG NOI DUNG KHAC "
                f"NHAU (khong an toan tu dong dedup) - article_id={article_id!r}, "
                f"cac file xung dot: {all_filenames}. Day la truong hop mo ho "
                "nguy hiem (research.md ADR-003) - KHONG tu dong doan chon "
                "ban nao dung, dung toan bo ingest truoc khi batch loop bat "
                "dau. Hay kiem tra thu cong noi dung cac file tren (thuong "
                "la 1 ban loi crawl/OCR, hoac 2 van ban khac nhau vo tinh "
                "trung article_id) roi chay lai."
            )
            logger.error(message)
            raise ArticleIdCollisionError(message)

        duplicates = group_files[1:]
        dropped.update(duplicates)
        logger.info(
            "phat hien %d file cung article_id=%s, noi dung giong het nhau "
            "(ban sao that cua corpus nguon, xem ADR-003) - giu file dau "
            "tien %s, bo qua (khong ingest): %s",
            len(group_files),
            article_id,
            first_file.name,
            ", ".join(f.name for f in duplicates),
        )

    return [f for f in files if f not in dropped]


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
        # T009e/ADR-003: quet trung article_id TRUOC khi doc checkpoint/bat
        # dau batch loop - dam bao neu phat hien xung dot noi dung khac nhau
        # thi KHONG file nao (kho khong chi phan con lai) duoc ingest duoi
        # gia dinh sai (xem ArticleIdCollisionError).
        files = _detect_and_dedupe_collisions(files)
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
