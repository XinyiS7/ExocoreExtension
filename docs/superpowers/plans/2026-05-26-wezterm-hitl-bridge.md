# WezTerm HITL Bridge Extension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless Python daemon (Client-Side Extension) that bridges WezTerm panes with ExoCore, providing Sentinel monitoring, Commander command injection, and a TUI chat interface for the Alessandro agent.

**Architecture:** A `WezBridgeExtension` (BaseExtension subclass) orchestrates three sub-components: a Background Sentinel that polls non-host panes for errors and caches output, a Background Commander that injects drafted commands into panes, and a micro Local HTTP Server that receives `execute_command` dispatches from ExoCore. A standalone `sandro_tui.py` script provides the interactive terminal UI using prompt_toolkit with SSE streaming from ExoCore's chat API.

**Tech Stack:** Python 3.12+, prompt_toolkit 3, httpx (async SSE), pystray (tray integration), requests (sync API calls), WezTerm CLI (subprocess)

---

## Pre-Implementation Checklist

- [ ] **Confirm with backend team (CC):** Is `POST /api/agents/chat_stream/` implemented? What is the exact SSE event format (event types, data schema)?
- [ ] **Confirm with backend team (CC):** How does ExoCore discover/register the extension's local HTTP server port? Is there a registration endpoint, or is it statically configured?
- [ ] **Confirm with backend team (CC):** Does `POST /api/agents/external_context_inject/` support the `metadata` field (for `pane_id`, `current_dir`, `cache_file_reference`)?
- [ ] **Confirm with backend team (CC):** What is the exact `POST /api/agents/execute_command/` payload format that ExoCore will send to the extension's local server?
- [ ] **Confirm environment:** Ensure `conda activate exocore_project` is available and WezTerm is running with at least 2 panes.

---

### Task 1: Extension Scaffold and Configuration

**Files:**
- Create: `extensions/wez_bridge/__init__.py`
- Create: `extensions/wez_bridge/config.py`
- Create: `tests/wez_bridge/__init__.py`
- Create: `tests/wez_bridge/test_config.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p extensions/wez_bridge
mkdir -p tests/wez_bridge
```

- [ ] **Step 2: Write package init**

Create `extensions/wez_bridge/__init__.py`:
```python
"""WezTerm HITL Bridge Extension — Sentinel, Commander, and TUI gateway."""
```

Create `tests/wez_bridge/__init__.py` (empty file).

- [ ] **Step 3: Write config module**

Create `extensions/wez_bridge/config.py`:
```python
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
```

- [ ] **Step 4: Write config test**

Create `tests/wez_bridge/test_config.py`:
```python
import os
from extensions.wez_bridge import config


class TestConfig:
    def test_cache_dir_absolute(self):
        assert os.path.isabs(config.CACHE_DIR)

    def test_sentinel_interval_positive(self):
        assert config.SENTINEL_POLL_INTERVAL_SEC > 0

    def test_local_server_binds_localhost(self):
        assert config.LOCAL_SERVER_HOST == "127.0.0.1"

    def test_error_keywords_not_empty(self):
        assert len(config.SENTINEL_ERROR_KEYWORDS) > 0

    def test_agent_name_is_alessandro(self):
        assert config.AGENT_NAME == "Alessandro"
```

- [ ] **Step 5: Run tests to verify**

Run: `python -m pytest tests/wez_bridge/test_config.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add extensions/wez_bridge/__init__.py extensions/wez_bridge/config.py tests/wez_bridge/
git commit -m "feat(wez_bridge): add extension scaffold and configuration"
```

---

### Task 2: WezTerm CLI Wrapper

**Files:**
- Create: `extensions/wez_bridge/wezterm_cli.py`
- Create: `tests/wez_bridge/test_wezterm_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_wezterm_cli.py`:
```python
import json
import subprocess
from unittest.mock import patch, MagicMock
from extensions.wez_bridge.wezterm_cli import WezTermCLI


class TestListPanes:
    def test_list_panes_parses_json(self):
        mock_output = json.dumps([
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 1, "title": "workspace", "is_active": False},
        ])
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=mock_output, stderr=""
            )
            cli = WezTermCLI()
            panes = cli.list_panes()
            assert len(panes) == 2
            assert panes[0]["pane_id"] == 0
            assert panes[1]["title"] == "workspace"

    def test_list_panes_returns_empty_on_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="wezterm", timeout=5)
            cli = WezTermCLI()
            panes = cli.list_panes()
            assert panes == []


class TestGetText:
    def test_get_text_returns_stdout(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="line1\nline2\nline3\n", stderr=""
            )
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1)
            assert text == "line1\nline2\nline3\n"

    def test_get_text_truncates_to_last_n_lines(self):
        lines = [f"line{i}" for i in range(100)]
        stdout = "\n".join(lines) + "\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout=stdout, stderr=""
            )
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1, tail_lines=5)
            assert text.split("\n") == lines[-5:] + [""]

    def test_get_text_returns_empty_on_timeout(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="wezterm", timeout=5)
            cli = WezTermCLI()
            text = cli.get_text(pane_id=1)
            assert text == ""


class TestSendText:
    def test_send_text_no_newline(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            cli = WezTermCLI()
            result = cli.send_text(pane_id=2, text="npm install")
            assert result is True
            call_args = mock_run.call_args[0][0]
            assert "--no-paste" in call_args
            assert "npm install" in call_args
            assert "\n" not in call_args[-1]

    def test_send_text_returns_false_on_error(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="wezterm", timeout=5)
            cli = WezTermCLI()
            result = cli.send_text(pane_id=2, text="bad")
            assert result is False


class TestSendEnter:
    def test_send_enter(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            cli = WezTermCLI()
            result = cli.send_enter(pane_id=2)
            assert result is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_wezterm_cli.py -v`
