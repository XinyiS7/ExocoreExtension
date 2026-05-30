# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Plan first, work later.

**Before working:** read `../AGENT.md` and `AGENTS.md` for cross-module context and module-specific conventions.
For API dependency checks, consult `../ExoCore/.agent/insight/backend.yaml` (the authoritative endpoint catalog).
Extension-to-backend couplings are documented in `.agent/insight/api_deps.yaml` (when available).

## Environment

- **Platform**: Windows only (depends on `uiautomation`, `pywin32`, `keyboard`).
- **Conda env**: `exocore_project`. Always activate before running Python/pytest.
- **Default shell**: WezTerm + Git Bash, conda pre-activated. Use `python.exe` directly.
- **PowerShell fallback**: Use `powershell.exe -Command "..."` or pwsh tool. PS chaining uses `;` not `&&`.
- **No lint/formatter/typecheck/CI** — no `pyproject.toml`, `pre-commit`, or GitHub Actions.
- **No build step** — pure Python, no codegen.

## Running the Project

```bash
conda activate exocore_project
python main.py                     # system-tray app with all extensions
python sandro_tui.py               # standalone TUI, must run inside a WezTerm pane
pytest tests/ -v                   # run all tests
pytest tests/wez_bridge/test_sentinel.py -v   # single test file
```

Tests use `unittest.mock` and `tempfile` — no live backend, game, or WezTerm CLI needed. `conftest.py` adds the project root to `sys.path`.

## Architecture

```
main.py                 # tray icon, discovers & starts all extensions
core/
  base_extension.py     # abstract BaseExtension (name, start, stop, get_menu_items)
  agent_registry.py     # thread-safe singleton backed by agent_registry.json (v2)
  api_client.py         # ExoCoreClient → POST to http://127.0.0.1:8000
  event_bus.py          # sync pub/sub singleton
config.py               # global constants, delegates agent config to agent_registry
agent_registry.json     # canonical agent+assignment registry
extensions/
  dst_bridge/           # DST game ↔ AI bridge (log tails, command queue)
  wez_bridge/           # WezTerm terminal error detection + HITL commands
  clipboard_capture/    # clipboard/active-window text capture via hotkeys
```

## Extension Loading

`main.py` uses `pkgutil.iter_modules(["extensions"])`. For each package `extensions/<name>/`, it imports `extensions.<name>.extension` and instantiates any `BaseExtension` subclass found within. Extensions are NOT auto-discovered from arbitrary files — the module must be named `extension.py` inside a package.

## Agent Resolution

Per `BaseExtension.get_assigned_agent_name()`:
1. `agent_registry.json` → `extension_assignments` (explicit override)
2. Extension's `self.default_agent` attribute (set from per-extension `config.py`)
3. Global default from `agent_registry.json`

An empty-string assignment means "cleared/unset" (falls through to next level).

## EventBus (synchronous!)

`event_bus.publish()` runs callbacks **synchronously** on the publishing thread. Subscribers needing async work MUST spawn their own daemon threads. Both `DSTController._consult_ai()` and `DSTWatcher._tail_log()` follow this pattern.

## AgentRegistry (thread-safe)

All reads/writes are under `threading.Lock`. Writes use atomic `tempfile` + `os.replace()`. Config schema is v2:
```json
{"version": 2, "agents": [...], "extension_assignments": {}}
```
Auto-migrates v1 flat-list format. Tests that need isolation create fresh `AgentRegistry(temp_dir)` instances.

## WezTerm Bridge (wez_bridge/)

### Component graph

```
WezBridgeExtension
├── Sentinel          — polls non-host panes for error keywords, fires alerts
├── Commander         — drafts/injects CLI commands into target panes
├── SessionManager    — CRUD for multi-turn conversation sessions (JSON files)
├── ContextBuilder    — assembles session→ExoCore external_context_inject payloads
├── MessageRouter     — dual-channel: (1) session→ExoCore, (2) agent→target pane
├── LocalCommandServer — HTTP server on 127.0.0.1:8777, receives ExoCore commands
├── CacheManager      — pane output dumps to ExocoreData/ExtensionData/cache/
└── WezTermCLI        — wraps `wezterm cli` subprocess calls
```

### Data flow

```
Channel 1 (Sentinel → ExoCore):
  pane text → Sentinel._poll_once() → error keyword match
  → _on_sentinel_alert() → new Session + Message
  → MessageRouter.route_to_exocore(mode="wez_bridge_sentinel")
  → POST /api/agents/external_context_inject/

Channel 2 (ExoCore → WezTerm):
  LocalCommandServer receives POST /api/agents/send_message/
  → MessageRouter.route_to_pane() → WezTermCLI.send_text()
  → text injected into target pane input area (no trailing newline)
```

### Key gotchas

- `send_enter` uses `\r` (CR), not `\n` — Windows/Git Bash needs it.
- Sentinel polls every 2s; error keyword match + text changed from last poll → alert.
- Sentinel starts OFF by default — user enables via `/sentinel on` in TUI.
- `sandero_tui.py` is standalone, not loaded as an extension.
- `external_session_id` from backend responses is stored per-session in `session.metadata`.
- `cache_reference` (Gemini File API) is stored on `ContextBuilder` singleton — shared across all sessions.

### Session lifecycle

- Sessions persisted as JSON under `ExocoreData/ExtensionData/sessions/`
- Auto-cleanup: 48h expiry from `last_active`
- `first_user_message[:20]` → `summary`
- Messages truncated to `CONTEXT_MAX_MESSAGES=50`, `CONTEXT_TRUNCATE_CHARS=4000` per message

## DST Bridge gotchas

- Klei Lua sandbox blocks `io.open` → the Lua mod uses `TheSim:GetPersistentString`/`SetPersistentString`.
- Python writes commands to `Master/save/exo_cmd_queue.txt` (must be in `save/` subdirectory).
- In `modmain.lua`: `pcall`, `tostring`, `loadstring` all need `GLOBAL.` prefix.
- `AddGamePostInit` fires on both server AND client → guard with `if TheWorld.ismastersim then`.

## Shell hazards

- **PowerShell `&&`** → `ParserError`. Use `;` instead. Bash (WSL) `&&` is fine.
- **Smart quotes**: Editing Python containing Chinese text may silently inject `“`/`”` → `SyntaxError`.
- **WSL Bash ≠ Git Bash**: The bash tool runs WSL; Django commands and Windows paths need PowerShell.

## Existing instruction files

- `AGENTS.md` — module-specific agent instructions, extension gotchas, skill references.
- `GEMINI.md` — project overview, DST data locations, known bugs/workarounds.
- `BUGLOG.md` — resolved DST bridge bugs with root-cause analysis.
- `.agents/skills/footgun/SKILL.md` — environment-specific mistakes catalog.
- `.agents/skills/wezterm_coop/SKILL.md` — multi-agent WezTerm cooperation protocol.
- `Plan/` — architecture blueprints and implementation plans.
