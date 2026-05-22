"""
Thread-safe agent configuration registry backed by JSON.

Single source of truth for agent names, modes, and models.
Replaces the fragile regex-based config.py mutation in _persist_agent()
and the scattered AGENT_CONFIGS reads across both extensions.

Migration: on first load, reads from config.py's AGENT_CONFIGS.
Thereafter reads/writes agent_registry.json alongside config.py.
"""
import json
import os
import threading


_STORAGE_FILENAME = "agent_registry.json"


class AgentRegistry:
    def __init__(self, storage_dir: str):
        self._lock = threading.Lock()
        self._path = os.path.join(storage_dir, _STORAGE_FILENAME)
        self._configs: list[dict] = []
        self._load()

    # ------------------------------------------------------------------
    # Public read API (all acquire the lock, return copies)
    # ------------------------------------------------------------------

    def get_all(self) -> list[dict]:
        with self._lock:
            return [dict(cfg) for cfg in self._configs]

    def get_default_name(self) -> str:
        with self._lock:
            if self._configs:
                return self._configs[0]["name"]
            return "Alessandro"

    def get_agent_config(self, name: str) -> dict:
        with self._lock:
            for cfg in self._configs:
                if cfg["name"] == name:
                    return dict(cfg)
            return {}

    def get_agent_mode(self, name: str) -> str:
        return self.get_agent_config(name).get("mode", "zero_tool")

    def get_agent_model(self, name: str) -> str:
        return self.get_agent_config(name).get("model", "")

    def list_names(self) -> list[str]:
        with self._lock:
            return [cfg["name"] for cfg in self._configs]

    # ------------------------------------------------------------------
    # Public write API
    # ------------------------------------------------------------------

    def add_agent(self, name: str, mode: str = "zero_tool", model: str = "") -> None:
        with self._lock:
            names = {cfg["name"] for cfg in self._configs}
            if name in names:
                return
            entry: dict = {"name": name, "mode": mode}
            if model:
                entry["model"] = model
            self._configs.append(entry)
            self._persist()

    def set_default_agent(self, name: str) -> None:
        with self._lock:
            for i, cfg in enumerate(self._configs):
                if cfg["name"] == name:
                    self._configs.insert(0, self._configs.pop(i))
                    self._persist()
                    return

    def update_agent(self, name: str, mode: str | None = None, model: str | None = None) -> bool:
        with self._lock:
            for cfg in self._configs:
                if cfg["name"] == name:
                    if mode is not None:
                        cfg["mode"] = mode
                    if model is not None:
                        cfg["model"] = model
                    self._persist()
                    return True
            return False

    def remove_agent(self, name: str) -> bool:
        with self._lock:
            for i, cfg in enumerate(self._configs):
                if cfg["name"] == name:
                    self._configs.pop(i)
                    self._persist()
                    return True
            return False

    def replace_all(self, configs: list[dict]) -> None:
        with self._lock:
            self._configs = [dict(cfg) for cfg in configs]
            self._persist()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self) -> None:
        """Write to a temp file and atomically rename to avoid corruption."""
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._configs, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception as e:
            print(f"[AgentRegistry] Failed to persist: {e}")

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._configs = json.load(f)
                return
            except (json.JSONDecodeError, OSError) as e:
                print(f"[AgentRegistry] Corrupt JSON, falling back to config.py: {e}")

        self._migrate_from_config()

    def _migrate_from_config(self) -> None:
        """First-run: seed with the default agent (avoids circular import from config)."""
        self._configs = [{"name": "Alessandro", "mode": "lite_private", "model": "gemini-2.5-flash"}]
        self._persist()
        print(f"[AgentRegistry] No JSON found — seeded with default agent")


# ------------------------------------------------------------------
# Singleton — created once at import time, shared by all extensions
# ------------------------------------------------------------------

_storage_dir = os.path.dirname(os.path.abspath(__file__))
_storage_dir = os.path.dirname(_storage_dir)  # up from core/ to project root
agent_registry = AgentRegistry(_storage_dir)
