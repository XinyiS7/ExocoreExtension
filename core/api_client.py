"""
HTTP client for ExoCore backend.
Endpoint: POST /api/agents/external_context_inject/
Spec: ExoCore/Plan/ExocoreExtension_Payload_Spec.md
"""
import requests
from config import EXOCORE_BASE_URL, EXOCORE_AGENT_NAME, EXOCORE_EXTENSION_KEY, EXOCORE_ADMIN_KEY

# Maps our internal capture method names to API source values
SOURCE_MAP = {
    "clipboard": "clipboard",
    "uiautomation": "uiautomation",
    "terminal": "terminal_bridge",
}


class ExocoreClient:
    def __init__(self, base_url: str = EXOCORE_BASE_URL, agent_name: str = EXOCORE_AGENT_NAME):
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

        # Auth: body extension_secret preferred; fallback to X-Admin-Key header
        headers = {}
        if EXOCORE_EXTENSION_KEY:
            payload["extension_secret"] = EXOCORE_EXTENSION_KEY
        elif EXOCORE_ADMIN_KEY:
            headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY

        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        return resp.json()
