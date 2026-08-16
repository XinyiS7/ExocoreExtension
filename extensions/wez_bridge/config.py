"""
WezTerm HITL Bridge configuration.
All paths and intervals are centralized here.
"""
import os

# ---------------------------------------------------------------------------
# WezTerm CLI binary
# ---------------------------------------------------------------------------
WEZTERM_CLI = "wezterm"

# ---------------------------------------------------------------------------
# Pane configuration
# ---------------------------------------------------------------------------
# Host pane is the TUI pane (Alessandro's interface). The Sentinel ignores it.
# Set to None to auto-detect from WEZTERM_PANE env var at startup.
HOST_PANE_ID: str | None = None

# ---------------------------------------------------------------------------
# Sentinel polling
# ---------------------------------------------------------------------------
SENTINEL_POLL_INTERVAL_SEC = 2.0           # How often the sentinel scans panes
SENTINEL_TRUNCATE_OUTPUT_CHARS = 2000      # Max chars kept from pane scrape
SENTINEL_ENTROPY_THRESHOLD = 10            # Min unique chars to consider "active"

# Error keywords that trigger sentinel alert (case-insensitive match)
SENTINEL_ERROR_KEYWORDS = [
    "Traceback",
    "Error",
    "Failed",
    "Conflict",
    "fatal",
    "cannot",
    "denied",
    "not found",
    "No such file",
    "ModuleNotFoundError",
    "ImportError",
    "SyntaxError",
]

# ---------------------------------------------------------------------------
# Cache directory (pane crash dumps)
# ---------------------------------------------------------------------------
EXOCORE_DATA_ROOT = r"D:\Alicia\ExoCore_Project\ExoCoreData\ExtensionData"
CACHE_DIR = os.path.join(EXOCORE_DATA_ROOT, "cache")

# ---------------------------------------------------------------------------
# Local HTTP server (receives commands from ExoCore)
# ---------------------------------------------------------------------------
LOCAL_SERVER_HOST = "127.0.0.1"
LOCAL_SERVER_PORT = 8777

# ---------------------------------------------------------------------------
# ExoCore agent binding
# ---------------------------------------------------------------------------
# Per-extension default agent. Can be overridden via agent_registry.json
# "extension_assignments" or via Extension Manager.
DEFAULT_AGENT = "Alessandro"
AGENT_NAME = DEFAULT_AGENT  # backward compat — prefer DEFAULT_AGENT
AGENT_ID = "G045"

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
# Backend auto-summary threshold: >30 messages → compress old → summary
# + keep last 15. compacted_up_to returned in response.
