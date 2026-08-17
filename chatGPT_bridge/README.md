# chatGPT_bridge — ChatGPT ↔ WezTerm MCP 桥（3 profile 工具面）

把本机 WezTerm / 工作区文件 / Engram 记忆包装成 MCP 工具，通过 OpenAI Secure MCP
Tunnel 暴露给 ChatGPT developer-mode app。跑通后，ChatGPT 里的索哥可以自己
"列窗格 → 读内容 → 发文字"、读/改工作区文件、查/存记忆，不用再让 Alicia 复制粘贴。

## 架构：3 个 profile，3 个面

| profile | 面 | 工具 | server |
|---|---|---|---|
| `wezterm-pane`（已有） | 执行 | list_panes / read_pane / send_to_pane / flush_pane | `wezterm_mcp.py` |
| `local-workspace`（新增） | 文件 | read_file / write_file / edit_file / bash_readonly / list_dir | `local_workspace/local_workspace_mcp.py` |
| `engram`（新增） | 记忆 | mem_search / mem_get_observation / mem_context / mem_save / mem_update | engram 自带 MCP |

职责边界：**执行类命令一律走 wezterm pane**（Alicia 可见）；workspace 只碰文件，
bash 只读契约；engram 只碰记忆。每个 server 的安全声明都保持简单。

---

## wezterm-pane（执行面）

## 工具

| 工具 | 底层 wezterm cli | 说明 |
|---|---|---|
| `list_panes()` | `list --format json` | 拿 pane_id 的入口 |
| `read_pane(pane_id, tail_lines=50)` | `get-text --pane-id N` | 默认末 50 行，0 = 全部 |
| `send_to_pane(pane_id, text, submit=false)` | `send-text --no-paste` | 只填输入框；submit=true 才补发 `\r` |
| `flush_pane(pane_id)` | `send-text "\x03"` | Ctrl+C 清场（脏缓冲区先清再写） |

## 设计决策

- **薄封装**：参数组合照搬 `extensions/wez_bridge/wezterm_cli.py`（已验证）
- **HITL 门**：submit 默认 false，AI 手滑也不会直接执行命令
- **回车用 `\r`**：Windows / Git Bash 上 `\n` 不触发提交（extension 血泪教训）
- **无 shell 能力**：不存在任意命令执行面，最坏情况是往窗格里打字
- **WEZTERM_UNIX_SOCKET 自修复**：GUI 会把该变量注入 pane shell，但 stdio_client /
  tunnel-client 在 Windows 上会过滤环境变量把它丢掉，导致 cli 连不上 GUI socket
  （多 GUI 时发现逻辑还会翻车）。server 启动时会自动扫描 `~/.local/share/wezterm/`
  下的 `gui-sock-*`，挑一个能用的补回去。

## 本地自测

```bash
python.exe /tmp/test_wezterm_mcp.py
# 或任意 stdio MCP client 连 E:/Miniconda3/envs/exocore_project/python.exe wezterm_mcp.py
```

## 上线步骤（tunnel-client）

1. **下载二进制**：Platform tunnel settings 页面 → 下载 `tunnel-client`，
   放进 `C:\Users\Alicia\bin\`（已在 PATH，之后可直接敲 `tunnel-client`）。
2. **建 API key**：platform.openai.com → API keys → 新建，
   写入 `~/.wezterm_tunnel.env`（一行 `CONTROL_PLANE_API_KEY=sk-...`，勿外传）。
3. **一次性 init**（Git Bash）：

```bash
export CONTROL_PLANE_API_KEY=$(grep -o 'sk-[^[:space:]]*' ~/.wezterm_tunnel.env | head -1)

tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile wezterm-pane \
  --tunnel-id tunnel_6a81716005f48191bfa2efd17d0ae357 \
  --mcp-command "E:/Miniconda3/envs/exocore_project/python.exe D:/Alicia/ExoCore_Project/ExoCore-Extension/chatGPT_bridge/wezterm_mcp.py"
