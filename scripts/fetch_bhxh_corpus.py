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
    python scripts/fetch_bhxh_corpus.py --dry-run              # chi fetch + parse, KHONG ghi Neo4j
    python scripts/fetch_bhxh_corpus.py --out-dir data/raw/bhxh  # fetch + ghi .txt ra dia, KHONG ghi Neo4j
"""
from __future__ import annotations

import argparse
import dataclasses
import time
from pathlib import Path

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
_B = "https://vbpl.vn/van-ban/chi-tiet/"
BHXH_CORPUS_URLS: list[dict] = [
    # --- Luat truc tiep (3 che do) ---
    {
        "url": _B + "van-ban-hop-nhat-so-19-vbhn-vpqh-2026-hop-nhat-luat-bao-hiem-xa-hoi-so-41-2024-qh15--ff9cd9e0-97aa-11f1-a50f-4bcbcb89bfc0",
        "che_do": ["huu_tri", "mot_lan", "thai_san"],  # Luat BHXH 2024 (VBHN)
        # Trang VBHN co "Ngay co hieu luc: --" -> override bang su that trong
        # chinh van ban: "co hieu luc ke tu ngay 01/7/2025".
        "ngay_hieu_luc": "2025-07-01",
    },
    # --- Nghi dinh/Thong tu huong dan Luat BHXH 2024 (2025) ---
    {
        "url": _B + "nghi-dinh-so-158-2025-nd-cp-quy-dinh-chi-tiet-va-huong-dan-thi-hanh-mot-so-dieu-cua-luat-bao-hiem-xa-hoi-ve-bao-hiem-xa-hoi-bat-buoc--178757",
        "che_do": ["huu_tri", "mot_lan", "thai_san"],  # ND 158/2025 BHXH bat buoc (chung)
    },
    {
        "url": _B + "nghi-dinh-so-159-2025-nd-cp-quy-dinh-chi-tiet-va-huong-dan-thi-hanh-mot-so-dieu-cua-luat-bao-hiem-xa-hoi-ve-bao-hiem-xa-hoi-tu-nguyen--179149",
        "che_do": ["huu_tri", "mot_lan"],  # ND 159/2025 BHXH tu nguyen
    },
    {
        "url": _B + "nghi-dinh-so-176-2025-nd-cp-huong-dan-luat-bao-hiem-xa-hoi-ve-tro-cap-huu-tri-xa-hoi--184035",
        "che_do": ["huu_tri"],  # ND 176/2025 tro cap huu tri xa hoi
    },
    {
        "url": _B + "nghi-dinh-so-157-2025-nd-cp-quy-dinh-chi-tiet-va-bien-phap-thi-hanh-mot-so-dieu-cua-luat-bao-hiem-xa-hoi-ve-bao-hiem-xa-hoi-bat-buoc-doi-voi-quan-nhan-cong-an-nhan-dan-dan-quan-thuong-truc-va-nguoi-lam-cong-tac-co-yeu-huong-luong-nhu-doi-voi-quan-nhan--179780",
        "che_do": ["huu_tri", "mot_lan", "thai_san"],  # ND 157/2025 BHXH bat buoc quan nhan/CAND
    },
    # --- Luat lien quan ---
    {
        "url": _B + "bo-luat-lao-dong-so-45-2019-qh14--139264",
        "che_do": ["thai_san"],  # Bo luat Lao dong 2019 (nghi thai san, HDLD)
    },
    {
        "url": _B + "luat-viec-lam-so-38-2013-qh13--32912",
        "che_do": ["that_nghiep"],  # Luat Viec lam (BH that nghiep)
    },
    {
        "url": _B + "nghi-dinh-so-374-2025-nd-cp-quy-dinh-chi-tiet-mot-so-dieu-cua-luat-viec-lam-ve-bao-hiem-that-nghiep--186281",
        "che_do": ["that_nghiep"],  # ND 374/2025 BH that nghiep
    },
    {
        "url": _B + "luat-an-toan-ve-sinh-lao-dong-so-84-2015-qh13--70811",
        "che_do": ["tai_nan_lao_dong"],  # Luat ATVSLD (TNLD-BNN)
    },
    {
        "url": _B + "thong-tu-so-60-2025-tt-byt-quy-dinh-ve-benh-nghe-nghiep-duoc-huong-bao-hiem-xa-hoi-va-huong-dan-chan-doan-giam-dinh-muc-suy-giam-kha-nang-lao-dong-do-benh-nghe-nghiep--187267",
        "che_do": ["tai_nan_lao_dong"],  # TT 60/2025-BYT benh nghe nghiep
    },
    {
        "url": _B + "luat-bao-hiem-y-te-so-25-2008-qh12--12326",
        "che_do": ["y_te"],  # Luat BHYT (lien quan)
    },
    # --- Mo rong dot 2 (2026-08-22): van ban hien hanh bo sung ---
    {
        "url": _B + "luat-bao-hiem-y-te-sua-doi-2024-so-luat-so-51-2024-qh15--172923",
        "che_do": ["y_te"],  # Luat BHYT sua doi 2024
    },
    {
        "url": _B + "nghi-dinh-so-88-2020-nd-cp-quy-dinh-chi-tiet-va-huong-dan-thi-hanh-mot-so-dieu-cua-luat-an-toan-ve-sinh-lao-dong-ve-bao-hiem-tai-nan-lao-dong-benh-nghe-nghiep-bat-buoc--143470",
        "che_do": ["tai_nan_lao_dong"],  # ND 88/2020 BH TNLD-BNN
    },
    {
        "url": _B + "nghi-dinh-so-75-2024-nd-cp-dieu-chinh-luong-huu-tro-cap-bao-hiem-xa-hoi-va-tro-cap-hang-thang--168671",
        "che_do": ["huu_tri"],  # ND 75/2024 dieu chinh luong huu
    },
    {
        "url": _B + "nghi-dinh-so-76-2024-nd-cp-sua-doi-bo-sung-mot-so-dieu-cua-nghi-dinh-so-20-2021-nd-cp-ngay-15-thang-3-nam-2021-cua-chinh-phu-quy-dinh-chinh-sach-tro-giup-xa-hoi-doi-voi-doi-tuong-bao-tro-xa-hoi--173641",
        "che_do": ["huu_tri"],  # ND 76/2024 tro giup xa hoi (huu tri xa hoi)
    },
    {
        "url": _B + "thong-tu-so-20-2023-tt-bldtbxh-quy-dinh-muc-dieu-chinh-tien-luong-va-thu-nhap-thang-da-dong-bao-hiem-xa-hoi--167036",
        "che_do": ["huu_tri", "mot_lan"],  # TT 20/2023 dieu chinh tien luong dong BHXH
    },
    {
        "url": _B + "nghi-dinh-so-12-2022-nd-cp-quy-dinh-xu-phat-vi-pham-hanh-chinh-trong-linh-vuc-lao-dong-bao-hiem-xa-hoi-nguoi-lao-dong-viet-nam-di-lam-viec-o-nuoc-ngoai-theo-hop-dong--153913",
        "che_do": ["xu_phat"],  # ND 12/2022 xu phat VPHC lao dong BHXH
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
    return fetch_vbpl_document(url)[0]


def fetch_vbpl_document(url: str) -> tuple[str, str]:
    """Fetch (noi_dung_text, thuoc_tinh_text) cua mot van ban vbpl.vn.

    `noi_dung_text`: tab "Noi dung" (mac dinh khi load), da `_strip_page_chrome`.
    `thuoc_tinh_text`: text sau khi CLICK tab "Thuoc tinh" - bang metadata
    nhan->gia tri (So hieu / Loai van ban / Ngay co hieu luc / Ngay het
    hieu luc...). CAN cho so hieu + ngay hieu luc DUNG: parse tu noi dung
    body chi lay duoc so hieu/ngay cua van ban DUOC DAN CHIEU o preamble
    ("Can cu Luat X so .../...") - SAI voi van ban khong phai Luat BHXH.
    `parse_vbpl_content` uu tien `thuoc_tinh_text` (xem vbpl_parser.py).
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(user_agent=_UA, locale="vi-VN").new_page()
        page.goto(url, wait_until="load", timeout=60000)
        # Cho render xong: body chua "Điều 1" (moi van ban luat deu co) VA du
        # dai (>6000 ky tu) de phan biet voi shell/trang "khong ton tai"
        # (~200-600 ky tu). Robust hon "Phạm vi điều chỉnh" (khong phai N-D/
        # T-T nao cung co dung cum do o Dieu 1).
        page.wait_for_function(
            "() => document.body.innerText.includes('Điều 1') "
            "&& document.body.innerText.length > 6000",
            timeout=40000,
        )
        noi_dung = _strip_page_chrome(page.inner_text("body"))
        thuoc_tinh = ""
        try:
            page.get_by_role("tab", name="Thuộc tính").click(timeout=8000)
            page.wait_for_timeout(1500)
            thuoc_tinh = page.inner_text("body")
        except Exception:  # noqa: BLE001 - thieu thuoc tinh chi lam giam metadata
            pass
        browser.close()
        return noi_dung, thuoc_tinh


