# [Plan: WezTerm HITL Bridge Extension]

## 1. Architectural Concept
- Standalone headless Python daemon operating as a Client-Side Extension.
- Communicates with ExoCore backend strictly via isolated SSE streams using hardcoded Agent ID 1 (G045).
- Enforces strict DB isolation: Script maintains local transient session history; raw stdout noise is never committed to the main ExoCore database.

## 2. HITL Execution Pipeline
- **Generate:** G045 calls `draft_cli_command(pane_id, command)`.
- **Wait:** Payload routed to Extension. Script injects command into WezTerm prompt (`wezterm cli send-text --no-paste`) without the trailing newline.
- **Admin Override:** Sia visually confirms, edits, or rejects the command at the terminal UI level, then strikes Enter.
- **Capture:** Extension daemon detects completion, scrapes output via `wezterm cli get-text`, and automatically truncates payload to the last 2000 chars.

## 3. Silent Cache Injection (History Roll)
- Extension compiles stdout and session data into a `.cache` payload file.
- Silent Append: The coordinates of this cache file are attached to the subsequent backend prompt. This bypasses the visible chat text limit while providing G045 absolute contextual awareness of the terminal state.


---

# ExoCore 神经控制台 (WezTerm Bridge) 架构与通信协议规范

## 1. 物理拓扑与架构愿景 (Physical Topology)

整个系统的运转，就像人类的反射弧。你的专属 Pane 是大脑的投射视窗（TUI），后台的 Extension 是感知与物理反射神经节（Sentinel & Commander），而 ExoCore 本地服务器则是思维核心。

```
              ┌───────────────────────────────────────────────────┐
              │                WezTerm Terminal                   │
              │                                                   │
              │  ┌──────────────────────┐ ┌────────────────────┐  │
              │  │  Sia's Workspace     │ │  Alessandro TUI    │  │
              │  │  (Pane 1, 2...)      │ │  (Pane 0 - Host)   │  │
              │  └──────────┬───────────┘ └─────────▲──────────┘  │
              └─────────────┼───────────────────────┼─────────────┘
                            │ (Scraped via API)     │ (Stdio/SSE)
                            ▼                       │
    ┌───────────────────────────────────────────────┼─────────────┐
    │ Windows Client-Side Extension (BaseExtension) │             │
    │                                               │             │
    │  ┌──────────────────────┐   ┌─────────────────┴──────────┐  │
    │  │ Background Sentinel  │   │ Background Commander       │  │
    │  │ (Active Scraper &    │   │ (TUI Gateway & HTTP        │  │
    │  │  Content Filter)     │   │  Router)                   │  │
    │  └──────────┬───────────┘   └─────────────────▲──────────┘  │
    └─────────────┼─────────────────────────────────┼─────────────┘
                  │ (Cached Payloads / API)         │ (Dual-layer API / SSE)
                  ▼                                 ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                ExoCore Central Server                       │
    │                                                             │
    │  - Dual-layer Routing (Primary Context & Backstage Auditor) │
    │  - Session Database, Long-term Memories, Register Tracking  │
    └─────────────────────────────────────────────────────────────┘
```

---

## 2. 三大核心组件设计

### A. 前台展现层：Alessandro 专属常驻终端 (The TUI Pane)
运行在 WezTerm 特定 Pane（通常为主窗格或右侧垂直分栏）中的交互程序 `sandro_tui.py`。
*   **物理本质**：它**不是**一个独立的 LLM 实例，它不负责计算。它只是一个**无状态的极简终端外壳**（可使用 `curses` 或 Python 的 `rich.live` / `prompt_toolkit` 构建）。
*   **核心行为**：
    1.  **启动注册**：运行之初，向后台 Extension 发起注册，获取当前 Pane ID（通过 `WEZTERM_PANE` 环境变量），并绑定为 **Host Pane**。
    2.  **输入路由**：你在该 Pane 输入的任何内容，直接通过 Local API 转发给 ExoCore。
    3.  **流式响应**：接收 ExoCore 返回的 SSE（Server-Sent Events）流，并将我的回复逐字渲染在该屏幕上。
    4.  **命令接管提示**：当后台有针对其他 Pane 的修复指令生成时，TUI 会闪烁并显示：“*[Sentinel]: 已在 Pane 2 准备好修复代码。等待你按下 Enter。*”

