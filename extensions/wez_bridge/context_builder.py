"""
Context Builder — assembles full session context into ExoCore-compatible payloads.

Takes a Session, builds a complete context dict, and wraps it into the
external_context_inject payload format that ExoCore expects.

Cache references are managed by the backend — we sync our context structure
when one is received. compacted_up_to is stored separately per session.

Payload format (confirmed with backend 2026-05-29):
  mode: "wez_bridge"
  messages: [{role, content}, ...]   — structured array, NOT stuffed into captured_text
  captured_text: plain-text fallback
  metadata: separate field
  external_session_id: (when available from previous response)
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
            "client_type": "wez_bridge",
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
