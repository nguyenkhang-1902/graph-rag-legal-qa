"""Ingest BHXH tu .txt da persist (data/raw/bhxh) vao Neo4j - KHONG crawl lai.
Doc noi_dung + sidecar .tt.txt, dung che_do map tu BHXH_CORPUS_URLS."""
from pathlib import Path

from app.graph_store.neo4j_client import Neo4jClient
from scripts.fetch_bhxh_corpus import BHXH_CORPUS_URLS, _slug_from_url, ingest_vbpl_doc

RAW = Path("data/raw/bhxh")


def main() -> None:
    ok, fail = 0, []
    with Neo4jClient() as client:
        client.ensure_constraints_and_indexes()
        for entry in BHXH_CORPUS_URLS:
            slug = _slug_from_url(entry["url"])
            txt = RAW / f"{slug}.txt"
            tt = RAW / f"{slug}.tt.txt"
            if not txt.exists():
                print(f"!! thieu file {txt.name} -> bo qua")
                fail.append(slug)
                continue
            noi_dung = txt.read_text(encoding="utf-8")
            thuoc_tinh = tt.read_text(encoding="utf-8") if tt.exists() else ""
            try:
                doc_id = ingest_vbpl_doc(
                    client, noi_dung, entry["che_do"], thuoc_tinh,
                    ngay_hieu_luc_override=entry.get("ngay_hieu_luc"),
                )
                print(f"ingested {doc_id}")
                ok += 1
            except Exception as exc:  # noqa: BLE001
                print(f"!! LOI {slug}: {type(exc).__name__}: {exc}")
                fail.append(slug)
    print(f"XONG: {ok} ok, {len(fail)} loi.")


if __name__ == "__main__":
    main()
