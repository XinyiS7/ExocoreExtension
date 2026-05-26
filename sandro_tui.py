#!/usr/bin/env python
"""
Alessandro Terminal Pane (TUI) — sandro_tui.py

A lightweight prompt_toolkit shell that:
1. Detects its WezTerm pane ID from WEZTERM_PANE env var.
2. Forwards user input to ExoCore chat_stream SSE endpoint.
3. Renders streaming responses token-by-token.
4. Handles Ctrl+C gracefully.

Launch inside a WezTerm pane:
    python sandro_tui.py
"""
import os
import sys
import json
import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
try:
    from config import EXOCORE_BASE_URL, EXOCORE_ADMIN_KEY, EXOCORE_EXTENSION_KEY
except ImportError:
    EXOCORE_BASE_URL = "http://127.0.0.1:8000"
    EXOCORE_ADMIN_KEY = "alessandro_root_045"
    EXOCORE_EXTENSION_KEY = "exocore_pollux"

AGENT_NAME = "Alessandro"
SESSION_ID = "wezterm_session_01"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict:
    headers = {"Accept": "text/event-stream"}
    if EXOCORE_ADMIN_KEY and not EXOCORE_EXTENSION_KEY:
        headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY
    return headers


def _build_payload(user_input: str, host_pane_id: str) -> dict:
    payload = {
        "agent": AGENT_NAME,
        "session_id": SESSION_ID,
        "host_pane_id": host_pane_id,
        "user_input": user_input,
    }
    if EXOCORE_EXTENSION_KEY:
        payload["extension_secret"] = EXOCORE_EXTENSION_KEY
    return payload


def stream_chat(user_input: str, host_pane_id: str):
    """Generator that yields tokens from the chat_stream SSE endpoint.

    BACKEND CONFIRMATION NEEDED: Verify SSE event format with backend team.
    """
    url = f"{EXOCORE_BASE_URL.rstrip('/')}/api/agents/chat_stream/"
    headers = _auth_headers()
    payload = _build_payload(user_input, host_pane_id)

    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=300, stream=True
        )
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
                token = obj.get("token", "")
                if token:
                    yield token
            except json.JSONDecodeError:
                continue
    except requests.ConnectionError:
        yield f"\n[ERR] Cannot reach ExoCore backend at {url}"
    except Exception as e:
        yield f"\n[ERR] {e}"


# ---------------------------------------------------------------------------
# TUI
# ---------------------------------------------------------------------------

STYLE = Style.from_dict({
    "prompt": "#edd554 bold",
    "input": "#E0E7FF",
    "thinking": "#b1b5c8 italic",
    "error": "#ff4444",
})

bindings = KeyBindings()


@bindings.add("c-c")
def _(event):
    """Ctrl+C: clear current input and signal interrupt."""
    print("\n[Interrupted] Sending stop signal...")
    event.app.renderer.clear()


def main():
    host_pane_id = os.environ.get("WEZTERM_PANE", "0")
    print(f"  Alessandro Terminal Pane")
    print(f"  Pane: {host_pane_id}  |  Session: {SESSION_ID}")
    print(f"  Backend: {EXOCORE_BASE_URL}")
    print(f"  Type /help for commands, Ctrl+C to interrupt, Ctrl+D to quit")
    print()

    session = PromptSession(style=STYLE, key_bindings=bindings)

    while True:
        try:
            user_input = session.prompt(
                [("class:prompt", ">>> ")],
                multiline=False,
            )
        except KeyboardInterrupt:
            continue
        except EOFError:
            print("\n[Exiting Alessandro TUI]")
            break

        if not user_input.strip():
            continue

        if user_input.strip() == "/help":
            print("  /help   - Show this message")
            print("  /clear  - Clear the screen")
            print("  /pane   - Show current pane ID")
            continue

        if user_input.strip() == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        if user_input.strip() == "/pane":
            print(f"  Host Pane ID: {host_pane_id}")
            continue

        # Stream the response
        print()
        try:
            for token in stream_chat(user_input, host_pane_id):
                print(token, end="", flush=True)
        except KeyboardInterrupt:
            print("\n[Interrupted]")

        print("\n")


if __name__ == "__main__":
    main()
