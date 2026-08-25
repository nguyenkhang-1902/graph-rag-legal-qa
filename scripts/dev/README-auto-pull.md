# Auto-pull: máy tự tải commit mới từ GitHub (không cần ra lệnh pull)

Cơ chế: **polling an toàn** — Task Scheduler chạy `auto-pull.ps1` định kỳ,
`git fetch` + `merge --ff-only`. Delay ≈ chu kỳ (mặc định 3 phút).

## Cài (chạy trên MÁY NHẬN — máy muốn tự cập nhật)

Mở **PowerShell**, `cd` vào thư mục repo, rồi:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev\install-auto-pull-task.ps1
```

Đổi chu kỳ (vd 5 phút): thêm `-Minutes 5`. Gỡ: thêm `-Uninstall`.

Xong. Từ giờ máy này tự kéo commit mới mỗi 3 phút. Xem hoạt động:
```powershell
Get-Content scripts\dev\auto-pull.log -Tail 10
```

## An toàn (script KHÔNG bao giờ phá việc đang làm)

| Tình huống | Hành vi |
|---|---|
| Đang sửa file (working tree bẩn) | **Bỏ qua** — không đụng tới |
| Có commit local chưa push (phân kỳ) | **Bỏ qua** — để bạn tự xử, không nuốt commit |
| Chỉ có commit mới trên remote | **Fast-forward** — kéo về |
| Mất mạng / GitHub lỗi | Bỏ qua lặng lẽ, thử lại chu kỳ sau |

- **Chỉ đồng bộ nhánh đang checkout.** Nhánh khác không đụng.
- Không rebase, không tạo merge commit tự động, không `reset --hard`.

## Điều kiện tiên quyết

1. Máy đã `git clone` repo + đăng nhập GitHub (credential đã lưu — vì đã
   push/pull được từ máy này thì OK). Script **không chứa token**.
2. Trên 2 máy nên `git config pull.ff only` để nhất quán.

## Nếu muốn tức thời (real-time) thay vì delay vài phút

Cần webhook (GitHub → máy bạn). Phức tạp hơn (mở cổng/reverse proxy hoặc
dùng smee.io). Với 2 máy cá nhân, polling 1-3 phút thường là đủ và đơn giản
hơn nhiều — khuyến nghị dùng cách này trước.
