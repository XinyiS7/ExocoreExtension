# WezBridge Multi-Turn Session & Agent-Supervisor Upgrade

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade wez_bridge from a passive sentinel+commander into an independent agent-supervisor tool that maintains multi-turn conversation sessions (decoupled from panes, 48h TTL), routes messages across dual channels (sentinel + direct Superior messages), and sends full formatted context records to ExoCore.

**Architecture:** Three new modules — SessionManager (CRUD for decoupled conversation sessions with 48h TTL, resume like Claude Code), MessageRouter (dual-channel dispatch: sentinel alerts + direct Superior-to-pane messages), ContextBuilder (assembles full session context into ExoCore-compatible payloads). The LocalCommandServer gains three new endpoints for session lifecycle and Superior message reception. The WezBridgeExtension is updated to wire all new components. Cache is backend-managed; we sync context structure when cache references come back from ExoCore.

**Tech Stack:** Python 3.12+, stdlib `http.server`, `threading`, `dataclasses`, `json`; no new dependencies required.

---

## Pre-Implementation Notes

- **Cache responsibility:** Backend (ExoCore) manages cache. If a `cache_reference` is returned in any response, wez_bridge syncs the context structure accordingly — no local cache logic beyond what CacheManager already does.
- **Pane discovery for Superior:** Backend auto-discovers open WezTerm windows. Wez_bridge only attaches its own `pane_id` as metadata in payloads; it does not need to discover the Superior's pane.
- **Superior → Pane messages:** Backend's Superior has a dedicated tool to send text to any WezTerm window. After invoking the tool, Superior replies with a text body. Wez_bridge receives this and displays it in the terminal (folding/collapsing is a future enhancement).
- **Session storage:** JSON files under `ExoCoreData/sessions/`. Auto-cleanup every time the session list is accessed. No migration concerns — this is a new feature.

### Confirmed Backend Decisions (2026-05-29)

**API Contract (Final):**
```
Request:  mode=wez_bridge, messages[{role,content}], external_session_id, metadata{}
Response: {success, reply, compacted_up_to, external_session_id}
```

**Auto-summary:** Backend auto-compresses when >30 messages → old messages → summary + keep last 15. `compacted_up_to` returns cursor position.

| # | Decision | Rationale | Code Impact |
|---|----------|-----------|-------------|
| 1 | `send_message` endpoint — wezterm CLI 直接注入即可；HTTP 端点预留给非 wezterm CLI agent 或跨机器场景 | Superior 调用 `wezterm_cli send-text` 后文本已在目标 pane | `local_server.py` keep route, document as cross-agent fallback |
| 2 | 用 `external_context_inject` 的 wez_bridge 模式, `external_session_id` 首次请求可为空, 响应回传后后续携带 | 阻塞式 context_inject, 非 SSE | `context_builder.py` sends `external_session_id` when available |
| 3 | compact 游标用独立字段 `compacted_up_to` | 与 `cache_reference` 分离 | Response: `{ "reply": "...", "compacted_up_to": 15 }` |
| 4 | **不**把 JSON 塞进 `captured_text`。用独立 `messages` 字段传 `[{role, content}, ...]` | 结构化数据走结构化字段 | `captured_text` = 纯文本 fallback |
| 5 | `mode` = `"wez_bridge"` | 后端此模式已实现 | `context_builder.py:build_inject_payload()` |
| 6 | 自动摘要阈值: >30条时压缩旧消息→摘要, 保留最近15条 | 后端 `ExternalContextService` 驱动 | Extension 侧接收 `compacted_up_to` 即可 |

---

## File Structure

```
extensions/wez_bridge/
├── __init__.py
├── config.py                # MODIFY: add session/route config values
├── wezterm_cli.py           # unchanged
├── cache_manager.py         # unchanged
├── sentinel.py              # MODIFY: wire alerts through MessageRouter
├── commander.py             # unchanged
├── local_server.py          # MODIFY: add 3 new endpoints
├── session_manager.py       # NEW: Session CRUD, 48h TTL, resume
├── message_router.py        # NEW: dual-channel message dispatch
├── context_builder.py       # NEW: full context assembly → ExoCore payload
└── extension.py             # MODIFY: wire SessionManager, MessageRouter, ContextBuilder

tests/wez_bridge/
├── __init__.py
├── test_config.py           # MODIFY: add tests for new config values
├── test_wezterm_cli.py      # unchanged
├── test_cache_manager.py    # unchanged
├── test_sentinel.py         # MODIFY: sentinel now routes through MessageRouter
├── test_commander.py        # unchanged
├── test_local_server.py     # MODIFY: add tests for new endpoints
├── test_extension.py        # MODIFY: add tests for new components
├── test_session_manager.py  # NEW
├── test_message_router.py   # NEW
├── test_context_builder.py  # NEW
└── test_integration.py      # MODIFY: add multi-turn integration test
```

---

### Task 1: Extend Config for Sessions and Routing

**Files:**
- Modify: `extensions/wez_bridge/config.py`

- [ ] **Step 1: Add new config values**

Edit `extensions/wez_bridge/config.py` — append after the existing `AGENT_ID` line:

```python
# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
SESSION_DIR = os.path.join(EXOCORE_DATA_ROOT, "sessions")
SESSION_MAX_AGE_SEC = 172800  # 48 hours
SESSION_SUMMARY_MAX_CHARS = 20  # first user message, truncated

# ---------------------------------------------------------------------------
# Message routing
# ---------------------------------------------------------------------------
# Backend auto-discovers WezTerm windows. We attach our pane_id as metadata
# so the Superior can target replies to the correct pane.
HOST_PANE_ID_ENV_VAR = "WEZTERM_PANE"

# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------
CONTEXT_MAX_MESSAGES = 50  # max messages to include in a context payload
CONTEXT_TRUNCATE_CHARS = 4000  # max chars per message in context payload
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('extensions/wez_bridge/config.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add extensions/wez_bridge/config.py
git commit -m "feat(wez_bridge): add session, routing, and context config values"
```

---

### Task 2: Session Manager — Core Data Structures and CRUD

**Files:**
- Create: `extensions/wez_bridge/session_manager.py`
- Create: `tests/wez_bridge/test_session_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_session_manager.py`:

