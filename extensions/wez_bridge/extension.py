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

        # 1. Start the local HTTP server
        self._server.start()

        # 2. Auto-discover host pane
        host_id = self._cli.get_host_pane_id()
        if host_id:
            self._sentinel._host_pane_id = host_id
            print(f"[{self._name}] Host pane detected: {host_id}")

        # 3. Start the sentinel
        self._sentinel.start()

        self._started = True
        print(f"[{self._name}] All components started. "
              f"Server: {self._server.address}")

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

    def _resolve_agent_for_session(self, session) -> str:
        """Resolve agent name for a session.

        Priority: session override > instance override > registry/config default.
        """
        session_agent = (session.metadata or {}).get("agent_name")
        if session_agent:
            return session_agent
        if self._instance_agent_override:
            return self._instance_agent_override
        return self.get_assigned_agent_name()

    # ------------------------------------------------------------------
    # Sentinel → ExoCore (Channel 1)
    # ------------------------------------------------------------------

    def _on_sentinel_alert(self, pane_id: str, cache_path: str, snippet: str):
        """Called when the Sentinel detects an error in a monitored pane.

        Creates a session, logs the alert, and routes full context to ExoCore
        through the MessageRouter.
        """
        # Create a session for this alert
        session = self._sessions.create_session(
            first_user_message=f"[Sentinel Alert] Pane {pane_id}",
            metadata={"pane_id": pane_id, "cache_path": cache_path},
        )
        self._sessions.add_message(
            session.session_id,
            Message(
                role="sentinel",
                content=snippet,
                metadata={"pane_id": pane_id, "cache_path": cache_path},
            ),
        )

        # Route full context to ExoCore
        host_id = self._sentinel._host_pane_id or ""
        agent_name = self._resolve_agent_for_session(session)
        ok = self._router.route_to_exocore(
            session=session,
            trigger="sentinel_alert",
            agent_name=agent_name,
            host_pane_id=host_id,
        )
        # Backend returns external_session_id in context_inject response.
        # Stored by MessageRouter in session metadata for correlation.

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
