# WezTerm HITL Bridge

WezTerm 人机协同桥接扩展。在后台静默监控你的工作终端，检测到错误后自动上报 ExoCore 审阅，并通过 HITL（Human-In-The-Loop）闸门将修复命令注入到目标 Pane —— 你只需看一眼，按下 Enter 即可执行。

```
┌─────────────────────────────────────────────────┐
│                   WezTerm                        │
│  ┌──────────────┐  ┌────────────────────────┐    │
│  │ 工作 Pane 1   │  │  Alessandro TUI        │    │
│  │ (被哨兵监控)   │  │  (Host Pane - 不监控)  │    │
│  └──────┬───────┘  └───────────▲────────────┘    │
│         │ 抓取文本              │ SSE 流式响应     │
└─────────┼──────────────────────┼─────────────────┘
          ▼                      │
  ┌──────────────────────────────┼─────────────────┐
  │  WezBridge Extension (本扩展)  │                 │
  │                              │                 │
  │  Sentinel ──→ CacheManager ──→ ExoCore         │
  │  (规则检测)    (本地缓存)       (special_extend) │
  │                              │                 │
  │  Commander ◄── LocalServer ◄── ExoCore         │
  │  (HITL 注入)   (:8777)        (execute_command) │
  └────────────────────────────────────────────────┘
```

## 三大组件

### Sentinel（哨兵）
- **检测方式**：关键词匹配（Traceback、Error、Failed 等 12 个关键词）+ 字符熵突变检测
- **轮询间隔**：2 秒（可配置）
- **防误报**：跳过 Host Pane、跳过重复内容、首次扫描不做熵检测
- **拦截后动作**：截取最后 2000 字符 → 本地缓存文件 → 上报 ExoCore

### Commander（指挥官）
- 接收 ExoCore 下发的命令
- **HITL 闸门**：命令注入到目标 Pane 输入区，**不带回车**
- 用户确认后手动按 Enter 执行

### TUI（沙德罗终端）
- `sandro_tui.py` — 独立脚本，运行在 WezTerm 某个 Pane 中
- 输入转发给 ExoCore `chat_stream` SSE 端点
- 流式渲染回复

## 启动方式

```bash
# 确保 conda 环境激活
conda activate exocore_project

# 启动系统托盘（加载所有扩展，包括 WezTerm Bridge）
python main.py
```

启动后输出：
```
[ExoCore] Starting extension: Clipboard Capture
[ExoCore] Starting extension: DST Bridge
[ExoCore] Starting extension: WezTerm Bridge
[WezTerm Bridge] Starting components...
[LocalCommandServer] Listening on 127.0.0.1:8777
[WezTerm Bridge] Host pane detected: 0
[WezTerm Bridge] All components started. Server: http://127.0.0.1:8777

[ExoCore] Extension Agent Assignments:
  Clipboard Capture        → Alessandro       (config default)
  DST Bridge               → Alessandro       (config default)
  WezTerm Bridge           → Alessandro       (config default)
```

### 启动 TUI（可选）
```bash
python sandro_tui.py
```

## 配置说明

所有配置在 `extensions/wez_bridge/config.py`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `HOST_PANE_ID` | `None` | TUI 所在 Pane，不监控。`None` 则自动检测当前活跃 Pane |
| `SENTINEL_POLL_INTERVAL_SEC` | `2.0` | 哨兵扫描间隔（秒） |
| `SENTINEL_TRUNCATE_OUTPUT_CHARS` | `2000` | 告警时保留的尾部字符数 |
| `SENTINEL_ENTROPY_THRESHOLD` | `10` | 低于此值视为低熵（静默提示符） |
| `LOCAL_SERVER_PORT` | `8777` | 本地 HTTP 服务端口 |
| `CACHE_DIR` | `D:\Alicia\ExoCoreData\cache` | Pane 转储缓存目录 |

### 更改哨兵使用的 Agent

哨兵上报使用 `special_extend` 模式，Agent 由扩展分配决定。修改方式：

编辑 `agent_registry.json`：
```json
{
  "version": 2,
  "agents": [...],
  "extension_assignments": {
    "WezTerm Bridge": "你想用的Agent名"
  }
}
```

不改则默认用 `Alessandro`。

## 工作流示例

1. 你在 Pane 2 跑 `npm install`，报了一堆 `ERESOLVE` 错误
2. 哨兵检测到关键词 `Error` + 内容突变 → 触发告警
3. Pane 2 内容被截取存入 `D:\Alicia\ExoCoreData\cache\pane_2_20260526_143021.log`
4. 上下文上报 ExoCore（`special_extend` 模式）
5. ExoCore Superior 链路分析错误，生成修复命令：
   ```
   npm install --legacy-peer-deps
   ```
6. ExoCore 调用本扩展的 `POST http://127.0.0.1:8777/api/agents/execute_command/`
7. Commander 将命令注入 Pane 2 输入区（不带回车）
8. 你在 Pane 2 看到命令，确认无误，按下 **Enter**
9. 命令执行，问题修复

## 托盘菜单

右击系统托盘图标：
- **WezTerm Bridge Status** — 打印当前 Pane 列表和服务器状态到控制台
- **Settings...** — 打开设置面板（由 Clipboard Capture 扩展提供）
- **Quit** — 退出所有扩展

## 文件结构

```
extensions/wez_bridge/
├── __init__.py          # 包标记
├── config.py            # 所有配置
├── wezterm_cli.py       # wezterm cli 子进程封装
├── cache_manager.py     # 本地缓存文件管理
├── sentinel.py          # 哨兵：Pane 监控 + 错误检测
├── commander.py         # 指挥官：HITL 命令注入
├── local_server.py      # 本地 HTTP 服务 (:8777)
├── extension.py         # 扩展协调器（BaseExtension 子类）
└── README.md            # 本文件

sandro_tui.py            # 独立 TUI 脚本（在 WezTerm Pane 内运行）
```
