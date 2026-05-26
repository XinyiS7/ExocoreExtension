"""
HTTP client for ExoCore backend.
Endpoint: POST /api/agents/external_context_inject/
Spec: ExoCore/Plan/ExocoreExtension_Payload_Spec.md
"""
import json

import requests
from core.agent_registry import agent_registry
from config import EXOCORE_BASE_URL, EXOCORE_EXTENSION_KEY, EXOCORE_ADMIN_KEY

# Maps our internal capture method names to API source values
SOURCE_MAP = {
    "clipboard": "clipboard",
    "uiautomation": "uiautomation",
    "terminal": "terminal",
}


class ExocoreClient:
    def __init__(self, base_url: str = EXOCORE_BASE_URL, agent_name: str | None = None):
        if agent_name is None:
            agent_name = agent_registry.get_default_name()
        self.base_url = base_url.rstrip("/")
        self.agent_name = agent_name

    def inject_context(
        self,
        captured_text: str,
        user_prompt: str,
        capture_method: str,    # "clipboard" | "uiautomation" | "terminal"
        target_storage: str,    # "external_session" | "session_memory"
        mode: str = "zero_tool",
        custom_title: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        POST captured context to ExoCore.
        Payload format per: ExoCore/Plan/ExocoreExtension_Payload_Spec.md
        """
        url = f"{self.base_url}/api/agents/external_context_inject/"
        payload = {
            "client_type":    "windows_extension",
            "client_display": "Clipboard Capture",
            "agent":          self.agent_name,
            "source":         SOURCE_MAP.get(capture_method, capture_method),
            "captured_text":  captured_text,
            "target_storage": target_storage,
            "mode":           mode,
        }
        if user_prompt:
            payload["user_prompt"] = user_prompt
        if custom_title:
            payload["custom_title"] = custom_title
        if metadata:
            payload["metadata"] = metadata

        # Auth: body extension_secret preferred; fallback to X-Admin-Key header
        headers = {}
        if EXOCORE_EXTENSION_KEY:
            payload["extension_secret"] = EXOCORE_EXTENSION_KEY
        elif EXOCORE_ADMIN_KEY:
            headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def chat_stream(
        self,
        session_id: str,
        host_pane_id: str,
        user_input: str,
    ):
        """Stream chat responses from ExoCore via SSE.

        POST /api/agents/chat_stream/
        Response: text/event-stream with JSON data chunks.
        Yields parsed JSON objects from each SSE data line.
        """
        url = f"{self.base_url}/api/agents/chat_stream/"
        payload = {
            "agent": self.agent_name,
            "session_id": session_id,
            "host_pane_id": host_pane_id,
            "user_input": user_input,
        }

        headers = {"Accept": "text/event-stream"}
        if not EXOCORE_EXTENSION_KEY and EXOCORE_ADMIN_KEY:
            headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY
        if EXOCORE_EXTENSION_KEY:
            payload["extension_secret"] = EXOCORE_EXTENSION_KEY

        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=300, stream=True
            )
            resp.raise_for_status()

            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]  # Strip "data: " prefix
                if data_str.strip() == "[DONE]":
                    break
                try:
                    yield json.loads(data_str)
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            print(f"[ExocoreClient] chat_stream error: {e}")
            return
