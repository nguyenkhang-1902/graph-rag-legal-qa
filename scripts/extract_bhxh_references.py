"""extract_bhxh_references.py (BHXH-P2-T2): trich xuat canh REFERENCES
(trich dan noi van ban, "Dieu N ...") cho toan bo corpus BHXH da fetch
(`data/raw/bhxh/*.txt`), cho multi-hop graph traversal hoat dong.

Trach nhiem duy nhat cua module nay (constitution Dieu 5): doc lai cac file
da luu boi `fetch_bhxh_corpus.py` (`<slug>.txt` = noi_dung, `<slug>.tt.txt`
= thuoc_tinh sidecar) tu DIA (khong crawl lai), roi day qua engine THAT da
co (T2/T7/T9) de ghi canh REFERENCES - khong tu viet lai
parser/extractor/upsert o day:

    parse_vbpl_content -> (moi Article) -> extract_references -> upsert_references

Mirror dung pattern `app/ingest.py:_ingest_one_file` da dung cho phan
references (xem docstring ham do) - CHI khac o cho khong goi lai
upsert_document (Document/Article/Chapter da duoc ghi boi
`fetch_bhxh_corpus.ingest_vbpl_doc` roi, script nay CHI bo sung canh
REFERENCES ma buoc ingest P1 chua lam).

doc_id la SLUGIFIED (`parse_vbpl_content` -> `build_doc_identity`, xem
vbpl_parser.py) - truyen `current_doc_slug=parsed.doc_id` de tu trich dan
(self-reference) resolve dung; `extract_references` tu dung cung
`build_doc_identity`/`slugify_doc_name` cho trich dan cheo van ban nen
target_article_id cung khop dung scheme, khong can bien doi gi them o day.

CACH DUNG (tren may that, Neo4j dang chay, cac Document/Article BHXH da
duoc ingest truoc boi `fetch_bhxh_corpus.py`):
    python -m scripts.extract_bhxh_references
"""
from __future__ import annotations

from pathlib import Path

from app.extraction.reference_extractor import extract_references
from app.extraction.vbpl_parser import parse_vbpl_content
from app.graph_store.neo4j_client import Neo4jClient
from app.graph_store.upsert import upsert_references
from app.ingest import _all_articles

DEFAULT_DATA_DIR = Path("data/raw/bhxh")

# Alias {cum-ten-luat-lowercase: doc_id} de resolve trich dan CHEO theo TEN
# (khong kem nam/so hieu) sang doc_id DUNG trong corpus - fix cross-doc
# multi-hop (Nghi dinh trich "Luat Bao hiem xa hoi" theo ten). Cac ten nay
# la van ban goc THUONG duoc trich chi bang ten trong corpus BHXH.
BHXH_DOC_ALIASES: dict[str, str] = {
    "luật bảo hiểm xã hội": "41-2024-qh15",
    "bộ luật lao động": "45-2019-qh14",
    "luật việc làm": "74-2025-qh15",
    "luật an toàn, vệ sinh lao động": "84-2015-qh13",
    "luật an toàn vệ sinh lao động": "84-2015-qh13",
    "luật bảo hiểm y tế": "25-2008-qh12",
}


def _noidung_files(data_dir: str | Path) -> list[Path]:
    """Liet ke `data_dir/*.txt` LA noi_dung (khong phai sidecar thuoc_tinh
    `*.tt.txt`), sap xep theo ten cho thu tu on dinh."""
    data_dir = Path(data_dir)
    return sorted(
        p for p in data_dir.glob("*.txt") if not p.name.endswith(".tt.txt")
    )


def extract_bhxh_references(paths: list[Path], client: Neo4jClient) -> int:
    """Voi moi file noi_dung trong `paths`: doc sidecar `.tt.txt` (thuoc_tinh,
    can cho so hieu/doc_id dung - doc mot minh noi_dung co the bat nham so
    hieu cua van ban DUOC DAN CHIEU o preamble, xem vbpl_parser.py), parse
    qua `parse_vbpl_content`, roi voi TUNG Article cua van ban do: trich
    xuat trich dan (`extract_references`) va ghi canh REFERENCES
    (`upsert_references`) - dung mirror phan references cua
    `app/ingest.py:_ingest_one_file`.

    Tra ve TONG so trich dan (canh REFERENCES) da xu ly qua toan bo `paths`
    (khong phan biet self-reference/cross-doc/external placeholder - chi la
    so dem tho de bao cao/smoke check)."""
    total_references = 0
    for noi_dung_path in paths:
        noi_dung_text = noi_dung_path.read_text(encoding="utf-8")
        thuoc_tinh_path = noi_dung_path.with_name(noi_dung_path.stem + ".tt.txt")
        thuoc_tinh_text = (
            thuoc_tinh_path.read_text(encoding="utf-8")
            if thuoc_tinh_path.exists()
            else ""
        )

        doc = parse_vbpl_content(noi_dung_text, thuoc_tinh_text)
        parsed = doc.parsed

        for article in _all_articles(parsed):
            references = extract_references(
                article.full_text,
                current_doc_slug=parsed.doc_id,
                doc_aliases=BHXH_DOC_ALIASES,
            )
            upsert_references(client, article.article_id, references)
            total_references += len(references)

    return total_references


def main() -> None:
    paths = _noidung_files(DEFAULT_DATA_DIR)
    print(
        f"[extract_bhxh_references] {len(paths)} file noi_dung trong "
        f"{DEFAULT_DATA_DIR}"
    )

    client = Neo4jClient()
    try:
        total_references = extract_bhxh_references(paths, client)
        print(
            f"[extract_bhxh_references] XONG: {total_references} trich dan "
            "REFERENCES da xu ly."
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
