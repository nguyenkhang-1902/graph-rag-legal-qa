"""fetch_bhxh_corpus.py (BHXH-P1-T5): crawler (Playwright) + ingest van ban
BHXH vao Neo4j - buoc cuoi cua P1 (nen du lieu BHXH, xem
.superpowers/sdd/2026-08-20-bhxh-p1-nen-du-lieu/).

Trach nhiem duy nhat cua module nay (constitution Dieu 5): lay text van ban
tu vbpl.vn (CSDL quoc gia ve phap luat) roi day qua pipeline engine THAT da
co (T2/T3) de ghi vao graph - khong tu viet lai parser/upsert o day.

=== VI SAO PLAYWRIGHT, KHONG PHAI requests/BeautifulSoup ===
vbpl.vn la Next.js App Router (React Server Components) - trang chi tiet
render noi dung bang JS phia client. `requests` thuan tra ve shell rong,
khong co text luat (xem tests/fixtures/bhxh/vbpl-source-notes.md, Task 1
spike). Recipe duoi day (`fetch_vbpl_noidung`) da duoc XAC MINH THAT render
dung noi dung ("Pham vi dieu chinh" xuat hien trong body).

=== URL PHAI LA DANG DAY DU "slug--uuid" ===
URL chi-tiet bare-uuid (`/van-ban/chi-tiet/<uuid>`) tra ve "Van ban khong
ton tai" - PHAI dung dang day du `slug--uuid` (xem BHXH_CORPUS_URLS).

=== NGAY HIEU LUC: khong can tab "Thuoc tinh" ===
`app.extraction.vbpl_parser.parse_vbpl_content` da tu trich `ngay_hieu_luc`
tu cau mo dau trong `noi_dung_text` ("... co hieu luc ke tu ngay 01 thang 7
nam 2025") khi khong co `thuoc_tinh_text` - nen script nay CHI can lay tab
"Noi dung" (khong bat buoc phai lay them tab "Thuoc tinh"), du van chap
nhan `thuoc_tinh_text` tuy chon cho nhung van ban sau nay can uu tien
nguon co cau truc hon.

CACH DUNG (tren may that, can Playwright + Chromium da cai, Neo4j dang
chay):
    python -m scripts.fetch_bhxh_corpus
    python scripts/fetch_bhxh_corpus.py --dry-run   # chi fetch + parse, KHONG ghi Neo4j
"""
from __future__ import annotations

import argparse
import dataclasses
import time

from playwright.sync_api import sync_playwright

from app.extraction.doc_identity import build_doc_identity
from app.extraction.vbpl_parser import parse_vbpl_content
from app.graph_store.neo4j_client import Neo4jClient
from app.graph_store.upsert import upsert_document

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Danh sach van ban nguon BHXH can ingest cho P1 (dien tu Task 1 spike).
#
# CHI 1 URL da duoc XAC MINH THAT (fetch + render dung noi dung) tinh den
# T5: ban hop nhat (VBHN) so 19/VBHN-VPQH cua Luat Bao hiem xa hoi so
# 41/2024/QH15 - toan van hien hanh, bao gom cau "co hieu luc ke tu ngay 01
# thang 7 nam 2025". Luat BHXH la MOT van ban DUY NHAT quy dinh chung ca 3
# che do (huu tri/mot lan/thai san, xem spec.md) - khong phai 3 van ban
# rieng - nen 1 URL nay gan che_do ca 3.
#
# Them URL vao day khi co van ban moi da XAC MINH THAT render dung (dang
# `slug--uuid` day du, xem module docstring) - KHONG doan URL chua kiem
# chung.
BHXH_CORPUS_URLS: list[dict] = [
    {
        "url": (
            "https://vbpl.vn/van-ban/chi-tiet/"
            "van-ban-hop-nhat-so-19-vbhn-vpqh-2026-hop-nhat-luat-bao-hiem-xa-hoi-so-41-2024-qh15"
            "--ff9cd9e0-97aa-11f1-a50f-4bcbcb89bfc0"
        ),
        "che_do": ["huu_tri", "mot_lan", "thai_san"],
    },
]