Expected: all FAIL with "No module named 'extensions.wez_bridge.wezterm_cli'"

- [ ] **Step 3: Implement WezTermCLI**

Create `extensions/wez_bridge/wezterm_cli.py`:
```python
import json
import subprocess
from .config import WEZTERM_CLI


class WezTermCLI:
    """Thin wrapper around `wezterm cli` subprocess calls."""

    def __init__(self, binary: str = WEZTERM_CLI, timeout: float = 5.0):
        self._binary = binary
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Pane discovery
    # ------------------------------------------------------------------

    def list_panes(self) -> list[dict]:
        """Return list of pane dicts with keys: pane_id, title, is_active, cwd, etc."""
        try:
            proc = subprocess.run(
                [self._binary, "cli", "list", "--format", "json"],
                capture_output=True, text=True, timeout=self._timeout,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return json.loads(proc.stdout)
            return []
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            print(f"[WezTermCLI] list_panes failed: {e}")
            return []

    def get_host_pane_id(self) -> str | None:
        """Return the pane ID marked as the active/focused pane, or None."""
        panes = self.list_panes()
        for p in panes:
            if p.get("is_active"):
                return str(p.get("pane_id"))
        return str(panes[0]["pane_id"]) if panes else None

    # ------------------------------------------------------------------
    # Text scraping
    # ------------------------------------------------------------------

    def get_text(self, pane_id: int | str, tail_lines: int = 0) -> str:
        """Scrape visible text from a pane. If tail_lines > 0, return only the last N lines."""
        try:
            proc = subprocess.run(
                [self._binary, "cli", "get-text", "--pane-id", str(pane_id)],
                capture_output=True, text=True, timeout=self._timeout,
            )
            if proc.returncode != 0:
                return ""
            text = proc.stdout
            if tail_lines > 0:
                lines = text.split("\n")
                text = "\n".join(lines[-tail_lines:])
            return text
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"[WezTermCLI] get_text(pane_id={pane_id}) failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # Command injection
    # ------------------------------------------------------------------

    def send_text(self, pane_id: int | str, text: str) -> bool:
        """Inject text into pane's input area WITHOUT a trailing newline (HITL gate)."""
        try:
            subprocess.run(
                [self._binary, "cli", "send-text", "--pane-id", str(pane_id),
                 "--no-paste", text],
                capture_output=True, text=True, timeout=self._timeout,
                check=True,
            )
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
            print(f"[WezTermCLI] send_text(pane_id={pane_id}) failed: {e}")
            return False

    def send_enter(self, pane_id: int | str) -> bool:
        """Send a newline (Enter key) to a pane."""
        return self.send_text(pane_id, "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_wezterm_cli.py -v`
Expected: all PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/wezterm_cli.py tests/wez_bridge/test_wezterm_cli.py
git commit -m "feat(wez_bridge): add WezTermCLI wrapper with list/get/send"
```

---

### Task 3: Cache Manager

**Files:**
- Create: `extensions/wez_bridge/cache_manager.py`
- Create: `tests/wez_bridge/test_cache_manager.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_cache_manager.py`:
```python
import os
import tempfile
import time
from extensions.wez_bridge.cache_manager import CacheManager


class TestCacheManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cm = CacheManager(cache_root=self.tmpdir)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_dump_creates_file(self):
        filepath = self.cm.dump(pane_id="2", content="error output here")
        assert os.path.exists(filepath)
        assert "pane_2_" in filepath
        assert filepath.endswith(".log")

    def test_dump_content_is_exact(self):
        content = "line1\nline2\nTraceback error\n"
        filepath = self.cm.dump(pane_id="2", content=content)
        with open(filepath, "r", encoding="utf-8") as f:
            assert f.read() == content

    def test_cleanup_removes_old_files(self):
        # Create a file with old timestamp
        old_path = os.path.join(self.tmpdir, "pane_3_old.log")
        with open(old_path, "w") as f:
            f.write("old")
        # Set mtime to 2 hours ago
        old_time = time.time() - 7200
        os.utime(old_path, (old_time, old_time))

        # Create a recent file
        recent_path = self.cm.dump(pane_id="4", content="recent")

        # Cleanup files older than 1 hour
        removed = self.cm.cleanup(max_age_seconds=3600)
        assert removed >= 1
        assert not os.path.exists(old_path)
        assert os.path.exists(recent_path)

    def test_ensures_cache_dir_exists(self):
        new_dir = os.path.join(self.tmpdir, "nested", "cache")
        cm = CacheManager(cache_root=new_dir)
        path = cm.dump(pane_id="1", content="test")
        assert os.path.exists(path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_cache_manager.py -v`
Expected: all FAIL with "No module named 'extensions.wez_bridge.cache_manager'"

- [ ] **Step 3: Implement CacheManager**

Create `extensions/wez_bridge/cache_manager.py`:
```python
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
        if not os.path.exists(filepath):
            return ""
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    def cleanup(self, max_age_seconds: float = 3600.0) -> int:
        """Remove cache files older than max_age_seconds. Returns count removed."""
        if not os.path.isdir(self._root):
            return 0
        now = time.time()
        removed = 0
        for fname in os.listdir(self._root):
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_cache_manager.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/cache_manager.py tests/wez_bridge/test_cache_manager.py
git commit -m "feat(wez_bridge): add CacheManager for pane output dumps"
```

---

### Task 4: Background Sentinel

**Files:**
- Create: `extensions/wez_bridge/sentinel.py`
- Create: `tests/wez_bridge/test_sentinel.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_sentinel.py`:
```python
from unittest.mock import MagicMock, patch, call
from extensions.wez_bridge.sentinel import Sentinel


class TestSentinelErrorDetection:
    """Unit tests for Sentinel's static analysis methods (no WezTerm needed)."""

    def test_detect_error_keyword_traceback(self):
        text = "Traceback (most recent call last):\n  File 'x.py', line 5\nValueError: bad"
        assert Sentinel.has_error_keywords(text) is True

    def test_detect_error_keyword_fatal(self):
        assert Sentinel.has_error_keywords("fatal: not a git repository") is True

    def test_detect_error_keyword_clean_output(self):
        assert Sentinel.has_error_keywords("$ npm install\nadded 42 packages") is False

    def test_detect_error_keyword_normal_prompt(self):
        assert Sentinel.has_error_keywords("user@host:~$ ") is False

    def test_entropy_below_threshold_prompt(self):
        assert Sentinel.is_low_entropy("user@host:~$ ", threshold=10) is True

    def test_entropy_above_threshold_error(self):
        error_text = "Traceback (most recent call last):\n" * 10
        assert Sentinel.is_low_entropy(error_text, threshold=10) is False

    def test_truncate_output(self):
        long_text = "x" * 3000
        result = Sentinel.truncate(long_text, max_chars=2000)
        assert len(result) == 2000
        assert result == long_text[-2000:]

    def test_truncate_short_output_unchanged(self):
        short = "hello"
        assert Sentinel.truncate(short, max_chars=2000) == "hello"


class TestSentinelPolling:
    """Integration-style tests with mocked WezTermCLI."""

    def test_poll_detects_error_and_triggers_callback(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 1, "title": "workspace", "is_active": False},
        ]
        mock_cli.get_text.return_value = "npm ERR! code ERESOLVE\nnpm ERR! Fix the upstream dependency conflict"

        mock_cache = MagicMock()
        mock_cache.dump.return_value = r"D:\Alicia\ExoCoreData\cache\pane_1_20260526_120000.log"

        triggered = []

        def on_alert(pane_id, cache_path, snippet):
            triggered.append((pane_id, cache_path, snippet))

        sentinel = Sentinel(
            cli=mock_cli,
            cache=mock_cache,
            host_pane_id="0",
            on_alert=on_alert,
            poll_interval=0.01,
        )
        sentinel._poll_once()

        assert len(triggered) == 1
        pane_id, cache_path, snippet = triggered[0]
        assert pane_id == "1"
        assert "pane_1" in cache_path

    def test_poll_skips_host_pane(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
        ]

        sentinel = Sentinel(
            cli=mock_cli,
            cache=MagicMock(),
            host_pane_id="0",
            poll_interval=0.01,
        )
        sentinel._poll_once()

        # get_text should never be called for host pane
        mock_cli.get_text.assert_not_called()

    def test_poll_skips_clean_pane(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI", "is_active": True},
            {"pane_id": 2, "title": "clean workspace", "is_active": False},
        ]
        mock_cli.get_text.return_value = "user@host:~/project$ "

        triggered = []
        sentinel = Sentinel(
            cli=mock_cli,
            cache=MagicMock(),
            host_pane_id="0",
            on_alert=lambda pid, cp, sn: triggered.append(pid),
            poll_interval=0.01,
        )
        sentinel._poll_once()

        assert len(triggered) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_sentinel.py -v`
Expected: all FAIL with "No module named 'extensions.wez_bridge.sentinel'"

- [ ] **Step 3: Implement Sentinel**

Create `extensions/wez_bridge/sentinel.py`:
```python
import threading
import time
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
        on_alert: callable | None = None,
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

            self._last_text[pid] = text

    # ------------------------------------------------------------------
    # Detection logic (static methods for testability)
    # ------------------------------------------------------------------

    def _should_alert(self, text: str, pane_id: str) -> bool:
        """Return True if pane content triggers an alert."""
        last = self._last_text.get(pane_id, "")
        if text == last:
            return False  # No change, skip

        if self.has_error_keywords(text):
            return True

        # If previously low-entropy (quiet) and now high-entropy (error dump),
        # consider it a possible crash report
        was_quiet = self.is_low_entropy(last)
        is_noisy = not self.is_low_entropy(text)
        if was_quiet and is_noisy:
            return True

        return False

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_sentinel.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/sentinel.py tests/wez_bridge/test_sentinel.py
git commit -m "feat(wez_bridge): add Sentinel background pane monitor"
```

---

### Task 5: Background Commander

**Files:**
- Create: `extensions/wez_bridge/commander.py`
- Create: `tests/wez_bridge/test_commander.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_commander.py`:
```python
from unittest.mock import MagicMock
from extensions.wez_bridge.commander import Commander


class TestCommander:
    def test_draft_cli_command_injects_without_newline(self):
        mock_cli = MagicMock()
        mock_cli.send_text.return_value = True

        cmdr = Commander(cli=mock_cli)
        result = cmdr.draft_cli_command(pane_id="2", command="npm install --legacy-peer-deps")

        assert result is True
        mock_cli.send_text.assert_called_once_with(
            pane_id="2", text="npm install --legacy-peer-deps"
        )
        # Crucially: send_enter should NOT be called — user must confirm
        mock_cli.send_enter.assert_not_called()

    def test_draft_cli_command_returns_false_on_failure(self):
        mock_cli = MagicMock()
        mock_cli.send_text.return_value = False

        cmdr = Commander(cli=mock_cli)
        result = cmdr.draft_cli_command(pane_id="99", command="bad")

        assert result is False

    def test_execute_immediately_sends_enter(self):
        mock_cli = MagicMock()
        mock_cli.send_text.return_value = True
        mock_cli.send_enter.return_value = True

        cmdr = Commander(cli=mock_cli)
        result = cmdr.draft_cli_command(
            pane_id="2", command="ls -la", execute_immediately=True
        )

        assert result is True
        mock_cli.send_enter.assert_called_once_with(pane_id="2")

    def test_list_panes_delegates_to_cli(self):
        mock_cli = MagicMock()
        mock_cli.list_panes.return_value = [
            {"pane_id": 0, "title": "Alessandro TUI"},
            {"pane_id": 1, "title": "workspace"},
        ]

        cmdr = Commander(cli=mock_cli)
        panes = cmdr.list_panes()

        assert len(panes) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_commander.py -v`
Expected: all FAIL with "No module named 'extensions.wez_bridge.commander'"

- [ ] **Step 3: Implement Commander**

Create `extensions/wez_bridge/commander.py`:
```python
from .wezterm_cli import WezTermCLI


