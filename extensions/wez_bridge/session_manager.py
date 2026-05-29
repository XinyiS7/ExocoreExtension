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
        if not os.path.isdir(self._dir):
            return removed
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
