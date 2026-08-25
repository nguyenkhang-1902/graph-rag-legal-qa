# install-auto-pull-task.ps1 - Dang ky (hoac go) Task Scheduler chay
# auto-pull.ps1 dinh ky, de MAY NAY tu keo commit moi tu GitHub ve.
#
# CHAY (mo PowerShell tai thu muc repo):
#   Dang ky moi 3 phut (mac dinh):
#     powershell -ExecutionPolicy Bypass -File scripts\dev\install-auto-pull-task.ps1
#   Doi chu ky (vd 5 phut):
#     powershell -ExecutionPolicy Bypass -File scripts\dev\install-auto-pull-task.ps1 -Minutes 5
#   Go bo:
#     powershell -ExecutionPolicy Bypass -File scripts\dev\install-auto-pull-task.ps1 -Uninstall
#
# KHONG can quyen admin (dang ky task cho user hien tai). Task chay AN
# (khong hien cua so), ke ca khi khong dang nhap thi... (mac dinh chi chay
# khi user dang logon - du cho may lam viec).

param(
    [int]$Minutes = 3,
    [switch]$Uninstall,
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"
$taskName = "GraphRAG-AutoPull"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        "Da GO task '$taskName'."
    } else {
        "Task '$taskName' khong ton tai."
    }
    return
}

$script = Join-Path $RepoPath "scripts\dev\auto-pull.ps1"
if (-not (Test-Path $script)) { throw "Khong thay $script" }

# Action: chay powershell an, goi auto-pull.ps1 voi -RepoPath tuyet doi.
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -RepoPath `"$RepoPath`""

# Trigger: chay 1 lan luc dang ky, roi lap lai moi $Minutes phut, vo thoi han.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $Minutes)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

# Xoa task cu neu co (de cap nhat interval).
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Tu dong git fetch + fast-forward repo Graph-RAG moi $Minutes phut" | Out-Null

"Da DANG KY task '$taskName' - chay auto-pull moi $Minutes phut."
"Repo: $RepoPath"
"Xem log: scripts\dev\auto-pull.log"
"Go bo:  powershell -ExecutionPolicy Bypass -File scripts\dev\install-auto-pull-task.ps1 -Uninstall"
