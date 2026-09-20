# 2026-09-20 tunnel 服务生命周期修复（stop 对称化 + start 幂等）

> **期望效果：** engram / local-workspace / wezterm-pane 三个 profile 各**恰好一个**
> tunnel-client 实例；反复 `start` 不再累积残留。
> **依据：** 进程表实测（2026-09-20 13:40）+ git 历史（stop 脚本自创建起从未改过）。
> **施工方：** Ecki — 2026-09-20（Alicia 拍板 Option A：stop 也要 stop wezterm-pane）

## 根因（实测）

`start_tunnel_services.ps1` 管 **3** 个 profile（0b87c87 起 wezterm-pane 纳入），
`stop_tunnel_services.ps1` 只杀 **2** 个（`-match 'engram' -or 'local-workspace'`，
自 a95ce09 创建以来从未改过）→ **每轮 start 净增 1 个 wezterm-pane，stop 永不回收**。

残留实测（全部是**活** dispatcher，各持有到隧道的 ESTABLISHED 连接）：

| PID | 启动时间 | 来源 |
|---|---|---|
| 2332 | 09-15 09:05:11 | 某次 start |
| 21628 | 09-17 20:06:44 | 某次 start |
| 34392 | 09-17 21:44:20 | 某次 start |
| 32140 | 09-20 13:13:30 | 修复前最后一次 start（本次会话触发） |

WezTerm GUI 只有 1 个（pid 15096，socket `gui-sock-15096` 唯一）——问题不在 WezTerm
本身，也不在"多个 GUI"，而在 bridge 自己的进程管理。风险的实质：同一 tunnel 上多个
dispatcher，connector 可能把工具调用派给**跑旧代码**的旧实例（本次 `bash_readonly`
修复期间就是活例：若派到旧 local-workspace 实例会看到"修复未生效"假象）。

排查提示：`Start-Process -RedirectStandardOutput` 每次启动会**截断**日志，残留不会
留在日志里，只能看进程表。

## 施工步骤

### Step 1：`chatGPT_bridge/stop_tunnel_services.ps1`（对称化）
- 匹配条件由裸名改为 `--profile\s+(engram|local-workspace|wezterm-pane)\b`（更精确）；
- 头注释重写（原「绝不碰 wezterm-pane」语义已过时）+ 记录本次根因；
- 安全边界不变：只匹配 `Name='tunnel-client.exe'`，绝不碰 GUI / pane / 其他进程。

### Step 2：`chatGPT_bridge/start_tunnel_services.ps1`（幂等）
- 启动前先 `& (Join-Path $PSScriptRoot "stop_tunnel_services.ps1")` + `Start-Sleep 2`
  （已实测：被调脚本里的 `exit` 只退出它自身，不会带走调用方）；
- 尾部确认改为**逐 profile 计数**（`x0`/`x2` 一眼可见，直接暴露幂等失效）。

### Step 3：`chatGPT_bridge/README.md`（同步）
- 「后台化」小节：修正 stop 语义描述（原「只杀 engram / local-workspace」已过时），
  合并两段重复命令块；
- 「已知坑」补 2026-09-20 条目（start/stop 不对称 → 活残留累积 + 日志截断遮蔽）。

## 不做（Scope 边界）
- 不引入常驻看门狗、不把 tunnel-client 与 WezTerm GUI 硬生命周期耦合（Option C 已否）；
- 不做 status 巡检脚本（Option B，Alicia 未选）；
- 不改三个 profile 的 yaml、不改 tunnel-client 拉起方式、不动 MCP 工具面代码；
- 不放松 stop 的安全边界。

## 验证
1. 直接跑修好的 `start`（内部先 stop）：期望旧 6 个实例（含 09-15/09-17 三个残留）
   全清、新起 3 个，**每 profile 恰好 1 个**；
2. 再跑一次 `start`：实例数仍为 3（幂等；修前每跑一次 +1）；
3. 进程表核对：残留 PID 2332 / 21628 / 34392 消失；`wezterm-gui.exe`（15096）与
   `gui-sock-15096` 不受影响；
4. health url 刷新且 healthz=200（engram / local-workspace）。

## 提交
- 提交：`ExoCore-Extension` 仓，仅本 memo + 两个脚本 + README；
  不夹带 `.gitignore`、`Plan/2026-09-07_*`、`extensions/uhh_mail/`（均非本次改动）。