```python
import os
import time
import tempfile
from extensions.wez_bridge.session_manager import (
    SessionManager, Session, Message,
)


class TestSessionManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.sm = SessionManager(session_dir=self.tmpdir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --- Session creation ---

    def test_create_session_returns_session(self):
        session = self.sm.create_session(
            first_user_message="帮我看看这个数据库报错是什么原因",
            metadata={"pane_id": "2", "agent_name": "Alessandro"},
        )
        assert isinstance(session, Session)
        assert session.session_id.startswith("sess_")
        assert len(session.messages) == 1
        assert session.messages[0].role == "user"

    def test_summary_is_first_20_chars_of_first_message(self):
        session = self.sm.create_session(
            first_user_message="12345678901234567890extra",
            metadata={},
        )
        assert session.summary == "12345678901234567890"
        assert len(session.summary) <= 20

    def test_summary_handles_short_message(self):
        session = self.sm.create_session(
            first_user_message="hi",
            metadata={},
        )
        assert session.summary == "hi"

    def test_summary_strips_whitespace(self):
        session = self.sm.create_session(
            first_user_message="   short message with spaces   ",
            metadata={},
        )
        assert session.summary == "short message with s"

    # --- Add message ---

    def test_add_message_appends_to_session(self):
        session = self.sm.create_session("hello world", {})
        self.sm.add_message(
            session.session_id,
            Message(role="agent", content="你好！有什么可以帮助你的？", metadata={}),
        )
        got = self.sm.get_session(session.session_id)
        assert len(got.messages) == 2
        assert got.messages[1].role == "agent"

    def test_add_message_updates_last_active(self):
        session = self.sm.create_session("hello", {})
        before = session.last_active
        time.sleep(0.01)
        self.sm.add_message(
            session.session_id,
            Message(role="system", content="done", metadata={}),
        )
        after = self.sm.get_session(session.session_id).last_active
        assert after > before

    def test_add_message_to_unknown_session_raises(self):
        try:
            self.sm.add_message(
                "nonexistent",
                Message(role="user", content="hi", metadata={}),
            )
            assert False, "should have raised"
        except KeyError:
            pass

    # --- List sessions ---

    def test_list_sessions_returns_recent_only(self):
        s1 = self.sm.create_session("first message here", {"pane_id": "1"})
        s2 = self.sm.create_session("second message goes", {"pane_id": "2"})
        sessions = self.sm.list_sessions()
        ids = [s.session_id for s in sessions]
        assert s1.session_id in ids
        assert s2.session_id in ids

    def test_list_sessions_sorted_by_last_active_desc(self):
        s1 = self.sm.create_session("aaa", {})
        time.sleep(0.02)
        s2 = self.sm.create_session("bbb", {})
        sessions = self.sm.list_sessions()
        assert sessions[0].session_id == s2.session_id

    # --- Cleanup (48h TTL) ---

    def test_cleanup_removes_expired_sessions(self):
        session = self.sm.create_session("test", {})
        # Artificially age the session
        session.last_active = time.time() - 200_000  # ~55h ago
        session.created_at = time.time() - 200_000
        self.sm._save_session(session)

        removed = self.sm.cleanup_expired()
        assert removed >= 1
        assert self.sm.get_session(session.session_id) is None

    def test_cleanup_keeps_recent_sessions(self):
        session = self.sm.create_session("test", {})
        removed = self.sm.cleanup_expired()
        assert removed == 0
        assert self.sm.get_session(session.session_id) is not None

    # --- Delete session ---

    def test_delete_session_removes_from_memory_and_disk(self):
        session = self.sm.create_session("test", {})
        self.sm.delete_session(session.session_id)
        assert self.sm.get_session(session.session_id) is None
        # File should also be gone
        import glob
        files = glob.glob(os.path.join(self.tmpdir, f"*{session.session_id}*"))
        assert len(files) == 0

    # --- Persistence ---

    def test_persist_and_restore(self):
        s1 = self.sm.create_session("hello world test message", {"pane_id": "3"})
        self.sm.add_message(
            s1.session_id,
            Message(role="agent", content="reply text", metadata={}),
        )
        sid = s1.session_id

        # Create a new SessionManager pointing to the same dir
        sm2 = SessionManager(session_dir=self.tmpdir)
        restored = sm2.get_session(sid)
        assert restored is not None
        assert restored.summary == s1.summary
        assert len(restored.messages) == 2
        assert restored.messages[1].content == "reply text"

    def test_ensure_session_dir_created(self):
        new_dir = os.path.join(self.tmpdir, "nested", "sessions")
        sm = SessionManager(session_dir=new_dir)
        session = sm.create_session("test", {})
        assert os.path.exists(new_dir)


class TestMessage:
    def test_message_has_timestamp_by_default(self):
        msg = Message(role="user", content="hi", metadata={})
        assert msg.timestamp > 0
        assert msg.timestamp <= time.time()

    def test_message_to_dict_and_back(self):
        msg = Message(role="sentinel", content="alert!", metadata={"pane_id": "2"})
        d = msg.to_dict()
        restored = Message.from_dict(d)
        assert restored.role == msg.role
        assert restored.content == msg.content
        assert restored.metadata == msg.metadata
        assert restored.timestamp == msg.timestamp
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_session_manager.py -v`
Expected: all FAIL with "No module named 'extensions.wez_bridge.session_manager'"

- [ ] **Step 3: Implement SessionManager**

Create `extensions/wez_bridge/session_manager.py`:

