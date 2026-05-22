"""
DST Bridge extension — event-driven architecture (Phase 3).

Watchers tail DST log files and publish raw line events to the EventBus.
The DSTController subscribes to those events, parses state/chat, manages
throttling, triggers AI consultation, and publishes high-level events.

The extension is now a thin orchestrator: it creates the watchers,
controller, executor, and wires them together. All game-state logic
lives in DSTController.
"""
import os

from pystray import MenuItem
from core.event_bus import event_bus
from core.base_extension import BaseExtension
from .config import DST_CLUSTER_PATH, DST_CMD_QUEUE_FILENAME
from .context_manager import DSTContextManager
from .watcher import DSTWatcher
from .executor import DSTExecutor
from .exocore_lite_client import ExocoreLiteClient
from .controller import DSTController
from .events import DST_STATE_LINE, DST_CHAT_LINE


class DSTBridgeExtension(BaseExtension):
    # ------------------------------------------------------------------
    # Path resolution — rooted at DST_CLUSTER_PATH (e.g. .../Cluster_4)
    # Master and Caves are direct subdirectories of that cluster folder.
    # ------------------------------------------------------------------

    def _shard_dir(self, shard: str) -> str:
        return os.path.join(DST_CLUSTER_PATH, shard)

    def _resolve_state_file(self, shard: str = "Master") -> str:
        return os.path.join(self._shard_dir(shard), "server_log.txt")

    def _resolve_chat_file(self) -> str:
        dst_root = os.path.dirname(os.path.normpath(DST_CLUSTER_PATH))
        client_log = os.path.join(dst_root, "client_chat_log.txt")
        if os.path.exists(client_log):
            return client_log
        return os.path.join(self._shard_dir("Master"), "server_chat_log.txt")

    def _resolve_cmd_queue_file(self) -> str:
        return os.path.join(self._shard_dir("Master"), "save", DST_CMD_QUEUE_FILENAME)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self):
        self._name = "DST Bridge"
        knowledge_file = os.path.join(os.path.dirname(__file__), "knowledge.md")

        # Shared services
        context = DSTContextManager(max_history=8)
        executor = DSTExecutor(method="file", queue_file_resolver=self._resolve_cmd_queue_file)
        client = ExocoreLiteClient()

        # Controller owns all game-state logic (was: _on_state_line, _on_chat_line,
        # on_state_changed, _consult_ai, _process_reply)
        self.controller = DSTController(
            context_manager=context,
            executor=executor,
            api_client=client,
            knowledge_file=knowledge_file,
        )
        self.context = context  # exposed for tray menu "Clear DST Context"

        # Watchers — publish raw lines to the EventBus instead of calling
        # extension methods directly.  The controller subscribes to these events.
        self.state_watcher = DSTWatcher(
            file_path=lambda: self._resolve_state_file("Master"),
            line_callback=lambda line: event_bus.publish(
                DST_STATE_LINE, {"shard": "Master", "line": line}
            ),
            line_filter=lambda line: "[EXO_STATE]" in line,
            name="DST-MasterStateWatcher",
        )

        self.caves_watcher = DSTWatcher(
            file_path=lambda: self._resolve_state_file("Caves"),
            line_callback=lambda line: event_bus.publish(
                DST_STATE_LINE, {"shard": "Caves", "line": line}
            ),
            line_filter=lambda line: "[EXO_STATE]" in line,
            name="DST-CavesStateWatcher",
        )

        self.chat_watcher = DSTWatcher(
            file_path=self._resolve_chat_file,
            line_callback=lambda line: event_bus.publish(
                DST_CHAT_LINE, {"line": line}
            ),
            name="DST-ChatWatcher",
        )

    # ------------------------------------------------------------------
    # BaseExtension protocol
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    def start(self):
        print(f"[{self._name}] Starting — Master state: {self._resolve_state_file('Master')}")
        print(f"[{self._name}] Starting — Caves  state: {self._resolve_state_file('Caves')}")
        print(f"[{self._name}] Starting — chat:         {self._resolve_chat_file()}")

        self.controller.start()       # subscribes to EventBus
        self.state_watcher.start()
        self.caves_watcher.start()
        self.chat_watcher.start()

    def stop(self):
        self.state_watcher.stop()
        self.caves_watcher.stop()
        self.chat_watcher.stop()
        self.controller.stop()        # unsubscribes from EventBus

    def get_settings_ui(self):
        return None  # DST bridge has no standalone settings UI yet (Phase 4)

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem("Clear DST Context", self.context.clear),
            MenuItem("Sync Now (Manual)", self._manual_sync),
        ]

    # ------------------------------------------------------------------
    # Manual trigger (tray menu)
    # ------------------------------------------------------------------

    def _manual_sync(self):
        self.controller.manual_sync()
