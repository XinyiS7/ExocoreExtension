import os
import time
from datetime import datetime


class CacheManager:
    """Manages local transient cache files for pane output dumps.

    Cache files store raw pane output so that only a file-path reference
    is passed to ExoCore instead of the full noisy log content.
    """

    def __init__(self, cache_root: str | None = None):
        from .config import CACHE_DIR
        self._root = cache_root or CACHE_DIR

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dump(self, pane_id: int | str, content: str, suffix: str = "") -> str:
        """Write pane content to a cache file. Returns the absolute file path."""
        self._ensure_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix_part = f"_{suffix}" if suffix else ""
        filename = f"pane_{pane_id}_{timestamp}{suffix_part}.log"
        filepath = os.path.join(self._root, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return filepath

    def load(self, filepath: str) -> str:
        """Read a cache file back into memory."""
        # Path-safety check: ensure filepath is within the cache root
        abs_filepath = os.path.abspath(filepath)
        abs_root = os.path.abspath(self._root)
        if os.path.commonpath([abs_filepath, abs_root]) != abs_root:
            raise ValueError(
                f"File path {filepath} is outside cache root {self._root}"
            )
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Cache file not found: {filepath}")
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def cleanup(self, max_age_seconds: float = 3600.0) -> int:
        """Remove cache files older than max_age_seconds. Returns count removed."""
        if not os.path.isdir(self._root):
            return 0
        now = time.time()
        removed = 0
        for fname in os.listdir(self._root):
            if not (fname.startswith("pane_") and fname.endswith(".log")):
                continue
            fpath = os.path.join(self._root, fname)
            if not os.path.isfile(fpath):
                continue
            if now - os.path.getmtime(fpath) > max_age_seconds:
                try:
                    os.remove(fpath)
                    removed += 1
                except OSError:
                    pass
        return removed

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_dir(self):
        os.makedirs(self._root, exist_ok=True)
