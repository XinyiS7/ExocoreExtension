"""
ExocoreExtension configuration.
"""

# ExoCore backend
EXOCORE_BASE_URL = "http://127.0.0.1:8000"
EXOCORE_API_KEY = ""
EXOCORE_PRESET_ID = 1
EXOCORE_AGENT_NAME = "Alessandro"  # Default agent
AVAILABLE_AGENTS = ['Alessandro']

# Obsidian vault
VAULT_PATH = r"D:\Alicia\Tales-on-leaves\壁炉书房"

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
