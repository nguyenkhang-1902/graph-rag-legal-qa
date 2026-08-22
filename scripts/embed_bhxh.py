"""embed_bhxh.py (BHXH-P2-T1): embed corpus BHXH da luu tren dia
(data/raw/bhxh/*.txt, ghi boi `scripts/fetch_bhxh_corpus.py`, T5) vao Chroma
collection `legal_articles` - buoc P2 dau tien de retrieval/QA co the tim
duoc Dieu BHXH qua dense search (Neo4j da co san Article node tu P1, nhung
Chroma la nguon su that duy nhat cho full_text + embedding, xem
backfill_embeddings.py's module docstring).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): CLI parsing +
dieu phoi vong lap file (doc .txt -> parse_vbpl_content -> upsert Chroma) -
KHONG chua logic parse van ban (goi `app.extraction.vbpl_parser`, tai dung
`app.ingest._all_articles` de gom Dieu tu ca Chuong LAN Dieu truc tiep duoi
Document - dung CHINH XAC pattern da thiet lap o `backfill_embeddings.py`),
khong chua logic "noi chuyen voi model/Chroma" (goi `app.retrieval.embedder`).

CRITICAL (xem task-1-brief.md): article_id cua BHXH la KHONG slugify/lowercase
(vd "41-2024-QH15_dieu-1") - `article.article_id` do `parse_vbpl_content` sinh
ra da DUNG dinh dang can dung lam Chroma id (phai khop dung Neo4j
Article.article_id da ingest o P1), nen o day dung NGUYEN VAN, khong bien
doi them.

CACH DUNG:
    python -m scripts.embed_bhxh
(glob toan bo data/raw/bhxh/*.txt, khong nhan tham so - so luong file con it
va co dinh, khac voi backfill_embeddings.py can --limit/--batch-size cho
60k+ file that)."""
from __future__ import annotations

import logging
from pathlib import Path

from app.extraction.vbpl_parser import parse_vbpl_content
from app.ingest import _all_articles
from app.retrieval import embedder

logger = logging.getLogger(__name__)

_BHXH_RAW_DIR = Path("data/raw/bhxh")


def embed_bhxh_txt(paths: list[Path]) -> int:
    """Doc moi file `.txt` trong `paths` (noi dung da render tu vbpl.vn, xem
    module docstring), parse bang `parse_vbpl_content`, gom TOAN BO Article
    (ca Dieu truc tiep duoi Document LAN Dieu nam trong Chuong, qua
    `_all_articles` - tai dung CHINH XAC logic `backfill_embeddings.py` da
    dung, tranh drift), roi upsert MOT LAN (khong phai N loi goi rieng le)
    vao Chroma qua `embedder.upsert_embeddings`. Article co `full_text` rong
    bi bo qua (khong co gi de embed). Tra ve tong so vector da upsert."""
    # Dedupe theo article_id (dict giu ban cuoi) - PHAI parse KEM thuoc_tinh
    # sidecar (`<slug>.tt.txt`): parse chi tu noi dung body lay so hieu tu van
    # ban DUOC DAN CHIEU o preamble -> doc_id/article_id SAI + trung (vd nhieu
    # van ban cung dan Luat BHXH 2014 -> deu ra "58-2014-QH13_dieu-N"). Chroma
    # upsert khong chap nhan id trung -> phai dung thuoc_tinh cho dung id khop
    # Neo4j (xem fetch_bhxh_corpus.fetch_vbpl_document / ingest_vbpl_doc).
    by_id: dict[str, tuple[str, dict]] = {}

    for path in paths:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        tt_path = path.with_name(path.name[: -len(".txt")] + ".tt.txt")
        thuoc_tinh = tt_path.read_text(encoding="utf-8") if tt_path.exists() else ""
        doc = parse_vbpl_content(text, thuoc_tinh)
        parsed = doc.parsed

        for article in _all_articles(parsed):
            if not article.full_text.strip():
                continue
            by_id[article.article_id] = (
                article.full_text,
                {"doc_id": parsed.doc_id, "so_dieu": article.so_dieu},
            )

    if not by_id:
        logger.info("khong co Article nao de embed (0 file hoac toan bo rong)")
        return 0

    ids = list(by_id.keys())
    texts = [by_id[i][0] for i in ids]
    metadatas = [by_id[i][1] for i in ids]
    embedder.upsert_embeddings(ids=ids, texts=texts, metadatas=metadatas)
    return len(ids)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    # Bo qua sidecar thuoc_tinh (`*.tt.txt`) - chung duoc doc kem theo file
    # noi dung tuong ung ben trong embed_bhxh_txt, khong phai file dau vao rieng.
    paths = sorted(
        p for p in _BHXH_RAW_DIR.glob("*.txt") if not p.name.endswith(".tt.txt")
    )
    logger.info("tim thay %d file trong %s", len(paths), _BHXH_RAW_DIR)
    count = embed_bhxh_txt(paths)
    print(f"Da embed {count} Dieu vao Chroma tu {len(paths)} file.")


if __name__ == "__main__":
    main()
