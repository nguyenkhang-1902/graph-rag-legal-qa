# auto-pull.ps1 - Tu dong keo commit moi tu GitHub ve (fast-forward AN TOAN).
#
# Nguyen tac an toan (khong bao gio pha viec dang lam):
#   1. Chi fetch + merge --ff-only  -> KHONG rebase/merge tao commit, KHONG
#      de len commit local chua push, KHONG nuot file dang sua.
#   2. Working tree ban (co thay doi chua commit) -> BO QUA (khong dung toi).
#   3. Chi sync nhanh HIEN TAI dang checkout.
#   4. Ghi log ra file de debug.
#
# Dung cho: Task Scheduler chay dinh ky (vd moi 3 phut) tren MAY B (may
# nhan), trong khi MAY A push len GitHub. Delay = chu ky Task Scheduler.
#
# CACH CHAY TAY (test):
#   powershell -ExecutionPolicy Bypass -File scripts\dev\auto-pull.ps1
#
# Tham so:
#   -RepoPath : duong dan repo (mac dinh: thu muc cha cua scripts/dev)

param(
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
$logFile = Join-Path $RepoPath "scripts\dev\auto-pull.log"

function Write-Log($msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

try {
    Set-Location $RepoPath

    # git co ton tai?
    $null = & git rev-parse --is-inside-work-tree 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Log "KHONG phai git repo: $RepoPath"; exit 0 }

    $branch = (& git rev-parse --abbrev-ref HEAD).Trim()

    # 1. Working tree ban? -> bo qua, khong dung file dang sua.
    $dirty = & git status --porcelain
    if ($dirty) {
        Write-Log "[$branch] working tree BAN -> bo qua lan nay (khong dung file dang sua)."
        exit 0
    }

    # 2. Fetch nhanh hien tai (chi nhanh nay, khong tags rac).
    & git fetch --quiet origin $branch 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Log "[$branch] git fetch LOI (mang/GitHub?)."; exit 0 }

    # 3. Co upstream cho nhanh nay khong?
    $upstream = "origin/$branch"
    $null = & git rev-parse --verify $upstream 2>$null
    if ($LASTEXITCODE -ne 0) { Write-Log "[$branch] chua co $upstream tren remote -> bo qua."; exit 0 }

    $local  = (& git rev-parse HEAD).Trim()
    $remote = (& git rev-parse $upstream).Trim()

    if ($local -eq $remote) { exit 0 }   # da moi nhat, khong log cho do rac.

    # 4. Local co di truoc/di khac remote khong? Neu KHONG the ff -> bo qua,
    #    de nguoi dung tu xu (tranh nuot commit local chua push).
    $base = (& git merge-base HEAD $upstream).Trim()
    if ($base -ne $local) {
        Write-Log "[$branch] local va remote DA PHAN KY (co commit local chua push?) -> bo qua, can xu ly tay."
        exit 0
    }

    # 5. Fast-forward AN TOAN.
    & git merge --ff-only $upstream --quiet 2>$null
    if ($LASTEXITCODE -eq 0) {
        $short = $remote.Substring(0, 7)
        Write-Log "[$branch] da fast-forward -> $short  (keo commit moi thanh cong)."
    } else {
        Write-Log "[$branch] merge --ff-only LOI (bat thuong) -> bo qua."
    }
}
catch {
    Write-Log "EXCEPTION: $($_.Exception.Message)"
}
