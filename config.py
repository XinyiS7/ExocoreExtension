"""
ExoCoreExtension — core configuration.

Extension-specific settings have moved to per-extension config modules
(Phase 2 split). The two path values below are retained as duplication
for backward compatibility with the Settings UI regex-based save; they
will be removed in Phase 4 when each extension manages its own paths.

Agent configuration is managed by core.agent_registry (Phase 1).
"""

# ---------------------------------------------------------------------------
# ExoCore backend (shared by all extensions)
# ---------------------------------------------------------------------------

EXOCORE_BASE_URL = "http://127.0.0.1:8000"
EXOCORE_API_KEY = ""
EXOCORE_ADMIN_KEY = "alessandro_root_045"
EXOCORE_EXTENSION_KEY = "exocore_pollux"

# ---------------------------------------------------------------------------
# UI theme (shared by all extensions)
# ---------------------------------------------------------------------------

COLORS = {
    "bg": "#080A0F",
    "panel": "#1A1E29",
    "surface": "#232836",
    "border": "#838387",
    "accent": "#edd554",
    "text": "#E0E7FF",
    "muted": "#b1b5c8",
}
FONTS = {
    "sans": ("Outfit", 12),
    "mono": ("JetBrains Mono", 11),
    "title": ("Outfit", 14, "bold"),
}

# ---------------------------------------------------------------------------
# Agent registry delegation (Phase 1 — thread-safe, JSON-backed)
# ---------------------------------------------------------------------------

from core.agent_registry import agent_registry  # noqa: E402


def _default_agent_name() -> str:
    return agent_registry.get_default_name()


EXOCORE_AGENT_NAME = _default_agent_name()


def _get_configs() -> list[dict]:
    return agent_registry.get_all()


AGENT_CONFIGS = _get_configs()


def get_agent_config(name: str) -> dict:
    return agent_registry.get_agent_config(name)


def get_agent_mode(name: str) -> str:
    return agent_registry.get_agent_mode(name)


def get_agent_model(name: str) -> str:
    return agent_registry.get_agent_model(name)


# ---------------------------------------------------------------------------
# Path values — duplicated from per-extension configs for backward compat
# with the Settings UI regex-based save.  Remove in Phase 4.
# ---------------------------------------------------------------------------

VAULT_PATH = r"D:/Alicia/Tales-on-leaves/壁炉书房/读书笔记"
DST_CLUSTER_PATH = r"D:\Documents\Klei\DoNotStarveTogether\325334978\Cluster_4"
