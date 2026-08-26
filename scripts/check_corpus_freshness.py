"""check_corpus_freshness.py (GD2 - cap nhat luat tu dong): kiem tra tung
van ban trong corpus CON HIEU LUC tren vbpl.vn khong -> phat hien van ban
da bi THAY THE (superseded) ma minh van dang phuc vu.

Luong: doc so_hieu + trang_thai da luu tu Neo4j -> search vbpl.vn qua
`discover_vbpl.search_vbpl` -> so trang_thai LIVE. Van ban vbpl bao "Het
hieu luc" ma minh dang phuc vu -> CANH BAO. Human-in-the-loop: script chi
BAO CAO, KHONG tu crawl/sua/xoa (nguoi duyet roi chay build_corpus lai).

Vi sao day la nen GD2: dung CHINH resolver (huong 1-B) + trang_thai vbpl
tra ve san trong ket qua search - khong can API rieng. Chay dinh ky (vd
hang thang) de biet luat nao trong corpus da cu.

CACH DUNG:
    python -m scripts.check_corpus_freshness            # kiem toan bo corpus
    python -m scripts.check_corpus_freshness --max 5    # gioi han (test nhanh)
"""
from __future__ import annotations

import argparse
import re

from app.graph_store.neo4j_client import Neo4jClient
from scripts.discover_vbpl import search_vbpl

# Phan loai trang_thai LIVE tu vbpl.vn (chuoi tieng Viet trong ket qua search).
STATUS_CURRENT = "current"    # Con hieu luc
STATUS_PARTIAL = "partial"    # Het hieu luc mot phan (sua doi mot so Dieu)
STATUS_EXPIRED = "expired"    # Het hieu luc toan bo (da bi thay the)
STATUS_UNKNOWN = "unknown"    # Khong tim thay / khong doc duoc trang_thai


def classify_status(live_trang_thai: str | None) -> str:
    """Phan loai chuoi trang_thai vbpl.vn thanh 4 muc. Ham THUAN (test offline).

    "Het hieu luc mot phan" -> PARTIAL (van con phan lon hieu luc, chi sua
    mot so Dieu). "Het hieu luc" (toan bo) -> EXPIRED. Thu tu kiem: PARTIAL
    truoc EXPIRED vi ca hai deu chua "het hieu luc".
    """
    if not live_trang_thai:
        return STATUS_UNKNOWN
    s = live_trang_thai.lower()
    if "một phần" in s:
        return STATUS_PARTIAL
    if "hết hiệu lực" in s:
        return STATUS_EXPIRED
    if "còn hiệu lực" in s:
        return STATUS_CURRENT
    return STATUS_UNKNOWN


def _corpus_docs(client: Neo4jClient) -> list[dict]:
    rows = client.run(
        "MATCH (d:Document) WHERE d.che_do IS NOT NULL AND d.so_hieu IS NOT NULL "
        "RETURN d.doc_id AS doc_id, d.so_hieu AS so_hieu, d.trang_thai AS trang_thai "
        "ORDER BY d.doc_id"
    )
    return [dict(r) for r in rows]


def title_matches_so_hieu(title: str, so_hieu: str) -> bool:
    """True neu `title` chua DUNG `so_hieu` (khong bi so hieu khac nuot lam
    substring - vd '112/2022/NĐ-CP' KHONG duoc coi la khop '12/2022/NĐ-CP').
    Ham THUAN. Chan bang look-behind: so hieu khong dung sau chu so/dau '/'."""
    return re.search(r"(?<![\d/])" + re.escape(so_hieu), title or "") is not None


def _live_status(so_hieu: str) -> tuple[str, str | None]:
    """Search vbpl.vn THEO SO HIEU (search_in='number' - chinh xac), tra
    (classify_status, trang_thai_raw) cua ket qua KHOP DUNG so_hieu. Khong
    khop -> UNKNOWN."""
    for hit in search_vbpl(so_hieu, max_results=5, search_in="number"):
        if title_matches_so_hieu(hit.get("title") or "", so_hieu):
            return classify_status(hit.get("trang_thai")), hit.get("trang_thai")
    return STATUS_UNKNOWN, None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kiem tra van ban corpus con hieu luc tren vbpl.vn (GD2)."
    )
    parser.add_argument("--max", type=int, default=None, help="Gioi han so van ban kiem (test).")
    args = parser.parse_args()

    with Neo4jClient() as client:
        docs = _corpus_docs(client)
    if args.max:
        docs = docs[: args.max]

    print(f"[freshness] kiem {len(docs)} van ban tren vbpl.vn ...\n")
    flagged: list[str] = []
    for i, d in enumerate(docs, 1):
        status, raw = _live_status(d["so_hieu"])
        icon = {
            STATUS_CURRENT: "OK  ",
            STATUS_PARTIAL: "~PART",
            STATUS_EXPIRED: "!!EXP",
            STATUS_UNKNOWN: "  ?  ",
        }[status]
        print(f"  [{i:>2}/{len(docs)}] {icon} {d['so_hieu']:<22} vbpl='{raw}'")
        if status in (STATUS_EXPIRED, STATUS_PARTIAL):
            flagged.append(f"{d['so_hieu']} ({raw})")

    print("\n=== TONG KET ===")
    if flagged:
        print(f"  {len(flagged)} van ban CAN RA SOAT (het hieu luc toan bo/mot phan):")
        for f in flagged:
            print(f"    - {f}")
        print("  -> Kiem nguon vbpl.vn, tim van ban thay the, cap nhat "
              "BHXH_CORPUS_URLS roi chay `python -m scripts.build_corpus --refresh`.")
    else:
        print("  Tat ca van ban con hieu luc (hoac khong doc duoc trang_thai).")


if __name__ == "__main__":
    main()
