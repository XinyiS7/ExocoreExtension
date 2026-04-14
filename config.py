"""
ExocoreExtension configuration.
"""

# DST Bridge — active cluster directory (change when switching saves)
# e.g. r"D:\Documents\Klei\DoNotStarveTogether\<SteamID>\Cluster_4"
DST_CLUSTER_PATH = r"D:\Documents\Klei\DoNotStarveTogether\325334978\Cluster_4"

# Queue file sits in the active shard's Master/ folder
# Resolved at runtime by DSTBridgeExtension._resolve_cmd_queue_file()
DST_CMD_QUEUE_FILENAME = "exo_cmd_queue.txt"

# ExoCore backend
EXOCORE_BASE_URL = "http://127.0.0.1:8000"
EXOCORE_API_KEY = ""
EXOCORE_ADMIN_KEY = "alessandro_root_045"        # Matches settings.ADMIN_TRIGGER_KEY  (admin override)
EXOCORE_EXTENSION_KEY = "exocore_pollux"    # Matches EXTENSION_SECRET in
# ExoCore .env (per-extension token)
EXOCORE_AGENT_NAME = "Alessandro"  # Default agent
AGENT_CONFIGS = [{'name': 'Alessandro', 'mode': 'lite_private', 'model': 'gemini-2.5-flash'}]


def get_agent_config(name: str) -> dict:
    """Return the full config dict for the given agent name."""
    for cfg in AGENT_CONFIGS:
        if cfg["name"] == name:
            return cfg
    return {}


def get_agent_mode(name: str) -> str:
    return get_agent_config(name).get("mode", "zero_tool")


def get_agent_model(name: str) -> str:
    return get_agent_config(name).get("model", "")

# Obsidian vault
VAULT_PATH = r"D:/Alicia/Tales-on-leaves/壁炉书房/读书笔记"

# Hotkeys
HOTKEY_CLIPBOARD_CAPTURE = "ctrl+alt+a"
HOTKEY_UI_CAPTURE = "ctrl+alt+s"

# Capture settings
CLIPBOARD_FALLBACK = True
MAX_CAPTURE_CHARS = 8000

# UI Visual Theme
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
