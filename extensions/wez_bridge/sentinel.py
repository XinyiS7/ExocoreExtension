import threading
import time
from typing import Callable
from .config import (
    SENTINEL_POLL_INTERVAL_SEC,
    SENTINEL_TRUNCATE_OUTPUT_CHARS,
    SENTINEL_ENTROPY_THRESHOLD,
    SENTINEL_ERROR_KEYWORDS,
    HOST_PANE_ID,
)
from .wezterm_cli import WezTermCLI
from .cache_manager import CacheManager


class Sentinel:
    """Background monitor that scans non-host WezTerm panes for errors.

    Polls all panes except the host/TUI pane on a fixed interval. When an
    error signature is detected (error keywords, non-zero exit, low entropy
    flip), the pane content is dumped to a cache file and the alert callback
    is invoked.
    """

    def __init__(
        self,
        cli: WezTermCLI | None = None,
        cache: CacheManager | None = None,
        host_pane_id: str | None = HOST_PANE_ID,
        on_alert: Callable | None = None,
        poll_interval: float = SENTINEL_POLL_INTERVAL_SEC,
    ):
        self._cli = cli or WezTermCLI()
        self._cache = cache or CacheManager()
        self._host_pane_id = host_pane_id
        self._on_alert = on_alert
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_text: dict[str, str] = {}  # pane_id -> last seen text
        self._seen_panes: set[str] = set()  # pane_ids seen at least once

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="Sentinel")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=self._poll_interval + 1.0)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self):
        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                print(f"[Sentinel] poll error: {e}")
            time.sleep(self._poll_interval)

    def _poll_once(self):
        panes = self._cli.list_panes()
        host_id = self._host_pane_id
        if host_id is None:
            host_id = self._cli.get_host_pane_id()
            self._host_pane_id = host_id

        for pane in panes:
            pid = str(pane.get("pane_id"))
            if pid == host_id:
                continue  # Never scrape the TUI host pane

            text = self._cli.get_text(pid, tail_lines=50)
            if not text:
                continue

            if self._should_alert(text, pid):
                truncated = self.truncate(text, SENTINEL_TRUNCATE_OUTPUT_CHARS)
                cache_path = self._cache.dump(pid, truncated)
                snippet = "\n".join(text.strip().split("\n")[-5:])
                print(f"[Sentinel] Alert on pane {pid}: {snippet[:120]}...")
                if self._on_alert:
                    self._on_alert(pid, cache_path, snippet)

            self._seen_panes.add(pid)
            self._last_text[pid] = text

    # ------------------------------------------------------------------
    # Detection logic (static methods for testability)
    # ------------------------------------------------------------------

    def _should_alert(self, text: str, pane_id: str) -> bool:
        """Return True if pane content triggers an alert.

        Only error keyword matches trigger alerts. Entropy-based detection
        proved too noisy — normal output (task lists, git status, progress
        bars) triggered false positives constantly.
        """
        last = self._last_text.get(pane_id, "")
        if text == last:
            return False  # No change, skip

        return self.has_error_keywords(text)

    @staticmethod
    def has_error_keywords(text: str) -> bool:
        """Check if text contains any known error signatures (case-insensitive)."""
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in SENTINEL_ERROR_KEYWORDS)

    @staticmethod
    def is_low_entropy(text: str, threshold: int = SENTINEL_ENTROPY_THRESHOLD) -> bool:
        """Return True if text has few unique characters (e.g. just a prompt)."""
        if not text:
            return True
        return len(set(text)) < threshold

    @staticmethod
    def truncate(text: str, max_chars: int) -> str:
        """Keep only the last max_chars of text."""
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]
