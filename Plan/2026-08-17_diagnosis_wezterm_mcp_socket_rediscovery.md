# 2026-08-17 wezterm_mcp.py socket 发现失效诊断（待施工）

> **状态：** Pending 诊断记录（非施工计划）
> **问题：** 重开 wezterm 窗口后，索哥（ChatGPT 侧 MCP 客户端）无法找到当前活跃窗口——list_panes 拿不到/拿错窗格
> **同源历史：** ExoCore 本体 `2026-07-31_fix_workspace_socket_agentdirs.md` 已修复同构问题（死实例 socket mtime 反而更新）；本文件为 chatGPT_bridge 独立部署的同病复发
> **署名：** deepseek-v4 / Ecki — 2026-08-17

---

## 1. 现象

ChatGPT 里的索哥通过 Secure MCP Tunnel → `wezterm-pane` profile → `wezterm_mcp.py` 操作本机 WezTerm。
重开 wezterm 窗口（GUI 实例重启/新建）后，`list_panes` / `read_pane` / `send_to_pane` 均无法命中当前活跃窗口：
- list 结果为空 / 报错 / 挂起超时；
- 或列出的 panes 属于**旧 GUI 实例**（窗口 ID 错位）。

## 2. 现场取证（2026-08-17 21:2x）

### 2.1 进程与 socket 对照

| wezterm-gui PID | StartTime | socket 文件 | socket mtime |
|---|---|---|---|
| 32036 | 08-16 08:42 | `gui-sock-32036` | 08-16 08:42（旧实例，仍活着） |
| 35504 | 08-17 17:50 | `gui-sock-35504` | 08-17 17:50（新实例，当前活跃） |

- 另有 **4 个 wezterm-mux-server**：23916、33196（正常实例各自 mux）+ **19012、32792（21:25 被我的探针 spawn——见 §2.3 副作用）**
- **两个 wezterm_mcp.py 实例并存**：
  - PID 21740：`C:/Users/Alicia/.venvs/wezterm-mcp-bridge/Scripts/python.exe wezterm_mcp.py`（README 指定 venv，父进程 13268 已死=孤儿）
  - PID 14340：`E:\Miniconda3\envs\exocore_project\python.exe wezterm_mcp.py`（21740 的子进程，**用错了环境**——README 要求隔离 venv，却跑在共享 env）
- **没有 `tunnel-client run --profile wezterm-pane` 在跑**（只有 engram / local-workspace 两个 tunnel）——即索哥当前实际无隧道连接，或另有拉起路径；两 python 实例可能由 connector 周期性重建拉起的孤儿。

### 2.2 WEZTERM_UNIX_SOCKET 值格式敏感（cli 侧行为实测）

| 环境变量值 | `wezterm cli list` 结果 |
|---|---|
| 无 env（默认发现） | 快速失败 `failed to connect to Socket("gui-sock-35504")` |
| 裸文件名 `gui-sock-35504` | WARN "Will try spawning the server" → 挂起（>5s）→ spawn mux-server → 失败 |
| 完整路径 `C:/Users/Alicia/.local/share/wezterm/gui-sock-35504` | ✅ 成功列出 panes（window_id/pane_id 正常） |
| 完整路径 `.../gui-sock-32036` | ✅ 成功列出 panes（旧实例的窗口） |

结论：**wezterm cli 只认完整路径形式的 `WEZTERM_UNIX_SOCKET`**；写裸文件名/不写时，cli 会尝试 daemonize 新 mux-server 并长时间挂起而非快速失败。

### 2.3 探针副作用（重要）

我仅用 `timeout 5 env WEZTERM_UNIX_SOCKET=... wezterm cli list` 探测两次，就**新 spawn 了两个 mux-server（19012、32792）**并残留。即：
**每次 wezterm cli 连不上 socket → 自动尝试拉起新 mux-server → 进程泄漏。** 生产路径若 socket 失效，每次工具调用都泄漏一个 mux-server 进程并挂起 T≤10s（`TIMEOUT=10.0`）。

## 3. 根因分析（wezterm_mcp.py 自身缺陷）

> 文件：`ExoCore-Extension/chatGPT_bridge/wezterm_mcp.py`（L36-74 `_ensure_wezterm_socket` + L76-89 `_run_cli`）

### 根因 1（主）：socket 选择一次性 + 永不重新验证

```python
def _ensure_wezterm_socket() -> None:
    if os.environ.get("WEZTERM_UNIX_SOCKET"):   # ← 已有值就短路，永不复查
        return
    ...glob 按 mtime 从新到旧逐个试...
```

- `_ensure_wezterm_socket()` 在**模块加载时执行一次**（底部调用），之后每次 `_run_cli` 也调用；
- 但只要 `os.environ` 里已有 `WEZTERM_UNIX_SOCKET`，**直接 return，不验证旧 socket 是否仍存活**；
- MCP server 是**长驻 stdio 进程**（生命周期 = tunnel 会话），跨 wezterm 重开不退出；
- 重开窗口 → 旧 GUI 可能已死（socket 文件**残留**，Windows 不随进程删除）→ 进程 env 仍指向死 socket → **所有后续 cli 调用 100% 失败或挂起**；
- 重开窗口 → 新 GUI 起来（新 socket mtime 更新）→ 但进程**永远不会重新扫描**，除非重启。

