"""discover_vbpl.py (huong 1-B): resolver SO HIEU -> URL chi tiet vbpl.vn.

Nhap so hieu (vd "145/2020/ND-CP") hoac tu khoa -> search vbpl.vn -> tra ve
danh sach ung vien {url, title, trang_thai, ngay_hieu_luc, ngay_ban_hanh}
de NGUOI DUYET truoc khi them vao BHXH_CORPUS_URLS. Human-in-the-loop:
module nay KHONG tu ingest (tranh nuot nham van ban sai/het hieu luc).

=== VI SAO PHAI CLICK (khong parse href) ===
Trang ket qua vbpl.vn la Ant Design + Next.js. Moi ket qua la mot
<li class="ant-list-item">; tieu de la
<span class="cursor-pointer"><div class="DocumentCard_documentTitle...">
voi React onClick MO TAB MOI - KHONG phai <a href>. Id van ban nam trong
React state, KHONG co trong HTML tinh (da xac minh: id "152668" khong xuat
hien trong page.content()). Cach ON DINH duy nhat lay URL chuan
"slug--uuid" la CLICK tieu de va bat tab moi (context.expect_page).

CACH DUNG:
    python -m scripts.discover_vbpl "145/2020/ND-CP"
    python -m scripts.discover_vbpl "luong toi thieu vung" --max 8
    python -m scripts.discover_vbpl "38/2013/QH13" --headed   # xem truc quan
"""
from __future__ import annotations

import argparse
import re

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HOME = "https://vbpl.vn/"
_SEARCH_BOX_PLACEHOLDER = "Nhập từ khóa tìm kiếm"

# Selector ON DINH (tranh hau to hash cua CSS module - dung *= chua-chuoi):
_RESULT_ITEM = "li.ant-list-item"
_RESULT_TITLE = "[class*='documentTitle']"
_RESULT_CLICKABLE = "span.cursor-pointer"

_DATE = r"(\d{2}/\d{2}/\d{4})"


def parse_result_meta(item_text: str) -> dict[str, str | None]:
    """Trich metadata tu text mot ket qua (khoi <li>): trang thai, ngay ban
    hanh, ngay hieu luc. Ham THUAN (khong mang) -> test offline duoc.

    Text mau: "... quan he lao dong PDF Luoc do Tai ve Trang thai: Het hieu
    luc mot phan Ngay ban hanh: 14/12/2020 Ngay hieu luc: 01/02/2021 ..."
    """
    def _find(pat: str) -> str | None:
        m = re.search(pat, item_text)
        return m.group(1).strip() if m else None

    return {
        "trang_thai": _find(r"Trạng thái:\s*(.+?)\s*Ngày ban hành:"),
        "ngay_ban_hanh": _find(r"Ngày ban hành:\s*" + _DATE),
        "ngay_hieu_luc": _find(r"Ngày hiệu lực:\s*" + _DATE),
    }


def search_vbpl(
    keyword: str,
    *,
    max_results: int = 5,
    headless: bool = True,
    nav_timeout_ms: int = 15000,
) -> list[dict]:
    """Search `keyword` tren vbpl.vn, tra ve toi da `max_results` ung vien
    {url, title, trang_thai, ngay_ban_hanh, ngay_hieu_luc}.

    Lay `url` bang cach CLICK tieu de tung ket qua va bat tab moi (xem
    docstring module). Ket qua khong click duoc/timeout -> bo qua ket qua do
    (van tra ve nhung ket qua lay duoc), khong lam gay ca lan search.
    """
    keyword = keyword.strip()
    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        ctx = browser.new_context(user_agent=_UA, locale="vi-VN")
        page = ctx.new_page()
        page.goto(_HOME, wait_until="load", timeout=40000)
        page.wait_for_timeout(2000)

        box = page.get_by_placeholder(_SEARCH_BOX_PLACEHOLDER)
        box.fill(keyword)
        box.press("Enter")
        try:
            page.wait_for_function(
                "() => document.body.innerText.includes('văn bản')",
                timeout=nav_timeout_ms,
            )
        except PWTimeout:
            browser.close()
            return results
        page.wait_for_timeout(1200)

        items = page.locator(_RESULT_ITEM)
        n = min(items.count(), max_results)
        for i in range(n):
            li = items.nth(i)
            try:
                title = li.locator(_RESULT_TITLE).first.inner_text().strip()
            except PWTimeout:
                continue
            meta = parse_result_meta(li.inner_text())
            url = None
            try:
                with ctx.expect_page(timeout=nav_timeout_ms) as pop:
                    li.locator(_RESULT_CLICKABLE).first.click(timeout=8000)
                new_page = pop.value
                new_page.wait_for_url("**/chi-tiet/**", timeout=nav_timeout_ms)
                url = new_page.url
                new_page.close()
            except PWTimeout:
                pass  # khong lay duoc URL ket qua nay -> van giu title+meta
            results.append({"title": title, "url": url, **meta})
        browser.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolver so hieu/tu khoa -> URL chi tiet vbpl.vn (duyet tay)."
    )
    parser.add_argument("keyword", help="So hieu (vd '145/2020/ND-CP') hoac tu khoa.")
    parser.add_argument("--max", type=int, default=5, help="So ket qua toi da (mac dinh 5).")
    parser.add_argument("--headed", action="store_true", help="Hien trinh duyet (debug).")
    args = parser.parse_args()

    print(f"[discover] tim: {args.keyword!r} ...")
    hits = search_vbpl(args.keyword, max_results=args.max, headless=not args.headed)
    if not hits:
        print("[discover] KHONG co ket qua (hoac search timeout). Thu tu khoa khac.")
        return
    print(f"[discover] {len(hits)} ung vien (duyet truoc khi them vao BHXH_CORPUS_URLS):\n")
    for i, h in enumerate(hits, 1):
        print(f"  {i}. {h['title']}")
        print(f"     trang_thai : {h['trang_thai']}")
        print(f"     hieu_luc   : {h['ngay_hieu_luc']}  (ban hanh {h['ngay_ban_hanh']})")
        print(f"     url        : {h['url'] or '(khong lay duoc - mo tay tren vbpl.vn)'}")
        print()


if __name__ == "__main__":
    main()
