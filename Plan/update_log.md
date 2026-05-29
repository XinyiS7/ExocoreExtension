# WezTerm Bridge (wez_bridge)

## 哨兵手动开关 + 后台活动标记 + 去熵值误报

**需求：** 哨兵不应自启动，需用户手动 `/sentinel on` 开启（离开屏幕前）。哨兵告警与用户聊天需在 payload 中区分，后端据此处理为后台活动。熵值翻转检测误报率太高（正常终端输出全触发），砍掉只保留错误关键词匹配。

**方案：**
- `start()` 不再调用 `self._sentinel.start()` —— 哨兵默认关闭，启动时打印提醒
- 新增 `POST /api/agents/sentinel/toggle/` 端点，接受 `action: "start"|"stop"|"status"`，返回 `sentinel_running` 布尔值
- sandro_tui.py 新增 `/sentinel [on|off]` 命令，`/status` 集成哨兵状态显示
- `_on_sentinel_alert` 中传递 `mode="wez_bridge_sentinel"` + `activity_type="sentinel_auto"` 给 `route_to_exocore`，后端可据此识别为后台自动活动（区别于用户聊天的 `mode="wez_bridge"`）
- `message_router.route_to_exocore` 新增 `mode` 和 `activity_type` 可选参数，透传到 `build_inject_payload`
- 哨兵告警保持 daemon thread 异步发射，不阻塞轮询循环
- `sentinel._should_alert` 移除熵值翻转检测逻辑 —— task list、git status、进度条等正常输出不再是误报源，仅错误关键词触发告警
- `test_extension.py` 更新：哨兵启动断言改为 `assert_not_called`，路由数 5→8

**涉及后端：**
- 新端点 `POST /api/agents/sentinel/toggle/`（Extension 侧，非后端）
- `external_context_inject` payload 新增可能字段：
  - `mode: "wez_bridge_sentinel"` — 哨兵自动告警
  - `activity_type: "sentinel_auto"` — 后台活动标记
- 后端收到 `mode == "wez_bridge_sentinel"` 或 `activity_type == "sentinel_auto"` 时应作为后台活动处理，不与用户聊天混入同一对话流

**本地改动摘要：**
| 文件 | 变更 |
|------|------|
| `extensions/wez_bridge/extension.py` | 修改 — 哨兵不自启 + `_on_sentinel_toggle` handler + 告警 payload 带 mode/activity_type |
| `extensions/wez_bridge/message_router.py` | 修改 — `route_to_exocore` 接受 `mode` / `activity_type` 参数 |
| `extensions/wez_bridge/sentinel.py` | 修改 — `_should_alert` 移除熵值翻转，仅保留关键词匹配 |
| `extensions/wez_bridge/local_server.py` | 修改 — +`/api/agents/sentinel/toggle` 路径 |
| `sandro_tui.py` | 修改 — +`/sentinel` 命令 + `/status` 集成哨兵状态 + `/help` 更新 |
| `tests/wez_bridge/test_extension.py` | 修改 — 哨兵不自动启动 + 路由数 8 |

**日期 & 署名：** 2026-05-29 · Extension Team (Alessandro)

---

## 上下文缓存释放端点

**需求：** 手动释放 Gemini 上下文缓存。由 compact skill 或手动触发。

**方案：**
- 新增 `POST /api/agents/cache/release/` 端点，调用后端 `POST /api/agents/cache/invalidate/`
- 接受可选 `agent_name`，默认使用扩展的默认 agent

**涉及后端：** 已有 `POST /api/agents/cache/invalidate/` 端点

**本地改动摘要：**
| 文件 | 变更 |
|------|------|
| `extensions/wez_bridge/extension.py` | 修改 — +`_on_cache_release` handler |
| `extensions/wez_bridge/local_server.py` | 修改 — +`/api/agents/cache/release` 路径 |

**日期 & 署名：** 2026-05-29 · Extension Team (Alessandro)

---