```python
"""
Session Manager — decoupled multi-turn conversation sessions.

Sessions are NOT bound to a specific pane. They can be resumed in any pane,
similar to Claude Code's resume mechanism. Sessions older than 48 hours are
auto-cleaned. The summary is the first 20 characters of the first user message.
"""
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Message:
    """A single message in a conversation session."""
    role: str           # "user" | "agent" | "system" | "sentinel"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            role=d["role"],
            content=d["content"],
            timestamp=d.get("timestamp", time.time()),
            metadata=d.get("metadata", {}),
        )


@dataclass
class Session:
    """A multi-turn conversation session."""
    session_id: str
    summary: str
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "summary": self.summary,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "last_active": self.last_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        messages = [Message.from_dict(m) for m in d.get("messages", [])]
        return cls(
            session_id=d["session_id"],
            summary=d.get("summary", ""),
            messages=messages,
            created_at=d.get("created_at", time.time()),
            last_active=d.get("last_active", time.time()),
            metadata=d.get("metadata", {}),
        )


class SessionManager:
    """CRUD for decoupled multi-turn conversation sessions.

    Sessions are persisted as JSON files under ``session_dir``.
    Auto-cleanup removes sessions older than ``max_age_seconds`` (default 48h).
    """

    def __init__(
        self,
        session_dir: Optional[str] = None,
        max_age_seconds: Optional[float] = None,
        summary_max_chars: Optional[int] = None,
    ):
        from .config import SESSION_DIR, SESSION_MAX_AGE_SEC, SESSION_SUMMARY_MAX_CHARS
        self._dir = session_dir or SESSION_DIR
        self._max_age = max_age_seconds or SESSION_MAX_AGE_SEC
        self._summary_max = summary_max_chars or SESSION_SUMMARY_MAX_CHARS
        self._cache: dict[str, Session] = {}  # in-memory cache
        self._ensure_dir()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(
        self,
        first_user_message: str,
        metadata: Optional[dict] = None,
    ) -> Session:
        """Create a new session from the first user message.

        The summary is derived from the first message (trimmed + first N chars).
        The first message is added as a ``user`` role Message.
        """
        session_id = self._generate_id()
        summary = first_user_message.strip()[:self._summary_max]
        session = Session(
            session_id=session_id,
            summary=summary,
            metadata=metadata or {},
        )
        session.messages.append(Message(
            role="user",
            content=first_user_message.strip(),
            metadata={"sequence": 0},
        ))
        self._cache[session_id] = session
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Return a session by ID, or None if not found / expired."""
        # Try in-memory cache first
        if session_id in self._cache:
            session = self._cache[session_id]
            if self._is_expired(session):
                self.delete_session(session_id)
                return None
            return session
        # Try disk
        session = self._load_session(session_id)
        if session is None:
            return None
        if self._is_expired(session):
            self.delete_session(session_id)
            return None
        self._cache[session_id] = session
        return session

    def list_sessions(self) -> list[Session]:
        """Return all non-expired sessions, most recent first."""
        self.cleanup_expired()
        # Load any sessions from disk not in cache
        self._load_all_from_disk()
        sessions = [s for s in self._cache.values() if not self._is_expired(s)]
        sessions.sort(key=lambda s: s.last_active, reverse=True)
        return sessions

    def add_message(self, session_id: str, message: Message) -> None:
        """Append a message to a session. Raises KeyError if session not found."""
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Session not found: {session_id}")
        session.messages.append(message)
        session.last_active = time.time()
        self._save_session(session)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from memory and disk. Returns True if it existed."""
        existed = session_id in self._cache or self._session_file_exists(session_id)
        self._cache.pop(session_id, None)
        filepath = self._session_path(session_id)
        if os.path.exists(filepath):
            os.remove(filepath)
        return existed

    def cleanup_expired(self) -> int:
        """Remove all expired sessions from memory and disk. Returns count removed."""
        removed = 0
        # Clean in-memory
        for sid in list(self._cache.keys()):
            if self._is_expired(self._cache[sid]):
                self.delete_session(sid)
                removed += 1
        # Clean orphaned files on disk
        for fname in os.listdir(self._dir):
            if not (fname.startswith("sess_") and fname.endswith(".json")):
                continue
            sid = fname[:-5]  # strip ".json"
            if sid in self._cache:
                continue
            fpath = os.path.join(self._dir, fname)
            if time.time() - os.path.getmtime(fpath) > self._max_age:
                try:
                    os.remove(fpath)
                    removed += 1
                except OSError:
                    pass
        return removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_id(self) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        short = uuid.uuid4().hex[:6]
        return f"sess_{ts}_{short}"

    def _session_path(self, session_id: str) -> str:
        return os.path.join(self._dir, f"{session_id}.json")

    def _session_file_exists(self, session_id: str) -> bool:
        return os.path.exists(self._session_path(session_id))

    def _is_expired(self, session: Session) -> bool:
        return (time.time() - session.last_active) > self._max_age

    def _save_session(self, session: Session) -> None:
        filepath = self._session_path(session.session_id)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)

    def _load_session(self, session_id: str) -> Optional[Session]:
        filepath = self._session_path(session_id)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Session.from_dict(data)
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _load_all_from_disk(self) -> None:
        """Load any session files on disk that are not already in the cache."""
        if not os.path.isdir(self._dir):
            return
        for fname in os.listdir(self._dir):
            if not (fname.startswith("sess_") and fname.endswith(".json")):
                continue
            sid = fname[:-5]
            if sid in self._cache:
                continue
            session = self._load_session(sid)
            if session is not None and not self._is_expired(session):
                self._cache[sid] = session

    def _ensure_dir(self) -> None:
        os.makedirs(self._dir, exist_ok=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_session_manager.py -v`
Expected: 15 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/session_manager.py tests/wez_bridge/test_session_manager.py
git commit -m "feat(wez_bridge): add SessionManager with 48h TTL and resume support"
```

---

### Task 3: Context Builder

**Files:**
- Create: `extensions/wez_bridge/context_builder.py`
- Create: `tests/wez_bridge/test_context_builder.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_context_builder.py`:

```python
import time
from extensions.wez_bridge.session_manager import SessionManager, Message
from extensions.wez_bridge.context_builder import ContextBuilder


