"""
ExoCore Extension — Polished Version.
"""
import threading
import keyboard
import pystray
import sys
from PIL import Image, ImageDraw

try:
    import win32gui
except ImportError:
    win32gui = None

from capture.clipboard import capture_selected_text
from capture.uiautomation_capture import capture_active_window_text
from ui.overlay import ask_prompt
from ui.response_popup import show_response
from ui.settings import show_settings
from vault.obsidian_writer import save_note, append_reply
from sender.exocore_client import ExocoreClient
from config import (
    HOTKEY_CLIPBOARD_CAPTURE,
    HOTKEY_UI_CAPTURE,
    CLIPBOARD_FALLBACK,
)


def _get_source_app() -> str:
    if not win32gui:
        return "Windows (No win32gui)"
    try:
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd) or "Unknown Window"
    except Exception:
        return "Unknown Window"


def handle_capture(text: str | None) -> None:
    if not text:
        print("[ExoCore] Capture failed or empty.")
        return

    source_app = _get_source_app()
    # Ensure UI runs in its own thread safely
    result = ask_prompt(text, source_app)
    if not result:
        return  # User cancelled

    custom_title = result.get("custom_title") or source_app
    agent_name = result.get("agent_name", "Alessandro")

    # Update AVAILABLE_AGENTS if this is a new name
    from config import AVAILABLE_AGENTS
    if agent_name and agent_name not in AVAILABLE_AGENTS:
        try:
            import os, re
            config_path = os.path.join(os.path.dirname(__file__), "config.py")
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

    client = ExocoreClient(agent_name=agent_name)

    # 1. Offline Save (Always)
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

    # 2. Online Injection
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
            
            # Auto-append the reply to the note immediately
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
                on_save_callback=None, # Already saved automatically
            )
        except Exception as e:
            print(f"[ExoCore] API Error: {e}", file=sys.stderr)
            # Optional: show an error popup here if the UI is preferred over console



def on_clipboard_hotkey():
    threading.Thread(target=lambda: handle_capture(capture_selected_text()), daemon=True).start()


def on_uia_hotkey():
    def _run():
        text = capture_active_window_text()
        if not text and CLIPBOARD_FALLBACK:
            text = capture_selected_text()
        handle_capture(text)
    threading.Thread(target=_run, daemon=True).start()


def open_settings_ui():
    threading.Thread(target=show_settings, daemon=True).start()


def _make_tray_icon() -> Image.Image:
    # A more "ExoCore" looking icon: Gold circle on dark gray
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill=(26, 30, 41)) # exo-panel
    d.ellipse([16, 16, 48, 48], outline=(237, 213, 84), width=3) # exo-accent
    return img


def main():
    keyboard.add_hotkey(HOTKEY_CLIPBOARD_CAPTURE, on_clipboard_hotkey)
    keyboard.add_hotkey(HOTKEY_UI_CAPTURE, on_uia_hotkey)

    icon = pystray.Icon(
        "ExoCoreExtension",
        _make_tray_icon(),
        "ExoCore Extension",
        menu=pystray.Menu(
            pystray.MenuItem("Capture selected (Ctrl+Alt+A)", lambda: on_clipboard_hotkey()),
            pystray.MenuItem("Capture window   (Ctrl+Alt+S)", lambda: on_uia_hotkey()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings...", lambda: open_settings_ui()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: icon.stop()),
        ),
    )

    from config import EXOCORE_AGENT_NAME
    print(f"[ExoCore Extension] Active. Mode: {EXOCORE_AGENT_NAME}")
    icon.run()


if __name__ == "__main__":
    main()