# Khoang cach lich su giua 2 lan fetch khi corpus co nhieu hon 1 van ban -
# tranh dong dap request len vbpl.vn. Hang so cuc bo (khong qua app/config.py)
# vi day la script mot-lan (crawler), khong phai hang so runtime cua app/
# (cung triet ly voi cac script khac trong scripts/, vd fetch_zalo_legal_corpus.py).
CRAWL_DELAY_SECONDS = 2.0

# Marker LAP LAI 2 LAN trong `page.inner_text("body")` cua trang chi tiet
# vbpl.vn: dong nhan tab ("Noi dung", "Thuoc tinh", "Luoc do", "Van ban
# goc", "Tai ve"). Lan XUAT HIEN THU HAI ket thuc dung truoc noi dung THAT
# cua tab dang mo (xem duoi). Chuoi nay duoc XAC MINH THAT tren URL trong
# BHXH_CORPUS_URLS (2026-08-21, xem tests/fixtures/bhxh/
# vbpl-detail-page-body-excerpt.txt - trich tu ket qua fetch that).
_TAB_BAR_MARKER = "Nội dung\nThuộc tính\nLược đồ\nVăn bản gốc\nTải về"


def _strip_page_chrome(body_text: str) -> str:
    """Cat bo phan "chrome" cua trang (breadcrumb, menu, dong tab, va bang
    tom tat "Ngay co hieu luc: -- / Ngay cap nhat: <ngay cap nhat trang>")
    dung truoc noi dung THAT cua van ban trong `page.inner_text("body")`.

    LY DO CAN HAM NAY (loi phat hien khi chay smoke that T5, khong phai gia
    dinh truoc): `page.inner_text("body")` lay TOAN BO text trang, bao gom
    ca bang tom tat o dau trang co dong "Ngay co hieu luc: --" roi "Ngay
    cap nhat: <ngay Playwright fetch trang, vd 14/08/2026>". Khi noi_dung_text
    KHONG duoc cat, `vbpl_parser._extract_ngay_hieu_luc` (tim tu khoa "hieu
    luc" DAU TIEN trong text) khop nham vao dong "Ngay co hieu luc:" rong
    o day, roi doc nham "14/08/2026" (ngay CAP NHAT TRANG, khong lien quan
    gi den ngay hieu luc PHAP LY that cua van ban) lam ngay_hieu_luc - sai
    hoan toan voi "01/07/2025" that su nam sau do trong noi dung van ban.

    Danh dau `_TAB_BAR_MARKER` (dong nhan 5 tab) xuat hien DUNG 2 LAN tren
    trang: lan 1 trong thanh dieu huong tren cung, lan 2 ngay truoc noi
    dung tab dang mo. Cat tai VI TRI CUOI CUNG cua marker nay -> phan con
    lai la noi dung THAT (bang thuoc tinh hoac noi dung, tuy tab).

    Neu KHONG tim thay marker (trang thay doi cau truc, hoac input da la
    text da cat san) -> tra ve `body_text` NGUYEN VEN, khong doan bua cat
    o dau khac.
    """
    idx = body_text.rfind(_TAB_BAR_MARKER)
    if idx == -1:
        return body_text
    return body_text[idx + len(_TAB_BAR_MARKER) :]


