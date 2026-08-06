"""migrate_references.py (T027): dua graph THAT ve dung voi extractor sau
T025 (Document.title/so_hieu/loai_vb) va T026 (resolve trich dan cheo van ban).

=== VI SAO CAN MIGRATION RIENG, KHONG CHI "CHAY LAI INGEST" ===
`app/graph_store/upsert.py` ghi moi thu bang MERGE (idempotent - dieu kien
song con cua batch/savepoint, research.md ADR-002). Tinh chat do co mat trai
o day: canh REFERENCES SAI do extractor CU tao ra KHONG tu bien mat khi chay
lai ingest - MERGE chi them canh moi, khong bao gio xoa canh cu. Ket qua se
la graph chua CA canh dung (moi) LAN canh sai (cu) - te hon truoc khi sua.

Do THAT (dry-run tren toan bo 61,068 file, 2026-08-06):
  - Edge duy nhat: 37,875 (cu, khop chinh xac so trong Neo4j) -> 38,300 (moi).
  - 2,594 edge cross-doc DUNG duoc thu hoi; 2,912 edge self-reference SAI bi
    loai (bao gom ca self-loop vo nghia "X_dieu-13 -> X_dieu-13").
  - Ban chat la DOI CHO, khong phai chi them: "Dieu 10 Nghi dinh so
    16/2010/ND-CP" truoc day resolve thanh Dieu 10 cua CHINH van ban dang doc.

=== KHONG MAT DU LIEU KHONG THE TAI TAO ===
Toan bo REFERENCES/placeholder deu suy ra duoc tu `data/raw/*.md` bang code -
day la lieu do dan xuat, khong phai du lieu nguon. Embedding (Chroma) va
`chroma_id` KHONG bi ham nay dong den. DEFINES/USES_TERM/Term (T012) va
AMENDS/SUPERSEDES/CONFLICTS_WITH (T013) cung KHONG bi dong den.

=== BON BUOC, THU TU BAT BUOC ===
  1. Xoa TOAN BO canh REFERENCES (theo lo - xem DELETE_REFERENCES_QUERY).
  2. Xoa cac Article external placeholder da thanh MO COI (khong con quan he
     nao). CHI mo coi: placeholder dang la dich cua AMENDS/SUPERSEDES/
     CONFLICTS_WITH (T013) phai duoc GIU.
  3. Reset checkpoint ingest. Neu bo buoc nay, `run_ingest` doc thay
     checkpoint cu ("da hoan tat batch cuoi") va KHONG LAM GI CA - migration
     se "thanh cong" trong im lang ma graph mat het REFERENCES.
  4. Chay lai `run_ingest` - tao lai REFERENCES bang extractor MOI, dong
     thoi ghi luon Document.title/so_hieu/loai_vb (T025) cho 3,203 Document.

Dao thu tu la sai: xoa REFERENCES SAU khi re-ingest se xoa mat chinh cac
canh vua tao dung.

=== AN TOAN ===
Mac dinh la DRY-RUN: chi dem va in bao cao, khong xoa/ghi gi. Phai truyen
`--apply` tuong minh moi thuc su thay doi du lieu (day la script duy nhat
trong project xoa du lieu that).

CACH DUNG:
    python -m scripts.migrate_references data/raw            # dry-run
    python -m scripts.migrate_references data/raw --apply     # thuc thi
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable

from app.graph_store.neo4j_client import Neo4jClient
from app.ingest import DEFAULT_STATE_FILE, run_ingest

logger = logging.getLogger(__name__)

# Xoa theo lo qua `CALL ... IN TRANSACTIONS`: 37,875 canh trong MOT
# transaction don de lam het heap cua Neo4j Community (mac dinh 512MB-1GB).
# 10,000 canh/transaction la muc thap an toan, khong can toi uu them (chay
# mot lan, khong phai duong nong).
DELETE_REFERENCES_QUERY = (
    "MATCH ()-[r:REFERENCES]->() "
    "CALL (r) { DELETE r } IN TRANSACTIONS OF 10000 ROWS"
)

# CHI xoa Article external placeholder DA THANH MO COI sau buoc 1.
# Hai rang buoc, ca hai deu bat buoc:
#   - `a.is_external = true`: KHONG bao gio duoc xoa Article that (60,679
#     node co chroma_id - xoa la mat lien ket sang Chroma, phai embed lai).
#   - `COUNT { (a)--() } = 0`: khong con quan he nao. KHONG dung DETACH
#     DELETE - placeholder van dang la dich cua AMENDS/SUPERSEDES/
#     CONFLICTS_WITH (T013 da ghi canh AMENDS that vao graph) phai duoc GIU
#     nguyen, khong bi xoa keo theo ca quan he.
DELETE_ORPHAN_EXTERNAL_ARTICLES_QUERY = (
    "MATCH (a:Article) "
    "WHERE a.is_external = true AND COUNT { (a)--() } = 0 "
    "CALL (a) { DELETE a } IN TRANSACTIONS OF 10000 ROWS"
)

_COUNT_QUERIES = {
    "references": "MATCH ()-[r:REFERENCES]->() RETURN count(r) AS n",
    "external_placeholder": (
        "MATCH (a:Article) WHERE a.is_external = true RETURN count(a) AS n"
    ),
    "document_co_so_hieu": (
        "MATCH (d:Document) WHERE d.so_hieu IS NOT NULL RETURN count(d) AS n"
    ),
    "article_that": (
        "MATCH (a:Article) WHERE coalesce(a.is_external, false) = false "
        "RETURN count(a) AS n"
    ),
    "article_co_chroma_id": (
        "MATCH (a:Article) WHERE a.chroma_id IS NOT NULL RETURN count(a) AS n"
    ),
}


def _reset_checkpoint(state_file: Path | str = DEFAULT_STATE_FILE) -> None:
    """Xoa file checkpoint ingest (buoc 3). Khong ton tai -> khong lam gi
    (khong raise: mot graph duoc ingest o may khac co the khong co file nay
    o day, va thieu checkpoint KHONG gay nguy hiem - chi nghia la ingest se
    chay tu batch 0, dung cai ta muon)."""
    path = Path(state_file)
    if path.exists():
        path.unlink()
        logger.info("da xoa checkpoint %s", path)
    else:
        logger.info("khong co checkpoint tai %s (bo qua)", path)


def _snapshot(client: Neo4jClient) -> dict[str, int]:
    """Dem trang thai hien tai (chi MATCH/count - khong ghi gi)."""
    return {
        name: client.run(query)[0]["n"] for name, query in _COUNT_QUERIES.items()
    }


def run_migration(
    data_dir: str | Path,
    *,
    client: Neo4jClient,
    apply: bool = False,
    reingest: Callable[..., None] = run_ingest,
    reset_checkpoint: Callable[..., None] = _reset_checkpoint,
) -> dict[str, dict[str, int]]:
    """Chay migration (hoac chi bao cao khi `apply=False`).

    `client`/`reingest`/`reset_checkpoint` injectable de test duoc khong can
    Neo4j that (cung quy uoc voi `run_ingest`).

    Tra ve {"truoc": {...}, "sau": {...}} - so lieu dem TRUOC va SAU. Khi
    `apply=False`, "sau" GIONG "truoc" (khong co gi thay doi).

    Neu `reingest` raise: KHONG bat/khong bao cao "xong" - de exception noi
    len nguyen ven. Luc do graph dang o trang thai DA xoa REFERENCES nhung
    CHUA tao lai het, operator PHAI biet de chay lai (cung nguyen tac "crash
    lon tieng thay vi lam sai trong im lang" cua BatchSizeMismatchError /
    ArticleIdCollisionError).
    """
    truoc = _snapshot(client)
    logger.info("TRUOC migration: %s", truoc)

    if not apply:
        logger.warning(
            "DRY-RUN: khong xoa/ghi gi. Se xoa %d canh REFERENCES va cac "
            "Article external placeholder mo coi (trong tong %d), roi chay "
            "lai ingest tren %s. Them --apply de thuc thi that.",
            truoc["references"],
            truoc["external_placeholder"],
            data_dir,
        )
        return {"truoc": truoc, "sau": truoc}

    logger.info("buoc 1/4: xoa toan bo canh REFERENCES (theo lo)")
    client.run(DELETE_REFERENCES_QUERY)

    logger.info("buoc 2/4: xoa Article external placeholder da thanh mo coi")
    client.run(DELETE_ORPHAN_EXTERNAL_ARTICLES_QUERY)

    logger.info("buoc 3/4: reset checkpoint ingest")
    reset_checkpoint()

    logger.info("buoc 4/4: chay lai ingest (tao lai REFERENCES + T025 metadata)")
    reingest(data_dir, client=client)

    sau = _snapshot(client)
    logger.info("SAU migration: %s", sau)
    return {"truoc": truoc, "sau": sau}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Migration T027: xoa REFERENCES/placeholder cu (extractor truoc "
            "T026) roi tao lai bang extractor moi, dong thoi ghi "
            "Document.title/so_hieu/loai_vb (T025). Mac dinh DRY-RUN."
        )
    )
    parser.add_argument(
        "data_dir",
        type=str,
        help="Thu muc chua cac file .md da fetch (vd data/raw).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "THUC SU xoa va tao lai du lieu. Khong co co nay = dry-run, chi "
            "in bao cao."
        ),
    )
    return parser


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = build_arg_parser().parse_args()
    client = Neo4jClient()
    try:
        report = run_migration(args.data_dir, client=client, apply=args.apply)
    finally:
        client.close()

    print()
    print(f"{'chi so':<24} {'truoc':>12} {'sau':>12}")
    for key in report["truoc"]:
        print(f"{key:<24} {report['truoc'][key]:>12,} {report['sau'][key]:>12,}")


if __name__ == "__main__":
    main()
