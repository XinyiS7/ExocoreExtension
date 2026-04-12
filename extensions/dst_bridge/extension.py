import os
import threading
import time
from pystray import MenuItem
from core.base_extension import BaseExtension
from .context_manager import DSTContextManager
from .watcher import DSTWatcher
from .executor import DSTExecutor
from .exocore_lite_client import ExocoreLiteClient

class DSTBridgeExtension(BaseExtension):
    def _resolve_state_file(self) -> str:
        """Dynamically find the most recently updated server_log.txt, prioritizing Master over Caves."""
        import glob
        base_dir = r"D:\Documents\Klei\DoNotStarveTogether"
        pattern = os.path.join(base_dir, "**", "server_log.txt")
        
        logs = glob.glob(pattern, recursive=True)
        logs = [l for l in logs if "Cluster" in l]
        
        if not logs:
            print("[DST Bridge] Warning: No server_log.txt found. Falling back to default.")
            return os.path.join(base_dir, "client_save", "log.txt")
            
        # Sort: Primary sort by folder name (Master before Caves), Secondary by time (newest first)
        # We use a tuple for sorting: (is_caves, -timestamp)
        # Master will have is_caves=False (0), Caves will have is_caves=True (1)
        # This ensures Master always wins if timestamps are close.
        logs.sort(key=lambda x: ("Caves" in x, -os.path.getmtime(x)))
        
        latest_log = logs[0]
        print(f"[DST Bridge] Auto-detected active log: {latest_log}")
        return latest_log

    def __init__(self):
        self._name = "DST Bridge"
        self.state_file = self._resolve_state_file()
        self.knowledge_file = os.path.join(os.path.dirname(__file__), "knowledge.md")
        
        # Components
        self.context = DSTContextManager(max_history=8)
        self.watcher = DSTWatcher(self.state_file, self.on_state_changed)
        self.executor = DSTExecutor(method="print") # Start with debug print
        self.client = ExocoreLiteClient()
        
        self.system_prompt = self._load_system_prompt()
        
        # State tracking for triggers
        self._last_trigger_time = 0
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
        
        return f"""You are 'Alessandro', an AI companion playing 'Don't Starve Together' with the user.
Your role: Monitor the game state and help the user via console commands or strategic advice.

{knowledge}

Guidelines:
1. Be concise. The user is playing a real-time game.
2. If you want to execute a command, wrap it in [EXEC] tags, e.g., [EXEC] c_give("log", 5) [/EXEC].
3. You can also just chat to give advice.
4. Use the provided state and history to make decisions.
"""

    def start(self):
        print(f"[{self._name}] Starting watcher for {self.state_file}...")
        self.watcher.start()

    def stop(self):
        self.watcher.stop()

    def get_menu_items(self) -> list[MenuItem]:
        return [
            MenuItem("Clear DST Context", self.context.clear),
            MenuItem("Sync Now (Manual)", self._manual_sync),
        ]

    def on_state_changed(self, state_json: dict):
        """Callback when the game mod dumps a new state."""
        self.context.update_state(state_json)
        
        now = time.time()
        trigger_reason = None
        
        # 1. Manual Force (F8)
        if state_json.get("is_forced"):
            trigger_reason = "User requested immediate check (F8)"
            
        # 2. Phase change (Day -> Dusk -> Night)
        current_phase = state_json.get("time")
        if current_phase != self._last_state_phase:
            if current_phase in ["dusk", "night"]:
                trigger_reason = f"Phase changed to {current_phase}"
            self._last_state_phase = current_phase
            
        # 3. Health Drop (significant drop or below threshold)
        health = state_json.get("health", 100)
        if health < 40 and self._last_health >= 40:
            trigger_reason = "Health dropped to dangerous levels"
        self._last_health = health
            
        if trigger_reason and (now - self._last_trigger_time > 10): # 10s debounce
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
                    # Record both sides of the turn for future context
                    self.context.add_turn("user", prompt)
                    self.context.add_turn("assistant", reply)
                    self._process_reply(reply)
            except Exception as e:
                print(f"[DST Bridge] API Error during consultation: {e}")

        threading.Thread(target=_task, daemon=True).start()

    def _process_reply(self, reply: str):
        """Parse commands out of the AI reply and execute them."""
        import re
        commands = re.findall(r"\[EXEC\](.*?)\[/EXEC\]", reply, re.DOTALL)
        for cmd in commands:
            self.executor.execute(cmd.strip())

    def _manual_sync(self):
        self.context.add_event("USER_REQUEST: Check status")
        self._consult_ai()
