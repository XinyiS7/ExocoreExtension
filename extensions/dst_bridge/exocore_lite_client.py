import requests
from config import EXOCORE_BASE_URL, EXOCORE_PRESET_ID, EXOCORE_ADMIN_KEY, EXOCORE_EXTENSION_KEY


class ExocoreLiteClient:
    """
    Client for ExoCore external_context_inject API.
    Used by DST Bridge to get real-time AI advice during gameplay.
    Payload format per: ExoCore/Plan/ExocoreExtension_Payload_Spec.md
    """

    ENDPOINT = "/api/agents/external_context_inject/"

    def __init__(self, base_url: str = EXOCORE_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.url = self.base_url + self.ENDPOINT

    def fast_inference(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "",
        level: str = "",
        temperature: float | None = None,
        preset_id: int | None = None,
        history: list | None = None,
    ) -> str:
        """
        Send game state + conversation history to ExoCore; return Alessandro's reply.

        Args:
            prompt:        Current game state / user message (latest turn).
            system_prompt: Appended (not replacing) to the preset's base system prompt.
            model:         Model override — empty string defers to preset default.
            level:         Thinking depth: "low" | "medium" | "high" (or numeric string).
            temperature:   Generation temperature override; None = use ExoCore default.
            preset_id:     AgentPreset ID; falls back to EXOCORE_PRESET_ID from config.
            history:       Prior turns as [{"role": "user"|"assistant", "content": "..."}].
                           Current prompt is appended as the final user turn.
        """
        resolved_preset_id = preset_id or EXOCORE_PRESET_ID

        messages = list(history) if history else []
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "preset_id":      resolved_preset_id,
            "messages":       messages,
            "source":         "game_state",
            "target_storage": "external_session",
            "mode":           "lite_tool",
            "client_type":    "dst_bridge",
        }

        # Optional overrides — only include when non-empty/non-None
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if model:
            payload["model"] = model
        if level:
            payload["level"] = level
        if temperature is not None:
            payload["temperature"] = temperature

        # Prefer per-extension token; fall back to admin key
        headers = {}
        if EXOCORE_EXTENSION_KEY:
            headers["X-Extension-Key"] = EXOCORE_EXTENSION_KEY
        elif EXOCORE_ADMIN_KEY:
            headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY

        try:
            resp = requests.post(self.url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data.get("reply", "")
        except requests.exceptions.ConnectionError:
            return f"[ExoCore] Cannot connect to {self.base_url} — is the server running?"
        except requests.exceptions.HTTPError as e:
            try:
                err = resp.json().get("error", str(e))
            except Exception:
                err = str(e)
            return f"[ExoCore] HTTP {resp.status_code}: {err}"
        except Exception as e:
            return f"[ExoCore] Error: {e}"
