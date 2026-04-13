"""
HTTP client for ExoCore backend.
Endpoint: POST /api/agents/external_context_inject/
Spec: ExoCore/Plan/ExocoreExtension_Payload_Spec.md
"""
import requests
from config import EXOCORE_BASE_URL, EXOCORE_PRESET_ID

# Maps our internal capture method names to API source values
SOURCE_MAP = {
    "clipboard": "windows_clipboard",
    "uiautomation": "uiautomation_pdf",
    "terminal": "terminal_bridge",
}


class ExocoreClient:
    def __init__(self, base_url: str = EXOCORE_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def inject_context(
        self,
        captured_text: str,
        user_prompt: str,
        capture_method: str,           # "clipboard" | "uiautomation" | "terminal"
        target_storage: str,           # "obsidian" | "session_memory" | "external_session"
        custom_title: str | None = None,
        preset_id: int = EXOCORE_PRESET_ID,
    ) -> dict:
        """
        POST captured context to ExoCore.
        Payload format per: ExoCore/Plan/ExocoreExtension_Payload_Spec.md
        """
        url = f"{self.base_url}/api/agents/external_context_inject/"
        payload = {
            "client_type":    "windows_companion",
            "preset_id":      preset_id,
            "source":         SOURCE_MAP.get(capture_method, capture_method),
            "captured_text":  captured_text,
            "target_storage": target_storage,
        }
        if user_prompt:
            payload["user_prompt"] = user_prompt
        if custom_title:
            payload["custom_title"] = custom_title

        resp = requests.post(url, json=payload, timeout=120)  # LLM can take a while
        resp.raise_for_status()
        return resp.json()
