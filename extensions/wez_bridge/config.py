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
EXOCORE_DATA_ROOT = r"D:\Alicia\ExoCoreData"
CACHE_DIR = os.path.join(EXOCORE_DATA_ROOT, "cache")

# ---------------------------------------------------------------------------
# Local HTTP server (receives commands from ExoCore)
# ---------------------------------------------------------------------------
LOCAL_SERVER_HOST = "127.0.0.1"
LOCAL_SERVER_PORT = 8777

# ---------------------------------------------------------------------------
# ExoCore agent binding
# ---------------------------------------------------------------------------
AGENT_NAME = "Alessandro"
AGENT_ID = "G045"