### 根因 2：无 env 时依赖 wezterm cli 默认发现 = 不可靠

无 env 实测：cli 默认选 mtime 最新 socket，但连接失败（`failed to connect to Socket("gui-sock-35504")`）——35504 明明活着。
`_ensure_wezterm_socket()` 的兜底 glob 逻辑（逐个试）本可跳过死 socket，但：
- 它把 `str(sock)`（完整路径）写进 env——格式其实正确 ✅；
- 但**探活用的是 `wezterm cli list`（3s timeout）**：socket 死 → cli 尝试 spawn → 3s 超时跳过 → 若全部死，兜底失败 → 最终无 env → `_run_cli` 交给 cli 默认发现 → 又失败（见 §2.2 第一行）。
- **探活方式本身会 spawn mux-server + 挂起**（§2.3），且无法区分"旧实例还活着的 socket"与"当前活跃实例的 socket"——多实例并存时可能选中旧的（32036）而非当前（35504），此时探活会"成功"（cli 能列出），但列的是**旧窗口**。

### 根因 3：部署污染（次生，非 socket 根因）

- 14340 用 `E:\Miniconda3\envs\exocore_project` 跑 wezterm_mcp.py，违反 README「隔离 venv `wezterm-mcp-bridge`」约定；共享 env 若 mcp 版本不一致，`server/discover` 兼容性会退化。
- 孤儿进程 21740（父 13268 已死）残留，可能与 connector 周期性拉起 / 异常退出有关。

## 4. 与 ExoCore 本体修复版的差距（对照）

本体 `agents/tool_declarations/_helpers.py::_get_wezterm_socket_path()`（已修复）的正确模式：
1. **env 优先但校验**：`env_path.exists()` 才用，死了就当没有；
2. **glob 回退 + 探活**：`socket.socket(AF_UNIX).connect_ex(str(p)) == 0` 判活，**微秒级、不 spawn 任何进程**，跳过死实例；
3. **每次都现算**：不写入 os.environ 全局缓存（调用方注入 subprocess env），窗口重开后自然发现新 socket；
4. AF_UNIX 不可用时才退回 mtime 启发式。

chatGPT_bridge 版缺：
- ❌ 无 `exists()` 校验（env 短路）；
- ❌ 探活用 `wezterm cli list`（副作用大：spawn mux-server / 挂起 / 多实例无法选"当前活跃"）而非 AF_UNIX connect；
- ❌ socket 写进 os.environ 全局缓存，进程生命周期内永不重新发现；
- ❌ 无"多个活实例时选当前窗口"的判定（mtime 最新 + 探活通过 = 通常就是新窗口，可兼作判据）。

## 5. 修复方向（待施工计划细化，勿动工）

1. **对齐本体模式改 `_ensure_wezterm_socket`**：
   - 每次 `_run_cli` 现算 socket：env 值校验 `Path(...).exists()`（且应为完整路径格式；必要时补 `.resolve()`）；
   - glob 候选按 mtime 从新到旧，**AF_UNIX `connect_ex` 探活**（0.5s timeout），首个活的即用；无 AF_UNIX → 退回 mtime 最优先 + `cli list` 探活（保留但需防 spawn）；
   - **不全局写 env**：把 socket 路径作为**本次 subprocess 的 env** 注入（`proc_env = {**os.environ, "WEZTERM_UNIX_SOCKET": sock}`），避免缓存污染。
2. **防挂起/泄漏**：`_run_cli` 保持 TIMEOUT（建议降到 5s）；探活候选失败时一定不触发 cli spawn——用 AF_UNIX 探活替代 cli 探活即天然解决。
3. **清理部署**：杀掉 14340（错环境实例）与孤儿 21740，统一由 `start_tunnel_services.ps1` 托管 wezterm-pane profile 或至少 README 明确唯一拉起路径；清理残留 mux-server（19012、32792）。
4. **验证**：
   - 单测：mock socket 目录含"死旧 + 活新"两候选 → 断言选中活新；env 残留死值 → 断言被忽略并重新发现；
   - 集成：重开 wezterm 窗口前后各调一次 `list_panes` → 均返回当前窗口 panes；
   - 进程泄漏：连打 10 次失效调用 → mux-server 数不增长。

## 6. 已知限制/待讨论

- `wezterm cli` 无 `--socket` 参数（`cli list --help` 仅 `--format`）；唯一注入途径就是 env 变量，故 env 值格式（完整路径）必须保持。
- 多 GUI 并存时"当前活跃窗口"语义：mtime 最新 = 最近启动/聚焦的实例，作为近似判据足够；若后续需要精确聚焦窗口，可考虑 `cli list` 输出里 is_active 字段交叉验证。