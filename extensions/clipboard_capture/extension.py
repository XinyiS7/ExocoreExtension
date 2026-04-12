import threading
import keyboard
from pystray import MenuItem, Menu
import sys

from .capture.clipboard import capture_selected_text
from .capture.uiautomation_capture import capture_active_window_text
from .ui.overlay import ask_prompt
from .ui.response_popup import show_response
from .ui.settings import show_settings
from .vault.obsidian_writer import save_note, append_reply
from core.api_client import ExocoreClient
from core.base_extension import BaseExtension
from config import (
    HOTKEY_CLIPBOARD_CAPTURE,
    HOTKEY_UI_CAPTURE,
    CLIPBOARD_FALLBACK,
    AVAILABLE_AGENTS
)

class ClipboardCaptureExtension(BaseExtension):
    @property
    def name(self) -> str:
        return "Clipboard Capture"

    def start(self):
        keyboard.add_hotkey(HOTKEY_CLIPBOARD_CAPTURE, self.on_clipboard_hotkey)
        keyboard.add_hotkey(HOTKEY_UI_CAPTURE, self.on_uia_hotkey)

    def stop(self):
        keyboard.remove_hotkey(HOTKEY_CLIPBOARD_CAPTURE)
        keyboard.remove_hotkey(HOTKEY_UI_CAPTURE)

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem("Capture selected (Ctrl+Alt+A)", self.on_clipboard_hotkey),
            MenuItem("Capture window   (Ctrl+Alt+S)", self.on_uia_hotkey),
            Menu.SEPARATOR,
            MenuItem("Settings...", self.open_settings_ui),
        ]

    def _get_source_app(self) -> str:
        try:
            import win32gui
            hwnd = win32gui.GetForegroundWindow()
            return win32gui.GetWindowText(hwnd) or "Unknown Window"
        except Exception:
            return "Unknown Window"

    def handle_capture(self, text: str | None) -> None:
        if not text:
            print("[ExoCore] Capture failed or empty.")
            return

        source_app = self._get_source_app()
        result = ask_prompt(text, source_app)
        if not result:
            return

        custom_title = result.get("custom_title") or source_app
        agent_name = result.get("agent_name", "Alessandro")

        # Update AVAILABLE_AGENTS if this is a new name
        if agent_name and agent_name not in AVAILABLE_AGENTS:
            self._persist_agent(agent_name)

        client = ExocoreClient(agent_name=agent_name)

        note_path = None
        try:
            note_path = save_note(
                content=text,
                user_prompt=result["prompt"],
                source_app=source_app,
                note_type=result["note_type"],
                custom_title=custom_title,
                target_path=result.get("vault_path")
            )
            print(f"[ExoCore] Local copy: {note_path}")
        except Exception as e:
            print(f"[ExoCore] CRITICAL: File save failed: {e}", file=sys.stderr)

        if result["send_to_exocore"]:
            print(f"[ExoCore] Injecting context for {agent_name}...")
            try:
                capture_method = "uiautomation" if "uia" in source_app.lower() else "clipboard"
                target = "obsidian" if result["note_type"] == "reading_note" else "session_memory"
                
                resp = client.inject_context(
                    captured_text=text,
                    user_prompt=result["prompt"],
                    capture_method=capture_method,
                    target_storage=target,
                    custom_title=custom_title,
                )
                
                g045_reply = resp.get("reply", "(no reply returned)")
                
                try:
                    from config import VAULT_PATH
                    base_path = result.get("vault_path") or VAULT_PATH
                    append_reply(note_path, base_path, custom_title, agent_name, g045_reply)
                    print(f"[ExoCore] Reply automatically appended via title '{custom_title}'")
                except Exception as e:
                    print(f"[ExoCore] CRITICAL: Failed to append reply: {e}", file=sys.stderr)

                show_response(
                    captured_text=text,
                    user_prompt=result["prompt"],
                    agent_name=agent_name,
                    agent_reply=g045_reply,
                    custom_title=custom_title,
                    on_save_callback=None,
                )
            except Exception as e:
                print(f"[ExoCore] API Error: {e}", file=sys.stderr)

    def _persist_agent(self, agent_name: str):
        try:
            import os, re
            # Since config.py is at root, we find it relative to this file
            config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.py"))
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            AVAILABLE_AGENTS.append(agent_name)
            new_list_str = str(AVAILABLE_AGENTS)
            content = re.sub(r'AVAILABLE_AGENTS\s*=\s*\[.*?\]', f'AVAILABLE_AGENTS = {new_list_str}', content)
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[ExoCore] New agent '{agent_name}' added to persistent config.")
        except Exception as e:
            print(f"[ExoCore] Failed to persist new agent: {e}")

    def on_clipboard_hotkey(self):
        threading.Thread(target=lambda: self.handle_capture(capture_selected_text()), daemon=True).start()

    def on_uia_hotkey(self):
        def _run():
            text = capture_active_window_text()
            if not text and CLIPBOARD_FALLBACK:
                text = capture_selected_text()
            self.handle_capture(text)
        threading.Thread(target=_run, daemon=True).start()

    def open_settings_ui(self):
        threading.Thread(target=show_settings, daemon=True).start()
