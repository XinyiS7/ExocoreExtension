import requests
from config import EXOCORE_BASE_URL, EXOCORE_AGENT_NAME, EXOCORE_EXTENSION_KEY, EXOCORE_ADMIN_KEY


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
        agent_name: str = "",
        history: list | None = None,
    ) -> str:
        """
        Send game state + conversation history to ExoCore; return Alessandro's reply.

        Args:
            prompt:        Current game state / user message (latest turn).
            system_prompt: Appended (not replacing) to the preset's base system prompt.
            model:         Model override — empty string defers to preset default.
            level:         Thinking depth: "low" | "medium" | "high".
            temperature:   Generation temperature override; None = use ExoCore default.
            agent_name:    Agent name string; falls back to EXOCORE_AGENT_NAME from config.
            history:       Prior turns as [{"role": "user"|"assistant", "content": "..."}].
                           Current prompt is appended as the final user turn.
        """
        resolved_agent = agent_name or EXOCORE_AGENT_NAME

        messages = list(history) if history else []
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "client_type":    "dst_bridge",
            "client_display": "DST Bridge",
            "agent":          resolved_agent,
            "messages":       messages,
            "source":         "game_state",
            "target_storage": "external_session",
            "mode":           "lite_private",
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

        # Auth: body extension_secret preferred; fallback to X-Admin-Key header
        headers = {}
        if EXOCORE_EXTENSION_KEY:
            payload["extension_secret"] = EXOCORE_EXTENSION_KEY
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
