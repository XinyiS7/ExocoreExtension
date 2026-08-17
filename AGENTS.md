# ExoCoreExtension — Agent Instructions

**Before working:** read `../.agent/project.md` and `../AGENT.md` for cross-module context.
**API dependency check:** when changing any backend-facing code, verify against
`../ExoCore/.agent/insight/backend.yaml` (the authoritative endpoint catalog).
Extension-to-backend couplings are documented in (when available) `.agent/insight/api_deps.yaml`.

## Environment

- **Platform**: Windows only (depends on `uiautomation`, `pywin32`, `keyboard`).
- **Conda env**: `exocore_project`. Always activate before running Python/pytest.
- **No lint/formatter/typecheck/CI config** — no `pyproject.toml`, `pre-commit`, or GitHub Actions.
- **No build step** — pure Python, no codegen.

## Run

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
  api_client.py         # ExocoreClient → POST to http://127.0.0.1:8000
  event_bus.py          # sync pub/sub singleton
config.py               # global constants, delegates agent config to agent_registry
agent_registry.json     # canonical agent+assignment registry
extensions/
  dst_bridge/           # DST game ↔ AI bridge (log tails, command queue)
  wez_bridge/           # WezTerm terminal error detection + HITL commands
  clipboard_capture/    # clipboard/active-window text capture via hotkeys
```

## Extension loading

`main.py` uses `pkgutil.iter_modules(["extensions"])`. For each package `extensions/<name>/`, it imports `extensions.<name>.extension` and instantiates any `BaseExtension` subclass found within. Extensions are NOT auto-discovered from arbitrary files — the module must be named `extension.py` inside a package.

## Agent resolution

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

## DST Bridge gotchas

- Klei Lua sandbox blocks `io.open` → the Lua mod uses `TheSim:GetPersistentString`/`SetPersistentString`.
- Python writes commands to `Master/save/exo_cmd_queue.txt` (must be in `save/` subdirectory).
- In `modmain.lua`: `pcall`, `tostring`, `loadstring` all need `GLOBAL.` prefix.
- `AddGamePostInit` fires on both server AND client → guard with `if TheWorld.ismastersim then`.

## WezTerm Bridge gotchas

- `send_enter` uses `\r` (CR), not `\n` — Windows/Git Bash needs it.
- Sentinel polls panes every 2s; first-sight of an error keyword does NOT trigger an alert (avoids noise on initial scan).
- `sandero_tui.py` is standalone, not loaded as an extension.

## Shell hazards

- **PowerShell `&&`** → `ParserError`. Use `;` instead. Bash (WSL) `&&` is fine.
- **Smart quotes**: Editing Python containing Chinese text may silently inject `\u201C`/`\u201D` → `SyntaxError`.
- **WSL Bash ≠ Git Bash**: The bash tool runs WSL; Django commands and Windows paths need PowerShell.

## Existing instruction files

- `GEMINI.md` — project overview, DST data locations, known bugs/workarounds.
- `BUGLOG.md` — resolved DST bridge bugs with root-cause analysis.
- **`chatGPT_bridge/README.md` — ChatGPT↔WezTerm MCP 桥与三 tunnel 工具面全说明书**
  （wezterm/local-workspace/engram 架构、init/后台脚本、已知坑：connector 单 tunnel
  单 server 限制 / 8080 撞车 / Git Bash 逃逸残留；经验与坑都在它自己目录里）。
- `.agents/skills/footgun/SKILL.md` — environment-specific mistakes catalog.
- `.agents/skills/wezterm_coop/SKILL.md` — multi-agent WezTerm cooperation protocol.
- `Plan/` — architecture blueprints and implementation plans.
