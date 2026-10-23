"""UHH Mail Watcher Extension for ExoCore.

Periodically monitors the UHH inbox in the background, applies the rules from
mail_rules.md, and publishes a structured mail_brief.md into CacheContext.

Liveness: the tray menu's first line always shows the last sync result, the
tooltip mirrors it, and the ring turns red after a failure. All activity is
appended to ``mail_watcher.log`` next to this file, because a tray started with
pythonw has no visible stdout.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import threading
import time

from PIL import Image, ImageDraw
from pystray import Menu, MenuItem

from core.base_extension import BaseExtension
from . import config
from .mail_client import fetch_and_generate_brief

LOG_PATH = Path(__file__).resolve().parent / "mail_watcher.log"
MAX_LOG_BYTES = 256 * 1024

_ICON_PANEL = (30, 30, 30, 255)
_ICON_OK = (212, 175, 55, 255)
_ICON_FAIL = (205, 65, 65, 255)

_COUNT_RE = re.compile(r"^(total_unread|high_priority_count):\s*(\d+)", re.MULTILINE)


def _log(line: str) -> None:
    """Append one line to mail_watcher.log, rotating once past the size cap."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_LOG_BYTES:
            backup = LOG_PATH.with_name(LOG_PATH.name + ".1")
            if backup.exists():
                backup.unlink()
            LOG_PATH.rename(backup)
    except Exception:
        pass
    try:
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {line}\n")
    except Exception:
        pass


def _read_counts(brief_path: Path) -> tuple[int, int]:
    """Read total_unread / high_priority_count from the generated front matter."""
    try:
        text = Path(brief_path).read_text(encoding="utf-8")
    except Exception:
        return (0, 0)
    found = {key: int(value) for key, value in _COUNT_RE.findall(text)}
    return (found.get("total_unread", 0), found.get("high_priority_count", 0))


def _status_image(ok: bool) -> Image.Image:
    img = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, 56, 56], fill=_ICON_PANEL)
    draw.ellipse([16, 16, 48, 48], outline=_ICON_OK if ok else _ICON_FAIL, width=3)
    return img


class UhhMailExtension(BaseExtension):
    """Extension to monitor UHH email and inject mail_brief.md into CacheContext."""

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._tray_icon = None

        self._last_success: datetime | None = None
        self._last_error: str | None = None
        self._last_error_at: datetime | None = None
        self._failures = 0
        self._unread = 0
        self._priority = 0

    @property
    def name(self) -> str:
        return "UHH Mail Watcher"

    # --- lifecycle --------------------------------------------------------
    def start(self):
        """Start background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="UhhMailWatcher", daemon=True)
        self._thread.start()
        _log("[start] watcher thread started")
        print("[UHH Mail] Background watcher service started.")

    def stop(self):
        """Stop background polling thread."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        _log("[stop] watcher stopped")
        print("[UHH Mail] Watcher stopped.")

    def attach_tray(self, icon):
        """Optional hook: the tray launcher hands us its icon so we can show status."""
        self._tray_icon = icon
        self._refresh_tray()

    # --- status -----------------------------------------------------------
    def _status_line(self) -> str:
        # Plain ASCII tags: pystray menus on Windows do not render colour emoji.
        with self._lock:
            if self._failures:
                when = self._last_error_at.strftime("%H:%M") if self._last_error_at else "—"
                reason = (self._last_error or "")[:38]
                return f"[FAIL] ×{self._failures} · {when} — {reason}"
            if self._last_success is None:
                return "[--] 尚未同步"
            return (
                f"[OK] 上次同步 {self._last_success.strftime('%H:%M')} · "
                f"未读 {self._unread} / 重点 {self._priority}"
            )

    def _status_menu_text(self, item=None) -> str:
        return self._status_line()

    def _tooltip(self) -> str:
        return f"UHH Mail · {self._status_line()}"

    def _refresh_tray(self) -> None:
        icon = self._tray_icon
        if icon is None:
            return
        with self._lock:
            healthy = self._failures == 0
        try:
            icon.title = self._tooltip()
        except Exception:
            pass
        try:
            icon.icon = _status_image(healthy)
        except Exception:
            pass

    # --- sync -------------------------------------------------------------
    def _sync_once(self, trigger: str) -> None:
        try:
            brief_path = fetch_and_generate_brief()
            unread, priority = _read_counts(brief_path)
            with self._lock:
                self._last_success = datetime.now()
                self._failures = 0
                self._last_error = None
                self._last_error_at = None
                self._unread = unread
                self._priority = priority
            _log(f"[{trigger}] ok unread={unread} priority={priority} -> {brief_path}")
        except Exception as exc:
            with self._lock:
                self._failures += 1
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._last_error_at = datetime.now()
                failures = self._failures
            _log(f"[{trigger}] FAIL #{failures} {type(exc).__name__}: {exc}")
        finally:
            self._refresh_tray()

    def _run_loop(self):
        # Stagger initial run slightly so startup remains fast
        if self._stop_event.wait(5):
            return

        while not self._stop_event.is_set():
            self._sync_once("poll")

            # Sleep in increments of 1s to respond promptly to stop_event
            for _ in range(config.POLL_INTERVAL_SECONDS):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def on_refresh_now(self, icon=None, item=None):
        """Trigger an immediate mail check in a separate worker thread."""

        def _worker():
            _log("[manual] refresh triggered")
            self._sync_once("manual")

        threading.Thread(target=_worker, daemon=True).start()

    # --- menu actions -----------------------------------------------------
    def on_open_rules(self, icon=None, item=None):
        """Open mail_rules.md in the default editor."""
        if config.RULES_PATH.exists():
            os.startfile(str(config.RULES_PATH))

    def on_open_brief(self, icon=None, item=None):
        """Open generated mail_brief.md in the default viewer."""
        if config.MAIL_BRIEF_PATH.exists():
            os.startfile(str(config.MAIL_BRIEF_PATH))

    def on_open_log(self, icon=None, item=None):
        """Open mail_watcher.log in the default viewer."""
        if LOG_PATH.exists():
            os.startfile(str(LOG_PATH))

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem(self._status_menu_text, None),
            Menu.SEPARATOR,
            MenuItem("刷新 UHH 邮件", self.on_refresh_now),
            MenuItem("编辑邮件规则 (mail_rules.md)", self.on_open_rules),
            MenuItem("查看邮件简报 (mail_brief.md)", self.on_open_brief),
            MenuItem("查看同步日志 (mail_watcher.log)", self.on_open_log),
        ]
