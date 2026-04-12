# Extension Refinement - Phase 1

## Goal
Transform the minimal implementation into a polished, configurable, and robust application that aligns with the ExoCore visual identity.

## 1. Configuration Schema Update (`config.py`)
- **Agent Name**: Add `EXOCORE_AGENT_NAME` (default "Alessandro") to be sent in the API payload.
- **Default Storage**: `DEFAULT_VAULT_PATH`.
- **UI Colors**: Map colors from `tailwind.config.js` to Python constants.

## 2. Dynamic File Naming (`vault/obsidian_writer.py`)
- **Smart Matching**: Before saving, scan `VAULT_PATH` for existing files that share keywords with the current `custom_title` or `source_app`.
- **Consistency**: If a pattern (e.g., "Study_Notes_Part_1.md") is found, suggest or use "Study_Notes_Part_2.md" or similar.

## 3. UI/UX Overhaul (`ui/overlay.py` & `ui/response_popup.py`)
- **Theme**: Apply #080A0F (BG) and #edd554 (Accent).
- **Storage Selector**: Add a directory picker (via `tkinter.filedialog`) to allow temporary storage overrides.
- **Settings Window**: (Optional/Future) A dedicated window to edit `config.py` values via UI.

## 4. Bug Fix: File Saving
- Verify `VAULT_PATH` existence and write permissions.
- Ensure `main.py` correctly handles the return path from `save_note` and logs any `IOError`.

## 5. ExoCore Client Update (`sender/exocore_client.py`)
- Include `agent_name` in the injection payload for backend matching.

## Execution Order
1. Update `config.py`.
2. Fix and enhance `vault/obsidian_writer.py` (Smart naming).
3. Update `sender/exocore_client.py`.
4. Rewrite `ui/overlay.py` with the new theme and storage picker.
5. Integration testing.