class TestContextBuilder:
    def setup_method(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.sm = SessionManager(session_dir=self.tmpdir)
        self.cb = ContextBuilder()

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_build_full_context_has_required_fields(self):
        session = self.sm.create_session("hello world", {"pane_id": "2"})
        self.sm.add_message(
            session.session_id,
            Message(role="agent", content="hi there", metadata={}),
        )
        context = self.cb.build_full_context(session, host_pane_id="2")
        assert "session_id" in context
        assert context["session_id"] == session.session_id
        assert "summary" in context
        assert context["summary"] == session.summary
        assert "messages" in context
        assert len(context["messages"]) == 2
        assert "metadata" in context

    def test_build_full_context_truncates_messages(self):
        session = self.sm.create_session("test", {})
        for i in range(60):
            self.sm.add_message(
                session.session_id,
                Message(role="system", content=f"msg_{i}", metadata={}),
            )
        context = self.cb.build_full_context(session, host_pane_id="1")
        # Should keep only the last CONTEXT_MAX_MESSAGES (50)
        assert len(context["messages"]) <= 50
        # The first one should be the oldest included
        messages = context["messages"]
        assert messages[0]["content"] in [f"msg_{i}" for i in range(10, 20)]

    def test_build_inject_payload_wraps_context(self):
        session = self.sm.create_session("fix the bug", {"pane_id": "3"})
        context = self.cb.build_full_context(session, host_pane_id="3")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
            mode="wez_bridge",
            custom_title="Multi-turn Session",
        )
        assert payload["agent"] == "Alessandro"
        assert payload["source"] == "terminal"
        assert payload["target_storage"] == "external_session"
        assert payload["mode"] == "wez_bridge"
        # Messages go in dedicated field, not stuffed into captured_text
        assert "messages" in payload
        assert len(payload["messages"]) > 0
        assert payload["messages"][0]["role"] == "user"
        # captured_text is plain text fallback only
        assert "captured_text" in payload
        # metadata is separate
        assert "metadata" in payload
        assert payload["metadata"]["session_id"] == session.session_id

    def test_build_inject_payload_includes_pane_id_in_metadata(self):
        session = self.sm.create_session("test", {"pane_id": "7"})
        context = self.cb.build_full_context(session, host_pane_id="7")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
            mode="wez_bridge",
        )
        assert payload["metadata"]["pane_id"] == "7"

    def test_build_inject_payload_sets_mode_to_wez_bridge(self):
        session = self.sm.create_session("test", {})
        context = self.cb.build_full_context(session, host_pane_id="1")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
        )
        assert payload["mode"] == "wez_bridge"

    def test_captured_text_is_plain_fallback(self):
        session = self.sm.create_session("plain text only", {})
        context = self.cb.build_full_context(session, host_pane_id="1")
        payload = self.cb.build_inject_payload(
            context,
            agent_name="Alessandro",
            capture_method="terminal",
            target_storage="external_session",
        )
        # captured_text should be a plain string, not JSON
        assert isinstance(payload["captured_text"], str)
        assert "{" not in payload["captured_text"]  # not JSON-stuffed

    def test_sync_cache_stores_reference(self):
        self.cb.sync_cache("cache_abc123")
        assert self.cb._cache_reference == "cache_abc123"

    def test_build_full_context_includes_cache_when_present(self):
        self.cb.sync_cache("cache_xyz")
        session = self.sm.create_session("test", {})
        context = self.cb.build_full_context(session, host_pane_id="1")
        assert context["metadata"]["cache_reference"] == "cache_xyz"

    def test_truncate_message_content(self):
        long_text = "x" * 5000
        truncated = self.cb._truncate_content(long_text)
        assert len(truncated) <= 4000
        assert truncated.endswith("...")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_context_builder.py -v`
Expected: all FAIL

- [ ] **Step 3: Implement ContextBuilder**

Create `extensions/wez_bridge/context_builder.py`:

```python
"""
Context Builder — assembles full session context into ExoCore-compatible payloads.

Takes a Session, builds a complete context dict, and wraps it into the
external_context_inject payload format that ExoCore expects. Cache references
are managed by the backend — we sync our context structure when one is received.
"""
import json
import time
from typing import Optional
from .session_manager import Session


class ContextBuilder:
    """Builds formatted context payloads from Session objects.

    Cache is backend-managed. When ExoCore returns a ``cache_reference``,
    call :meth:`sync_cache` to attach it to subsequent context payloads.
    """

    def __init__(self):
        self._cache_reference: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_full_context(
        self,
        session: Session,
        host_pane_id: str = "",
    ) -> dict:
        """Build a full context dict from a session.

        The output is a structured dict containing session metadata and
        all messages (truncated to ``CONTEXT_MAX_MESSAGES``).
        """
        from .config import CONTEXT_MAX_MESSAGES

        messages = session.messages
        # Keep only the most recent messages if over limit
        if len(messages) > CONTEXT_MAX_MESSAGES:
            messages = messages[-CONTEXT_MAX_MESSAGES:]

        serialized_messages = []
        for msg in messages:
            serialized_messages.append({
                "role": msg.role,
                "content": self._truncate_content(msg.content),
                "timestamp": msg.timestamp,
                "metadata": msg.metadata,
            })

        metadata = dict(session.metadata)
        metadata["pane_id"] = host_pane_id
        metadata["message_count"] = len(session.messages)
        metadata["truncated"] = len(session.messages) > CONTEXT_MAX_MESSAGES
        if self._cache_reference:
            metadata["cache_reference"] = self._cache_reference

        return {
            "session_id": session.session_id,
            "summary": session.summary,
            "messages": serialized_messages,
            "created_at": session.created_at,
            "last_active": session.last_active,
            "metadata": metadata,
        }

    def build_inject_payload(
        self,
        context: dict,
        agent_name: str,
        capture_method: str,
        target_storage: str,
        mode: str = "wez_bridge",
        custom_title: Optional[str] = None,
    ) -> dict:
        """Wrap a full context dict into the external_context_inject payload format.

        Structured data is sent in dedicated fields (messages, metadata).
        ``captured_text`` is kept as a plain-text fallback summary only.
        """
        # Build plain-text fallback from session summary + last messages
        fallback_text = f"[{context.get('summary', '')}] "
        recent = context.get("messages", [])[-3:]  # last 3 messages as fallback
        fallback_text += " | ".join(
            f"{m['role']}: {m['content'][:100]}" for m in recent
        )

        payload = {
            "client_type": "windows_extension",
            "client_display": "WezTerm Bridge",
            "agent": agent_name,
            "source": capture_method,
            "captured_text": fallback_text,
            "messages": context.get("messages", []),
            "target_storage": target_storage,
            "mode": mode,
            "metadata": context.get("metadata", {}),
        }
        if custom_title:
            payload["custom_title"] = custom_title
        # Carry external_session_id from previous responses for session correlation
        ext_sid = context.get("metadata", {}).get("external_session_id")
        if ext_sid:
            payload["external_session_id"] = ext_sid
        return payload

    def sync_cache(self, cache_reference: str) -> None:
        """Store a cache reference from the backend for future context payloads."""
        self._cache_reference = cache_reference

    def clear_cache(self) -> None:
        """Clear the stored cache reference."""
        self._cache_reference = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate_content(content: str) -> str:
        from .config import CONTEXT_TRUNCATE_CHARS
        if len(content) <= CONTEXT_TRUNCATE_CHARS:
            return content
        return content[:CONTEXT_TRUNCATE_CHARS - 3] + "..."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_context_builder.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/context_builder.py tests/wez_bridge/test_context_builder.py
git commit -m "feat(wez_bridge): add ContextBuilder for full session payload assembly"
```

---

### Task 4: Message Router

**Files:**
- Create: `extensions/wez_bridge/message_router.py`
- Create: `tests/wez_bridge/test_message_router.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_message_router.py`:

```python
from unittest.mock import MagicMock, patch
from extensions.wez_bridge.message_router import MessageRouter


