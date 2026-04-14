from collections import deque
import json
from datetime import datetime

class DSTContextManager:
    # max_history=10 ensures we keep up to 5 full turns (5 user, 5 assistant)
    def __init__(self, max_history=10):
        self.max_history = max_history
        self.event_log = deque(maxlen=20)       # raw game events for context building
        self.conv_history = deque(maxlen=max_history)  # {"role", "content"} turns for LLM
        self.absolute_state = {}

    def update_state(self, state_json: dict):
        """Update current absolute state from game dump."""
        self.absolute_state = state_json

    def add_event(self, event_text: str):
        """Add a raw game event string (triggers, warnings, system messages)."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_log.append(f"[{timestamp}] {event_text}")

    def add_turn(self, role: str, content: str):
        """Record a completed conversation turn for multi-turn history."""
        self.conv_history.append({"role": role, "content": content})

    def get_prompt_context(self) -> str:
        """Build the current-turn user message: game state + recent events."""
        context = "### CURRENT GAME STATE ###\n"
        context += json.dumps(self.absolute_state, indent=2, ensure_ascii=False)
        if self.event_log:
            context += "\n\n### RECENT EVENTS ###\n"
            context += "\n".join(self.event_log)
        return context

    def get_conversation_history(self) -> list:
        """
        Return prior turns formatted for the API.
        Enforces strict alternating roles, starts with 'user', max 10 messages.
        """
        raw_history = list(self.conv_history)
        sanitized = []
        
        # Build backwards to keep the most recent pairs intact
        for msg in reversed(raw_history):
            expected_role = "user" if not sanitized or sanitized[0]["role"] == "assistant" else "assistant"
            if msg["role"] == expected_role:
                sanitized.insert(0, msg)
        
        # If the oldest message is 'assistant', drop it so it starts with 'user'
        if sanitized and sanitized[0]["role"] == "assistant":
            sanitized.pop(0)
            
        return sanitized

    def clear(self):
        self.event_log.clear()
        self.conv_history.clear()
        self.absolute_state = {}
