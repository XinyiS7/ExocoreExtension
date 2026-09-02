# start_tunnel_services.ps1 — 后台启动 tunnel-client services（隐藏窗口 + 日志落盘）
# 用法: powershell -ExecutionPolicy Bypass -File start_tunnel_services.ps1
# 说明:
#   - 管理 engram + local-workspace + wezterm-pane 三个 profile，隐藏窗口后台运行
#   - 日志: ~/.config/tunnel-client/logs/<profile>.log（stdout）/ .err（stderr）
#   - 健康: ~/.config/tunnel-client/health-<profile>.url
$ErrorActionPreference = "Stop"

# 显式指定 profile 目录：Windows 上 tunnel-client 默认去 %APPDATA%\tunnel-client 找，
# 但三个 yaml 实际在 ~/.config/tunnel-client（init 时写入的位置）。
# 不设置的话 run 秒挂：`read config file ...: The system cannot find the path specified`（2026-08-26 踩坑）。
$env:TUNNEL_CLIENT_PROFILE_DIR = "C:/Users/Alicia/.config/tunnel-client"

$profiles = @("engram", "local-workspace", "wezterm-pane")
$tunnelBin = "$env:USERPROFILE\bin\tunnel-client.exe"
$logDir = "$env:USERPROFILE\.config\tunnel-client\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

foreach ($p in $profiles) {
    $logOut = Join-Path $logDir "$p.log"
    $logErr = Join-Path $logDir "$p.err"
    Start-Process -WindowStyle Hidden `
        -FilePath $tunnelBin `
        -ArgumentList "run", "--profile", $p `
        -RedirectStandardOutput $logOut `
        -RedirectStandardError $logErr
    Write-Host "started $p -> stdout:$logOut"
}

# 确认
Start-Sleep -Seconds 3
$running = Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" |
    Where-Object { $_.CommandLine -match 'engram' -or $_.CommandLine -match 'local-workspace' -or $_.CommandLine -match 'wezterm-pane' }
Write-Host "running tunnel-client (managed): $($running.Count)"