class TestMessageRouter:
    def setup_method(self):
        self.mock_cli = MagicMock()
        self.mock_session_manager = MagicMock()
        self.mock_context_builder = MagicMock()
        self.mock_client_factory = MagicMock()
        self.router = MessageRouter(
            cli=self.mock_cli,
            session_manager=self.mock_session_manager,
            context_builder=self.mock_context_builder,
            client_factory=self.mock_client_factory,
        )

    # --- Route to pane ---

    def test_route_to_pane_sends_text(self):
        self.mock_cli.send_text.return_value = True
        result = self.router.route_to_pane(
            target_pane_id="3",
            message="hello from superior",
            from_agent="G045",
        )
        assert result is True
        self.mock_cli.send_text.assert_called_once()
        call_text = self.mock_cli.send_text.call_args[1]["text"]
        assert "hello from superior" in call_text
        assert "G045" in call_text

    def test_route_to_pane_returns_false_on_failure(self):
        self.mock_cli.send_text.return_value = False
        result = self.router.route_to_pane(
            target_pane_id="99",
            message="test",
            from_agent="unknown",
        )
        assert result is False

    # --- Route to ExoCore ---

    def test_route_to_exocore_builds_context_and_injects(self):
        mock_session = MagicMock()
        mock_session.session_id = "sess_test"
        mock_session.summary = "test summary"
        mock_session.metadata = {"pane_id": "2"}

        self.mock_context_builder.build_full_context.return_value = {
            "session_id": "sess_test",
            "summary": "test summary",
            "messages": [],
            "metadata": {},
        }
        self.mock_context_builder.build_inject_payload.return_value = {
            "agent": "Alessandro",
            "captured_text": "...",
        }

        mock_client = MagicMock()
        mock_client.inject_context.return_value = {"status": "ok"}
        self.mock_client_factory.return_value = mock_client

        result = self.router.route_to_exocore(
            session=mock_session,
            trigger="sentinel_alert",
            agent_name="Alessandro",
            host_pane_id="2",
        )
        assert result is True
        self.mock_context_builder.build_full_context.assert_called_once()
        mock_client.inject_context.assert_called_once()

    def test_route_to_exocore_handles_inject_failure(self):
        mock_session = MagicMock()
        mock_session.session_id = "sess_test"
        self.mock_context_builder.build_full_context.return_value = {
            "session_id": "sess_test",
            "messages": [],
            "metadata": {},
        }
        self.mock_context_builder.build_inject_payload.return_value = {}

        mock_client = MagicMock()
        mock_client.inject_context.side_effect = Exception("Connection refused")
        self.mock_client_factory.return_value = mock_client

        result = self.router.route_to_exocore(
            session=mock_session,
            trigger="sentinel_alert",
            agent_name="Alessandro",
            host_pane_id="2",
        )
        assert result is False

    # --- Display incoming ---

    def test_display_incoming_prints_formatted_message(self, capsys):
        self.router.display_incoming(
            from_agent="G045",
            message="Build completed successfully",
        )
        captured = capsys.readouterr()
        assert "G045" in captured.out
        assert "Build completed successfully" in captured.out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_message_router.py -v`
Expected: all FAIL

- [ ] **Step 3: Implement MessageRouter**

Create `extensions/wez_bridge/message_router.py`:

```python
"""
Message Router — dual-channel dispatch for WezTerm panes.

Channel 1 (Sentinel): sentinel alerts → session → context builder → ExoCore.
Channel 2 (Direct): Superior/CLI agent → target pane via wezterm cli send-text.

The router does NOT handle Superior pane discovery — the backend auto-discovers
WezTerm windows. We only attach our own pane_id as metadata.
"""
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
        client_factory: Optional[Callable] = None,
    ):
        self._cli = cli or WezTermCLI()
        self._sessions = session_manager or SessionManager()
        self._context_builder = context_builder or ContextBuilder()
        self._client_factory = client_factory or self._default_client

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
    ) -> bool:
        """Build full context from a session and inject it into ExoCore.

        Args:
            session: The conversation session.
            trigger: What triggered this route ("sentinel_alert", "user_message", "manual").
            agent_name: Target agent name for ExoCore.
            host_pane_id: Current host pane ID for metadata.

        Returns:
            True if context was successfully injected.

        Response fields from ExoCore (stored in session metadata):
            - external_session_id: ExoCore's session correlation ID.
            - compacted_up_to: Message index cursor after compact.
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
                mode="wez_bridge",
                custom_title=f"[{trigger}] {session.summary}",
            )

            client = self._client_factory(agent_name)
            response = client.inject_context(**payload)

            # Store correlation IDs from backend response
            if response.get("external_session_id"):
                session.metadata["external_session_id"] = response["external_session_id"]
            if response.get("compacted_up_to") is not None:
                session.metadata["compacted_up_to"] = response["compacted_up_to"]
            if response.get("cache_reference"):
                self._context_builder.sync_cache(response["cache_reference"])

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

    @staticmethod
    def _default_client(agent_name: str):
        from core.api_client import ExocoreClient
        return ExocoreClient(agent_name=agent_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_message_router.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/message_router.py tests/wez_bridge/test_message_router.py
git commit -m "feat(wez_bridge): add MessageRouter for dual-channel dispatch"
```

---

### Task 5: Enhance Local Server with Session and Message Endpoints

**Files:**
- Modify: `extensions/wez_bridge/local_server.py`
- Modify: `tests/wez_bridge/test_local_server.py`

- [ ] **Step 1: Write the failing tests for new endpoints**

Append to `tests/wez_bridge/test_local_server.py`:

```python
import json
import time
import urllib.request
import urllib.error


class TestSessionEndpoints:
    """Tests for new session management endpoints."""

    def test_create_session_endpoint(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "session_id": "sess_test_001"}

        from extensions.wez_bridge.local_server import LocalCommandServer
        server = LocalCommandServer(host="127.0.0.1", port=18781, handler=handler)
        server.start()
        time.sleep(0.3)

        try:
            payload = json.dumps({
                "first_user_message": "帮我看看这个报错",
                "metadata": {"pane_id": "2"},
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18781/api/agents/session/new/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["status"] == "ok"
            assert body["session_id"] == "sess_test_001"
            assert len(received) == 1
            assert received[0]["first_user_message"] == "帮我看看这个报错"
        finally:
            server.stop()

    def test_resume_session_endpoint(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "session_id": "sess_abc", "messages": []}

        from extensions.wez_bridge.local_server import LocalCommandServer
        server = LocalCommandServer(host="127.0.0.1", port=18782, handler=handler)
        server.start()
        time.sleep(0.3)

        try:
            payload = json.dumps({
                "session_id": "sess_abc",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18782/api/agents/session/resume/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["session_id"] == "sess_abc"
            assert len(received) == 1
        finally:
            server.stop()

    def test_list_sessions_endpoint(self):
        received_path = []

        def handler(payload):
            received_path.append(payload)  # won't be called for GET
            return {"status": "ok"}

        from extensions.wez_bridge.local_server import LocalCommandServer
        server = LocalCommandServer(host="127.0.0.1", port=18783, handler=handler)
        server.start()
        time.sleep(0.3)

        try:
            req = urllib.request.Request(
                "http://127.0.0.1:18783/api/agents/sessions/",
                method="GET",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert "sessions" in body
        finally:
            server.stop()

    def test_send_message_endpoint(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "routed": True}

        from extensions.wez_bridge.local_server import LocalCommandServer
        server = LocalCommandServer(host="127.0.0.1", port=18784, handler=handler)
        server.start()
        time.sleep(0.3)

        try:
            payload = json.dumps({
                "from_agent": "G045",
                "target_pane_id": "2",
                "message": "构建完成，可以测试了",
                "msg_type": "notification",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18784/api/agents/send_message/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["status"] == "ok"
            assert body["routed"] is True
            assert len(received) == 1
            assert received[0]["from_agent"] == "G045"
        finally:
            server.stop()


class TestLocalServerRouting:
    """Verify the router dispatches to the correct handler based on path."""

    def test_different_paths_go_to_different_handlers(self):
        # We'll register separate handlers and verify routing
        from extensions.wez_bridge.local_server import LocalCommandServer

        calls = {}

        def default_handler(payload):
            calls["default"] = payload
            return {"status": "ok"}

        server = LocalCommandServer(host="127.0.0.1", port=18785, handler=default_handler)
        # Register route-specific handlers
        server.register_route("send_message", lambda p: calls.update({"send_message": p}) or {"status": "ok"})
        server.register_route("session_new", lambda p: calls.update({"session_new": p}) or {"status": "ok"})
        server.register_route("session_resume", lambda p: calls.update({"session_resume": p}) or {"status": "ok"})
        server.register_route("sessions_list", lambda: calls.update({"sessions_list": True}) or {"sessions": []})
        server.start()
        time.sleep(0.3)

        try:
            # Test send_message routing
            payload = json.dumps({
                "from_agent": "test", "target_pane_id": "1", "message": "hi"
            }).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:18785/api/agents/send_message/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
            assert "send_message" in calls

            # Test session_new routing
            payload2 = json.dumps({
                "first_user_message": "hello"
            }).encode("utf-8")
            req2 = urllib.request.Request(
                "http://127.0.0.1:18785/api/agents/session/new/",
                data=payload2,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req2, timeout=3)
            assert "session_new" in calls

        finally:
            server.stop()
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `python -m pytest tests/wez_bridge/test_local_server.py::TestSessionEndpoints -v`
Expected: FAIL — `register_route` method doesn't exist

- [ ] **Step 3: Rewrite local_server.py with multi-route support**

Rewrite `extensions/wez_bridge/local_server.py`:

```python
"""
Local HTTP server — receives commands and messages from ExoCore / CLI agents.

