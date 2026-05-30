"""
WezTerm HITL Bridge Extension.

Orchestrates the Sentinel, Commander, SessionManager, MessageRouter,
ContextBuilder, and Local HTTP Server. Provides dual-channel communication
between WezTerm panes and ExoCore.
"""
from core.base_extension import BaseExtension
from .wezterm_cli import WezTermCLI
from .cache_manager import CacheManager
from .session_manager import SessionManager, Session, Message
from .context_builder import ContextBuilder
from .message_router import MessageRouter
from .sentinel import Sentinel
from .commander import Commander
from .local_server import LocalCommandServer
from .config import DEFAULT_AGENT
import time


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

        # Active chat session — sentinel alerts reuse this session for cache continuity
        self._active_chat_session_id: str | None = None

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
            self._active_chat_session_id = session_id
        else:
            session = self._sessions.create_session(
                first_user_message=message,
                metadata={
                    "pane_id": self._sentinel._host_pane_id or "",
                    "agent_name": self._resolve_agent_for_session(None),
                },
            )
            session_id = session.session_id
            self._active_chat_session_id = session_id

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

    def _get_or_create_chat_session(self) -> Session:
        """Return the active chat session, creating one if none exists.

        Sentinel alerts reuse this session so the backend's per-preset
        cache (cli_conv) stays warm across sentinel rounds.
        """
        if self._active_chat_session_id:
            session = self._sessions.get_session(self._active_chat_session_id)
            if session is not None:
                return session
        # No active session — create a fresh one (will be adopted by _on_chat)
        host_id = self._sentinel._host_pane_id or ""
        agent_name = self._resolve_agent_for_session(None)
        session = self._sessions.create_session(
            first_user_message="[WezTerm Bridge Session]",
            metadata={
                "pane_id": host_id,
                "agent_name": agent_name,
            },
        )
        self._active_chat_session_id = session.session_id
        print(f"[{self._name}] Created fallback chat session {session.session_id} "
              f"for sentinel")
        return session

    def _on_sentinel_alert(self, pane_id: str, cache_path: str, snippet: str):
        """Called when the Sentinel detects an error in a monitored pane.

        Reuses the active chat session instead of creating a new one.
        Sentinel content goes into ``pending_sentinel`` (temp field), NOT
        the permanent message list. After the backend responds, two messages
        are generated: user summary + assistant reply.
        """
        import hashlib

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

        # Reuse the active chat session — do NOT create a new one
        session = self._get_or_create_chat_session()

        # Store sentinel content in temp field, NOT in messages
        session.pending_sentinel = {
            "pane_id": pane_id,
            "snippet": snippet,
            "cache_path": cache_path,
            "sent_at": now,
        }
        self._sessions._save_session(session)

        host_id = self._sentinel._host_pane_id or ""
        agent_name = self._resolve_agent_for_session(session)

        # Fire-and-forget in daemon thread so the sentinel loop stays responsive
        import threading
        threading.Thread(
            target=self._process_sentinel,
            args=(session.session_id, pane_id, snippet, agent_name, host_id),
            daemon=True,
            name=f"sentinel-alert-pane{pane_id}",
        ).start()

    def _process_sentinel(
        self, session_id: str, pane_id: str, snippet: str,
        agent_name: str, host_id: str,
    ):
        """Send sentinel alert to backend and resolve the response.

        Runs in a daemon thread. On success, generates two permanent
        messages (user summary + assistant reply) and handles compaction.
        """
        session = self._sessions.get_session(session_id)
        if session is None:
            print(f"[{self._name}] Sentinel session {session_id} expired, skipping")
            return
        if not session.pending_sentinel:
            print(f"[{self._name}] Sentinel pending_sentinel cleared for {session_id}, skipping")
            return

        ok = self._router.route_to_exocore(
            session=session,
            trigger="sentinel_alert",
            agent_name=agent_name,
            host_pane_id=host_id,
            mode="wez_bridge_sentinel",
            activity_type="sentinel_auto",
        )

        if not ok:
            print(f"[{self._name}] Sentinel backend route failed for pane {pane_id}")
            # Clear pending so we don't retry forever
            session.pending_sentinel = None
            self._sessions._save_session(session)
            return

        # Backend responded — resolve sentinel into permanent messages
        self._resolve_sentinel(session, pane_id, snippet)

    def _resolve_sentinel(self, session: Session, pane_id: str, snippet: str):
        """Convert pending sentinel into user+assistant messages.

        Generates:
          user: [HH:MM:SS] 哨兵报告：Pane {id} — {last error line}
          assistant: backend reply (if any)

        Then clears pending_sentinel and applies compaction if the backend
        signalled it.
        """
        from datetime import datetime

        reply = session.metadata.get("last_reply", "")
        now_str = datetime.now().strftime("%H:%M:%S")

        # Build user-facing summary from the sentinel snippet
        snippet_last_line = (
            snippet.strip().split("\n")[-1][:100] if snippet else "pane output"
        )
        user_msg = f"[{now_str}] 哨兵报告：Pane {pane_id} — {snippet_last_line}"

        # Append both messages to the session (each add_message saves)
        self._sessions.add_message(
            session.session_id,
            Message(
                role="user",
                content=user_msg,
                metadata={"source": "sentinel", "pane_id": pane_id},
            ),
        )
        if reply:
            self._sessions.add_message(
                session.session_id,
                Message(
                    role="assistant",
                    content=reply,
                    metadata={"source": "sentinel_response"},
                ),
            )
            # Clear last_reply so it isn't re-read by later rounds
            session.metadata.pop("last_reply", None)

        # Apply compaction if the backend signalled it
        compacted_up_to = session.metadata.get("compacted_up_to")
        if compacted_up_to is not None:
            self._apply_compaction(session, compacted_up_to)

        # Clear pending sentinel
        session.pending_sentinel = None
        session.last_active = time.time()
        self._sessions._save_session(session)

        print(f"[{self._name}] Sentinel resolved for pane {pane_id}: {user_msg[:100]}...")

    def _apply_compaction(self, session: Session, compacted_up_to: int):
        """Restructure session messages after backend compaction.

        Backend sends ``compact_chunks`` (aligned with Proposal model):
          [{summary, start_index, end_index}]
        and ``compacted_up_to`` (the last compacted index, n).

        Restructuring rules:
        - Build a single user message: "这是之前的会话总结：{summaries}"
        - Keep raw messages from n+1 onward
        - If the first kept message (was n+1) is ``user`` → discard
          (avoids two consecutive user messages)
        - Replace session.messages with the restructured list
        """
        compact_chunks = session.metadata.pop("compact_chunks", None)

        if compact_chunks:
            # Assemble compact summary as first user message
            summaries = " ".join(
                c.get("summary", "") for c in compact_chunks
            )
            compact_msg = f"这是之前的会话总结：{summaries}"

            # Raw messages start from compacted_up_to + 1
            raw_start = compacted_up_to + 1
            raw = session.messages[raw_start:] if raw_start < len(session.messages) else []

            # Discard first kept message if it's also user (no consecutive users)
            if raw and raw[0].role == "user":
                discarded = raw.pop(0)
                print(f"[{self._name}] Compaction: discarding consecutive user msg "
                      f"at index {raw_start}: {discarded.content[:60]}...")

            # Rebuild message list
            new_messages = [
                Message(
                    role="user",
                    content=compact_msg,
                    metadata={
                        "source": "compaction",
                        "compacted_up_to": compacted_up_to,
                        "chunk_count": len(compact_chunks),
                    },
                ),
            ]
            new_messages.extend(raw)

            old_count = len(session.messages)
            session.messages = new_messages
            session.compact_chunks = compact_chunks

            print(f"[{self._name}] Compaction applied: {old_count} msgs → "
                  f"{len(new_messages)} msgs ({len(compact_chunks)} chunks, "
                  f"compacted_up_to={compacted_up_to})")

            # compacted_up_to is no longer meaningful after restructuring —
            # the old indices are gone. Clear it so the backend doesn't
            # receive a stale cursor.
            session.metadata.pop("compacted_up_to", None)

        # Track cache rebuild signal
        cache_rebuilt = session.metadata.pop("cache_rebuilt", None)
        if cache_rebuilt:
            print(f"[{self._name}] Backend cache rebuilt — local state synced")

        # Track sentinel rounds completed
        rounds = session.metadata.pop("sentinel_rounds_completed", None)
        if rounds is not None:
            print(f"[{self._name}] Sentinel rounds completed: {rounds}")

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
