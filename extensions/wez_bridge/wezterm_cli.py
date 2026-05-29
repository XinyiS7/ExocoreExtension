import json
import subprocess
from .config import WEZTERM_CLI


class WezTermCLI:
    """Thin wrapper around ``wezterm cli`` subprocess calls."""

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
        """Scrape visible text from a pane.  If tail_lines > 0, return only the last N lines."""
        try:
            proc = subprocess.run(
                [self._binary, "cli", "get-text", "--pane-id", str(pane_id)],
                capture_output=True, text=True, timeout=self._timeout,
            )
            if proc.returncode != 0:
                return ""
            text = proc.stdout
            if tail_lines > 0:
                lines = text.rstrip("\n").split("\n")
                text = "\n".join(lines[-tail_lines:]) + "\n"
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
        """Send a carriage return to submit the command.
        On Windows / Git Bash, standard LF (\\n) often fails to submit the buffer.
        Carriage Return (\\r) ensures the shell executes the command raw.
        """
        return self.send_text(pane_id, "\r")
