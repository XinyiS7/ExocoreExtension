# 2026-09-07 wezterm_mcp.py socket 选中错实例诊断 + 修复方向（待施工）

> **状态：** Pending 诊断记录 + 修复方向（非施工计划，待施工方细化动工）
> **问题：** ChatGPT 侧擅自拉起新 WezTerm GUI 后，tunnel 的 `wezterm-pane` profile 工具调用全部命中新实例（看不到正在工作的 pane）；杀掉新实例后无法自动回落原实例，期间 `wezterm cli` 反复拉起 mux-server 造成阻塞/进程泄漏。
> **前史：** `Plan/2026-08-17_fix_wezterm_mcp_socket_rediscovery.md` 已修复「重开窗口后 socket 永不重发现」；本文件是**同一发现函数的下一层盲区**——多 GUI 并存时选中了错误的活实例。
> **署名：** deepseek-v4 / Ecki — 2026-09-07（Alicia 排查现场后要求记录）

---

## 1. 现象（2026-09-07 晚）

1. Alicia 正常在固定 WezTerm GUI（PID **26512**）协作施工；
2. ChatGPT 侧 agent 擅自开了一个**新的 wezterm 进程**（GUI **43564**，逻辑判断为 chat 拉起）；
3. 新进程的 socket `gui-sock-43564` mtime 更新 → `_resolve_wezterm_socket()`（2026-08-17 修复版）**mtime 倒序优先 + PID 探活通过** → 直接选中新实例；
4. 于是 `list_panes` / `send_to_pane` 全部命中**空的新窗口**，看不到正在工作的 pane（26512 里的面板）；
5. chat 发现不对，杀掉新进程 43564 —— 但 Windows **socket 文件残留**（`gui-sock-43564` 至今仍在目录里）；
6. 杀掉后 tunnel **没有自动回落**到仍存活的 26512——期间 chat 试图反复操作，每次失败路径都触发 `wezterm cli` spawn 新 mux-server（8-17 诊断 §2.3 已知副作用），造成进程堆积与命令阻塞，最终由 Alicia 手动重启三个 tunnel daemon 才恢复。

## 2. 现场取证（2026-09-07 21:1x，恢复后）

### 2.1 进程与 socket 对照

| wezterm-gui PID | 状态 | socket 文件 | socket mtime | 备注 |
|---|---|---|---|---|
| 26512 | 🟢 活着（当前活动 GUI） | `gui-sock-26512` | 22:23 | env `WEZTERM_UNIX_SOCKET` 指向它 |
| 43564 | 💀 已死（chat 开过的新实例） | `gui-sock-43564` | 15:34 | **残留文件**，PID 无进程 |

- 另有 `wezterm-mux-server.exe` PID 40708（活）—— 待确认归属；
- 三个 tunnel-client daemon 全部已由 `start_tunnel_services.ps1` 重新拉起（healthz 200 ✅）。

### 2.2 当前 `_resolve_wezterm_socket()` 的候选策略（2026-08-17 修复版）

```python
socks = sorted(glob("gui-sock-*"), key=mtime, reverse=True)  # 新优先
env_val = os.environ.get("WEZTERM_UNIX_SOCKET")
if env_val: socks.append(env_path)                            # env 仅追加到【末尾】
for sock in socks:
    pid = _socket_pid(sock)
    if pid is not None and _pid_alive(pid):                    # OpenProcess 探活
        return sock
return None
```

### 2.3 关键事实

1. `_pid_alive()` 只查 **PID 是否存活**，**不校验该 PID 是不是 wezterm-gui/wezterm-mux-server**；
2. env 里的 `WEZTERM_UNIX_SOCKET`（指向启动 tunnel 时的 GUI = 通常是**正在工作的实例 26512**）被排在候选**末尾**，永远最后一个试；
3. 因此：只要存在任何一个「mtime 更新 + PID 存活」的 GUI（哪怕是 chat 刚开的空窗口），正确实例 26512 就**永远不会被选中**；
4. 杀掉 43564 后其 socket 文件残留但 PID 死——本应靠探活跳过它选 26512，但：
   - 若 chat 反复开/杀进程，**PID 可能被 Windows 复用**（探活误判"活着"→ 选死 socket → cli spawn mux-server → 挂起/积压）；
   - 或 chat 操作期间又拉起了别的存活 wezterm 进程，继续抢占 mtime 首位。

## 3. 根因分析（2026-08-17 修复版的残余盲区）

