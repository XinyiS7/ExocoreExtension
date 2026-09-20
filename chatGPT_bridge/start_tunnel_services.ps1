# start_tunnel_services.ps1 — 后台启动 tunnel-client services（隐藏窗口 + 日志落盘）
# 用法: powershell -ExecutionPolicy Bypass -File start_tunnel_services.ps1
# 说明:
#   - 管理 engram + local-workspace + wezterm-pane 三个 profile，隐藏窗口后台运行
#   - **幂等**：启动前先调用 stop_tunnel_services.ps1，保证「每个 profile 恰好一个」
#     （2026-09-20 前 stop 漏 wezterm-pane，反复 start 会累积活残留实例）
#   - 日志: ~/.config/tunnel-client/logs/<profile>.log（stdout）/ .err（stderr）
#   - 健康: ~/.config/tunnel-client/health-<profile>.url
$ErrorActionPreference = "Stop"

# 显式指定 profile 目录：Windows 上 tunnel-client 默认去 %APPDATA%\tunnel-client 找，
# 但三个 yaml 实际在 ~/.config/tunnel-client（init 时写入的位置）。
# 不设置的话 run 秒挂：`read config file ...: The system cannot find the path specified`（2026-08-26 踩坑）。
$env:TUNNEL_CLIENT_PROFILE_DIR = "C:/Users/Alicia/.config/tunnel-client"

# ── 幂等前置：先把已有托管实例全部停掉 ──
# （被调脚本里的 exit 只退出它自身，不会带走本脚本——已实测）
& (Join-Path $PSScriptRoot "stop_tunnel_services.ps1")
Start-Sleep -Seconds 2

$profiles = @("engram", "local-workspace", "wezterm-pane")
$profilePattern = '--profile\s+(' + ($profiles -join '|') + ')\b'
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

# 确认：每个托管 profile 应恰好 1 个实例（>1 就是幂等失效，需排查）
Start-Sleep -Seconds 3
$running = Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" |
    Where-Object { $_.CommandLine -match $profilePattern }
Write-Host "running tunnel-client (managed): $($running.Count)"
foreach ($p in $profiles) {
    $n = @($running | Where-Object { $_.CommandLine -match "--profile\s+$p\b" }).Count
    Write-Host ("  {0,-16} x{1}" -f $p, $n)
}