```

4. **体检**：`tunnel-client doctor --profile wezterm-pane --explain`
5. **上岗**（长驻，用索哥期间保持开启）：

```bash
export CONTROL_PLANE_API_KEY=$(grep -o 'sk-[^[:space:]]*' ~/.wezterm_tunnel.env | head -1)
tunnel-client run --profile wezterm-pane
```

建议给 tunnel-client 单独开一个 WezTerm pane 跑，方便随时看它的日志。

## local-workspace（文件面）

文件操作极薄封装，设计原则：

- **写锁死**：write_file / edit_file 的路径 resolve 后必须落在 `--root` 内，
  `..` / 绝对路径逃逸直接拒绝。没有第二个写入口。
- **bash 只读契约**：`cd ROOT && cmd` 显式锁 cwd（不依赖进程 cwd——tunnel-client
  拉起时 cwd 不可控），只允许查询类命令（rg / git status / diff / tail…）。
- **edit_file 全成或不动**：old_text 必须唯一命中，多块互不重叠，任一失败整个
  文件保持原样——大文件局部修改、git diff 干净。
- ROOT 来自 `--root` argv（写死在 profile command），默认 `D:/Alicia/ExoCore_Project`。

### 工具

| 工具 | 说明 |
|---|---|
| `read_file(path, offset=1, limit=2000, tail=false)` | UTF-8 阅读，带行号，超限截断 |
| `write_file(path, content)` | 全量写 / 新建（自动建父目录） |
| `edit_file(path, edits_json)` | 精确文本替换，一次多块，全成或不动 |
| `bash_readonly(cmd, timeout=30)` | 只读查询，`cd ROOT && cmd`，输出截断 |
| `list_dir(path, pattern, depth=1)` | 列目录，glob 过滤，最多 3 层 |

### 上线

```bash
export CONTROL_PLANE_API_KEY=$(grep -o 'sk-[^[:space:]]*' ~/.wezterm_tunnel.env | head -1)

tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile local-workspace \
  --tunnel-id tunnel_6a81716005f48191bfa2efd17d0ae357 \
  --health-listen-addr "127.0.0.1:0" \
  --mcp-command "C:/Users/Alicia/.venvs/wezterm-mcp-bridge/Scripts/python.exe D:/Alicia/ExoCore_Project/ExoCore-Extension/chatGPT_bridge/local_workspace/local_workspace_mcp.py --root D:/Alicia/ExoCore_Project"

tunnel-client doctor --profile local-workspace --explain  # 体检
tunnel-client run --profile local-workspace               # 上岗（额外一个 pane）
```

自测：`python.exe local_workspace/test_local_workspace.py`（28 例，monkeypatch 临时目录，不碰真实库）。

## engram（记忆面）

engram v1.19 自带 MCP server（stdio），直接挑 5 个工具挂上，零代码：

```bash
export CONTROL_PLANE_API_KEY=$(grep -o 'sk-[^[:space:]]*' ~/.wezterm_tunnel.env | head -1)

tunnel-client init \
  --sample sample_mcp_stdio_local \
  --profile engram \
  --tunnel-id tunnel_6a81716005f48191bfa2efd17d0ae357 \
  --health-listen-addr "127.0.0.1:0" \
  --mcp-command "C:/Users/Alicia/AppData/Local/gentle-ai/bin/engram mcp --tools=mem_search,mem_get_observation,mem_context,mem_save,mem_update --project exocore_project"

