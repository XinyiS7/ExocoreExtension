# Multi-Extension Architecture Plan

## Goal
Restructure `ExocoreExtension` from a single-purpose hotkey capture tool into a modular framework that can host multiple independent or semi-independent ExoCore extensions.

## 1. Directory Structure Changes
- **Root**: `main.py` becomes the orchestrator.
- **`core/`**: Extract shared logic (Tray icon, ExoCore API client, UI themes).
- **`extensions/`**: Create a dedicated directory for modules.
- **`extensions/clipboard_capture/`**: Move existing `capture/`, `sender/`, `ui/`, `vault/` into this module.

## 2. Abstraction Layer
- Define a `BaseExtension` class in `core/base_extension.py`.
- Extensions should implement `start()`, `stop()`, and `get_menu_items()`.

## 3. Implementation Steps
1. **Prepare `core/`**:
   - Move `config.py` constants that are global (URL, Colors) to `core/config.py`.
   - Extract `ExocoreClient` to `core/api_client.py`.
2. **Encapsulate `clipboard_capture`**:
   - Create `extensions/clipboard_capture/`.
   - Move specific hotkey and capture logic there.
   - Create `extensions/clipboard_capture/extension.py` to handle its initialization.
3. **Refactor `main.py`**:
   - Update to discover and load extensions from the `extensions/` folder.
   - Delegate system tray menu generation to extensions.

## 4. Verification
- Verify that the original "Capture selected text" (Ctrl+Alt+A) and "Active window capture" (Ctrl+Alt+S) still work as expected.
- Ensure the tray icon correctly displays and manages the new modular structure.
