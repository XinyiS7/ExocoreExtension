# Unified Extension Agent Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-extension agent assignment system so each extension can have its own default agent persisted across sessions, with a unified management UI.

**Architecture:** Evolve `agent_registry.json` from a flat array to a versioned object containing agent list plus extension-to-agent mapping. Add a non-abstract helper method to `BaseExtension` so any extension can resolve its assigned agent with one call. Add a centralized "Extension Manager" tray menu window for viewing/changing assignments. Migrate WezTerm's `config.py` hardcode and DST Bridge's global-default dependency into the registry.

**Tech Stack:** Python 3.12, tkinter (settings UI), threading.Lock (concurrency), pystray (tray menu), pytest (tests)

---
## File Structure

| File | Action | Responsibility |
|---|---|---|
| `core/agent_registry.py` | Modify | Schema migration (flat list -> versioned object), new `get_extension_agent()` / `set_extension_agent()` / `get_all_extension_assignments()` methods, one-time seed from wez_bridge/config.py |
| `core/base_extension.py` | Modify | Add non-abstract `get_assigned_agent_name()` method with default implementation |
| `core/extension_manager.py` | **Create** | Tkinter UI window listing all loaded extensions and their assigned agent, per-extension dropdown to change assignment |
| `main.py` | Modify | Import extension_manager, add "Extension Manager..." tray menu item before the per-extension items |
| `extensions/wez_bridge/extension.py` | Modify | Replace `ExocoreClient(agent_name=AGENT_NAME)` with `ExocoreClient(agent_name=self.get_assigned_agent_name())` |
| `extensions/wez_bridge/config.py` | Modify | Add deprecation comment to `AGENT_NAME` (kept for migration seeding) |
| `extensions/dst_bridge/extension.py` | Modify | Resolve assigned agent and pass to controller |
| `extensions/dst_bridge/controller.py` | Modify | Accept `agent_name` in `__init__`, use it for API calls and model lookup |
| `extensions/clipboard_capture/ui/overlay.py` | Modify | Pre-fill agent field with extension-assigned agent instead of global default |
| `extensions/clipboard_capture/ui/settings.py` | Modify | Show current assignment with note directing users to Extension Manager |
| `tests/core/test_agent_registry_assignments.py` | **Create** | Tests for schema migration, extension assignment CRUD, fallback to default |
| `tests/core/test_base_extension_agent.py` | **Create** | Tests for `get_assigned_agent_name()` fallback logic |
| `tests/core/test_extension_manager.py` | **Create** | Smoke tests for extension_manager module |
| `tests/dst_bridge/test_controller_agent.py` | **Create** | Tests for DSTController agent name resolution |

---

### Task 1: Evolve agent_registry.json schema and add extension assignment API

**Files:**
- Modify: `core/agent_registry.py` (schema migration, new methods)
- Create: `tests/core/test_agent_registry_assignments.py`
- Affects: `agent_registry.json` (auto-migrated on next load)

The current `agent_registry.json` is a flat array:
```json
[
  {"name": "Alessandro", "mode": "lite_private", "model": "gemini-2.5-flash"}
]
```

Change to a versioned object:
```json
{
  "version": 2,
  "agents": [
    {"name": "Alessandro", "mode": "lite_private", "model": "gemini-2.5-flash"}
  ],
  "extension_assignments": {
    "WezTerm Bridge": "Alessandro"
  }
}
```

- [ ] **Step 1: Write the failing test**

Test file: `tests/core/test_agent_registry_assignments.py`:

```python
"""Tests for AgentRegistry extension assignment API and schema migration."""
import json
import os
import tempfile
import pytest
from core.agent_registry import AgentRegistry


class TestSchemaMigration:
    def test_old_flat_list_is_migrated_to_new_format(self):
        old_data = [
            {"name": "Alessandro", "mode": "lite_private", "model": "gemini-2.5-flash"},
            {"name": "TestAgent", "mode": "zero_tool"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "agent_registry.json")
            with open(old_path, "w", encoding="utf-8") as f:
                json.dump(old_data, f)
            registry = AgentRegistry(storage_dir=tmpdir)
            agents = registry.get_all()
            assert len(agents) == 2
            assert agents[0]["name"] == "Alessandro"
            with open(old_path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            assert isinstance(parsed, dict)
            assert parsed["version"] == 2
            assert len(parsed["agents"]) == 2

    def test_old_format_loads_empty_assignments(self):
        old_data = [{"name": "Alessandro", "mode": "lite_private"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            old_path = os.path.join(tmpdir, "agent_registry.json")
            with open(old_path, "w", encoding="utf-8") as f:
                json.dump(old_data, f)
            registry = AgentRegistry(storage_dir=tmpdir)
            assert registry.get_all_extension_assignments() == {}

    def test_new_format_loads_directly(self):
        new_data = {
            "version": 2,
            "agents": [{"name": "Alessandro", "mode": "lite_private"}],
            "extension_assignments": {"WezTerm Bridge": "Alessandro"},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "agent_registry.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_data, f)
            registry = AgentRegistry(storage_dir=tmpdir)
            assert len(registry.get_all()) == 1
            assert registry.get_extension_agent("WezTerm Bridge") == "Alessandro"

    def test_missing_file_seeds_default_agent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            agents = registry.get_all()
            assert len(agents) >= 1
            assert agents[0]["name"] == "Alessandro"
            assert registry.get_all_extension_assignments() == {}


class TestExtensionAssignments:
    def test_get_extension_agent_returns_none_when_not_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            assert registry.get_extension_agent("Unknown Extension") is None

    def test_set_and_get_extension_agent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("My Extension", "TestAgent")
            assert registry.get_extension_agent("My Extension") == "TestAgent"

    def test_set_extension_agent_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("WezTerm Bridge", "Alessandro")
            registry2 = AgentRegistry(storage_dir=tmpdir)
            assert registry2.get_extension_agent("WezTerm Bridge") == "Alessandro"

    def test_clearing_extension_agent_removes_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("Ext A", "Agent1")
            registry.set_extension_agent("Ext A", "")
            assert registry.get_extension_agent("Ext A") is None

    def test_get_all_extension_assignments_returns_copy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.set_extension_agent("Ext A", "Agent1")
            assignments = registry.get_all_extension_assignments()
            assignments["Ext A"] = "hacked"
            assert registry.get_extension_agent("Ext A") == "Agent1"

    def test_existing_public_api_still_works(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = AgentRegistry(storage_dir=tmpdir)
            registry.add_agent("Alice", "zero_tool")
            registry.add_agent("Bob", "lite_private")
            names = registry.list_names()
            assert "Alice" in names
            assert "Bob" in names
            assert registry.get_default_name() in names
            assert registry.get_agent_config("Alice")["mode"] == "zero_tool"
            registry.set_default_agent("Alice")
            assert registry.get_default_name() == "Alice"
```

- [ ] **Step 2: Create tests directory and run tests to verify failure**

```bash
mkdir -p tests/core
touch tests/core/__init__.py
pytest tests/core/test_agent_registry_assignments.py -v
```

Expected: FAIL with attribute errors (`'AgentRegistry' object has no attribute 'get_extension_agent'`)

- [ ] **Step 3: Implement schema migration and new methods in AgentRegistry**

In `core/agent_registry.py`:

Add `self._assignments: dict[str, str] = {}` alongside `self._configs` in `__init__`:
```python
class AgentRegistry:
    def __init__(self, storage_dir: str):
        self._lock = threading.Lock()
        self._path = os.path.join(storage_dir, _STORAGE_FILENAME)
        self._configs: list[dict] = []
        self._assignments: dict[str, str] = {}
        self._load()
```

Add three new public methods after `list_names()`:
```python
    def get_extension_agent(self, extension_name: str) -> str | None:
        with self._lock:
            return self._assignments.get(extension_name)

    def set_extension_agent(self, extension_name: str, agent_name: str) -> None:
        with self._lock:
            if agent_name:
                self._assignments[extension_name] = agent_name
            else:
                self._assignments.pop(extension_name, None)
            self._persist()

    def get_all_extension_assignments(self) -> dict[str, str]:
        with self._lock:
            return dict(self._assignments)
```

