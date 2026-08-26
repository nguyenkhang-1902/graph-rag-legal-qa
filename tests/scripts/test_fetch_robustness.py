"""Tests cho lop robustness cua crawler (huong 1-C) - CHI ham THUAN + phan
loai exception, khong chay Playwright/mang. Retry/click that xac minh bang
chay tay end-to-end."""
from scripts.fetch_bhxh_corpus import (
    VbplFetchError,
    VbplNotFoundError,
    _is_not_found_shell,
)


def test_not_found_shell_detected():
    # Trang loi vbpl.vn: ngan + co marker "khong ton tai".
    assert _is_not_found_shell("Văn bản không tồn tại") is True
    assert _is_not_found_shell("404 Not Found") is True


def test_real_document_not_flagged_as_not_found():
    # Van ban that: dai (> nguong) -> KHONG bi coi la not-found du co tinh co
    # chua tu "not found" o dau do.
    long_body = "Điều 1. Phạm vi điều chỉnh " * 500
    assert _is_not_found_shell(long_body) is False


def test_short_page_without_marker_not_flagged():
    # Ngan nhung khong co marker loi -> khong ket luan not-found (co the la
    # trang dang render do) -> de retry xu ly, khong fail vinh vien nham.
    assert _is_not_found_shell("Đang tải...") is False


def test_not_found_is_subclass_of_fetch_error():
    # De caller co the catch chung VbplFetchError.
    assert issubclass(VbplNotFoundError, VbplFetchError)
