"""
Message Router — dual-channel dispatch for WezTerm panes.

Channel 1 (Sentinel): sentinel alerts → session → context builder → ExoCore.
Channel 2 (Direct): Superior/CLI agent → target pane via wezterm cli send-text.

The router does NOT handle Superior pane discovery — the backend auto-discovers
WezTerm windows via its own wezterm_cli tool. We only attach our own pane_id
as metadata.

Response fields from ExoCore (wez_bridge mode):
    - external_session_id: ExoCore's session correlation ID.
    - compacted_up_to: Message index cursor after compact (>30 msgs).
    - cache_reference: Gemini File API reference (if backend sends).
"""
import json
import requests
from typing import Callable, Optional
from .wezterm_cli import WezTermCLI
from .session_manager import SessionManager, Session, Message
from .context_builder import ContextBuilder


class MessageRouter:
    """Routes messages between panes, sessions, and the ExoCore backend."""

    def __init__(
        self,
        cli: Optional[WezTermCLI] = None,
        session_manager: Optional[SessionManager] = None,
        context_builder: Optional[ContextBuilder] = None,
    ):
        self._cli = cli or WezTermCLI()
        self._sessions = session_manager or SessionManager()
        self._context_builder = context_builder or ContextBuilder()

    # ------------------------------------------------------------------
    # Channel 2: Direct messages → target pane
    # ------------------------------------------------------------------

    def route_to_pane(
        self,
        target_pane_id: str,
        message: str,
        from_agent: str = "unknown",
    ) -> bool:
        """Send a message from an external agent to a target WezTerm pane.

        The message is injected into the pane's input area WITHOUT a trailing
        newline (HITL gate). The user can press Enter to execute if it's a
        command, or simply read it as a notification.
        """
        formatted = f"[from: {from_agent}] {message}"
        ok = self._cli.send_text(target_pane_id, formatted)
        if not ok:
            print(f"[MessageRouter] Failed to route message to pane {target_pane_id}")
        return ok

    # ------------------------------------------------------------------
    # Channel 1: Session → Context → ExoCore
    # ------------------------------------------------------------------

    def route_to_exocore(
        self,
        session: Session,
        trigger: str,
        agent_name: str,
        host_pane_id: str = "",
        mode: str = "wez_bridge",
        activity_type: str = "",
    ) -> bool:
        """Build full context from a session and inject it into ExoCore.

        Args:
            session: The conversation session.
            trigger: What triggered this route
                     ("sentinel_alert", "user_message", "manual").
            agent_name: Target agent name for ExoCore.
            host_pane_id: Current host pane ID for metadata.
            mode: Payload mode — "wez_bridge" (user chat) or
                  "wez_bridge_sentinel" (automated background).
            activity_type: If set, added to payload so backend can
                           route as background activity.

        Returns:
            True if context was successfully injected.

        Stores response fields (external_session_id, compacted_up_to,
        cache_reference) in session metadata for correlation across rounds.
        """
        try:
            context = self._context_builder.build_full_context(
                session, host_pane_id=host_pane_id
            )
            # Add trigger info
            context["metadata"]["trigger"] = trigger

            payload = self._context_builder.build_inject_payload(
                context,
                agent_name=agent_name,
                capture_method="terminal",
                target_storage="external_session",
                mode=mode,
                custom_title=f"[{trigger}] {session.summary}",
            )
            if activity_type:
                payload["activity_type"] = activity_type

            # Auth: body extension_secret preferred; fallback to X-Admin-Key header
            from config import EXOCORE_BASE_URL, EXOCORE_EXTENSION_KEY, EXOCORE_ADMIN_KEY
            url = f"{EXOCORE_BASE_URL.rstrip('/')}/api/agents/external_context_inject/"
            headers = {}
            if EXOCORE_EXTENSION_KEY:
                payload["extension_secret"] = EXOCORE_EXTENSION_KEY
            elif EXOCORE_ADMIN_KEY:
                headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY

            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            response = resp.json()

            # Store correlation IDs from backend response
            if response.get("external_session_id"):
                session.metadata["external_session_id"] = response["external_session_id"]
            if response.get("compacted_up_to") is not None:
                session.metadata["compacted_up_to"] = response["compacted_up_to"]
            if response.get("cache_reference"):
                self._context_builder.sync_cache(response["cache_reference"])
            if response.get("reply"):
                session.metadata["last_reply"] = response["reply"]

            return True
        except Exception as e:
            print(f"[MessageRouter] route_to_exocore failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Display incoming messages (Channel 2 receive side)
    # ------------------------------------------------------------------

    def display_incoming(self, from_agent: str, message: str) -> None:
        """Display an incoming message in the terminal.

        Called when the local server receives a message from the Superior
        or another CLI agent. For now, prints directly. Folding/collapsing
        is a future enhancement.
        """
        border = "─" * 60
        print(f"\n{border}")
        print(f"  [来自 {from_agent}]")
        print(f"  {message}")
        print(f"{border}\n")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
