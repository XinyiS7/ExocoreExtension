"""UHH Mail Watcher Extension for ExoCore.

Periodically monitors UHH inbox in background, applies rules from mail_rules.md,
and publishes structured mail_brief.md into CacheContext.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import time

from pystray import MenuItem

from core.base_extension import BaseExtension
from . import config
from .mail_client import fetch_and_generate_brief


class UhhMailExtension(BaseExtension):
    """Extension to monitor UHH email and inject mail_brief.md into CacheContext."""

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def name(self) -> str:
        return "UHH Mail Watcher"

    def start(self):
        """Start background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="UhhMailWatcher", daemon=True)
        self._thread.start()
        print("[UHH Mail] Background watcher service started.")

    def stop(self):
        """Stop background polling thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        print("[UHH Mail] Watcher stopped.")

    def _run_loop(self):
        # Stagger initial run slightly so startup remains fast
        if self._stop_event.wait(5):
            return

        while not self._stop_event.is_set():
            try:
                fetch_and_generate_brief()
            except Exception as e:
                print(f"[UHH Mail] Background sync error: {e}")

            # Sleep in increments of 1s to respond promptly to stop_event
            for _ in range(config.POLL_INTERVAL_SECONDS):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def on_refresh_now(self, icon=None, item=None):
        """Trigger an immediate mail check in a separate worker thread."""
        def _worker():
            try:
                print("[UHH Mail] Manual refresh triggered...")
                brief_path = fetch_and_generate_brief()
                print(f"[UHH Mail] Manual refresh completed: {brief_path}")
            except Exception as e:
                print(f"[UHH Mail] Manual refresh failed: {e}")

        threading.Thread(target=_worker, daemon=True).start()

    def on_open_rules(self, icon=None, item=None):
        """Open mail_rules.md in the default editor."""
        if config.RULES_PATH.exists():
            os.startfile(str(config.RULES_PATH))

    def on_open_brief(self, icon=None, item=None):
        """Open generated mail_brief.md in the default viewer."""
        if config.MAIL_BRIEF_PATH.exists():
            os.startfile(str(config.MAIL_BRIEF_PATH))

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem("刷新 UHH 邮件", self.on_refresh_now),
            MenuItem("编辑邮件规则 (mail_rules.md)", self.on_open_rules),
            MenuItem("查看邮件简报 (mail_brief.md)", self.on_open_brief),
        ]