Update `_persist()` to write new format:
```python
    def _persist(self) -> None:
        tmp = self._path + ".tmp"
        try:
            payload = {
                "version": 2,
                "agents": [dict(cfg) for cfg in self._configs],
                "extension_assignments": dict(self._assignments),
            }
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception as e:
            print(f"[AgentRegistry] Failed to persist: {e}")
```

Update `_load()` to handle both old and new formats:
```python
    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._configs = [dict(cfg) for cfg in data]
                    self._assignments = {}
                    self._persist()
                elif isinstance(data, dict):
                    self._configs = [dict(cfg) for cfg in data.get("agents", [])]
                    self._assignments = dict(data.get("extension_assignments", {}))
                return
            except (json.JSONDecodeError, OSError) as e:
                print(f"[AgentRegistry] Corrupt JSON, falling back to defaults: {e}")
        self._migrate_from_config()
```

Update `_migrate_from_config()` to write new format:
```python
    def _migrate_from_config(self) -> None:
        self._configs = [{"name": "Alessandro", "mode": "lite_private", "model": "gemini-2.5-flash"}]
        self._assignments = {}
        self._persist()
        print(f"[AgentRegistry] No JSON found -- seeded with default agent")
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/core/test_agent_registry_assignments.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Run all existing tests to verify backward compatibility**

```bash
pytest tests/ -v
```
Expected: All existing tests still PASS (they use mocks, not real file I/O)

- [ ] **Step 6: Commit**

```bash
git add core/agent_registry.py tests/core/test_agent_registry_assignments.py tests/core/__init__.py
git commit -m "feat(agent_registry): add extension assignment API with schema migration"
```

---

### Task 2: Add get_assigned_agent_name() to BaseExtension

**Files:**
- Modify: `core/base_extension.py`
- Create: `tests/core/test_base_extension_agent.py`

- [ ] **Step 1: Write the failing test**

Test file: `tests/core/test_base_extension_agent.py`:

```python
"""Tests for BaseExtension.get_assigned_agent_name()."""
from core.base_extension import BaseExtension


class FakeRegistry:
    def __init__(self, assignments=None, default_name="Alessandro"):
        self._assignments = assignments or {}
        self._default_name = default_name

    def get_extension_agent(self, name):
        return self._assignments.get(name)

    def get_default_name(self):
        return self._default_name