| # | 缺陷 | 后果 |
|---|---|---|
| 1 | **探活只看 PID 存活，不验进程身份**（`OpenProcess` 后未用 `QueryFullProcessImageName` 等核对 `wezterm-gui.exe`/`wezterm-mux-server.exe`） | PID 复用 → 死 socket 被当作活候选 → `wezterm cli` 连死 socket 自动 spawn mux-server（8-17 §2.2 已实测）→ 挂起 + 泄漏 |
| 2 | **env 里的 `WEZTERM_UNIX_SOCKET` 只在末尾兜底**，而它恰恰指向「启动 tunnel 的那个 pane 所在 GUI」（通常=用户正在工作的实例） | 任意新 GUI 存活即可永久抢占正确实例；「新窗口优先」本意是重开后找新窗口，但没考虑「chat 乱开窗口」场景 |
| 3 | socket 文件残留（Windows 不随进程退出清理）与 mtime 排序结合，放大了 1、2 的误判面 | 死实例文件长期占据候选列表首位（若其 PID 恰好被复用 → 持续选错） |
| 4 | 失败路径的 mux-server spawn 副作用无进程数护栏 | 反复失败工具调用 = 反复泄漏 mux-server，最终表现「阻塞」 |

## 4. 修复方向（建议；具体施工计划由施工方细化，勿直接动工）

### 4.1 探活升级：PID 存活 + 进程身份校验（主修复）

`_pid_alive(pid)` 之后（或之内）增加：
- `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, ...)` 成功 → 取 `QueryFullProcessImageName`（或 `GetModuleFileNameEx`）→ 断言 basename ∈ {`wezterm-gui.exe`, `wezterm-mux-server.exe`}；
- 失败/名不符 → 视为死候选，跳过。
- **效果：** PID 复用误判归零；残留 socket 文件永远不会被选中；cli 永远不会拿到死 socket → 不再触发 spawn 副作用。

### 4.2 候选优先级调整：env 活实例 > mtime 扫描（次修复）

- `WEZTERM_UNIX_SOCKET` 指向的 socket **若通过完整探活（4.1）→ 首选**（它是启动 tunnel 时的活动实例，最符合「正在工作的 pane」语义）；
- env 失效 → 退回 mtime 倒序扫描（新实例优先，保留 8-17 的「重开后找新窗口」能力）；
- 非绝对路径的 env 值补全为完整路径（8-17 已实现的逻辑保留）。
- **保留其他约束：** 每次现算、不写全局 env（8-17 已实现，不动）；子进程 env 注入完整路径。

### 4.3 失败路径护栏（建议项）

- 全部候选探活失败 → `_run_cli` 快速返回 error（现状已由 `None` 兜底 + TIMEOUT 5s 控制），**确保绝不把失效 socket 交给 cli**；
- 可考虑在 bridge 侧记录失败计数，连续 N 次失败提示人工介入（可选，不强制）。

### 4.4 运维清理（施工时顺带）

- 检查并清理残留孤儿 mux-server（本次事件可能又泄漏）；确认 `start_tunnel_services.ps1` 是 wezterm-pane profile 的唯一拉起路径；
- 验证 3 个 tunnel daemon 重启后 healthz 正常（本次已由 Alicia/Ecki 手动完成）。

## 5. 验证方式（建议）

| 项 | 命令/步骤 | 预期 |
|---|---|---|
| 单测 | `test_wezterm_mcp.py` 增加用例：活候选含「非 wezterm 同名 PID」→ 跳过；env 指向活 GUI → env 优先于 mtime 更年轻候选；env 死 + 残留 socket + PID 复用 → 不选中 | 全 PASS |
| 集成 1 | 保留两个 GUI（26512 + 新开 43564 场景）→ `_resolve_wezterm_socket()` 应返回 26512 | env 实例胜出 |
| 集成 2 | 杀掉新实例后连续 5 次 `_run_cli("list")` → 始终命中 26512 pane 列表 | 自动回落 ✅ |
| 泄漏 | mock 全死候选 ×5 → mux-server 进程数不增长 | 无 spawn 副作用 |
| 回归 | 重开 wezterm 窗口（旧实例死亡、新实例接管）→ 工具调用命中新窗口 | 8-17 修复行为不回退 |

## 6. Scope 边界（不变部分）

- MCP 工具声明（4 个 tool）与 `\r` 回车 / HITL submit 门控不动；
- 不引入第三方依赖（仍只 mcp SDK + 标准库 + ctypes）；
- 不动 ExoCore / ExoCore-Desktop / ExoCore-Extension 其他文件；不动 tunnel-cli 版本；
- 施工完成前不 commit，走 builder →（Alicia 拍板）→ 验收链。

---

**待决：** 修复方向 4.1+4.2 是否采纳；若采纳，由 ExoCore-Extension 施工方细化步骤并实施。