# stop_tunnel_services.ps1 — 停止后台 tunnel-client services（三个托管 profile 全停）
# 用法: powershell -ExecutionPolicy Bypass -File stop_tunnel_services.ps1
# 安全: 只匹配 Name='tunnel-client.exe' 且命令行含 --profile <托管 profile 之一> 的进程，
#       绝不碰 WezTerm GUI / pane / 其他任何进程。
# 历史: 2026-09-20 前本脚本只杀 engram + local-workspace，而 start 启动三个 profile，
#       于是每轮 start 净增 1 个 wezterm-pane 残留（09-15 / 09-17 累积 3 个）。
#       残留是**活** dispatcher（各持有到隧道的 ESTABLISHED 连接），同一 tunnel 上
#       多实例会让 connector 可能把工具调用派给跑旧代码的旧实例。
#       现与 start 对称：start 启三个 → stop 停三个（start 亦会先调用本脚本，保证幂等）。
$ErrorActionPreference = "Stop"

$managedProfiles = @("engram", "local-workspace", "wezterm-pane")
$profilePattern = '--profile\s+(' + ($managedProfiles -join '|') + ')\b'

$targets = Get-CimInstance Win32_Process -Filter "Name='tunnel-client.exe'" |
    Where-Object { $_.CommandLine -match $profilePattern }

if (-not $targets) {
    Write-Host "no managed tunnel-client processes running"
    exit 0
}
foreach ($t in $targets) {
    Stop-Process -Id $t.ProcessId -Force
    Write-Host "stopped $($t.ProcessId)"
}