Endpoints:
    POST /api/agents/execute_command/   — ExoCore dispatch to Commander
    POST /api/agents/send_message/      — Superior/CLI agent → target pane
    POST /api/agents/session/new/       — Create a new session
    POST /api/agents/session/resume/    — Resume an existing session
    GET  /api/agents/sessions/          — List recent sessions

Route handlers are registered via :meth:`register_route` and dispatched by
path. The legacy ``handler`` callback is used for ``execute_command`` only.
"""
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Callable, Optional
from .config import LOCAL_SERVER_HOST, LOCAL_SERVER_PORT


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    """Multi-route HTTP handler.

    Route callbacks are set on the CLASS before starting the server.
    Each route key maps to a callable:

    - ``execute_command``: callable(payload: dict) -> dict
    - ``send_message``:    callable(payload: dict) -> dict
    - ``session_new``:     callable(payload: dict) -> dict
    - ``session_resume``:  callable(payload: dict) -> dict
    - ``sessions_list``:   callable() -> dict
    """

    # Route dispatch table — set by LocalCommandServer before start()
    routes: dict = {}

    def do_POST(self):
        path = self.path.rstrip("/")

        # Determine which route key to use
        route_key = None
        if path == "/api/agents/execute_command":
            route_key = "execute_command"
        elif path == "/api/agents/send_message":
            route_key = "send_message"
        elif path == "/api/agents/session/new":
            route_key = "session_new"
        elif path == "/api/agents/session/resume":
            route_key = "session_resume"
        else:
            self.send_error(404, "Not Found")
            return

        # Read and parse body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_error(400, "Invalid JSON")
            return

        # Dispatch to route handler
        cb = self.__class__.routes.get(route_key)
        if cb is None:
            self.send_error(404, "No handler registered")
            return

        try:
            result = cb(payload)
        except Exception as exc:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps({"error": str(exc)}).encode("utf-8")
            )
            return

        self._send_json(200, result)

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/api/agents/sessions":
            cb = self.__class__.routes.get("sessions_list")
            if cb is None:
                self.send_error(404, "No handler registered")
                return
            try:
                result = cb()
            except Exception as exc:
                self.send_error(500, str(exc))
                return
            self._send_json(200, result)
        else:
            self.send_error(404, "Not Found")

    def _send_json(self, status: int, data: dict):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def log_message(self, format, *args):
        pass  # Suppress HTTP request logging noise


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

class LocalCommandServer:
    """Micro HTTP server bound to 127.0.0.1.

    Routes:
        POST /api/agents/execute_command/   — execute_command handler
        POST /api/agents/send_message/      — send_message handler
        POST /api/agents/session/new/       — session_new handler
        POST /api/agents/session/resume/    — session_resume handler
        GET  /api/agents/sessions/          — sessions_list handler
    """

    def __init__(
        self,
        host: str = LOCAL_SERVER_HOST,
        port: int = LOCAL_SERVER_PORT,
        handler: Optional[Callable] = None,
    ):
        self._host = host
        self._port = port
        self._handler = handler  # legacy handler, maps to execute_command
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._httpd is not None:
            return

        # Set up route table on the handler CLASS
        _Handler.routes = {}
        if self._handler:
            _Handler.routes["execute_command"] = self._handler

        self._httpd = HTTPServer((self._host, self._port), _Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="WezBridgeHTTPServer"
        )
        self._thread.start()
        print(f"[LocalCommandServer] Listening on {self._host}:{self._port}")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def register_route(
        self,
        route_key: str,
        callback: Callable,
    ) -> None:
        """Register a route callback.

        Args:
            route_key: One of "execute_command", "send_message",
                       "session_new", "session_resume", "sessions_list".
            callback: Callable matching the route signature.
        """
        _Handler.routes[route_key] = callback

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}"
```

- [ ] **Step 4: Run all local server tests**

Run: `python -m pytest tests/wez_bridge/test_local_server.py -v`
Expected: all PASS (original 3 + new 5 = 8 PASS)

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/local_server.py tests/wez_bridge/test_local_server.py
git commit -m "feat(wez_bridge): add session and message endpoints to LocalCommandServer"
```

---

### Task 6: Update WezBridgeExtension to Wire New Components

**Files:**
- Modify: `extensions/wez_bridge/extension.py`
- Modify: `tests/wez_bridge/test_extension.py`

- [ ] **Step 1: Update the extension test**

Rewrite `tests/wez_bridge/test_extension.py`:

```python
from unittest.mock import MagicMock, patch
from extensions.wez_bridge.extension import WezBridgeExtension


class TestWezBridgeExtension:
    def test_name_is_wezterm_bridge(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            assert "WezTerm" in ext.name

    def test_start_registers_all_routes_and_starts_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI") as mock_cli_class, \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager") as mock_sm_class, \
             patch("extensions.wez_bridge.extension.ContextBuilder") as mock_cb_class, \
             patch("extensions.wez_bridge.extension.MessageRouter") as mock_mr_class, \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel_class, \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_cli = mock_cli_class.return_value
            mock_cli.get_host_pane_id.return_value = "2"
            mock_srv = mock_srv_class.return_value

            ext = WezBridgeExtension()
            ext.start()

            # Server should be started
            mock_srv.start.assert_called_once()
            # Sentinel should be started
            mock_sentinel_class.return_value.start.assert_called_once()
            # Routes should be registered
            assert mock_srv.register_route.call_count >= 4

    def test_stop_stops_all_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel_class, \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            ext = WezBridgeExtension()
            ext.start()
            ext.stop()

            mock_srv_class.return_value.stop.assert_called_once()
            mock_sentinel_class.return_value.stop.assert_called_once()

    def test_create_session_route(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager") as mock_sm_class, \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_sm = mock_sm_class.return_value
            mock_sm.create_session.return_value = MagicMock(
                session_id="sess_new_001",
                summary="test summary",
            )
            mock_srv = mock_srv_class.return_value
            # Capture the registered route handler
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb

            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            # Call the session_new handler
            result = registered["session_new"]({
                "first_user_message": "帮我看看这个报错",
                "metadata": {"pane_id": "2"},
            })
            assert result["status"] == "ok"
            assert result["session_id"] == "sess_new_001"
            mock_sm.create_session.assert_called_once_with(
                first_user_message="帮我看看这个报错",
                metadata={"pane_id": "2"},
            )

    def test_send_message_route_routes_to_pane(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter") as mock_mr_class, \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv_class:
            mock_mr = mock_mr_class.return_value
            mock_mr.route_to_pane.return_value = True
            mock_srv = mock_srv_class.return_value
            registered = {}

            def fake_register(key, cb):
                registered[key] = cb

            mock_srv.register_route.side_effect = fake_register

            ext = WezBridgeExtension()
            ext.start()

            result = registered["send_message"]({
                "from_agent": "G045",
                "target_pane_id": "2",
                "message": "构建完成",
                "msg_type": "notification",
            })
            assert result["status"] == "ok"
            mock_mr.route_to_pane.assert_called_once_with(
                target_pane_id="2",
                message="构建完成",
                from_agent="G045",
            )
            mock_mr.display_incoming.assert_called_once()

    def test_get_menu_items_includes_status(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.SessionManager"), \
             patch("extensions.wez_bridge.extension.ContextBuilder"), \
             patch("extensions.wez_bridge.extension.MessageRouter"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            ext = WezBridgeExtension()
            items = ext.get_menu_items()
            assert len(items) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_extension.py -v`
Expected: FAIL — SessionManager, ContextBuilder, MessageRouter imports missing

- [ ] **Step 3: Rewrite WezBridgeExtension**

Rewrite `extensions/wez_bridge/extension.py`:

```python
"""
WezTerm HITL Bridge Extension.

