"""
Layer 1: Clipboard-based text capture.
Reads whatever text is currently in the clipboard.

Workflow: select text in any app → Ctrl+C → then press the hotkey.
We intentionally do NOT simulate Ctrl+C because the hotkey triggers
a focus change that causes the simulated keypress to hit the wrong window.
"""
import pyperclip


def capture_selected_text() -> str | None:
    """
    Read current clipboard content.
    Returns text if present, None if clipboard is empty or non-text.
    """
    text = _safe_get_clipboard()
    return text.strip() if text and text.strip() else None


def _safe_get_clipboard() -> str | None:
    try:
        return pyperclip.paste()
    except Exception:
        return None
