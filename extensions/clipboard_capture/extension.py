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
    AGENT_CONFIGS,
    get_agent_mode,
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
        agent_mode = result.get("mode", "zero_tool")

        # Persist new agent name to config if not already known
        known_names = [cfg["name"] for cfg in AGENT_CONFIGS]
        if agent_name and agent_name not in known_names:
            self._persist_agent(agent_name, agent_mode)

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
            print(f"[ExoCore] Injecting context for {agent_name} (mode: {agent_mode})...")
            try:
                capture_method = "uiautomation" if "uia" in source_app.lower() else "clipboard"
                target = "external_session" if result["note_type"] == "reading_note" else "session_memory"

                resp = client.inject_context(
                    captured_text=text,
                    user_prompt=result["prompt"],
                    capture_method=capture_method,
                    target_storage=target,
                    mode=agent_mode,
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

    def _persist_agent(self, agent_name: str, mode: str = "zero_tool"):
        try:
            import os, re
            # Find config.py by climbing up
            base_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = None
            for _ in range(5):
                candidate = os.path.join(base_dir, "config.py")
                if os.path.exists(candidate):
                    config_path = candidate
                    break
                base_dir = os.path.dirname(base_dir)
            
            if not config_path:
                print("[ExoCore] Could not locate config.py for persisting agent.")
                return

            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # Update local AGENT_CONFIGS as well
            AGENT_CONFIGS.append({"name": agent_name, "mode": mode})
            new_str = repr(AGENT_CONFIGS)
            content = re.sub(
                r'AGENT_CONFIGS\s*=\s*\[.*?\]',
                f'AGENT_CONFIGS = {new_str}',
                content,
                flags=re.DOTALL,
            )
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[ExoCore] New agent '{agent_name}' with mode '{mode}' added to persistent config.")
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