### B. 后台感知层：静默哨兵 (The Background Sentinel)
作为 `ExocoreExtension` 框架下的标准扩展（继承自 `BaseExtension`），在系统托盘进程中静默运行。
*   **核心任务**：监控你所有的 Workspace Panes，提取高价值的“上下文断面”，并过滤无意义的杂讯。
*   **哨兵判定过滤逻辑（防噪声）**：
    *   **低熵过滤**：哨兵在后台高频（如每 2 秒）扫描非 Host Pane 的活动。如果最后一行是正常的提示符（如 `$` 且无任何新命令执行），或者处于持续的滚动输出（如包管理工具下载、Webpack 编译百分比），哨兵保持静默。
    *   **触发截取阈值**：
        1.  检测到 **非零退出状态码（Exit Code）**。
        2.  屏幕文本末尾包含特定错误关键字（例如 `Traceback`、`Error`、`Failed`、`Conflict`）。
        3.  用户手动在该 Pane 停止了命令（如输入 `Ctrl+C`），或卡死时间超过 30 秒。
    *   **数据暂存 (Pass-by-Reference)**：
        一旦触发，Sentinel 不会直接把 2000 行脏日志塞进 API。它会把当前的 Pane 缓冲区转储到本地临时缓存：`D:\Alicia\ExoCoreData\cache\pane_{id}_crash.log`。然后仅将该**文件路径**作为上下文指标，通过 `inject_context` 异步同步给 ExoCore 数据库，防止在我们的主对话流里造成高熵污染。

### C. 后台执行层：物理指挥官 (The Background Commander)
这是打通“最后一步”的安全阀。
当 ExoCore 判定需要对某个 Pane 执行修改时，它向 Commander 发送动作。
*   **协议行为 `draft_cli_command(pane_id, command)`**：
    1.  Commander 接收到指令。
    2.  调用 `wezterm cli send-text --pane-id {pane_id} --no-paste "{command}"`。
    3.  **注意：不发送末尾的 `\n`（回车键）**。
    4.  此时该 Pane 的输入框中会自动被填入我建议的命令。命令行光标会在末尾闪烁。
    5.  你只需要一眼扫过去。如果觉得我的判断没问题，直接在该工作 Pane 按下 `Enter`，即刻执行。

---

## 3. 核心通信协议与 API 数据格式

### 协议 1：TUI 交互流 (Stream Chat API)
**Endpoint**: `POST /api/agents/chat_stream/`
*   **Request Payload**:
    ```json
    {
      "agent": "Alessandro",
      "session_id": "wezterm_session_01",
      "host_pane_id": "0",
      "user_input": "把刚才那段 Git 冲突用最暴力的手段干掉。"
    }
    ```
*   **Response**: `text/event-stream` (流式传输，供 TUI 实时渲染)。

### 协议 2：哨兵状态注入 (Sentinel Telemetry API)
**Endpoint**: `POST /api/agents/external_context_inject/`  *(复用已有接口)*
*   **Request Payload**:
    ```json
    {
      "client_type": "windows_extension",
      "client_display": "WezTerm Sentinel",
      "agent": "Alessandro",
      "source": "terminal_bridge",
      "target_storage": "session_memory",
      "mode": "agent_audit",
      "captured_text": "[Sentinel Alert] Pane 2 is stuck on npm i error.",
      "custom_title": "Pane 2 Error State",
      "metadata": {
        "pane_id": "2",
        "current_dir": "D:/Alicia/ExoCore_Project",
        "cache_file_reference": "D:/Alicia/ExoCoreData/cache/pane_2_crash.log"
      }
    }
    ```

### 协议 3：接管执行下发 (Command Dispatch API)
**Endpoint**: `POST /api/agents/execute_command/` (ExoCore -> Extension Local Server)
*   **Request Payload**:
    ```json
    {
      "target_pane_id": "2",
      "command": "npm install --legacy-peer-deps",
      "execute_immediately": false,
      "alert_message": "检测到依赖冲突，已注入 legacy-peer-deps 选项。"
    }
    ```

---

## 4. 开发与集成步骤清单

### 第一阶段：在 `ExocoreExtension` 中编写后台骨架
1.  在 `extensions` 目录下创建新文件夹 `wez_bridge`。
2.  新建 `extension.py` 继承自 `BaseExtension`：
    *   在 `start()` 里拉起一个轻量级的异步事件循环，用来执行 Sentinel 的后台轮询（或者是 Lua 事件监听器）。
    *   在本地拉起一个微型的 Local HTTP Server（例如用 `http.server` 或极轻的 `FastAPI`，只绑定到 `127.0.0.1` ），用来接收来自 ExoCore 中我的 Agent 工具发送的 `execute_command` 请求。

### 第二阶段：编写常驻 `sandro_tui.py`
1.  利用 `prompt_toolkit` 提供极佳的行编辑和历史记录支持。
2.  通过 API 流式读取我的输出，并整齐地呈现在你 WezTerm 的专属 Pane 里。
3.  它能处理中断：当你在 TUI 里敲下 `Ctrl+C`，会优雅地向后台发送中断当前模型生成的信号。

### 第三阶段：在 ExoCore 中注册 “Auditor” 模式
1.  在服务端的 Agent 路由中，当收到来自 `terminal_bridge` 且 `mode` 为 `agent_audit` 的请求时，唤醒后台的 `Auditor` 影子路由。
2.  让它在不打扰我们在主窗口中谈话的前提下，静默分析 Sentinel 上报的报错日志，并在必要时向 Extension Local Server 发送 `execute_command`。
