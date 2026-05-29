#!/usr/bin/env python
"""
Alessandro Terminal Pane (TUI) — sandro_tui.py

A prompt_toolkit CLI agent that talks to the local wez_bridge daemon.
All session management, agent selection, and ExoCore communication is
handled by wez_bridge — this TUI is a thin interactive frontend.

Launch inside a WezTerm pane:
    python sandro_tui.py
    python sandro_tui.py --bridge http://127.0.0.1:8777
"""
import os
import json
import argparse
import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.shortcuts import radiolist_dialog

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BRIDGE_URL = "http://127.0.0.1:8777"
HOST_PANE_ID = os.environ.get("WEZTERM_PANE", "0")


# ---------------------------------------------------------------------------
# wez_bridge API helpers
# ---------------------------------------------------------------------------

def _post(endpoint: str, payload: dict) -> dict:
    """POST JSON to wez_bridge, return parsed response."""
    url = f"{BRIDGE_URL.rstrip('/')}{endpoint}"
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        return {"status": "error", "message": f"Cannot reach wez_bridge at {BRIDGE_URL}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _get(endpoint: str) -> dict:
    """GET JSON from wez_bridge."""
    url = f"{BRIDGE_URL.rstrip('/')}{endpoint}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# TUI State
# ---------------------------------------------------------------------------

class TuiState:
    """Mutable state shared across the TUI session."""

    def __init__(self):
        self.session_id: str | None = None
        self.agent_name: str = "Alessandro"
        self.summary: str = ""


state = TuiState()


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def cmd_agent(args: str):
    """Switch agent: /agent <name|id>"""
    if not args.strip():
        print("  Usage: /agent <name|id>")
        return
    payload = {}
    # Heuristic: if args looks like an ID (short alphanumeric with digits), try as ID
    if any(c.isdigit() for c in args) and len(args) <= 10:
        payload["agent_id"] = args.strip()
    else:
        payload["agent_name"] = args.strip()

    result = _post("/api/agents/agent/select/", payload)
    if result.get("status") == "ok":
        state.agent_name = result["agent_name"]
        print(f"  Agent → {result['agent_name']} (id={result.get('agent_id', '')})")
    else:
        print(f"  [ERR] {result.get('message', 'unknown error')}")


def cmd_resume(args: str):
    """List recent sessions and pick one to resume."""
    result = _get("/api/agents/sessions/")
    sessions = result.get("sessions", [])
    if not sessions:
        print("  No recent sessions. Type a message to start a new one.")
        return

    print(f"  Recent sessions ({len(sessions)}):")
    for i, s in enumerate(sessions[:10]):
        active = "●" if i == 0 else "○"
        print(f"  {active} [{i}] {s['summary'][:30]} · {s['message_count']}msgs "
              f"· {s['session_id']}")

    if args.strip():
        try:
            idx = int(args.strip())
            sess = sessions[idx]
            state.session_id = sess["session_id"]
            state.summary = sess.get("summary", "")
            print(f"  Resumed → {sess['summary'][:30]}")
        except (ValueError, IndexError):
            print(f"  [ERR] Invalid index: {args}")


def cmd_sessions(args: str):
    """List sessions (compact)."""
    result = _get("/api/agents/sessions/")
    sessions = result.get("sessions", [])
    if not sessions:
        print("  No sessions yet.")
        return
    for s in sessions[:10]:
        marker = "→" if s["session_id"] == state.session_id else " "
        print(f"  {marker} {s['summary'][:40]} · {s['message_count']}msgs")


def cmd_new(args: str):
    """Start a fresh session."""
    state.session_id = None
    state.summary = ""
    print("  New session started.")


def cmd_help(args: str):
    """Show help."""
    print("  /agent <name|id>  — Switch agent")
    print("  /resume [index]   — List or pick a recent session")
    print("  /sessions         — List recent sessions")
    print("  /new              — Start a fresh session")
    print("  /sentinel [on|off] — Toggle background pane monitor")
    print("  /status           — Show current session + agent")
    print("  /clear            — Clear the screen")
    print("  /help             — Show this message")
    print("  Ctrl+C            — Quit")


def cmd_status(args: str):
    """Show current TUI state."""
    sentinel = _post("/api/agents/sentinel/toggle/", {"action": "status"})
    sentinel_status = "ON" if sentinel.get("sentinel_running") else "OFF"
    print(f"  Agent:    {state.agent_name}")
    print(f"  Session:  {state.session_id or '(new)'}")
    print(f"  Summary:  {state.summary or '(none)'}")
    print(f"  Bridge:   {BRIDGE_URL}")
    print(f"  Pane:     {HOST_PANE_ID}")
    print(f"  Sentinel: {sentinel_status}")


def cmd_sentinel(args: str):
    """Toggle sentinel on/off: /sentinel [on|off]"""
    action = args.strip().lower()
    if action not in ("on", "off", ""):
        print("  Usage: /sentinel [on|off]")
        print("    on  — Start background pane monitoring")
        print("    off — Stop background pane monitoring")
        return
    if not action:
        # Default: show status
        result = _post("/api/agents/sentinel/toggle/", {"action": "status"})
        status = "ON" if result.get("sentinel_running") else "OFF"
        print(f"  Sentinel: {status}")
        return

    result = _post("/api/agents/sentinel/toggle/", {"action": "start" if action == "on" else "stop"})
    if result.get("status") == "ok":
        status = "ON" if result.get("sentinel_running") else "OFF"
        print(f"  Sentinel → {status}  ({result.get('message', '')})")
    else:
        print(f"  [ERR] {result.get('message', 'unknown')}")


COMMANDS = {
    "/agent":     cmd_agent,
    "/resume":    cmd_resume,
    "/sessions":  cmd_sessions,
    "/new":       cmd_new,
    "/sentinel":  cmd_sentinel,
    "/help":      cmd_help,
    "/status":    cmd_status,
    "/clear":     lambda _: os.system("cls" if os.name == "nt" else "clear"),
    "/pane":      lambda _: print(f"  Host Pane ID: {HOST_PANE_ID}"),
}


# ---------------------------------------------------------------------------
# TUI
# ---------------------------------------------------------------------------

STYLE = Style.from_dict({
    "prompt":    "#edd554 bold",
    "input":     "#E0E7FF",
    "agent":     "#7ec98c bold",
    "thinking":  "#b1b5c8 italic",
    "error":     "#ff4444",
    "meta":      "#6b7280",
})

bindings = KeyBindings()


@bindings.add("c-c")
def _(event):
    """Ctrl+C: quit the TUI."""
    print("\n[Exiting]")
    event.app.exit()


def main():
    global BRIDGE_URL

    parser = argparse.ArgumentParser(description="Alessandro Terminal Pane")
    parser.add_argument("--bridge", default=BRIDGE_URL,
                        help="wez_bridge URL (default: http://127.0.0.1:8777)")
    args_cli = parser.parse_args()

    BRIDGE_URL = args_cli.bridge

    # Try to get current agent from bridge
    try:
        r = requests.get(f"{BRIDGE_URL.rstrip('/')}/api/agents/sessions/", timeout=3)
    except Exception:
        pass

    print(f"  ╭─────────── Alessandro CLI Agent ───────────╮")
    print(f"  │ Agent:  {state.agent_name:<36}│")
    print(f"  │ Bridge: {BRIDGE_URL:<36}│")
    print(f"  │ Pane:   {HOST_PANE_ID:<36}│")
    print(f"  │ /help for commands · Ctrl+D to quit        │")
    print(f"  ╰─────────────────────────────────────────────╯")
    print()

    session = PromptSession(style=STYLE, key_bindings=bindings)

    while True:
        try:
            prompt_label = state.agent_name[:12] if state.agent_name else ">>>"
            user_input = session.prompt(
                [("class:prompt", f"{prompt_label}› ")],
                multiline=False,
            )
        except KeyboardInterrupt:
            print("\n[Exiting]")
            break
        except EOFError:
            print("\n[Exiting]")
            break

        if not user_input.strip():
            continue

        # Commands
        parts = user_input.strip().split(maxsplit=1)
        cmd_key = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""

        if cmd_key in COMMANDS:
            COMMANDS[cmd_key](cmd_args)
            continue

        # Normal message → wez_bridge chat
        payload = {"message": user_input.strip()}
        if state.session_id:
            payload["session_id"] = state.session_id

        print()
        print(f"[{state.agent_name}] ", end="", flush=True)

        result = _post("/api/agents/chat/", payload)

        if result.get("status") == "ok":
            # Update state from response
            state.session_id = result.get("session_id", state.session_id)
            state.summary = result.get("summary", state.summary)
            reply = result.get("reply", "")
            if reply:
                print(reply)
            else:
                print("(no reply from backend yet)")
        else:
            print(f"[ERR] {result.get('message', 'unknown')}")

        print()


if __name__ == "__main__":
    main()
