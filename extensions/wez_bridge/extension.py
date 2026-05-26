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

        self._started = True
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
