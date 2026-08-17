# 2026-08-17 wezterm_mcp.py socket 发现修复施工计划

> **期望效果：** 重开 wezterm 窗口后，`list_panes` / `read_pane` / `send_to_pane` / `flush_pane` 仍能命中当前活跃窗口；杜绝 `wezterm cli` 连死 socket 时的 spawn 泄漏与挂起。
> **依据：** `Plan/2026-08-17_diagnosis_wezterm_mcp_socket_rediscovery.md`（诊断已取证）
> **施工方：** deepseek-v4 / Ecki — 2026-08-17（Alicia 拍板，不等独立验收方）

---

## 施工步骤

### Step 1：重写 socket 发现（`chatGPT_bridge/wezterm_mcp.py` Modify）

`_ensure_wezterm_socket()` → `_resolve_wezterm_socket() -> "Path | None"`：

- **每次现算，不写全局 env**（不再有模块级 `os.environ` 缓存污染）；
- 候选 = `_sock_dir().glob("gui-sock-*")` 按 mtime 倒序（新优先）；
- 探活 = **进程存活检查**（socket 文件名 `gui-sock-<pid>` 里的 PID，`OpenProcess` 查询；标准库 `ctypes`，零 spawn、零依赖，替代无 AF_UNIX 时的 `cli list` 探活）；
- 首个「文件存在 + 对应进程存活」即返回；全部死亡返回 `None`；
- env 中的 `WEZTERM_UNIX_SOCKET` 仅作为**额外候选**（补全路径后同样过 pid 探活；MCP 常驻进程 env 是旧的，不可直接信任）。

`_run_cli()` Modify：

- 每次调用 `sock = _resolve_wezterm_socket()`；
- `proc_env = dict(os.environ)`，`if sock: proc_env["WEZTERM_UNIX_SOCKET"] = str(sock)`（**完整路径**，实测 cli 只认完整路径）；
- `subprocess.run(..., env=proc_env, timeout=TIMEOUT)`，`TIMEOUT` 10.0 → 5.0（配合有效 socket，正常调用毫秒级）；
- 移除模块级 `_ensure_wezterm_socket()` 调用。

### Step 2：单测（`chatGPT_bridge/test_wezterm_mcp.py` Create）

对齐 `local_workspace/test_local_workspace.py` 模式（unittest + mock，不碰真实 socket/真实进程）：

- 候选「死 pid 新 + 活 pid 旧」→ 选中活 pid（mtime 优先但跳过死）；
- env 残留死值 → 不被采纳，glob 胜出；
- 全死 → `None`，`_run_cli` 返回 error 不挂起不 spawn；
- `_run_cli` 传给 subprocess 的 env 含 `WEZTERM_UNIX_SOCKET=完整路径`；
- 测试环境：mock `wezterm_mcp` 内 `mcp.server` 导入（测试运行器可能无 mcp SDK）。

### Step 3：部署清理（运维动作，报告第 3 条）

- 杀 14340（错环境实例 `exocore_project`）；
- 杀 21740（孤儿 venv 实例）；
- 杀 19012 / 32792（诊断探针 spawn 的残留 mux-server）；
- 保留 23916 / 33196（活动 GUI 的 mux）与两个 GUI 进程；
- 更新 README「后台化」小节：wezterm-pane 也纳入 `start_tunnel_services.ps1` 管理（或明确唯一拉起路径），避免错环境/孤儿残留。

### Step 4：验证

- 单测全绿（Step 2）；
- 集成：真实调用 `_run_cli("list", "--format", "json")` 命中当前窗口（35504）panes；
- 进程泄漏：连续 5 次失败路径（mock 全死）→ mux-server 数不增长；
- 收工：`git add` + commit 本计划与改动。

---

## 不变部分（Scope 边界）

- MCP 工具声明（4 个 tool 签名/行为）不动；`\r` 回车、HITL submit 门不动；
- 不引入第三方依赖（仍只依赖 mcp SDK + 标准库）；
- 不动 ExoCore / ExoCore-Extension 本体其他文件。

## 验证方式汇总

| 项 | 命令/步骤 | 预期 |
|---|---|---|
| 单测 | `C:/Users/Alicia/.venvs/wezterm-mcp-bridge/Scripts/python.exe test_wezterm_mcp.py`（或无 mcp SDK 则 `python.exe` + mock） | 全 PASS |
| 集成 | `python.exe -c "import wezterm_mcp; print(wezterm_mcp._resolve_wezterm_socket())"` | 返回 35504 完整路径 |
| cli 实调 | venv python 调 `_run_cli("list")` | 列出当前窗口 panes |
| 泄漏 | mock 全死候选 ×5 | mux-server 数不变 |

**署名：** deepseek-v4 / Ecki — 2026-08-17