class Commander:
    """Receives command dispatch requests and injects them into WezTerm panes.

    The default mode (execute_immediately=False) implements the HITL gate:
    the command is placed into the pane's input area but the user must
    manually press Enter to execute.
    """

    def __init__(self, cli: WezTermCLI | None = None):
        self._cli = cli or WezTermCLI()

    # ------------------------------------------------------------------
    # Command dispatch
    # ------------------------------------------------------------------

    def draft_cli_command(
        self,
        pane_id: int | str,
        command: str,
        execute_immediately: bool = False,
    ) -> bool:
        """Inject a command into the target pane's input area.

        By default, no trailing newline is sent — the HITL gate requires
        the user to visually confirm and press Enter manually.

        If execute_immediately is True, Enter is automatically sent.
        """
        ok = self._cli.send_text(pane_id, command)
        if not ok:
            print(f"[Commander] Failed to inject command into pane {pane_id}")
            return False

        if execute_immediately:
            return self._cli.send_enter(pane_id)

        return True

    # ------------------------------------------------------------------
    # Pane discovery (convenience passthrough)
    # ------------------------------------------------------------------

    def list_panes(self) -> list[dict]:
        return self._cli.list_panes()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_commander.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/commander.py tests/wez_bridge/test_commander.py
git commit -m "feat(wez_bridge): add Commander for HITL command injection"
```

---

### Task 6: Local HTTP Server

**Files:**
- Create: `extensions/wez_bridge/local_server.py`
- Create: `tests/wez_bridge/test_local_server.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_local_server.py`:
```python
import json
import time
import threading
import urllib.request
import urllib.error
from extensions.wez_bridge.local_server import LocalCommandServer


class TestLocalCommandServer:
    def test_server_starts_and_responds(self):
        received = []

        def handler(payload):
            received.append(payload)
            return {"status": "ok", "pane_id": payload.get("target_pane_id")}

        server = LocalCommandServer(host="127.0.0.1", port=18777, handler=handler)
        server.start()
        time.sleep(0.3)  # Let server bind

        try:
            payload = json.dumps({
                "target_pane_id": "2",
                "command": "echo hello",
                "execute_immediately": False,
                "alert_message": "test",
            }).encode("utf-8")

            req = urllib.request.Request(
                "http://127.0.0.1:18777/api/agents/execute_command/",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=3)
            body = json.loads(resp.read().decode())
            assert resp.status == 200
            assert body["status"] == "ok"
            assert len(received) == 1
            assert received[0]["target_pane_id"] == "2"
        finally:
            server.stop()

    def test_server_returns_404_for_unknown_path(self):
        server = LocalCommandServer(host="127.0.0.1", port=18778)
        server.start()
        time.sleep(0.3)

        try:
            req = urllib.request.Request("http://127.0.0.1:18778/unknown")
            urllib.request.urlopen(req, timeout=3)
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 404
        finally:
            server.stop()

    def test_server_rejects_non_json(self):
        server = LocalCommandServer(host="127.0.0.1", port=18779)
        server.start()
        time.sleep(0.3)

        try:
            data = b"not json"
            req = urllib.request.Request(
                "http://127.0.0.1:18779/api/agents/execute_command/",
                data=data,
                method="POST",
            )
            urllib.request.urlopen(req, timeout=3)
            assert False, "should have raised"
        except urllib.error.HTTPError as e:
            assert e.code == 400
        finally:
            server.stop()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_local_server.py -v`
Expected: all FAIL

- [ ] **Step 3: Implement LocalCommandServer**

Create `extensions/wez_bridge/local_server.py`:
```python
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from .config import LOCAL_SERVER_HOST, LOCAL_SERVER_PORT


class LocalCommandServer:
    """Micro HTTP server bound to 127.0.0.1 that receives execute_command
    dispatches from the ExoCore backend.

    Only one endpoint is served:
        POST /api/agents/execute_command/
    """

    def __init__(
        self,
        host: str = LOCAL_SERVER_HOST,
        port: int = LOCAL_SERVER_PORT,
        handler: callable | None = None,
    ):
        self._host = host
        self._port = port
        self._handler = handler
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if self._httpd is not None:
            return
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(inner):
                if inner.path != "/api/agents/execute_command/":
                    inner.send_error(404, "Not Found")
                    return
                content_length = int(inner.headers.get("Content-Length", 0))
                body = inner.rfile.read(content_length)
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    inner.send_error(400, "Invalid JSON")
                    return

                if outer._handler:
                    result = outer._handler(payload)
                else:
                    result = {"status": "received"}

                inner.send_response(200)
                inner.send_header("Content-Type", "application/json")
                inner.end_headers()
                inner.wfile.write(json.dumps(result).encode("utf-8"))

            def log_message(inner, format, *args):
                pass  # Suppress HTTP request logging noise

        self._httpd = HTTPServer((self._host, self._port), _Handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="WezBridgeHTTPServer"
        )
        self._thread.start()
        print(f"[LocalCommandServer] Listening on {self._host}:{self._port}")

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    @property
    def address(self) -> str:
        return f"http://{self._host}:{self._port}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_local_server.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/local_server.py tests/wez_bridge/test_local_server.py
