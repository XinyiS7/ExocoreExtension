# ExoCore Extension

## Project Overview
... (existing content)

## Bug Tracking Rules
...

### 🏆 SUCCESS: DST Bridge IPC Restored (The "Save Folder" Discovery)
**Date:** 2026-04-14
1. **Symptom**: AI commands written to `exo_cmd_queue.txt` were being ignored by the game; file was never cleared; no in-game effect.
2. **Reasoning**: Klei's Lua sandbox blocks `io.open` for custom files and absolute paths. The game only allows trusted I/O in specific subdirectories like `save/`.
3. **Solution**: 
   - Switched to official `TheSim:GetPersistentString` / `SetPersistentString` APIs.
   - Relocated the queue file to `Master/save/exo_cmd_queue.txt`.
   - Re-wrapped console helpers in `modmain.lua` to ensure they target the local player even when run from a server context.
4. **Result**: Full bi-directional sync achieved. Chat and Commands (Heal, Give, etc.) are now fully functional and silent debugging triggers were removed.

## DST Data Locations (Reference)
- **Global Chat Log**: `D:\Documents\Klei\DoNotStarveTogether\client_chat_log.txt` (Convenient, includes all servers/saves for the local host).
- **Player State (Watcher Target)**: `..\..\..\Documents\Klei\DoNotStarveTogether\master_server_log.txt`.
- **Cluster Specific Logs**: `D:\Documents\Klei\DoNotStarveTogether\325334978\Cluster_4\Master\server_chat_log.txt`.
- **AI Command Queue**: `Cluster_4\Master\exo_cmd_queue.txt`.

## Building and Running
... (existing content)

### Prerequisites
- Windows OS (required for UI Automation and Win32 APIs)
- Python 3.10 or higher

### Installation
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure your environment in `config.py`:
   - Set `VAULT_PATH` to your Obsidian vault directory.
   - Set `EXOCORE_BASE_URL` if your backend is not local.

### Execution
Run the application from the root directory:
```bash
python main.py
```
The application will appear in the system tray.

### Usage
- **Ctrl+Alt+A**: Capture selected text via clipboard.
- **Ctrl+Alt+S**: Capture text from the active window using UI Automation.

## Development Conventions

- **Concurrency**: Hotkey handlers are executed in daemon threads to keep the system tray and UI responsive.
- **Error Handling**: Failures in capture or backend communication are logged to the console; the UI should degrade gracefully (e.g., falling back to clipboard if UIA fails).
- **Extensibility**: 
  - New capture methods should be added to the `capture/` directory.
  - New target storages should be added to the `vault/` or a similar directory.
- **Testing**:
  - TODO: Implement a test suite for API communication and note rendering.
  - Manual testing is currently required for UI Automation due to dependency on active window states.
