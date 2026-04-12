import os
from config import DST_CMD_QUEUE_FILENAME


class DSTExecutor:
    """
    Executes Lua commands in the DST game by writing to a file-based command
    queue that the game mod polls every second and executes via loadstring().

    The queue file is placed in the active shard's Master/ folder (same dir as
    server_log.txt), matching the relative path "exo_cmd_queue.txt" used by the
    mod — avoiding absolute-path sandbox violations in the dedicated server env.

    method="file"  — write to the resolved queue file (default, real execution)
    method="print" — log only, no file write (debug / no-game mode)

    queue_file_resolver: callable() -> str  (optional)
        Called each time execute() runs to get the current queue file path.
        Falls back to DST_CMD_QUEUE_FILENAME in the current directory if not set.
    """

    def __init__(self, method="file", queue_file_resolver=None):
        self.method = method
        self._resolver = queue_file_resolver

    def _queue_path(self) -> str:
        if self._resolver:
            return self._resolver()
        return DST_CMD_QUEUE_FILENAME

    def execute(self, lua_code: str):
        """Append a Lua command to the queue file for the mod to pick up."""
        path = self._queue_path()
        print(f"[DST Executor] Queuing ({path}): {lua_code}")

        if self.method == "print":
            return

        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(lua_code.strip() + "\n")
        except Exception as e:
            print(f"[DST Executor] Failed to write command queue: {e}")