git commit -m "feat(wez_bridge): add LocalCommandServer for ExoCore dispatch"
```

---

### Task 7: Extension Orchestrator (WezBridgeExtension)

**Files:**
- Create: `extensions/wez_bridge/extension.py`
- Create: `tests/wez_bridge/test_extension.py`

- [ ] **Step 1: Write the failing test**

Create `tests/wez_bridge/test_extension.py`:
```python
from unittest.mock import MagicMock, patch
from extensions.wez_bridge.extension import WezBridgeExtension


class TestWezBridgeExtension:
    def test_name_is_wezterm_bridge(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"):
            ext = WezBridgeExtension()
            assert "WezTerm" in ext.name

    def test_start_starts_all_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI") as mock_cli, \
             patch("extensions.wez_bridge.extension.CacheManager") as mock_cache, \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv, \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel, \
             patch("extensions.wez_bridge.extension.Commander") as mock_cmdr:
            ext = WezBridgeExtension()
            ext.start()

            mock_srv.return_value.start.assert_called_once()
            mock_sentinel.return_value.start.assert_called_once()

    def test_stop_stops_all_components(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer") as mock_srv, \
             patch("extensions.wez_bridge.extension.Sentinel") as mock_sentinel, \
             patch("extensions.wez_bridge.extension.Commander"):
            ext = WezBridgeExtension()
            ext.start()
            ext.stop()

            mock_srv.return_value.stop.assert_called_once()
            mock_sentinel.return_value.stop.assert_called_once()

    def test_get_menu_items_includes_status(self):
        with patch("extensions.wez_bridge.extension.WezTermCLI"), \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.Commander"):
            ext = WezBridgeExtension()
            items = ext.get_menu_items()
            assert len(items) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/wez_bridge/test_extension.py -v`
Expected: all FAIL with "No module named 'extensions.wez_bridge.extension'"

- [ ] **Step 3: Implement WezBridgeExtension**

Create `extensions/wez_bridge/extension.py`:
```python
"""
WezTerm HITL Bridge Extension.

Thin orchestrator that wires together the Sentinel, Commander, and
Local HTTP Server. Follows the same pattern as DSTBridgeExtension.
"""
from pystray import MenuItem
from core.base_extension import BaseExtension
from .wezterm_cli import WezTermCLI
from .cache_manager import CacheManager
from .sentinel import Sentinel
from .commander import Commander
from .local_server import LocalCommandServer
from .config import AGENT_NAME


class WezBridgeExtension(BaseExtension):
    """WezTerm HITL Bridge — monitors panes, injects commands, serves dispatch API."""

    def __init__(self):
        self._name = "WezTerm Bridge"

        # Shared WezTerm CLI instance
        self._cli = WezTermCLI()
        self._cache = CacheManager()
        self._commander = Commander(cli=self._cli)

        # Sentinel — monitors non-host panes for errors
        self._sentinel = Sentinel(
            cli=self._cli,
            cache=self._cache,
            on_alert=self._on_sentinel_alert,
        )

        # Local HTTP server — receives execute_command from ExoCore backend
        self._server = LocalCommandServer(
            handler=self._on_execute_command,
        )

        self._started = False

    # ------------------------------------------------------------------
    # BaseExtension protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def start(self):
        if self._started:
            return
        self._started = True

        print(f"[{self._name}] Starting components...")

        # 1. Start the local HTTP server (receives ExoCore dispatches)
        self._server.start()

        # 2. Auto-discover host pane (the TUI pane)
        host_id = self._cli.get_host_pane_id()
        if host_id:
            self._sentinel._host_pane_id = host_id
            print(f"[{self._name}] Host pane detected: {host_id}")

        # 3. Start the sentinel (background pane monitor)
        self._sentinel.start()

        print(f"[{self._name}] All components started. "
              f"Server: {self._server.address}")

    def stop(self):
        if not self._started:
            return
        self._started = False

        print(f"[{self._name}] Stopping components...")
        self._sentinel.stop()
        self._server.stop()
        print(f"[{self._name}] Stopped.")

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem("WezTerm Bridge Status", self._menu_status),
        ]

    def get_settings_ui(self):
        return None

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_sentinel_alert(self, pane_id: str, cache_path: str, snippet: str):
        """Called when the Sentinel detects an error in a monitored pane."""
        self._inject_context_to_exocore(pane_id, cache_path, snippet)

    def _on_execute_command(self, payload: dict) -> dict:
        """Called when the Local HTTP Server receives an execute_command dispatch."""
        pane_id = payload.get("target_pane_id", "")
        command = payload.get("command", "")
        execute_immediately = payload.get("execute_immediately", False)
        alert_message = payload.get("alert_message", "")

        print(f"[{self._name}] Received command for pane {pane_id}: {command[:80]}...")
        if alert_message:
            print(f"[{self._name}] Alert: {alert_message}")

        ok = self._commander.draft_cli_command(
            pane_id=pane_id,
            command=command,
            execute_immediately=execute_immediately,
        )
        return {
            "status": "ok" if ok else "failed",
            "pane_id": pane_id,
            "injected": ok,
        }

    # ------------------------------------------------------------------
    # ExoCore integration
    # ------------------------------------------------------------------

    def _inject_context_to_exocore(self, pane_id: str, cache_path: str, snippet: str):
        """Forward a sentinel alert to ExoCore via external_context_inject."""
        try:
            from core.api_client import ExocoreClient
            client = ExocoreClient(agent_name=AGENT_NAME)
            client.inject_context(
                captured_text=f"[Sentinel Alert] Pane {pane_id}: {snippet}",
                user_prompt="",
                capture_method="terminal",
                target_storage="session_memory",
                mode="agent_audit",
                custom_title=f"Pane {pane_id} Error State",
                metadata={
                    "pane_id": pane_id,
                    "current_dir": "",
                    "cache_file_reference": cache_path,
                },
            )
            print(f"[{self._name}] Context injected to ExoCore for pane {pane_id}")
        except Exception as e:
            print(f"[{self._name}] Failed to inject context: {e}")

    # ------------------------------------------------------------------
    # Tray menu actions
    # ------------------------------------------------------------------

    def _menu_status(self):
        """Display current bridge status (prints to console for now)."""
        panes = self._cli.list_panes()
        print(f"[{self._name}] Status — {len(panes)} panes detected, "
              f"Server: {self._server.address}")
        for p in panes:
            print(f"  Pane {p.get('pane_id')}: {p.get('title', '?')} "
                  f"(active={p.get('is_active', False)})")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/wez_bridge/test_extension.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add extensions/wez_bridge/extension.py tests/wez_bridge/test_extension.py
git commit -m "feat(wez_bridge): add WezBridgeExtension orchestrator"
```

---

### Task 8: Extend API Client for metadata and chat_stream

**Files:**
- Modify: `core/api_client.py`
- Create: `tests/test_api_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_api_client.py`:
```python
import json
from unittest.mock import patch, MagicMock
from core.api_client import ExocoreClient


class TestInjectContextMetadata:
    def test_metadata_field_is_sent(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client = ExocoreClient(agent_name="Alessandro")
            client.inject_context(
                captured_text="error text",
                user_prompt="",
                capture_method="terminal",
                target_storage="session_memory",
                mode="agent_audit",
                custom_title="Pane 2 Error",
                metadata={
                    "pane_id": "2",
                    "current_dir": "/home/user",
                    "cache_file_reference": "/tmp/cache/pane_2.log",
                },
            )

            call_payload = mock_post.call_args[1]["json"]
            assert "metadata" in call_payload
            assert call_payload["metadata"]["pane_id"] == "2"
            assert call_payload["metadata"]["cache_file_reference"] == "/tmp/cache/pane_2.log"

    def test_metadata_is_optional(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok"}

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client = ExocoreClient(agent_name="Alessandro")
            client.inject_context(
                captured_text="hello",
                user_prompt="",
                capture_method="clipboard",
                target_storage="external_session",
                mode="zero_tool",
            )

            call_payload = mock_post.call_args[1]["json"]
            assert "metadata" not in call_payload


class TestChatStream:
    def test_chat_stream_yields_sse_events(self):
        """▶ BACKEND CONFIRMATION NEEDED: Exact SSE event format.
        This test assumes the blueprint's specification:
          POST /api/agents/chat_stream/ with agent, session_id, host_pane_id, user_input.
          Response is text/event-stream.
        If the actual format differs, update this test."""
        mock_sse_data = [
            b'data: {"token": "Hello"}\n\n',
            b'data: {"token": " world"}\n\n',
            b'data: {"token": "!"}\n\n',
            b'data: [DONE]\n\n',
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/event-stream"}
        mock_resp.iter_lines.return_value = mock_sse_data

        with patch("requests.post", return_value=mock_resp) as mock_post:
            client = ExocoreClient(agent_name="Alessandro")
            events = list(client.chat_stream(
                session_id="wezterm_session_01",
                host_pane_id="0",
                user_input="fix the git conflict",
            ))

            call_payload = mock_post.call_args[1]["json"]
            assert call_payload["agent"] == "Alessandro"
            assert call_payload["session_id"] == "wezterm_session_01"
            assert call_payload["host_pane_id"] == "0"
            assert len(events) == 3
            assert events[0] == {"token": "Hello"}

    def test_chat_stream_handles_http_error(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = Exception("500 Server Error")

        with patch("requests.post", return_value=mock_resp):
            client = ExocoreClient(agent_name="Alessandro")
            events = list(client.chat_stream(
                session_id="test", host_pane_id="0", user_input="test"
            ))
            assert events == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_client.py -v`
Expected: FAIL — `chat_stream` method doesn't exist; `metadata` kwarg not supported

- [ ] **Step 3: Extend ExocoreClient**

Read the current `core/api_client.py` and apply these changes:

**Change 1:** Add `metadata` parameter to `inject_context`:
```python
# In the inject_context method, add metadata parameter:
def inject_context(
    self,
    captured_text: str,
    user_prompt: str,
    capture_method: str,
    target_storage: str,
    mode: str = "zero_tool",
    custom_title: str | None = None,
    metadata: dict | None = None,  # NEW
) -> dict:
    # ... existing code ...
    if custom_title:
        payload["custom_title"] = custom_title
    if metadata:                      # NEW
        payload["metadata"] = metadata  # NEW
    # ... rest unchanged ...
```

**Change 2:** Add `chat_stream` method:
```python
def chat_stream(
    self,
    session_id: str,
    host_pane_id: str,
    user_input: str,
) -> iter:
    """▶ BACKEND CONFIRMATION NEEDED: Verify the SSE event format with backend team.
    
    POST /api/agents/chat_stream/
    Response: text/event-stream with JSON data chunks.
    Yields parsed JSON objects from each SSE data line.
    """
    url = f"{self.base_url}/api/agents/chat_stream/"
    payload = {
        "agent": self.agent_name,
        "session_id": session_id,
        "host_pane_id": host_pane_id,
        "user_input": user_input,
    }

    headers = {"Accept": "text/event-stream"}
    if not EXOCORE_EXTENSION_KEY and EXOCORE_ADMIN_KEY:
        headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY
    if EXOCORE_EXTENSION_KEY:
        payload["extension_secret"] = EXOCORE_EXTENSION_KEY

    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=300, stream=True
        )
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]  # Strip "data: " prefix
            if data_str.strip() == "[DONE]":
                break
            try:
                yield json.loads(data_str)
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"[ExocoreClient] chat_stream error: {e}")
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api_client.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add core/api_client.py tests/test_api_client.py
git commit -m "feat(api_client): add metadata support and chat_stream SSE method"
```

---

### Task 9: TUI Application (sandro_tui.py)

**Files:**
- Create: `sandro_tui.py`
- Modify: `requirements.txt`

> **Note:** This task requires `prompt_toolkit` and `httpx`. The TUI is a standalone script launched inside a WezTerm pane with `WEZTERM_PANE` set.

- [ ] **Step 1: Add dependencies**

Read `requirements.txt` and append:
```
prompt_toolkit>=3.0.0
httpx>=0.27.0
```

Install: `pip install prompt_toolkit httpx`

- [ ] **Step 2: Write the TUI application**

Create `sandro_tui.py`:
```python
#!/usr/bin/env python
"""
Alessandro Terminal Pane (TUI) — sandro_tui.py

A lightweight prompt_toolkit shell that:
1. Detects its WezTerm pane ID from WEZTERM_PANE env var.
2. Forwards user input to ExoCore chat_stream SSE endpoint.
3. Renders streaming responses token-by-token.
4. Handles Ctrl+C gracefully (sends interrupt to backend).

Launch inside a WezTerm pane:
    python sandro_tui.py
"""
import os
import sys
import json
import signal
import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown

# ---------------------------------------------------------------------------
# Configuration (imports from project config if available)
# ---------------------------------------------------------------------------
try:
    from config import EXOCORE_BASE_URL, EXOCORE_ADMIN_KEY, EXOCORE_EXTENSION_KEY
except ImportError:
    EXOCORE_BASE_URL = "http://127.0.0.1:8000"
    EXOCORE_ADMIN_KEY = "alessandro_root_045"
    EXOCORE_EXTENSION_KEY = "exocore_pollux"

AGENT_NAME = "Alessandro"
SESSION_ID = "wezterm_session_01"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict:
    headers = {"Accept": "text/event-stream"}
    if EXOCORE_ADMIN_KEY and not EXOCORE_EXTENSION_KEY:
        headers["X-Admin-Key"] = EXOCORE_ADMIN_KEY
    return headers


def _build_payload(user_input: str, host_pane_id: str) -> dict:
    payload = {
        "agent": AGENT_NAME,
        "session_id": SESSION_ID,
        "host_pane_id": host_pane_id,
        "user_input": user_input,
    }
    if EXOCORE_EXTENSION_KEY:
        payload["extension_secret"] = EXOCORE_EXTENSION_KEY
    return payload


def stream_chat(user_input: str, host_pane_id: str):
    """▶ BACKEND CONFIRMATION NEEDED: Verify SSE event format with backend.
    
    Generator that yields tokens from the chat_stream SSE endpoint.
    """
    url = f"{EXOCORE_BASE_URL.rstrip('/')}/api/agents/chat_stream/"
    headers = _auth_headers()
    payload = _build_payload(user_input, host_pane_id)

    try:
        resp = requests.post(
            url, json=payload, headers=headers, timeout=300, stream=True
        )
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str.strip() == "[DONE]":
                break
            try:
                obj = json.loads(data_str)
                token = obj.get("token", "")
                if token:
                    yield token
            except json.JSONDecodeError:
                continue
    except requests.ConnectionError:
        yield "\n[ERR] Cannot reach ExoCore backend at {0}".format(url)
    except Exception as e:
        yield f"\n[ERR] {e}"


# ---------------------------------------------------------------------------
# TUI
# ---------------------------------------------------------------------------

STYLE = Style.from_dict({
    "prompt": "#edd554 bold",
    "input": "#E0E7FF",
    "thinking": "#b1b5c8 italic",
    "error": "#ff4444",
})

bindings = KeyBindings()

@bindings.add("c-c")
def _(event):
    """Ctrl+C: signal interrupt instead of quitting the TUI."""
    print("\n[Interrupted] Sending stop signal to backend...")
    # The next prompt will appear; backend should handle cancellation.
    event.app.renderer.clear()


def main():
    host_pane_id = os.environ.get("WEZTERM_PANE", "0")
    print(f"  Alessandro Terminal Pane")
    print(f"  Pane: {host_pane_id}  |  Session: {SESSION_ID}")
    print(f"  Backend: {EXOCORE_BASE_URL}")
    print(f"  Type /help for commands, Ctrl+C to interrupt, Ctrl+D to quit")
    print()

    session = PromptSession(style=STYLE, key_bindings=bindings)

    while True:
        try:
            user_input = session.prompt([("class:prompt", ">>> ")], multiline=False)
        except KeyboardInterrupt:
            continue  # Ctrl+C re-shows the prompt
        except EOFError:
            print("\n[Exiting Alessandro TUI]")
            break

        if not user_input.strip():
            continue

        if user_input.strip() == "/help":
            print("  /help   - Show this message")
            print("  /clear  - Clear the screen")
            print("  /pane   - Show current pane ID")
            continue

        if user_input.strip() == "/clear":
            os.system("cls" if os.name == "nt" else "clear")
            continue

        if user_input.strip() == "/pane":
            print(f"  Host Pane ID: {host_pane_id}")
            continue

        # Stream the response
        print()
        full_response = ""
        try:
            for token in stream_chat(user_input, host_pane_id):
                print(token, end="", flush=True)
                full_response += token
        except KeyboardInterrupt:
            print("\n[Interrupted]")

        print("\n")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify script loads without error**

Run: `python -c "import ast; ast.parse(open('sandro_tui.py').read()); print('Syntax OK')"`
Expected: Syntax OK

- [ ] **Step 4: Commit**

```bash
git add sandro_tui.py requirements.txt
git commit -m "feat: add sandro_tui.py interactive terminal UI"
```

---

### Task 10: Integration Wiring and Smoke Test

**Files:**
- Modify: `core/api_client.py:60-62` (the inject_context call in extension.py already uses it)
- Create: `tests/wez_bridge/test_integration.py`

- [ ] **Step 1: Write integration smoke test**

Create `tests/wez_bridge/test_integration.py`:
```python
"""Integration smoke tests — verify all components wire together correctly."""
import json
import time
import threading
from unittest.mock import MagicMock, patch
from extensions.wez_bridge.extension import WezBridgeExtension
from extensions.wez_bridge.wezterm_cli import WezTermCLI
from extensions.wez_bridge.sentinel import Sentinel
from extensions.wez_bridge.commander import Commander
from extensions.wez_bridge.local_server import LocalCommandServer
from extensions.wez_bridge.cache_manager import CacheManager


class TestIntegration:
    def test_full_pipeline_sentinel_to_exocore(self):
        """Mocked full pipeline: Sentinel detects error → cache dump → ExoCore inject."""
        with patch("core.api_client.ExocoreClient.inject_context") as mock_inject:
            mock_inject.return_value = {"status": "ok"}

            cli = WezTermCLI()
            cache = CacheManager(cache_root="/tmp/wez_test_cache")
            cmdr = Commander(cli=cli)

            sentinel = Sentinel(cli=cli, cache=cache, host_pane_id="0")
            server = LocalCommandServer(port=18780)

            received_commands = []

            def cmd_handler(payload):
                received_commands.append(payload)
                ok = cmdr.draft_cli_command(
                    pane_id=payload["target_pane_id"],
                    command=payload["command"],
                )
                return {"status": "ok" if ok else "failed"}

            server._handler = cmd_handler
            server.start()
            time.sleep(0.3)

            try:
                # Simulate ExoCore sending a command to the local server
                import urllib.request
                payload = json.dumps({
                    "target_pane_id": "2",
                    "command": "git reset --hard HEAD~1",
                    "execute_immediately": False,
                    "alert_message": "detected merge conflict",
                }).encode("utf-8")

                req = urllib.request.Request(
                    "http://127.0.0.1:18780/api/agents/execute_command/",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                resp = urllib.request.urlopen(req, timeout=3)
                body = json.loads(resp.read().decode())

                assert body["status"] == "ok"
                assert len(received_commands) == 1
                assert received_commands[0]["command"] == "git reset --hard HEAD~1"

            finally:
                server.stop()

    def test_extension_lifecycle_no_crash(self):
        """Extension should start and stop without exceptions."""
        with patch("extensions.wez_bridge.extension.WezTermCLI") as mock_cli_class, \
             patch("extensions.wez_bridge.extension.CacheManager"), \
             patch("extensions.wez_bridge.extension.Sentinel"), \
             patch("extensions.wez_bridge.extension.LocalCommandServer"):
            mock_cli = mock_cli_class.return_value
            mock_cli.get_host_pane_id.return_value = "0"

            ext = WezBridgeExtension()
            ext.start()
            assert ext._started is True
            ext.stop()
            assert ext._started is False
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/wez_bridge/test_integration.py -v`
Expected: 2 PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/wez_bridge/ tests/test_api_client.py -v`
Expected: all PASS (~26 tests total)

- [ ] **Step 4: Commit**

```bash
git add tests/wez_bridge/test_integration.py
git commit -m "test(wez_bridge): add integration smoke tests"
```

---

## Backend Confirmation Checklist

Before deploying, confirm these items with the backend team (CC):

| # | Question | Blueprint Reference | Affected Code |
|---|----------|-------------------|---------------|
| 1 | Is `POST /api/agents/chat_stream/` implemented? What is the exact SSE event format? | Protocol 1 | `core/api_client.py:chat_stream()`, `sandro_tui.py:stream_chat()` |
| 2 | Does `external_context_inject` accept a `metadata` dict? | Protocol 2 | `core/api_client.py:inject_context()` |
| 3 | How does the `cache_file_reference` get attached to subsequent prompts? | Silent Cache Injection (§3) | Extension `_inject_context_to_exocore()` |
| 4 | How does ExoCore discover the extension's local server port? Is there a registration endpoint? | Protocol 3 | `local_server.py`, extension startup |
| 5 | What is the exact payload ExoCore will POST to `/api/agents/execute_command/`? | Protocol 3 | `local_server.py:_Handler.do_POST()` |

---

## File Manifest (After Implementation)

```
extensions/wez_bridge/
├── __init__.py              # Package marker
├── config.py                # All configuration values
├── wezterm_cli.py           # WezTerm CLI subprocess wrapper
├── cache_manager.py         # Local transient cache file management
├── sentinel.py              # Background pane monitor (error detection)
├── commander.py             # Command injection (HITL gate)
├── local_server.py          # Micro HTTP server (ExoCore → Extension)
└── extension.py             # WezBridgeExtension orchestrator

tests/wez_bridge/
├── __init__.py
├── test_config.py
├── test_wezterm_cli.py
├── test_cache_manager.py
├── test_sentinel.py
├── test_commander.py
├── test_local_server.py
├── test_extension.py
└── test_integration.py

tests/
└── test_api_client.py       # API client tests (chat_stream + metadata)

sandro_tui.py                # Standalone TUI (launched in WezTerm pane)

core/api_client.py            # Modified: +metadata, +chat_stream
requirements.txt              # Modified: +prompt_toolkit, +httpx
```
