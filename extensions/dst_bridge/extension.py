import glob
import json
import os
import re
import threading
import time

from pystray import MenuItem
from core.base_extension import BaseExtension
from config import DST_CMD_QUEUE_FILENAME
from .context_manager import DSTContextManager
from .watcher import DSTWatcher
from .executor import DSTExecutor
from .exocore_lite_client import ExocoreLiteClient


class DSTBridgeExtension(BaseExtension):
    # ------------------------------------------------------------------
    # Path resolution — dynamic, called at runtime via lambda
    # ------------------------------------------------------------------

    _KLEI_BASE = r"D:\Documents\Klei\DoNotStarveTogether"

    def _resolve_log_dir(self) -> str:
        """
        Find the Master directory of the most recently active cluster.
        Returns the full path to the Master folder, or an empty string if not found.
        """
        pattern = os.path.join(self._KLEI_BASE, "**", "Master", "server_log.txt")
        logs = glob.glob(pattern, recursive=True)
        logs = [l for l in logs if "Cluster" in l]

        if not logs:
            # Fallback: search without requiring Master sub-folder
            pattern_flat = os.path.join(self._KLEI_BASE, "**", "server_log.txt")
            logs = [l for l in glob.glob(pattern_flat, recursive=True) if "Cluster" in l]

        if not logs:
            print("[DST Bridge] Warning: No server_log.txt found under Klei base.")
            return ""

        # Master always preferred over Caves; break ties by most-recently modified
        logs.sort(key=lambda x: ("Caves" in x, -os.path.getmtime(x)))
        log_dir = os.path.dirname(logs[0])
        print(f"[DST Bridge] Active log dir: {log_dir}")
        return log_dir

    def _resolve_state_file(self) -> str:
        log_dir = self._resolve_log_dir()
        if not log_dir:
            return os.path.join(self._KLEI_BASE, "client_save", "log.txt")
        return os.path.join(log_dir, "server_log.txt")

    def _resolve_chat_file(self) -> str:
        log_dir = self._resolve_log_dir()
        if not log_dir:
            return os.path.join(self._KLEI_BASE, "client_save", "server_chat_log.txt")
        return os.path.join(log_dir, "server_chat_log.txt")

    def _resolve_cmd_queue_file(self) -> str:
        log_dir = self._resolve_log_dir()
        if not log_dir:
            return os.path.join(self._KLEI_BASE, DST_CMD_QUEUE_FILENAME)
        return os.path.join(log_dir, DST_CMD_QUEUE_FILENAME)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(self):
        self._name = "DST Bridge"
        self.knowledge_file = os.path.join(os.path.dirname(__file__), "knowledge.md")

        self.context = DSTContextManager(max_history=8)
        self.executor = DSTExecutor(method="file", queue_file_resolver=self._resolve_cmd_queue_file)
        self.client = ExocoreLiteClient()

        # State log watcher: forwards [EXO_STATE] JSON lines
        self.state_watcher = DSTWatcher(
            file_path=self._resolve_state_file,
            line_callback=self._on_state_line,
            line_filter=lambda line: "[EXO_STATE]" in line,
            name="DST-StateWatcher",
        )

        # Chat log watcher: forwards all non-empty lines as chat events
        self.chat_watcher = DSTWatcher(
            file_path=self._resolve_chat_file,
            line_callback=self._on_chat_line,
            name="DST-ChatWatcher",
        )

        self.system_prompt = self._load_system_prompt()

        self._last_trigger_time = 0
        self._last_chat_trigger_time = 0
        self._last_state_phase = None
        self._last_health = 100

    @property
    def name(self) -> str:
        return self._name

    def _load_system_prompt(self) -> str:
        knowledge = ""
        if os.path.exists(self.knowledge_file):
            with open(self.knowledge_file, "r", encoding="utf-8") as f:
                knowledge = f.read()

        return f"""You are 'Alessandro', an AI companion playing 'Don't 
        Starve Together' with the Alicia.
Your role: Monitor the game state and help the user via console commands or 
strategic advice. 
或者仅仅是陪她闲聊，闲聊时保持轻松愉快的氛围，即使危险也不要催促或情绪激动。你暂时无法操控游戏角色，但你拥有上帝模式。chat
时保持语言精炼，**只允许输出单句**\n

{knowledge}
\n
Guidelines:
1. Be concise. The user is playing a real-time game.
2. If you want to execute a command, wrap it in [EXEC] tags, e.g., [EXEC] c_give("log", 5) [/EXEC].
3. You can also just chat to give advice.
4. Use the provided state and history to make decisions.
"""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        state_path = self._resolve_state_file()
        chat_path = self._resolve_chat_file()
        print(f"[{self._name}] Starting — state: {state_path}")
        print(f"[{self._name}] Starting — chat:  {chat_path}")
        self.state_watcher.start()
        self.chat_watcher.start()

    def stop(self):
        self.state_watcher.stop()
        self.chat_watcher.stop()

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem("Clear DST Context", self.context.clear),
            MenuItem("Sync Now (Manual)", self._manual_sync),
        ]

    # ------------------------------------------------------------------
    # Watcher callbacks
    # ------------------------------------------------------------------

    def _on_state_line(self, line: str):
        """Parse [EXO_STATE] JSON and handle game state update."""
        try:
            json_str = line.split("[EXO_STATE]")[1].strip()
            data = json.loads(json_str)
        except Exception as e:
            print(f"[DST Bridge] Error parsing EXO_STATE line: {e}")
            return
        self.on_state_changed(data)

    # Keywords that identify DST system events (not player-initiated chat)
    _SYSTEM_CHAT_KEYWORDS = ("Announcement",)

    def _on_chat_line(self, line: str):
        """
        Forward a server_chat_log.txt line into context.
        Lines NOT containing system keywords are treated as real player chat
        and trigger an AI reply (with a short independent cooldown).

        System lines look like:
            [HH:MM:SS]: [Join Announcement] PlayerName
            [HH:MM:SS]: [Roll Announcement] (KU_...) PlayerName N (1-100)
            [HH:MM:SS]: [Leave Announcement] PlayerName
        Player chat looks like:
            [HH:MM:SS]: (PlayerName) message text
        """
        stripped = line.strip()
        if not stripped:
            return

        is_system = any(kw in stripped for kw in self._SYSTEM_CHAT_KEYWORDS)
        label = "EVENT" if is_system else "CHAT"
        self.context.add_event(f"{label}: {stripped}")
        print(f"[DST ChatWatcher] {stripped}")

        if not is_system:
            now = time.time()
            if now - self._last_chat_trigger_time > 5:
                self._last_chat_trigger_time = now
                self._last_trigger_time = now  # also suppress state triggers briefly
                self.context.add_event("SYSTEM_TRIGGER: Player sent a chat message")
                self._consult_ai()

    # ------------------------------------------------------------------
    # Game state logic (unchanged from original)
    # ------------------------------------------------------------------

    def on_state_changed(self, state_json: dict):
        """Called when the game mod dumps a new state."""
        self.context.update_state(state_json)

        now = time.time()
        trigger_reason = None

        if state_json.get("is_forced"):
            trigger_reason = "User requested immediate check (F8)"

        current_phase = state_json.get("time")
        if current_phase != self._last_state_phase:
            if current_phase in ["dusk", "night"]:
                trigger_reason = f"Phase changed to {current_phase}"
            self._last_state_phase = current_phase

        health = state_json.get("health", 100)
        if health < 40 and self._last_health >= 40:
            trigger_reason = "Health dropped to dangerous levels"
        self._last_health = health

        if trigger_reason and (now - self._last_trigger_time > 10):
            print(f"[DST Bridge] AI Trigger: {trigger_reason}")
            self._last_trigger_time = now
            self.context.add_event(f"SYSTEM_TRIGGER: {trigger_reason}")
            self._consult_ai()

    def _consult_ai(self):
        def _task():
            prompt = self.context.get_prompt_context()
            history = self.context.get_conversation_history()
            print(f"[{self._name}] Consulting ExoCore ({len(history)} prior turns)...")

            try:
                reply = self.client.fast_inference(
                    prompt=prompt,
                    system_prompt=self.system_prompt,
                    history=history,
                )
                if reply:
                    print(f"[Alessandro] {reply}")
                    self.context.add_turn("user", prompt)
                    self.context.add_turn("assistant", reply)
                    self._process_reply(reply)
            except Exception as e:
                print(f"[DST Bridge] API Error: {e}")

        threading.Thread(target=_task, daemon=True).start()

    def _process_reply(self, reply: str):
        # 1. Execute embedded Lua commands
        commands = re.findall(r"\[EXEC\](.*?)\[/EXEC\]", reply, re.DOTALL)
        for cmd in commands:
            self.executor.execute(cmd.strip())

        # 2. Announce the text response in-game via TheNet:Announce
        text = re.sub(r"\[EXEC\].*?\[/EXEC\]", "", reply, flags=re.DOTALL).strip()
        if text:
            # Truncate, flatten newlines, escape for Lua double-quoted string
            text = text[:300].replace("\n", " ").replace("\\", "\\\\").replace('"', '\\"').strip()
            if text:
                self.executor.execute(f'TheNet:Announce("[Alessandro] {text}")')

    def _manual_sync(self):
        self.context.add_event("USER_REQUEST: Check status")
        self._consult_ai()