## 哨兵告警去重

**需求：** 同一 pane 的相同内容在 30s 内不重复告警。

**方案：** 哨兵维护 `(pane_id, text_hash)` → 上次告警时间的映射，30s 内相同 hash 跳过。

**涉及后端：** 无

**日期 & 署名：** 2026-05-29 · Extension Team (Alessandro)

---

## CLI Agent TUI 接入 + /chat 端点

**需求：** sandro_tui.py 接上 wez_bridge 本地 daemon，用户在下方面板通过 prompt_toolkit 交互界面直接打字对话，获得 CLI agent 手感。支持 `/agent`、`/resume`、`/sessions`、`/new` 等命令。

**方案：**
- 新增 `POST /api/agents/chat/` 端点 — 接收用户消息，自动创建/恢复 session，添加消息，route_to_exocore，返回回复
- MessageRouter 将 ExoCore 返回的 `reply` 存入 `session.metadata["last_reply"]`，_on_chat 读取返回给 TUI
- sandro_tui.py 全量重写 — 不再直连 ExoCore chat_stream，改为通过 wez_bridge 本地 HTTP 代理
- TUI 状态管理（`TuiState`）：跟踪当前 session_id、agent_name、summary
- 命令系统：`/agent <name|id>`（切换 agent）、`/resume [idx]`（选择恢复近期会话）、`/sessions`（列出）、`/new`（新建）、`/status`（当前状态）、`/help`、`/clear`
- `_resolve_agent_for_session` 支持 `session=None` 参数，用于新 session 创建时确定初始 agent

**涉及后端：** 无（纯 extension 侧 TUI ↔ wez_bridge 内部接口）

**本地改动摘要：**
| 文件 | 变更 |
|------|------|
| `sandro_tui.py` | 重写 — TUI 接 wez_bridge，命令系统，状态管理 |
| `extensions/wez_bridge/extension.py` | 修改 — +_on_chat handler + chat 路由注册 + _resolve_agent_for_session 兼容 None |
| `extensions/wez_bridge/local_server.py` | 修改 — +/api/agents/chat 路径 |
| `extensions/wez_bridge/message_router.py` | 修改 — route_to_exocore 存储 last_reply 到 session metadata |

**日期 & 署名：** 2026-05-29 · Extension Team (Alessandro)

---

## 多轮对话 & Agent-Supervisor 独立化

**需求：** wez_bridge 从被动哨兵升级为独立的 agent-supervisor 工具。支持多轮对话 session 管理（与 pane 解耦，48h TTL，仿 Claude Code resume），双重信息接收渠道（哨兵 + Superior 直接消息），向 ExoCore 发送全量格式化 context。

**方案：**
- 新增 SessionManager（Session CRUD + JSON 持久化 + 48h 自动清理，摘要=首条消息前20字）
- 新增 ContextBuilder（Session → ExoCore wez_bridge payload 格式化，messages 数组 + captured_text 纯文本 fallback）
- 新增 MessageRouter（双渠道路由：sentinel→ExoCore context_inject / Superior→pane 直接消息）
- 增强 LocalCommandServer（5 端点：execute_command / send_message / session new / resume / list）

**涉及后端：**
- API contract: `mode=wez_bridge`, `messages[{role,content}]`, `external_session_id` 回传
- `compacted_up_to` 压缩游标（>30条自动压缩旧消息→摘要，保留最近15条）
- `external_context_inject` 响应新增 `session_type_used` 字段
- 后端 `ExternalContextService` 实现 wez_bridge 模式
- 工具组：`WEZ_BRIDGE` = write_private_log + update_register + wezterm_cli + my_files

