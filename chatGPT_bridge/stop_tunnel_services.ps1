# stop_tunnel_services.ps1 — 停止后台 tunnel-client services（只动 engram + local-workspace）
# 用法: powershell -ExecutionPolicy Bypass -File stop_tunnel_services.ps1
# 安全: 只匹配命令行里含 engram / local-workspace 的进程，绝不碰 wezterm-pane
$ErrorActionPreference = "Stop"

$targets = Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" |
    Where-Object { $_.CommandLine -match 'engram' -or $_.CommandLine -match 'local-workspace' }

if (-not $targets) {
    Write-Host "no managed tunnel-client processes running"
    exit 0
}
foreach ($t in $targets) {
    Stop-Process -Id $t.ProcessId -Force
    Write-Host "stopped $($t.ProcessId)"
}