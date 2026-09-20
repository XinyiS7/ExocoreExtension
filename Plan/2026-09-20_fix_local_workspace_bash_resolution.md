# 2026-09-20 local_workspace bash 解析修复（WSL 劫持 + 路径域）

> **期望效果：** `bash_readonly` 稳定跑在 Git Bash 里（不再被 System32 的 WSL 启动器劫持）；
> ROOT 交给 shell 前转成 Git Bash 语法（`/d/...`）；工具入参 `/d/...`（WezTerm pane 里看到的形式）
> 与 `D:/...` 两种写法都能用。
> **依据：** 本 memo「根因」一节 —— 干净会话 PATH 下的实测复现（探针见「验证」）。
> **施工方：** Ecki — 2026-09-20（Alicia 拍板：不碰 WSL、引号要修、短 memo 够用）

## 根因（实测，非推测）

`bash_readonly` 用 `shutil.which("bash")` 解析 shell。tunnel-client 由 PowerShell
（`start_tunnel_services.ps1`）拉起，干净会话 PATH 第一位是 `C:\WINDOWS\system32` ——
那里有 WSL 的 `bash.exe`；而 Git 只把 `cmd\`（里面**没有** bash.exe）放进 PATH，
真正的 `bin\bash.exe` **不在 PATH 上**。实测：

| 探针（干净 PATH） | 结果 |
|---|---|
| `shutil.which("bash")` | `C:\WINDOWS\system32\bash.EXE`（WSL 启动器） |
| 该 bash 跑 `cd D:/Alicia/ExoCore_Project` | rc=1 `/bin/bash: line 1: cd: D:/Alicia/...: No such file or directory` |
| Git Bash 跑同一条命令 | rc=0 → `/d/Alicia/ExoCore_Project` |

两点推论：

1. **Git Bash 自己兼容 `D:/...`** —— 所以"路径格式没转换"不是本次挂掉的直接原因，
   报错前缀 `/bin/bash:`（Git Bash 会说 `/usr/bin/bash:`）才是真凶口音；
2. **只做路径转换会更糟**：这台机器的 WSL 把盘挂在 `/d`，`cd /d/...` 在 WSL 里会**成功**，
   命令静默跑进 WSL Ubuntu（`MSYSTEM=<none>`、无 conda / wezterm、drvfs 语义）——
   bug 表面消失、实际换错环境。故顺序必须是：**先钉死 bash，再做路径域转换**。

同源教训后端已有：`ExoCore/core/shell.py::_resolve_bash_exe()`
（"NEVER spawn the bare name bash.exe ... Observed 2026-08-16 after WSL was installed"）。

修复前真实环境快照：`25 passed, 3 failed`（3 条 bash 用例复现索哥报错原文）。

## 施工步骤

### Step 1：bash 解析（`chatGPT_bridge/local_workspace/local_workspace_mcp.py` Modify）
- 新增 `_is_wsl_launcher(p)`：路径段含 `system32` 或 `windowsapps` 即判 WSL 启动器
  （WindowsApps 那个实测是 `wsl.exe` 的软链，属同源陷阱）；
- 新增 `_resolve_bash_exe() -> str | None`：`which("bash.exe")` → 过滤 WSL 启动器 →
  显式查 `%ProgramW6432%` / `%ProgramFiles%` / `%ProgramFiles(x86)%` 下的
  `Git\bin\bash.exe`；全落空返回 `None`；
- **不退回裸 `"bash"`**（与后端唯一分歧：bridge 的故障模式恰是"静默进 WSL"，而裸名会被
  CreateProcess 的 System32 优先规则再次劫持）；落空时 `bash_readonly` 明确报错 + 给出期望路径。
  移除旧 `GIT_BASH` 常量。

### Step 2：路径双域转换（对齐 `ExoCore/core/shell.py` 的 MSYS 处理）
- `_to_windows(s)`：`/d/Alicia/...` → `D:\Alicia\...`；Windows 写法原样返回；**不认 `/mnt/...`**；
- `_to_bash(p)`：`D:\Alicia\...` → `/d/Alicia/...`；
- `_resolve()` 与 `--root` 入口先过 `_to_windows`（沙箱检查逻辑不变，仍在转换后执行）。

### Step 3：`cd` 引号加固 + 可观测性
- `_sh_quote(s)` 单引号包裹（内部 `'` → `'\''`）；`script = f"cd {_sh_quote(bash_root)} && {cmd}"`；
- hint 行改为 `rc=… | bash=… | cwd=/d/…`：本次故障就是"到底哪个 bash 在跑"不可见，
  显式暴露出来。

### Step 4：单测（`local_workspace/test_local_workspace.py` Modify）
- `_is_wsl_launcher`（System32 / WindowsApps 判真、Git 路径判假）；
- `_resolve_bash_exe`：**结果存在 且 非 WSL 启动器**（根因永久锁）+ 指向 Git 安装；
- `_to_windows` / `_to_bash` 对照表（含 `/mnt/d/...` 原样返回 = 明确不支持 WSL）；
- `_resolve(_to_bash(inside_root))` 命中；`/d/...` 越界仍拒绝；
- ROOT 含空格目录下 `bash_readonly("pwd && cat 'sp probe.txt'")` 正常（引号锁）；
- 原 `bash cwd locked` 断言改为**真断言**：`pwd` 输出/hint 的 cwd 为 bash 域（`/c/...`），
  并显式断言不出现 Windows 域（该老断言原为假通过：匹配到 hint 字符串而非真实 pwd）。

### Step 5：README（`chatGPT_bridge/README.md` Modify）
- local-workspace 设计原则补一行（shell 固定 Git Bash + 双写法入参 + 不做 WSL 支持）；
- 「已知坑」补 2026-09-20 条目（WSL 劫持机制 + 与后端同源）；
- 自测例数更新。

## 不做（Scope 边界）
- 文件工具 API 保持 Windows 域（`read_file` / `write_file` / `edit_file` / `list_dir` 行为与输出不变）；
- **不重写命令体**（Git Bash 两域都吃；正则改写会破坏 `rg 'D:\\foo'` 之类模式）；
- 不提供任何 WSL 支持，不往 WSL 区域写任何东西；
- 不动 `wezterm_mcp.py` / engram profile / GitHub 相对路径面；
- 不引入第三方依赖（仍 mcp SDK + 标准库）；
- 不加启动期 shell 探测（保持极薄；解析结果由 hint 行与单测暴露）。

## 验证
1. 单测全绿（含新增根因锁）；分别在 Git Bash 环境与**干净会话 PATH**（真实启动环境）下各跑一遍；
2. `_resolve_bash_exe()` 在真实环境解析到 Git Bash，`bash_readonly("pwd")` 的 cwd 为 `/d/...`；
3. E2E（需重启 profile 才生效）：`stop_tunnel_services.ps1` → `start_tunnel_services.ps1`
   （只动 engram + local-workspace，不碰 wezterm-pane），ChatGPT 侧索哥重跑
   `bash_readonly("pwd")` + `read_file("/d/Alicia/ExoCore_Project/AGENT.md")`。

### 验证结果（2026-09-20 实测）

| 检查 | 修复前 | 修复后 |
|---|---|---|
| 测试套件（干净会话 PATH） | 25 passed / 3 failed | **45 passed / 0 failed** |
| `_resolve_bash_exe()`（干净会话） | System32 WSL 启动器 | `C:\Program Files\Git\bin\bash.exe` |
| `bash_readonly("pwd")` | rc=1 `No such file or directory` | rc=0 → `/d/Alicia/ExoCore_Project` |
| `bash_readonly("git … rev-parse")` | 不可用 | rc=0 → `main` |
| `read_file("/d/Alicia/.../AGENT.md")` | 拒绝（escapes workspace root） | 正常读取 |
| 文件工具 / list_dir 行为 | — | 不变（回归通过） |

环境侧不变（`which bash` 仍是 System32 WSL）——修的是 bridge 自己的解析，不动系统 PATH。
Git Bash 环境与干净会话环境两轮均 45/45；E2E（第 3 项）待重启 profile 后由 ChatGPT 侧确认。

## 提交与文档
- 提交：`ExoCore-Extension` 仓，仅本 memo + bridge 三文件（脚本/测试/README），不夹带他人在途改动；
- `Plan/update_log.md`：**不更新**（既有惯例：chatGPT_bridge 的修复不入 update_log，见 190ef81 / 0ab1c0d / a95ce09）。