**本地改动摘要：**
| 文件 | 变更 |
|------|------|
| `extensions/wez_bridge/session_manager.py` | 新建 — Session/Message 数据结构 + CRUD |
| `extensions/wez_bridge/context_builder.py` | 新建 — wez_bridge payload 组装 |
| `extensions/wez_bridge/message_router.py` | 新建 — 双渠道路由 |
| `extensions/wez_bridge/local_server.py` | 重写 — 多路由支持 (register_route) |
| `extensions/wez_bridge/extension.py` | 重写 — 接线所有新组件 |
| `extensions/wez_bridge/config.py` | 修改 — +session/context 配置 |
| `core/api_client.py` | 已有 — inject_context 支持 metadata + chat_stream |

**日期 & 署名：** 2026-05-29 · Extension Team (Alessandro)

---

## 独立运行入口 + /agent 选择

**需求：** wez_bridge 从 main.py 的 tray launcher 中拆出，可独立运行。支持运行时通过 `/agent <name|id>` 切换 ExoCore agent。

**方案：**
- 创建 `run_wez_bridge.py` 独立入口脚本（SIGINT/SIGTERM 优雅关闭，支持 --host --port CLI 参数）
- extension.py 中 pystray 懒加载（仅在 tray 模式触发）
- AgentRegistry 新增 `agent_id` 字段 + `get_by_agent_id()` + `resolve_agent()` 方法
- 新增 `POST /api/agents/agent/select/` 端点，支持按 name 或 ID 选择 agent
- Agent 解析优先级：session 级覆盖 > instance 级覆盖 > registry/config 全局默认

**涉及后端：** 无（纯 extension 侧改动）

**本地改动摘要：**
| 文件 | 变更 |
|------|------|
| `run_wez_bridge.py` | 新建 — 独立入口脚本 |
| `extensions/wez_bridge/extension.py` | 修改 — lazy pystray + agent select handler + resolve_agent_for_session |
| `extensions/wez_bridge/local_server.py` | 修改 — +agent/select 路径 |
| `core/agent_registry.py` | 修改 — +agent_id 字段 + get_by_agent_id + resolve_agent |
| `tests/wez_bridge/test_agent_selection.py` | 新建 — 16 tests |

**日期 & 署名：** 2026-05-29 · Extension Team (Alessandro)

---

## WezTerm CLI 包装器 & 哨兵基础架构

**需求：** 在 Extension 侧建立 WezTerm pane 操作能力，实现跨 pane 通信、错误监控（哨兵）、命令注入（Commander）三项基础能力。

**方案：**
- WezTermCLI：`wezterm cli` 子进程包装器（list / get-text / send-text / send-enter）
- Sentinel：后台轮询非 host pane，检测错误关键词 + 低熵翻转，告警时 dump 到 CacheManager 并回调
- Commander：命令注入（HITL gate，默认不带换行，需用户确认后手动 Enter）
- CacheManager：pane 输出本地缓存文件管理
- LocalCommandServer：微 HTTP 服务器接收 ExoCore 的 execute_command dispatch
- WezBridgeExtension：编排器，继承 BaseExtension，通过 main.py tray launcher 加载

**涉及后端：**
- `POST /api/agents/external_context_inject/` — sentinel 告警注入
- `POST /api/agents/execute_command/` → Extension localhost:8777 — 命令回传

**本地改动摘要：**
| 文件 | 变更 |
|------|------|
| `extensions/wez_bridge/wezterm_cli.py` | 新建 — WezTermCLI 包装器 |
| `extensions/wez_bridge/sentinel.py` | 新建 — 后台哨兵监控 |
| `extensions/wez_bridge/commander.py` | 新建 — HITL 命令注入 |
| `extensions/wez_bridge/cache_manager.py` | 新建 — 本地缓存管理 |
| `extensions/wez_bridge/local_server.py` | 新建 — 初始版（单端点） |
| `extensions/wez_bridge/extension.py` | 新建 — 编排器 |
| `extensions/wez_bridge/config.py` | 新建 — 集中配置 |
| `.agents/skills/wezterm_coop/SKILL.md` | 参照 — WezTerm 多 Agent 协作协议 |

**日期 & 署名：** 2026-05-26 · Extension Team (Alessandro)