def _slug_from_url(url: str) -> str:
    """Rut ten file tu URL chi tiet vbpl.vn dang ".../van-ban/chi-tiet/
    <slug>--<uuid>" (xem module docstring, muc "URL PHAI LA DANG DAY DU"):
    lay PHAN CUOI CUNG cua duong dan (sau dau "/" cuoi), roi cat truoc dau
    "--" DAU TIEN (phan sau la UUID, khong on dinh/khong doc duoc). Vd URL
    trong BHXH_CORPUS_URLS ->
    "van-ban-hop-nhat-so-19-vbhn-vpqh-2026-hop-nhat-luat-bao-hiem-xa-hoi-so-41-2024-qh15".
    """
    last_segment = url.rstrip("/").rsplit("/", 1)[-1]
    slug = last_segment.split("--", 1)[0]
    # Gioi han do dai ten file: slug vbpl.vn co the rat dai (vd ND 157 quan
    # nhan ~230 ky tu) -> vuot MAX_PATH ~260 cua Windows khi ghep vao out_dir.
    # Cat con 100 ky tu (van du phan biet trong danh muc BHXH nho).
    return slug[:100]


def fetch_bhxh_corpus(urls: list[str], out_dir: str | Path) -> list[Path]:
    """Fetch noi dung render (`fetch_vbpl_noidung`, tai su dung KHONG viet
    lai) cho tung URL trong `urls`, ghi ra 1 file `.txt`/URL duoi `out_dir`
    (ten file = slug URL, xem `_slug_from_url`), roi tra ve danh sach
    `Path` da ghi (CUNG THU TU voi `urls`).

    LY DO (xem task-5 brief, Step 5 - doi voi review round 1): ghi noi dung
    da render ra dia TRUOC khi ingest cho phep parse/ingest lai OFFLINE ma
    khong can crawl lai vbpl.vn moi lan (kha nang phuc hoi khi Neo4j/parser
    loi giua chung, hoac khi can thu nghiem lai logic parse tren cung du
    lieu) - cung mau hinh voi `scripts/fetch_zalo_legal_corpus.py` (ghi
    van ban ra `<out>/*.md` truoc, ingest la buoc rieng doc lai tu dia).

    `out_dir` duoc tao neu chua ton tai. Lich su giua cac lan fetch qua
    `CRAWL_DELAY_SECONDS` (giong `main()`), CHI khi `urls` co nhieu hon 1
    phan tu.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for i, url in enumerate(urls):
        try:
            noi_dung, thuoc_tinh = fetch_vbpl_document(url)
            slug = _slug_from_url(url)
            file_path = out_path / f"{slug}.txt"
            file_path.write_text(noi_dung, encoding="utf-8")
            # Sidecar thuoc_tinh: CAN cho embed/parse lai offline lay DUNG so
            # hieu (parse tu noi dung body -> so hieu van ban DUOC DAN CHIEU).
            (out_path / f"{slug}.tt.txt").write_text(thuoc_tinh, encoding="utf-8")
            written.append(file_path)
        except Exception as exc:  # bo qua doc loi, chay tiep
            print(f"[fetch_bhxh_corpus] !! LOI luu {url}: {type(exc).__name__}: {exc}")
        if i < len(urls) - 1:
            time.sleep(CRAWL_DELAY_SECONDS)
    return written


def ingest_vbpl_doc(
    client: Neo4jClient,
    noi_dung_text: str,
    che_do: list[str],
    thuoc_tinh_text: str = "",
    ngay_hieu_luc_override: str | None = None,
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
    # `ngay_hieu_luc_override`: dung khi nguon (Thuoc tinh + noi dung) khong
    # cho ngay hieu luc dung - vd trang VBHN co "Ngay co hieu luc: --" va
    # phan strip chrome khong bat duoc "Ngay cap nhat" -> doc nham. Gia tri
    # override PHAI la su that ghi trong chinh van ban (vd Luat BHXH 2024:
    # "co hieu luc ke tu ngay 01/7/2025"), KHONG phai doan.
    ngay_hl = ngay_hieu_luc_override or doc.ngay_hieu_luc
    ident = dataclasses.replace(
        ident,
        ngay_hieu_luc=ngay_hl,
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
    parser.add_argument(
        "--out-dir",
        default=None,
        help=(
            "Fetch va ghi noi dung render ra .txt duoi thu muc nay qua "
            "fetch_bhxh_corpus() (KHONG ghi Neo4j trong lan chay nay) - de "
            "parse/ingest lai OFFLINE sau, khong can crawl lai. Loai tru "
            "--dry-run (uu tien --out-dir neu ca hai deu duoc truyen)."
        ),
    )
    args = parser.parse_args()

    entries = BHXH_CORPUS_URLS
    print(f"[fetch_bhxh_corpus] {len(entries)} van ban trong danh muc.")

    if args.out_dir:
        urls = [entry["url"] for entry in entries]
        for path in fetch_bhxh_corpus(urls, args.out_dir):
            print(f"[fetch_bhxh_corpus] saved {path}")
        return

    client_cm = None if args.dry_run else Neo4jClient()
    try:
        if client_cm is not None:
            client_cm.ensure_constraints_and_indexes()

        ok, failed = 0, []
        for i, entry in enumerate(entries):
            url, che_do = entry["url"], entry["che_do"]
            print(f"[fetch_bhxh_corpus] ({i + 1}/{len(entries)}) fetching {url}")
            try:
                noi_dung_text, thuoc_tinh_text = fetch_vbpl_document(url)
                if args.dry_run:
                    doc = parse_vbpl_content(noi_dung_text, thuoc_tinh_text)
                    print(
                        f"[fetch_bhxh_corpus] DRY RUN so={doc.so} nam={doc.nam} "
                        f"ma_hieu={doc.ma_hieu} ngay_hieu_luc={doc.ngay_hieu_luc} "
                        f"ngay_het_hieu_luc={doc.ngay_het_hieu_luc}"
                    )
                else:
                    doc_id = ingest_vbpl_doc(
                        client_cm, noi_dung_text, che_do, thuoc_tinh_text,
                        ngay_hieu_luc_override=entry.get("ngay_hieu_luc"),
                    )
                    print(f"[fetch_bhxh_corpus] ingested doc_id={doc_id}")
                ok += 1
            except Exception as exc:  # bo qua doc loi, chay tiep batch
                print(f"[fetch_bhxh_corpus] !! LOI bo qua {url}: {type(exc).__name__}: {exc}")
                failed.append(url)

            if i < len(entries) - 1:
                time.sleep(CRAWL_DELAY_SECONDS)

        print(f"[fetch_bhxh_corpus] XONG: {ok}/{len(entries)} ok, {len(failed)} loi.")
        for u in failed:
            print(f"[fetch_bhxh_corpus]   FAILED: {u}")
    finally:
        if client_cm is not None:
            client_cm.close()


if __name__ == "__main__":
    main()