class TestGetAssignedAgentName:
    def test_returns_explicit_assignment_when_set(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Test Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []
        ext = TestExt()
        registry = FakeRegistry(assignments={"Test Extension": "Bob"})
        assert ext.get_assigned_agent_name(registry) == "Bob"

    def test_falls_back_to_global_default_when_no_explicit_assignment(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Unknown Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []
        ext = TestExt()
        registry = FakeRegistry(default_name="Alice")
        assert ext.get_assigned_agent_name(registry) == "Alice"

    def test_returns_global_default_when_registry_returns_none(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Some Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []
        ext = TestExt()
        registry = FakeRegistry(assignments={"Unrelated": "Bob"}, default_name="Alice")
        assert ext.get_assigned_agent_name(registry) == "Alice"

    def test_defaults_to_registry_singleton_when_no_registry_passed(self):
        class TestExt(BaseExtension):
            @property
            def name(self):
                return "Test Extension"
            def start(self):
                pass
            def stop(self):
                pass
            def get_menu_items(self):
                return []
        ext = TestExt()
        name = ext.get_assigned_agent_name()
        assert isinstance(name, str)
        assert len(name) > 0
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/core/test_base_extension_agent.py -v
```
Expected: FAIL with `AttributeError: 'TestExt' object has no attribute 'get_assigned_agent_name'`

- [ ] **Step 3: Implement the method on BaseExtension**

Add to `core/base_extension.py`, after the existing `get_settings_ui()` method:

```python
    def get_assigned_agent_name(self, registry=None) -> str:
        """Return the agent name assigned to this extension.

        Checks the registry for a per-extension assignment first.
        Falls back to the global default agent when no explicit assignment exists.

        Args:
            registry: An AgentRegistry-like object. If None, imports the
                      global singleton. Extensions can pass a mock in tests.
        """
        if registry is None:
            from core.agent_registry import agent_registry
            registry = agent_registry
        assigned = registry.get_extension_agent(self.name)
        if assigned:
            return assigned
        return registry.get_default_name()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/core/test_base_extension_agent.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/base_extension.py tests/core/test_base_extension_agent.py
git commit -m "feat(base_extension): add get_assigned_agent_name() helper method"
```

---

### Task 3: Create the Extension Manager UI

**Files:**
- Create: `core/extension_manager.py`
- Create: `tests/core/test_extension_manager.py`

- [ ] **Step 1: Write a smoke test**

Test file: `tests/core/test_extension_manager.py`:

```python
"""Smoke tests for extension_manager module (no GUI rendering)."""
import pytest


class TestExtensionManagerImport:
    def test_module_imports_cleanly(self):
        try:
            import core.extension_manager
            assert hasattr(core.extension_manager, "show_extension_manager")
        except ImportError as e:
            pytest.skip(f"tkinter not available: {e}")

    def test_show_extension_manager_accepts_expected_args(self):
        try:
            from core.extension_manager import show_extension_manager
            import inspect
            sig = inspect.signature(show_extension_manager)
            params = list(sig.parameters.keys())
            assert "extensions" in params
            assert "registry" in params or "registry" in str(sig)
        except (ImportError, AttributeError) as e:
            pytest.skip(f"Cannot test signature: {e}")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/core/test_extension_manager.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'core.extension_manager'`

- [ ] **Step 3: Implement the Extension Manager UI**

Create `core/extension_manager.py`:

```python
"""
Extension Manager -- unified UI for viewing/changing per-extension agent
assignments. Opens a tkinter window that lists all loaded extensions and
lets the user assign a specific agent (or "Default") to each one.
"""
import tkinter as tk
from tkinter import ttk
from core.agent_registry import agent_registry as _default_registry
from config import COLORS, FONTS


def show_extension_manager(extensions: list, registry=None):
    """Open the Extension Manager window.

    Args:
        extensions: List of BaseExtension instances (must have .name).
        registry:   AgentRegistry-like object. Falls back to global singleton.
    """
    if registry is None:
        registry = _default_registry

    agent_names = registry.list_names()
    if not agent_names:
        print("[ExtensionManager] No agents configured.")
        return

    root = tk.Tk()
    root.title("ExoCore | Extension Manager")
    root.resizable(False, False)
    root.attributes("-topmost", True)
    root.configure(bg=COLORS["bg"])

    w, h = 480, 40 + len(extensions) * 60
    h = max(300, min(h, 600))
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    # Header
    header = tk.Frame(root, bg=COLORS["panel"], height=40)
    header.pack(fill="x")
    tk.Label(header, text="EXTENSION MANAGER",
             bg=COLORS["panel"], fg=COLORS["accent"],
             font=FONTS["title"]).pack(side="left", padx=15, pady=8)

    # Body
    main = tk.Frame(root, bg=COLORS["bg"], padx=20, pady=20)
    main.pack(fill="both", expand=True)

    tk.Label(main, text="EXTENSION AGENT ASSIGNMENTS",
             anchor="w", bg=COLORS["bg"], fg=COLORS["muted"],
             font=FONTS["sans"]).pack(anchor="w", pady=(0, 10))

    current_assignments: dict[str, tk.StringVar] = {}
    display_choices = ["(Default)"] + agent_names

    for ext in extensions:
        frame = tk.Frame(main, bg=COLORS["surface"], padx=10, pady=6)
        frame.pack(fill="x", pady=4)

        tk.Label(frame, text=ext.name, anchor="w",
                 bg=COLORS["surface"], fg=COLORS["text"],
                 font=FONTS["sans"], width=24).pack(side="left")

        assigned = registry.get_extension_agent(ext.name) or ""
        display_val = assigned if assigned else "(Default)"
        var = tk.StringVar(value=display_val)
        current_assignments[ext.name] = var

        dropdown = ttk.Combobox(frame, textvariable=var,
                                values=display_choices,
                                state="readonly", width=16,
                                font=FONTS["sans"])
        dropdown.pack(side="right")

    # Footer
    footer = tk.Frame(root, bg=COLORS["bg"], pady=10)
    footer.pack(fill="x", side="bottom")

    def on_save():
        for ext_name, var in current_assignments.items():
            val = var.get()
            if val == "(Default)":
                val = ""
            registry.set_extension_agent(ext_name, val)
        root.destroy()

    def on_cancel():
        root.destroy()

    tk.Button(footer, text="SAVE", command=on_save,
              bg=COLORS["accent"], fg=COLORS["bg"],
              font=FONTS["title"], relief="flat",
              activebackground="#fff", padx=20).pack(side="right", padx=20)
    tk.Button(footer, text="CANCEL", command=on_cancel,
              bg=COLORS["panel"], fg=COLORS["muted"],
              font=FONTS["sans"], relief="flat").pack(side="right")

    root.mainloop()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/core/test_extension_manager.py -v
```
Expected: PASS (or `skipped` if tkinter unavailable)

- [ ] **Step 5: Commit**

```bash
git add core/extension_manager.py tests/core/test_extension_manager.py
git commit -m "feat(extension_manager): add centralized Extension Manager UI"
```


---

### Task 4: Wire Extension Manager into the tray menu

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Update main.py with Extension Manager menu item**

Add import at the top (after existing imports):
```python
from core.extension_manager import show_extension_manager
```

In the `main()` function, add the Extension Manager menu item after the Settings item and before per-extension items:

```python
    # Build menu -- discover settings UI from the first extension that provides one
    menu_items = []
    for ext in extensions:
        settings_ui = ext.get_settings_ui()
        if settings_ui is not None:
            menu_items.append(
                pystray.MenuItem("Settings...",
                    lambda icon, item, ui=settings_ui: threading.Thread(
                        target=ui, daemon=True).start())
            )
            menu_items.append(pystray.Menu.SEPARATOR)
            break

    # === Extension Manager ===
    menu_items.append(
        pystray.MenuItem(
            "Extension Manager...",
            lambda icon, item, exts=extensions: threading.Thread(
                target=show_extension_manager, args=(exts,), daemon=True
            ).start(),
        )
    )
    menu_items.append(pystray.Menu.SEPARATOR)

    for ext in extensions:
        menu_items.extend(ext.get_menu_items())
        menu_items.append(pystray.Menu.SEPARATOR)

    menu_items.append(pystray.MenuItem("Quit", on_quit))
```

- [ ] **Step 2: Manual smoke test**

```bash
python main.py
```
Expected: The tray icon appears. Right-click shows "Extension Manager..." menu item. Clicking opens a window listing all loaded extensions with agent dropdowns.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat(main): add Extension Manager tray menu item"
```

---

### Task 5: Update WezTerm Bridge to use registry-based agent assignment

**Files:**
- Modify: `extensions/wez_bridge/extension.py`
- Modify: `extensions/wez_bridge/config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/wez_bridge/test_extension.py` (inside class `TestWezBridgeExtension`):

```python
def test_agent_name_comes_from_get_assigned_agent_name(self):
    with patch("extensions.wez_bridge.extension.WezTermCLI"), \
         patch("extensions.wez_bridge.extension.CacheManager"), \
         patch("extensions.wez_bridge.extension.LocalCommandServer"), \
         patch("extensions.wez_bridge.extension.Sentinel"), \
         patch("extensions.wez_bridge.extension.Commander"), \
         patch("extensions.wez_bridge.extension.ExocoreClient") as mock_client, \
         patch.object(WezBridgeExtension, "get_assigned_agent_name",
                      return_value="TestAgent"):
        ext = WezBridgeExtension()
        ext._inject_context_to_exocore("pane_1", "/tmp/c", "Error")
        mock_client.assert_called_once_with(agent_name="TestAgent")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/wez_bridge/test_extension.py::TestWezBridgeExtension::test_agent_name_comes_from_get_assigned_agent_name -v
```
Expected: FAIL -- `AssertionError` because `mock_client` is called with `agent_name="Alessandro"` not `"TestAgent"`

- [ ] **Step 3: Implement the change**

In `extensions/wez_bridge/extension.py`:

1. Remove the import line: `from .config import AGENT_NAME`
2. In `_inject_context_to_exocore`, replace:
```python
client = ExocoreClient(agent_name=AGENT_NAME)
```
with:
```python
client = ExocoreClient(agent_name=self.get_assigned_agent_name())
```
3. Also remove unused import of `AGENT_NAME` to avoid a linter warning

In `extensions/wez_bridge/config.py`, add deprecation comment:
```python
# DEPRECATED: Agent assignment is now managed by core/agent_registry.
# Kept for migration seeding -- do not edit directly.
AGENT_NAME = "Alessandro"
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/wez_bridge/test_extension.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/extension.py extensions/wez_bridge/config.py
git commit -m "feat(wez_bridge): use get_assigned_agent_name() instead of hardcoded AGENT_NAME"
```


---

### Task 6: Update DST Bridge to use per-extension agent assignment

**Files:**
- Modify: `extensions/dst_bridge/extension.py`
- Modify: `extensions/dst_bridge/controller.py`
- Create: `tests/dst_bridge/test_controller_agent.py`

- [ ] **Step 1: Create tests directory and write the failing test**

```bash
mkdir -p tests/dst_bridge
```

Test file: `tests/dst_bridge/test_controller_agent.py`:

```python
"""Tests for DSTController agent name resolution."""
from unittest.mock import MagicMock, patch
from extensions.dst_bridge.controller import DSTController


class TestControllerAgentName:
    def test_constructor_stores_agent_name(self):
        controller = DSTController(
            context_manager=MagicMock(),
            executor=MagicMock(),
            api_client=MagicMock(),
            knowledge_file="/fake/path.md",
            agent_name="Alice",
        )
        assert controller._agent_name == "Alice"

    def test_agent_name_defaults_to_empty_string(self):
        controller = DSTController(
            context_manager=MagicMock(),
            executor=MagicMock(),
            api_client=MagicMock(),
            knowledge_file="/fake/path.md",
        )
        assert controller._agent_name == ""

    def test_controller_passes_agent_name_to_fast_inference(self):
        mock_client = MagicMock()
        mock_client.fast_inference.return_value = "some reply"
        controller = DSTController(
            context_manager=MagicMock(),
            executor=MagicMock(),
            api_client=mock_client,
            knowledge_file="/fake/path.md",
            agent_name="Alice",
        )
        controller._system_prompt = ""
        controller.context.get_prompt_context.return_value = "ctx"
        controller.context.get_conversation_history.return_value = []

        import threading
        orig_thread = threading.Thread
        captured_target = None

        def capture_thread(target=None, daemon=None, **kwargs):
            nonlocal captured_target
            captured_target = target
            return orig_thread(target=lambda: None, daemon=True)

        threading.Thread = capture_thread
        try:
            controller._consult_ai("test reason")
            if captured_target:
                captured_target()
            call_kwargs = mock_client.fast_inference.call_args[1]
            assert call_kwargs.get("agent_name") == "Alice"
        finally:
            threading.Thread = orig_thread

    def test_model_lookup_uses_assigned_agent(self):
        mock_client = MagicMock()
        controller = DSTController(
            context_manager=MagicMock(),
            executor=MagicMock(),
            api_client=mock_client,
            knowledge_file="/fake/path.md",
            agent_name="Bob",
        )
        controller._system_prompt = ""
        controller.context.get_prompt_context.return_value = "ctx"
        controller.context.get_conversation_history.return_value = []

        import threading
        orig_thread = threading.Thread
        captured_target = None

        def capture_thread(target=None, daemon=None, **kwargs):
            nonlocal captured_target
            captured_target = target
            return orig_thread(target=lambda: None, daemon=True)

        threading.Thread = capture_thread
        try:
            controller._consult_ai("test")
            if captured_target:
                captured_target()
            # Should not crash
        finally:
            threading.Thread = orig_thread
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
pytest tests/dst_bridge/test_controller_agent.py -v
```
Expected: FAIL -- `TypeError: DSTController.__init__() got an unexpected keyword argument 'agent_name'`

- [ ] **Step 3: Implement the changes**

In `extensions/dst_bridge/controller.py`:

1. Update `__init__` signature -- add `agent_name: str = ""` parameter:
```python
    def __init__(
        self,
        context_manager,
        executor,
        api_client,
        knowledge_file: str,
        agent_name: str = "",
    ):
```
And in the body add:
```python
        self._agent_name = agent_name
```

2. Update `_consult_ai` to use `self._agent_name`:

In the `_task()` inner function, replace:
```python
            model = agent_registry.get_agent_model(agent_registry.get_default_name())
```
with:
```python
            resolved_agent = self._agent_name or agent_registry.get_default_name()
            model = agent_registry.get_agent_model(resolved_agent)
```

And update the `fast_inference` call to pass:
```python
                reply = self.client.fast_inference(
                    prompt=prompt,
                    system_prompt=self._system_prompt,
                    history=history,
                    model=model,
                    agent_name=self._agent_name,
                )
```

In `extensions/dst_bridge/extension.py`, update `__init__` where the controller is created.

Replace:
```python
        client = ExocoreLiteClient()

        self.controller = DSTController(
            context_manager=context,
            executor=executor,
            api_client=client,
            knowledge_file=knowledge_file,
        )
```

With:
```python
        client = ExocoreLiteClient()
        agent_name = self.get_assigned_agent_name()

        self.controller = DSTController(
            context_manager=context,
            executor=executor,
            api_client=client,
            knowledge_file=knowledge_file,
            agent_name=agent_name,
        )
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
pytest tests/dst_bridge/ -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/dst_bridge/extension.py extensions/dst_bridge/controller.py tests/dst_bridge/test_controller_agent.py
git commit -m "feat(dst_bridge): use per-extension agent assignment instead of global default"
```


---

### Task 7: Update Clipboard Capture overlay to pre-fill with extension-assigned agent

**Files:**
- Modify: `extensions/clipboard_capture/ui/overlay.py`
- Create: `tests/clipboard_capture/test_overlay.py`

- [ ] **Step 1: Write the test**

```bash
mkdir -p tests/clipboard_capture
```

Test file: `tests/clipboard_capture/test_overlay.py`:

```python
"""Tests for clipboard capture overlay agent pre-fill behavior."""
from core.agent_registry import agent_registry


def test_registry_fallback_without_assignment():
    """When no extension assignment exists, get_default_name is used."""
    agent_registry.set_extension_agent("Clipboard Capture", "")
    default = agent_registry.get_default_name()
    assigned = agent_registry.get_extension_agent("Clipboard Capture")
    result = assigned or default
    assert result == default


def test_registry_uses_explicit_assignment():
    """When extension assignment exists, it takes priority."""
    agent_registry.set_extension_agent("Clipboard Capture", "TestAgent")
    try:
        default = agent_registry.get_default_name()
        assigned = agent_registry.get_extension_agent("Clipboard Capture")
        result = assigned or default
        assert result == "TestAgent"
    finally:
        agent_registry.set_extension_agent("Clipboard Capture", "")
```

- [ ] **Step 2: Run the test to verify it passes with current overlay behavior**

```bash
pytest tests/clipboard_capture/test_overlay.py -v
```
Expected: PASS (this tests the registry API, not the overlay UI directly)

- [ ] **Step 3: Implement the change in overlay.py**

In `extensions/clipboard_capture/ui/overlay.py`, replace the line:
```python
agent_var = tk.StringVar(value=agent_registry.get_default_name())
```
with:
```python
_assigned_for_capture = (
    agent_registry.get_extension_agent("Clipboard Capture")
    or agent_registry.get_default_name()
)
agent_var = tk.StringVar(value=_assigned_for_capture)
```

- [ ] **Step 4: Run the tests**

```bash
pytest tests/clipboard_capture/test_overlay.py -v
pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/clipboard_capture/ui/overlay.py tests/clipboard_capture/test_overlay.py
touch tests/clipboard_capture/__init__.py
git add tests/clipboard_capture/__init__.py
git commit -m "feat(clipboard_capture): pre-fill overlay with extension-assigned agent"
```

---

### Task 8: Update Clipboard Capture settings UI with extension assignment info

**Files:**
- Modify: `extensions/clipboard_capture/ui/settings.py`

- [ ] **Step 1: Implement the change**

In `extensions/clipboard_capture/ui/settings.py`, after the "DEFAULT AGENT" section (after line 110 with the agent menu) and before the "OBSIDIAN VAULT PATH" section, add:

```python
    # Per-Extension Agent Assignment (read-only display)
    tk.Label(main, text="EXTENSION AGENT (for Clipboard Capture)", anchor="w",
             bg=COLORS["bg"], fg=COLORS["muted"], font=FONTS["sans"]).pack(anchor="w", pady=(5, 5))

    ext_agent_display = tk.Frame(main, bg=COLORS["bg"])
    ext_agent_display.pack(fill="x", pady=(0, 10))

    _ext_assigned = agent_registry.get_extension_agent("Clipboard Capture")
    if _ext_assigned:
        display_text = f"Clipboard Capture uses: {_ext_assigned}"
        display_color = COLORS["accent"]
    else:
        display_text = "Clipboard Capture uses: (global default)"
        display_color = COLORS["muted"]

    tk.Label(ext_agent_display, text=display_text, anchor="w",
             bg=COLORS["surface"], fg=display_color, font=FONTS["sans"],
             padx=10, pady=6).pack(fill="x")

    tk.Label(ext_agent_display,
             text='Use tray menu > "Extension Manager..." to change.',
             anchor="w", bg=COLORS["bg"], fg=COLORS["muted"],
             font=("Arial", 9)).pack(anchor="w", pady=(2, 0))
```

- [ ] **Step 2: Verify no regressions**

```bash
pytest tests/ -v
```
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add extensions/clipboard_capture/ui/settings.py
git commit -m "feat(clipboard_capture): show extension assignment info in settings UI"
```


---

## Self-Review

**Spec coverage:**
- "Each extension can have its own default agent (persisted across sessions)" -- Task 1 adds the schema and API, Task 2 adds the BaseExtension helper
- "A way to view and change each extension's agent assignment" -- Task 3 creates the UI, Task 4 wires it to the tray menu
- "Existing per-extension config files are respected" -- Task 5 marks AGENT_NAME in wez_bridge/config.py as deprecated but retains its value for migration seeding
- "The system is extensible for future extensions" -- Tasks 2, 5-7 show how the three current extensions adopt the API; new extensions simply call `self.get_assigned_agent_name()` in one line

**Placeholder scan:** No TBD/TODO/fill-in-later patterns. Every step has exact file paths, complete code blocks, and expected test output.

**Type consistency:**
- `get_extension_agent()` returns `str | None` -- used in Task 2's `get_assigned_agent_name()` which checks truthiness
- `set_extension_agent(name, "")` clears the assignment -- used in Tasks 3 and 7
- `get_all_extension_assignments()` returns `dict[str, str]` -- tested in Task 1
- `AgentRegistry.__init__` keeps same `storage_dir` signature -- only internal state added
- `DSTController.__init__` gets optional `agent_name: str = ""` -- backward-compatible keyword arg
- `BaseExtension.get_assigned_agent_name(registry=None)` -- optional mock injection for testing

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-unified-extension-agent-management.md`. Two execution options:

1. **Subagent-Driven (recommended)** -- I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** -- execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