Orchestrates the Sentinel, Commander, SessionManager, MessageRouter,
ContextBuilder, and Local HTTP Server. Provides dual-channel communication
between WezTerm panes and ExoCore.
"""
from pystray import MenuItem
from core.base_extension import BaseExtension
from .wezterm_cli import WezTermCLI
from .cache_manager import CacheManager
from .session_manager import SessionManager
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

    def get_menu_items(self) -> list[MenuItem]:
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

    # ------------------------------------------------------------------
    # Sentinel → ExoCore
    # ------------------------------------------------------------------

    def _on_sentinel_alert(self, pane_id: str, cache_path: str, snippet: str):
        """Called when the Sentinel detects an error in a monitored pane.

        Creates or updates a session and routes the full context to ExoCore
        through the MessageRouter (Channel 1).
        """
        # Create a session for this alert if we don't have one for this pane
        session = self._sessions.create_session(
            first_user_message=f"[Sentinel Alert] Pane {pane_id}",
            metadata={"pane_id": pane_id, "cache_path": cache_path},
        )
        from .session_manager import Message
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
        agent_name = self.get_assigned_agent_name()
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
```

- [ ] **Step 4: Run extension tests**

Run: `python -m pytest tests/wez_bridge/test_extension.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/extension.py tests/wez_bridge/test_extension.py
git commit -m "feat(wez_bridge): wire SessionManager, ContextBuilder, MessageRouter into extension"
```

---

### Task 7: Update Sentinel to Use MessageRouter

**Files:**
- Modify: `extensions/wez_bridge/sentinel.py` (minor — add `router` parameter)
- Modify: `tests/wez_bridge/test_sentinel.py` (minor — update mocks)

- [ ] **Step 1: Update sentinel tests**

The sentinel's `on_alert` callback signature remains the same — it's the extension's callback that now routes through MessageRouter. The sentinel tests themselves don't need to change because the callback is injected.

Run the existing sentinel tests to confirm they still pass:

Run: `python -m pytest tests/wez_bridge/test_sentinel.py -v`
Expected: 10 PASS (unchanged)

The Sentinel's interface is unchanged — it still calls `on_alert(pane_id, cache_path, snippet)`. The extension's `_on_sentinel_alert` now delegates to `MessageRouter.route_to_exocore()` instead of directly calling `ExocoreClient.inject_context()`. The sentinel module itself needs no modifications.

- [ ] **Step 2: Commit (mark that sentinel is unchanged)**

No changes needed to sentinel — the existing `on_alert` callback is sufficient. The routing logic moves to the extension layer.

---

### Task 8: Integration Test

**Files:**
- Modify: `tests/wez_bridge/test_integration.py`

- [ ] **Step 1: Add multi-turn integration test**

Append to `tests/wez_bridge/test_integration.py`:

```python
class TestMultiTurnIntegration:
    """End-to-end test: session creation → message routing → context injection."""

    def test_full_multi_turn_flow(self):
        import tempfile
        from extensions.wez_bridge.session_manager import SessionManager, Message
        from extensions.wez_bridge.context_builder import ContextBuilder
        from extensions.wez_bridge.message_router import MessageRouter
        from unittest.mock import MagicMock, patch

        tmpdir = tempfile.mkdtemp()
        try:
            sm = SessionManager(session_dir=tmpdir)
            cb = ContextBuilder()
            mock_cli = MagicMock()
            mock_client = MagicMock()
            mock_client.inject_context.return_value = {"status": "ok"}

            router = MessageRouter(
                cli=mock_cli,
                session_manager=sm,
                context_builder=cb,
                client_factory=lambda name: mock_client,
            )

            # 1. User creates a session
            session = sm.create_session(
                first_user_message="帮我看看这个数据库报错是什么原因",
                metadata={"pane_id": "2"},
            )
            assert session.summary == "帮我看看这个数据库报错是"

            # 2. Agent replies
            sm.add_message(
                session.session_id,
                Message(
                    role="agent",
                    content="这是一个外键约束错误，需要检查 users 表和 orders 表的关联。",
                    metadata={},
                ),
            )

            # 3. User follows up
            sm.add_message(
                session.session_id,
                Message(
                    role="user",
                    content="好，帮我修复它",
                    metadata={},
                ),
            )

            # 4. Route to ExoCore
            ok = router.route_to_exocore(
                session=sm.get_session(session.session_id),
                trigger="user_message",
                agent_name="Alessandro",
                host_pane_id="2",
            )
            assert ok is True
            mock_client.inject_context.assert_called_once()

            # 5. Verify the inject payload sent messages + metadata separately
            call_kwargs = mock_client.inject_context.call_args[1]
            assert "messages" in call_kwargs
            assert len(call_kwargs["messages"]) == 3
            assert call_kwargs["mode"] == "wez_bridge"
            assert call_kwargs["metadata"]["trigger"] == "user_message"
            # captured_text is plain fallback, not JSON
            assert isinstance(call_kwargs["captured_text"], str)
            assert not call_kwargs["captured_text"].startswith("{")

        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_sentinel_to_exocore_flow(self):
        """Sentinel alert → session → ExoCore."""
        import tempfile
        from extensions.wez_bridge.session_manager import SessionManager, Message
        from extensions.wez_bridge.context_builder import ContextBuilder
        from extensions.wez_bridge.message_router import MessageRouter
        from unittest.mock import MagicMock

        tmpdir = tempfile.mkdtemp()
        try:
            sm = SessionManager(session_dir=tmpdir)
            cb = ContextBuilder()
            mock_cli = MagicMock()
            mock_client = MagicMock()
            mock_client.inject_context.return_value = {"status": "ok"}

            router = MessageRouter(
                cli=mock_cli,
                session_manager=sm,
                context_builder=cb,
                client_factory=lambda name: mock_client,
            )

            # Simulate sentinel alert: create session + add sentinel message
            session = sm.create_session(
                first_user_message="[Sentinel Alert] Pane 1",
                metadata={"pane_id": "1"},
            )
            sm.add_message(
                session.session_id,
                Message(
                    role="sentinel",
                    content="ModuleNotFoundError: No module named 'requests'",
                    metadata={"pane_id": "1"},
                ),
            )

            ok = router.route_to_exocore(
                session=sm.get_session(session.session_id),
                trigger="sentinel_alert",
                agent_name="Alessandro",
                host_pane_id="2",
            )
            assert ok is True

            # Verify payload uses structured messages field
            call_kwargs = mock_client.inject_context.call_args[1]
            assert call_kwargs["mode"] == "wez_bridge"
            assert "messages" in call_kwargs
            assert any(
                "ModuleNotFoundError" in m.get("content", "")
                for m in call_kwargs["messages"]
            )
            assert "sentinel_alert" in call_kwargs["custom_title"]

        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/wez_bridge/test_integration.py -v`
Expected: 4 PASS (2 original + 2 new)

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/wez_bridge/ -v`
Expected: all PASS (~35 tests total)

- [ ] **Step 4: Commit**

```bash
git add tests/wez_bridge/test_integration.py
git commit -m "test(wez_bridge): add multi-turn and sentinel integration tests"
```

---

## Backend Coordination Checklist

Before marking this plan complete, coordinate with the backend team on:

| # | Question | Answer Needed For |
|---|----------|-------------------|
| 1 | What is the exact payload format Superior will POST to `/api/agents/send_message/`? | `_on_send_message()` handler |
| 2 | Does `chat_stream` SSE response include a `session_id` field? | Session correlation in context_builder |
| 3 | Does `external_context_inject` accept our structured `captured_text` (JSON stringified context)? | `build_inject_payload()` format |
| 4 | What field name does backend use for cache references in responses? | `ContextBuilder.sync_cache()` |
| 5 | Does backend need any additional metadata fields from us (pane dimensions, terminal type, etc.)? | payload `metadata` dict |

---

## File Manifest (After Implementation)

```
extensions/wez_bridge/
├── __init__.py
├── config.py                # MODIFIED: +session/context config
├── wezterm_cli.py           # unchanged
├── cache_manager.py         # unchanged
├── session_manager.py       # NEW: Session CRUD, 48h TTL
├── context_builder.py       # NEW: context → ExoCore payload
├── message_router.py        # NEW: dual-channel dispatch
├── sentinel.py              # unchanged (callback interface sufficient)
├── commander.py             # unchanged
├── local_server.py          # MODIFIED: multi-route with register_route()
└── extension.py             # MODIFIED: wires all new components

tests/wez_bridge/
├── __init__.py
├── test_config.py
├── test_wezterm_cli.py
├── test_cache_manager.py
├── test_session_manager.py  # NEW: 15 tests
├── test_context_builder.py  # NEW: 7 tests
├── test_message_router.py   # NEW: 5 tests
├── test_sentinel.py
├── test_commander.py
├── test_local_server.py     # MODIFIED: +5 tests
├── test_extension.py        # MODIFIED: updated for new components
└── test_integration.py      # MODIFIED: +2 multi-turn tests
```
