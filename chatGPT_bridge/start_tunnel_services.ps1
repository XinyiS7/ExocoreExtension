# start_tunnel_services.ps1 — 后台启动 tunnel-client services（隐藏窗口 + 日志落盘）
# 用法: powershell -ExecutionPolicy Bypass -File start_tunnel_services.ps1
# 说明:
#   - 管理 engram + local-workspace 两个 profile，隐藏窗口后台运行
#   - wezterm-pane 不在管理范围（保持其手动 pane 方式，避免误伤索哥在用通道）
#   - 日志: ~/.config/tunnel-client/logs/<profile>.log（stdout）/ .err（stderr）
#   - 健康: ~/.config/tunnel-client/health-<profile>.url
$ErrorActionPreference = "Stop"

$profiles = @("engram", "local-workspace")
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
    Where-Object { $_.CommandLine -match 'engram' -or $_.CommandLine -match 'local-workspace' }
Write-Host "running tunnel-client (managed): $($running.Count)"