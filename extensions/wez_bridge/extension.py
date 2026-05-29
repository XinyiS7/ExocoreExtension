"""
WezTerm HITL Bridge Extension.

Orchestrates the Sentinel, Commander, SessionManager, MessageRouter,
ContextBuilder, and Local HTTP Server. Provides dual-channel communication
between WezTerm panes and ExoCore.
"""
from core.base_extension import BaseExtension
from .wezterm_cli import WezTermCLI
from .cache_manager import CacheManager
from .session_manager import SessionManager, Message
from .context_builder import ContextBuilder
from .message_router import MessageRouter
from .sentinel import Sentinel
from .commander import Commander
from .local_server import LocalCommandServer
from .config import DEFAULT_AGENT


class WezBridgeExtension(BaseExtension):
    """WezTerm HITL Bridge — multi-turn sessions, dual-channel messaging."""

    def __init__(self):
        self._name = "WezTerm Bridge"
        self.default_agent = DEFAULT_AGENT

        # Shared services
        self._cli = WezTermCLI()
        self._cache = CacheManager()
        self._sessions = SessionManager()
        self._context_builder = ContextBuilder()
        self._commander = Commander(cli=self._cli)

        # Message router — dual-channel dispatch
        self._router = MessageRouter(
            cli=self._cli,
            session_manager=self._sessions,
            context_builder=self._context_builder,
        )

        # Sentinel — monitors non-host panes, routes alerts through MessageRouter
        self._sentinel = Sentinel(
            cli=self._cli,
            cache=self._cache,
            on_alert=self._on_sentinel_alert,
        )

        # Local HTTP server — receives commands, messages, and session ops
        self._server = LocalCommandServer()

        self._instance_agent_override: str | None = None  # set by /agent w/o session_id
        self._started = False

        # 哨兵去重：pane_id → (text_hash, timestamp)
        self._last_alert_hash: dict[str, tuple[str, float]] = {}
        self._ALERT_DEDUP_SEC = 30.0

    # ------------------------------------------------------------------
    # BaseExtension protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def start(self):
        if self._started:
            return

        print(f"[{self._name}] Starting components...")

        # Register all HTTP routes before starting the server
        self._server.register_route("execute_command", self._on_execute_command)
        self._server.register_route("send_message", self._on_send_message)
        self._server.register_route("session_new", self._on_session_new)
        self._server.register_route("session_resume", self._on_session_resume)
        self._server.register_route("sessions_list", self._on_sessions_list)
        self._server.register_route("agent_select", self._on_agent_select)
        self._server.register_route("chat", self._on_chat)
        self._server.register_route("sentinel_toggle", self._on_sentinel_toggle)
        self._server.register_route("cache_release", self._on_cache_release)

        # 1. Start the local HTTP server
        self._server.start()

        # 2. Auto-discover host pane
        host_id = self._cli.get_host_pane_id()
        if host_id:
            self._sentinel._host_pane_id = host_id
            print(f"[{self._name}] Host pane detected: {host_id}")

        # 3. Sentinel starts OFF — user enables via /sentinel on in TUI
        self._started = True
        print(f"[{self._name}] All components started. "
              f"Server: {self._server.address}")
        print(f"[{self._name}] Sentinel is OFF. Use /sentinel on to enable.")

    def stop(self):
        if not self._started:
            return
        self._started = False

        print(f"[{self._name}] Stopping components...")
        self._sentinel.stop()
        self._server.stop()
        print(f"[{self._name}] Stopped.")

    def get_menu_items(self) -> list:
        from pystray import MenuItem  # lazy — only tray mode triggers this
        return [
            MenuItem("WezTerm Bridge Status", self._menu_status),
        ]

    def get_settings_ui(self):
        return None

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    def _on_execute_command(self, payload: dict) -> dict:
        """POST /api/agents/execute_command/ — ExoCore dispatch to Commander."""
        pane_id = payload.get("target_pane_id", "")
        command = payload.get("command", "")
        execute_immediately = payload.get("execute_immediately", False)
        alert_message = payload.get("alert_message", "")

        print(f"[{self._name}] Received command for pane {pane_id}: {command[:80]}...")
        if alert_message:
            print(f"[{self._name}] Alert: {alert_message}")

        ok = self._commander.draft_cli_command(
            pane_id=pane_id,
            command=command,
            execute_immediately=execute_immediately,
        )
        return {
            "status": "ok" if ok else "failed",
            "pane_id": pane_id,
            "injected": ok,
        }

    def _on_send_message(self, payload: dict) -> dict:
        """POST /api/agents/send_message/ — Superior/CLI agent → target pane."""
        from_agent = payload.get("from_agent", "unknown")
        target_pane_id = payload.get("target_pane_id", "")
        message = payload.get("message", "")
        msg_type = payload.get("msg_type", "notification")

        # Display the incoming message in our terminal
        self._router.display_incoming(from_agent, message)

        # Route the message to the target pane
        ok = self._router.route_to_pane(
            target_pane_id=target_pane_id,
            message=message,
            from_agent=from_agent,
        )

        return {
            "status": "ok" if ok else "failed",
            "routed": ok,
            "target_pane_id": target_pane_id,
        }

    def _on_session_new(self, payload: dict) -> dict:
        """POST /api/agents/session/new/ — Create a new conversation session."""
        first_message = payload.get("first_user_message", "")
        metadata = payload.get("metadata", {})
        if not first_message.strip():
            return {"status": "error", "message": "first_user_message is required"}

        # Stamp the effective agent on session creation
        if "agent_name" not in metadata:
            metadata["agent_name"] = (
                self._instance_agent_override or self.get_assigned_agent_name()
            )

        session = self._sessions.create_session(
            first_user_message=first_message,
            metadata=metadata,
        )
        return {
            "status": "ok",
            "session_id": session.session_id,
            "summary": session.summary,
            "created_at": session.created_at,
        }

    def _on_session_resume(self, payload: dict) -> dict:
        """POST /api/agents/session/resume/ — Resume an existing session."""
        session_id = payload.get("session_id", "")
        session = self._sessions.get_session(session_id)
        if session is None:
            return {"status": "error", "message": f"Session not found: {session_id}"}

        return {
            "status": "ok",
            "session_id": session.session_id,
            "summary": session.summary,
            "messages": [
                {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                for m in session.messages
            ],
        }

    def _on_sessions_list(self) -> dict:
        """GET /api/agents/sessions/ — List recent sessions."""
        sessions = self._sessions.list_sessions()
        return {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "summary": s.summary,
                    "last_active": s.last_active,
                    "message_count": len(s.messages),
                }
                for s in sessions
            ],
        }

    def _on_agent_select(self, payload: dict) -> dict:
        """POST /api/agents/agent/select/ — Switch agent by name or ID.

        Payload:
            agent_name (str, optional): Agent name (e.g. "Alessandro").
            agent_id   (str, optional): Agent ID (e.g. "G045").
            session_id (str, optional): If set, override agent for that session
                                        only. Otherwise set instance default.
        """
        from core.agent_registry import agent_registry

        agent_name = payload.get("agent_name", "")
        agent_id = payload.get("agent_id", "")
        session_id = payload.get("session_id", "")

        if not agent_name and not agent_id:
            return {"status": "error", "message": "Provide agent_name or agent_id"}

        # Resolve: try name first, then ID fallback
        resolved = None
        if agent_name:
            resolved = agent_registry.get_agent_config(agent_name)
        if not resolved and agent_id:
            resolved = agent_registry.get_by_agent_id(agent_id)

        if not resolved:
            return {
                "status": "error",
                "message": f"Agent not found: name='{agent_name}' id='{agent_id}'",
            }

        resolved_name = resolved["name"]
        resolved_id = resolved.get("agent_id", "")

        if session_id:
            session = self._sessions.get_session(session_id)
            if session is None:
                return {"status": "error", "message": f"Session not found: {session_id}"}
            session.metadata["agent_name"] = resolved_name
            self._sessions._save_session(session)
        else:
            self._instance_agent_override = resolved_name

        return {
            "status": "ok",
            "agent_name": resolved_name,
            "agent_id": resolved_id,
        }

    def _on_chat(self, payload: dict) -> dict:
        """POST /api/agents/chat/ — Send a user message, get an agent reply.

        Payload:
            message    (str): User's message text.
            session_id (str, optional): Existing session to continue.
                                        If omitted, a new session is created.

        Returns:
            {reply, session_id, external_session_id, summary}

        external_context_inject already returns the agent reply synchronously
        in its HTTP response. No second call needed — route_to_exocore stores
        the reply in session.metadata["last_reply"].
        """
        message = payload.get("message", "")
        session_id = payload.get("session_id", "")
        if not message.strip():
            return {"status": "error", "message": "message is required"}

        # Get or create session
        if session_id:
            session = self._sessions.get_session(session_id)
            if session is None:
                return {"status": "error", "message": f"Session not found: {session_id}"}
        else:
            session = self._sessions.create_session(
                first_user_message=message,
                metadata={
                    "pane_id": self._sentinel._host_pane_id or "",
                    "agent_name": self._resolve_agent_for_session(None),
                },
            )
            session_id = session.session_id

        # Add user message
        self._sessions.add_message(
            session_id,
            Message(role="user", content=message, metadata={}),
        )

        # Inject full session context into ExoCore and get the agent reply.
        # The backend processes synchronously and returns the reply in the
        # HTTP response — route_to_exocore stores it as last_reply.
        host_id = self._sentinel._host_pane_id or ""
        agent_name = self._resolve_agent_for_session(session)
        ok = self._router.route_to_exocore(
            session=session,
            trigger="user_message",
            agent_name=agent_name,
            host_pane_id=host_id,
        )

        reply = session.metadata.get("last_reply", "")
        if not reply and ok:
            reply = "(sent — awaiting backend reply)"

        result = {
            "status": "ok" if ok else "error",
            "reply": reply,
            "session_id": session_id,
            "summary": session.summary,
            "external_session_id": session.metadata.get("external_session_id", ""),
        }
        if not ok:
            result["message"] = "Failed to reach ExoCore backend"
        return result

    def _resolve_agent_for_session(self, session=None) -> str:
        """Resolve agent name for a session.

        Priority: session override > instance override > registry/config default.
        """
        if session is not None:
            session_agent = (session.metadata or {}).get("agent_name")
            if session_agent:
                return session_agent
        if self._instance_agent_override:
            return self._instance_agent_override
        return self.get_assigned_agent_name()

    # ------------------------------------------------------------------
    # Sentinel control
    # ------------------------------------------------------------------

    def _on_sentinel_toggle(self, payload: dict) -> dict:
        """POST /api/agents/sentinel/toggle/ — Start/stop/status of the sentinel.

        Payload:
            action (str): "start" | "stop" | "status"

        The sentinel is OFF by default. User enables it via /sentinel on
        when leaving the screen. Alerts are marked as background activity
        so the backend handles them without treating them as user chat.
        """
        action = payload.get("action", "status")

        if action == "start":
            if not self._sentinel._running:
                self._sentinel.start()
                print(f"[{self._name}] Sentinel started by user")
                return {"status": "ok", "sentinel_running": True,
                        "message": "Sentinel started — monitoring panes"}
            return {"status": "ok", "sentinel_running": True,
                    "message": "Sentinel already running"}

        elif action == "stop":
            if self._sentinel._running:
                self._sentinel.stop()
                print(f"[{self._name}] Sentinel stopped by user")
                return {"status": "ok", "sentinel_running": False,
                        "message": "Sentinel stopped"}
            return {"status": "ok", "sentinel_running": False,
                    "message": "Sentinel already stopped"}

        else:  # status
            return {"status": "ok",
                    "sentinel_running": self._sentinel._running}

    def _on_cache_release(self, payload: dict) -> dict:
        """POST /api/agents/cache/release/ — 手动释放 Gemini 上下文缓存。

        调用 ExoCore 后端 POST /api/agents/cache/invalidate/ 释放当前 agent
        的 wez_bridge 缓存。通常由 compact skill 触发。
        """
        from config import EXOCORE_BASE_URL, EXOCORE_EXTENSION_KEY, EXOCORE_ADMIN_KEY
        from core.agent_registry import agent_registry as reg
        import requests as _requests

        agent_name = payload.get("agent_name") or self.get_assigned_agent_name()

        url = f"{EXOCORE_BASE_URL.rstrip('/')}/api/agents/cache/invalidate/"
        body = {"agent": agent_name}
        headers = {}
        if EXOCORE_EXTENSION_KEY:
            body["extension_secret"] = EXOCORE_EXTENSION_KEY
        elif EXOCORE_ADMIN_KEY:
            headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY

        try:
            resp = _requests.post(url, json=body, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()
            print(f"[{self._name}] Cache released for '{agent_name}': {result.get('message', '')}")
            return {"status": "ok", **result}
        except Exception as e:
            print(f"[{self._name}] Cache release failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Sentinel → ExoCore (Channel 1)
    # ------------------------------------------------------------------

    def _on_sentinel_alert(self, pane_id: str, cache_path: str, snippet: str):
        """Called when the Sentinel detects an error in a monitored pane.

        Dedup + fire-and-forget to ExoCore with mode="wez_bridge_sentinel".
        Same pane + same text hash within 30s → skip.
        """
        import hashlib
        import time

        # --- 去重：相同 pane + 相同文本哈希 30s 内不重复发送 ---
        text_hash = hashlib.sha256(snippet.encode()).hexdigest()
        now = time.time()
        prev = self._last_alert_hash.get(pane_id)
        if prev is not None:
            prev_hash, prev_ts = prev
            if prev_hash == text_hash and (now - prev_ts) < self._ALERT_DEDUP_SEC:
                print(f"[{self._name}] Sentinel dedup: pane {pane_id} same alert within "
                      f"{now - prev_ts:.1f}s, skipping")
                return
        self._last_alert_hash[pane_id] = (text_hash, now)

        # Create a session for this alert
        session = self._sessions.create_session(
            first_user_message=f"[Sentinel Alert] Pane {pane_id}",
            metadata={"pane_id": pane_id, "cache_path": cache_path,
                      "activity_type": "sentinel_auto"},
        )
        self._sessions.add_message(
            session.session_id,
            Message(
                role="sentinel",
                content=snippet,
                metadata={"pane_id": pane_id, "cache_path": cache_path},
            ),
        )

        # Fire-and-forget: inject context in a daemon thread so the
        # sentinel loop stays responsive. mode + activity_type tell
        # the backend this is automated background activity.
        host_id = self._sentinel._host_pane_id or ""
        agent_name = self._resolve_agent_for_session(session)
        import threading
        threading.Thread(
            target=self._router.route_to_exocore,
            args=(session,),
            kwargs={
                "trigger": "sentinel_alert",
                "agent_name": agent_name,
                "host_pane_id": host_id,
                "mode": "wez_bridge_sentinel",
                "activity_type": "sentinel_auto",
            },
            daemon=True,
            name=f"sentinel-alert-pane{pane_id}",
        ).start()

    # ------------------------------------------------------------------
    # Tray menu
    # ------------------------------------------------------------------

    def _menu_status(self):
        """Display current bridge status."""
        panes = self._cli.list_panes()
        sessions = self._sessions.list_sessions()
        print(f"[{self._name}] Status — {len(panes)} panes, "
              f"{len(sessions)} active sessions, "
              f"Server: {self._server.address}")
        for p in panes:
            print(f"  Pane {p.get('pane_id')}: {p.get('title', '?')} "
                  f"(active={p.get('is_active', False)})")
        if sessions:
            print(f"  Recent sessions:")
            for s in sessions[:5]:
                print(f"    {s.session_id} | {s.summary} | "
                      f"{len(s.messages)} msgs")
