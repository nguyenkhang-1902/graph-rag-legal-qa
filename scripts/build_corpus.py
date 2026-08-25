"""build_corpus.py: MOT lenh xay lai TOAN BO corpus - idempotent + tu verify.

Bien quy trinh 5 script roi (chay tay, phu thuoc thu tu, don tay) thanh MOT
lenh tin cay. Moi lan chay cho ra CUNG mot trang thai sach.

Cac buoc (tu dong, dung thu tu):
  1. WIPE   - xoa sach graph (Document/Chapter/Article/Clause/Term + moi canh)
              + Chroma collection. (Corpus la lao dong-BHXH, khong con Zalo.)
  2. CRAWL  - neu --refresh HOAC data/raw/bhxh trong: fetch_bhxh_corpus persist
              .txt + sidecar tu vbpl.vn. Nguoc lai dung .txt da co (offline, nhanh).
  3. INGEST - doc .txt + sidecar -> ingest_vbpl_doc -> Neo4j (doc_id/hieu luc dung).
  4. EMBED  - embed_bhxh_txt -> Chroma (article_id = khoa khop Neo4j).
  5. REFS   - extract_bhxh_references (alias cross-doc) -> canh REFERENCES.
  6. RECONCILE - Chroma count PHAI == so Article that (is_external=false). Lech -> loi.

CACH DUNG:
    python -m scripts.build_corpus            # rebuild tu .txt da co
    python -m scripts.build_corpus --refresh  # crawl lai tu vbpl.vn (~10 phut)
"""
from __future__ import annotations

import argparse
from pathlib import Path

import chromadb

from app import config
from app.graph_store.neo4j_client import Neo4jClient
from scripts.embed_bhxh import embed_bhxh_txt
from scripts.extract_bhxh_references import _noidung_files, extract_bhxh_references
from scripts.fetch_bhxh_corpus import (
    BHXH_CORPUS_URLS,
    _slug_from_url,
    fetch_bhxh_corpus,
    ingest_vbpl_doc,
)

RAW_DIR = Path("data/raw/bhxh")


def _wipe(client: Neo4jClient) -> None:
    # Xoa moi node cua corpus theo lo (tranh transaction qua lon).
    client.run(
        "MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 1000 ROWS"
    )
    cli = chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
    try:
        cli.delete_collection(config.CHROMA_COLLECTION_NAME)
    except Exception:  # noqa: BLE001 - collection co the chua ton tai
        pass
    cli.get_or_create_collection(
        config.CHROMA_COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def _ingest_from_disk(client: Neo4jClient) -> tuple[int, list[str]]:
    ok, missing = 0, []
    for entry in BHXH_CORPUS_URLS:
        slug = _slug_from_url(entry["url"])
        txt = RAW_DIR / f"{slug}.txt"
        if not txt.exists():
            missing.append(slug)
            continue
        tt = RAW_DIR / f"{slug}.tt.txt"
        ingest_vbpl_doc(
            client,
            txt.read_text(encoding="utf-8"),
            entry["che_do"],
            tt.read_text(encoding="utf-8") if tt.exists() else "",
            ngay_hieu_luc_override=entry.get("ngay_hieu_luc"),
        )
        ok += 1
    return ok, missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Xay lai corpus (idempotent).")
    parser.add_argument(
        "--refresh", action="store_true",
        help="Crawl lai .txt tu vbpl.vn (neu khong: dung .txt da co tren dia).",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    have_txt = any(
        p for p in RAW_DIR.glob("*.txt") if not p.name.endswith(".tt.txt")
    )

    with Neo4jClient() as client:
        client.ensure_constraints_and_indexes()

        print("[build] 1/6 WIPE graph + Chroma...")
        _wipe(client)

        if args.refresh or not have_txt:
            print(f"[build] 2/6 CRAWL {len(BHXH_CORPUS_URLS)} van ban -> {RAW_DIR}...")
            fetch_bhxh_corpus([e["url"] for e in BHXH_CORPUS_URLS], RAW_DIR)
        else:
            print("[build] 2/6 CRAWL bo qua (dung .txt da co; --refresh de crawl lai).")

        print("[build] 3/6 INGEST tu dia -> Neo4j...")
        ok, missing = _ingest_from_disk(client)
        print(f"        {ok} van ban ingested; {len(missing)} thieu file: {missing}")

        paths = _noidung_files(RAW_DIR)
        print(f"[build] 4/6 EMBED {len(paths)} van ban -> Chroma...")
        n_vec = embed_bhxh_txt(paths)

        print("[build] 5/6 REFERENCES (alias cross-doc)...")
        n_ref = extract_bhxh_references(paths, client)

        print("[build] 6/6 RECONCILE...")
        real = client.run(
            "MATCH (a:Article) WHERE coalesce(a.is_external,false)=false "
            "RETURN count(a) AS n"
        )[0]["n"]
        docs = client.run(
            "MATCH (d:Document) WHERE d.che_do IS NOT NULL RETURN count(d) AS n"
        )[0]["n"]
    chroma = (
        chromadb.PersistentClient(path=config.CHROMA_PERSIST_DIR)
        .get_or_create_collection(config.CHROMA_COLLECTION_NAME)
        .count()
    )

    print("\n=== KET QUA BUILD ===")
    print(f"  Document (che_do): {docs}")
    print(f"  Article that:      {real}")
    print(f"  Chroma vector:     {chroma}  ({n_vec} embed lan nay)")
    print(f"  REFERENCES:        {n_ref}")
    if chroma != real:
        raise SystemExit(
            f"!! RECONCILE FAIL: Chroma ({chroma}) != Article that ({real}). "
            "Build KHONG sach - kiem tra lai."
        )
    print("  RECONCILE OK: Chroma == Article that. Build SACH.")


if __name__ == "__main__":
    main()