def fetch_vbpl_noidung(url: str) -> str:
    """Mo `url` bang Chromium headless (Playwright), cho JS render xong, roi
    tra ve toan bo text cua `<body>` - dung lam `noi_dung_text` cho
    `parse_vbpl_content`.

    Cho render xong bang cach doi `document.body.innerText` chua cum
    "Pham vi dieu chinh" (heading co that trong Dieu 1 cua moi van ban luat
    BHXH) thay vi mot khoang `sleep` co dinh - on dinh hon truoc bien dong
    toc do mang/render.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=_UA, locale="vi-VN").new_page()
        page.goto(url, wait_until="load", timeout=60000)
        page.wait_for_function(
            "() => document.body.innerText.includes('Phạm vi điều chỉnh')",
            timeout=30000,
        )
        text = page.inner_text("body")
        browser.close()
        return _strip_page_chrome(text)


def ingest_vbpl_doc(
    client: Neo4jClient,
    noi_dung_text: str,
    che_do: list[str],
    thuoc_tinh_text: str = "",
) -> str:
    """Parse text da render cua trang chi tiet vbpl.vn (`noi_dung_text`,
    tuy chon `thuoc_tinh_text`) va ghi vao graph qua engine THAT (T2/T3):

        parse_vbpl_content -> build_doc_identity -> (gan ngay_hieu_luc/
        ngay_het_hieu_luc/che_do qua dataclasses.replace) -> upsert_document

    Tra ve `doc_id` cua van ban vua ghi (khoa `Document.doc_id` trong graph).

    LUU Y quan trong (phat hien khi viet test T5, khong phai gia dinh):
    `upsert_document` LUON dung `doc.parsed.doc_id` (sinh boi
    `structure_parser.parse_document`, TU dong tieu de "# {title}" cua van
    ban neu co, hoac fallback_doc_id "{so}-{nam}-{ma_hieu}" CHUA slugify
    cua `parse_vbpl_content` neu khong) lam KHOA MERGE cua node Document -
    KHONG BAO GIO dung `identity.doc_id` (`build_doc_identity` sinh doc_id
    slug hoa rieng, chi dung lam gia tri hien thi/tra ve o cac caller khac,
    xem doc_identity.py). Van ban render tu vbpl.vn (text thuan, khong co
    dong "# title" dang markdown cua corpus Zalo cu) hau nhu LUON di theo
    nhanh fallback_doc_id. Vi vay ham nay tra ve `doc.parsed.doc_id` (khoa
    THAT da ghi vao graph), khong phai `ident.doc_id` - de gia tri tra ve
    luon truy van lai dung bang `MATCH (d:Document {doc_id: $id})`.

    Idempotent: `upsert_document` chi dung MERGE (xem upsert.py) - goi lai
    ham nay nhieu lan voi cung noi dung khong tao node/canh trung lap.
    """
    doc = parse_vbpl_content(noi_dung_text, thuoc_tinh_text)
    ident = build_doc_identity(doc.so, doc.nam, doc.ma_hieu)
    ident = dataclasses.replace(
        ident,
        ngay_hieu_luc=doc.ngay_hieu_luc,
        ngay_het_hieu_luc=doc.ngay_het_hieu_luc,
        che_do=che_do,
    )
    upsert_document(client, doc.parsed, batch_id="bhxh", identity=ident)
    return doc.parsed.doc_id


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch + ingest van ban BHXH tu vbpl.vn vao Neo4j "
            "(BHXH-P1-T5, xem module docstring cho danh sach URL)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chi fetch + parse (in ra doc_id/ngay_hieu_luc du kien), KHONG ghi Neo4j.",
    )
    args = parser.parse_args()

    entries = BHXH_CORPUS_URLS
    print(f"[fetch_bhxh_corpus] {len(entries)} van ban trong danh muc.")

    client_cm = None if args.dry_run else Neo4jClient()
    try:
        if client_cm is not None:
            client_cm.ensure_constraints_and_indexes()

        for i, entry in enumerate(entries):
            url, che_do = entry["url"], entry["che_do"]
            print(f"[fetch_bhxh_corpus] ({i + 1}/{len(entries)}) fetching {url}")
            noi_dung_text = fetch_vbpl_noidung(url)

            if args.dry_run:
                doc = parse_vbpl_content(noi_dung_text)
                print(
                    f"[fetch_bhxh_corpus] DRY RUN so={doc.so} nam={doc.nam} "
                    f"ma_hieu={doc.ma_hieu} ngay_hieu_luc={doc.ngay_hieu_luc} "
                    f"ngay_het_hieu_luc={doc.ngay_het_hieu_luc}"
                )
            else:
                doc_id = ingest_vbpl_doc(client_cm, noi_dung_text, che_do)
                print(f"[fetch_bhxh_corpus] ingested doc_id={doc_id}")

            if i < len(entries) - 1:
                time.sleep(CRAWL_DELAY_SECONDS)
    finally:
        if client_cm is not None:
            client_cm.close()


if __name__ == "__main__":
    main()
