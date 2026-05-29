# WezTerm Bridge (wez_bridge)

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