tunnel-client doctor --profile engram --explain
tunnel-client run --profile engram
```

注意 `--project exocore_project`（engram 侧的项目名，与 pi 侧一致）。
agent profile 全量 18 个工具，这里只挑索哥高频 5 个，避免工具列表冗余。

## 后台化（不占 pane）

三个 profile 中 wezterm-pane 延续手动 pane 方式（实现简洁且索哥在用）；
engram + local-workspace 由脚本隐藏窗口后台管理：

```powershell
# 启动
powershell -ExecutionPolicy Bypass -File start_tunnel_services.ps1
# 停止（只杀 engram / local-workspace，不碰 wezterm-pane）
powershell -ExecutionPolicy Bypass -File stop_tunnel_services.ps1
```

- 日志：`~/.config/tunnel-client/logs/<profile>.log`（stdout）/ `.err`（stderr）
- 健康：`~/.config/tunnel-client/health-<profile>.url`
- 常见病：用 `timeout`/`&` 之类在 Git Bash 里后台拉 tunnel-client 会逃逸残留
  进程（kill 不干净），造成同 profile 双实例；一律用上面的脚本管理。

---

## 运维

```bash
# 启动（新终端）
export CONTROL_PLANE_API_KEY=$(grep -o 'sk-[^[:space:]]*' ~/.wezterm_tunnel.env | head -1)
tunnel-client run --profile wezterm-pane

# 日志：~/tunnel-client.log（json 格式，ERROR 行排查用）
# 健康/Web UI：~/.config/tunnel-client/health.url 里记录的地址（随机端口）
# 停止：Ctrl+C（前台跑时）或 taskkill /IM tunnel-client.exe /F
```

**已知坑**：
- **8080 冲突（血泪）**：init 默认 `listen_addr: 127.0.0.1:8080`，多个 profile 同时 run 时
  后起的 bind 失败直接退出（滚动一堆 INFO 日志然后 ERROR `bind: Only one usage...`）。
  所有 profile 必须用 `--health-listen-addr "127.0.0.1:0"` 随机端口（README 各 init 命令已带）；
  还可以配 url_file 记录实际端口。已踩坑记录见 ExoCore_update_log（wezterm-pane 首次）。
- 8080 被 Docker/nginx 占用 → yaml 已改用 `127.0.0.1:0` 随机端口（health.url 会记录实际端口）
- Windows 上 stdio_client/tunnel-client 拉起子进程会过滤环境变量，
  wezterm_mcp.py 已内置 WEZTERM_UNIX_SOCKET 自修复，无需处理
- **server/discover（重要）**：ChatGPT connector 会周期性重建/刷新 tool 注册，
  向 MCP server 发 `server/discover`。mcp SDK <2.0.0（FastMCP）不认识这个方法，
  会 pydantic 报错，connector 判定注册失效 → 会话中途所有工具变
  "Resource not found"（list_panes 能成功、下一个 send_to_pane 就死）。
  修复：改用 mcp 2.0.0 的 `MCPServer`（FastMCP 被 2.0.0 移除，继任者就是这个）
  ——原生处理 server/discover。环境用**隔离 venv**，不动 ExoCore 共享环境：
  `C:/Users/Alicia/.venvs/wezterm-mcp-bridge`（mcp==2.0.0），
  由 profile 的 mcp-command 指向它。

## 环境与依赖

- wezterm_mcp.py 依赖 `mcp>=2.0.0`，跑在隔离 venv：
  `C:/Users/Alicia/.venvs/wezterm-mcp-bridge`（python 3.12）
- 升级方式：`python -m venv <venv> && <venv>/Scripts/python -m pip install mcp==2.0.0`
- profile 里 mcp-command 用 venv 的 python.exe 直接拉脚本（stdio）

## 验收标准（第一阶段）

在新 ChatGPT 聊天里说"按照 wezterm-pane-interaction skill 看一下其他 pane
在干什么"，索哥能自己调用 MCP 完成 `list_panes → read_pane`，并正确描述
各 pane 的内容，就算接通。

第二阶段（local-workspace + engram）：索哥能 `read_file` 读工作区代码、
`edit_file` 精确改一处、`bash_readonly` 跑 `git status`、`mem_search` 查到
一条旧记忆——四个面各通一个工具，就算接通。
