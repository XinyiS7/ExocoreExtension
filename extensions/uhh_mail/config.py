"""Configuration for UHH Mail Watcher Extension."""

from __future__ import annotations

import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parents[1]  # D:\Alicia\ExoCore_Project

DATA_DIR = Path(
    os.environ.get("EXOCORE_DATA_DIR", r"D:\Alicia\ExoCore_Project\ExoCoreData")
)
CACHE_CONTEXT_DIR = DATA_DIR / "CacheContext"
MAIL_BRIEF_PATH = CACHE_CONTEXT_DIR / "mail_brief.md"

RULES_PATH = BASE_DIR / "mail_rules.md"
ENV_PATH = BASE_DIR / ".env"

# Polling Interval: 15 minutes
POLL_INTERVAL_SECONDS = 900

# Text cleaning limits
MAX_BODY_CHARS = 1200
MAX_EMAILS_TO_SCAN = 50
