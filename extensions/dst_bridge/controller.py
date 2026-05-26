"""
DSTController — event-driven coordinator for the DST Bridge.

Subscribes to raw watcher events on the EventBus, parses state and chat,
manages throttling / cooldowns, triggers AI consultation, and publishes
high-level events (state_changed, chat_message, ai_reply, etc.).

Replaces the direct callback chain (watcher → _on_state_line →
on_state_changed → _consult_ai → _process_reply) that was previously
embedded in DSTBridgeExtension.
"""
import json
import os
import re
import threading
import time

from core.event_bus import event_bus
from core.agent_registry import agent_registry
from .events import (
    DST_STATE_LINE,
    DST_CHAT_LINE,
    DST_STATE_CHANGED,
    DST_CHAT_MESSAGE,
    DST_SYSTEM_EVENT,
    DST_AI_TRIGGER,
    DST_AI_REPLY,
    DST_AI_ERROR,
    DST_COMMAND_QUEUED,
    DST_ANNOUNCE_QUEUED,
)


class DSTController:
    """Event-driven coordinator that owns the DST Bridge state machine."""

    # Chat classification constants
    _SYSTEM_CHAT_KEYWORDS = ("Announcement",)
    _PLAYER_CHAT_KEYWORD = "[Say]"

    def __init__(
        self,
        context_manager,
        executor,
        api_client,
        knowledge_file: str,
        agent_name: str = "",
    ):
        self.context = context_manager
        self.executor = executor
        self.client = api_client
        self.knowledge_file = knowledge_file

        # Per-shard state tracking — fixes Master/Caves cross-contamination
        # (Phase 3: each shard tracks its own health / phase independently)
        self._shard_state: dict[str, dict] = {}  # shard_name → {"last_health", "last_phase"}

        # Global cooldowns
        self._last_trigger_time: float = 0.0
        self._last_chat_trigger_time: float = 0.0

        # Subscription ids for cleanup
        self._sub_ids: list[int] = []
        self._started = False

        # Lazy-loaded system prompt
        self._system_prompt: str = ""
        self._agent_name = agent_name

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._system_prompt = self._load_system_prompt()

        self._sub_ids.append(
            event_bus.subscribe(DST_STATE_LINE, self._on_raw_state_line)
        )
        self._sub_ids.append(
            event_bus.subscribe(DST_CHAT_LINE, self._on_raw_chat_line)
        )
        event_bus.publish("dst.bridge_started", None)
        print("[DSTController] Subscribed — listening for state and chat events")

    def stop(self) -> None:
        self._started = False
        for sub_id in self._sub_ids:
            event_bus.unsubscribe(sub_id)
        self._sub_ids.clear()
        event_bus.publish("dst.bridge_stopped", None)
        print("[DSTController] Unsubscribed — stopped")

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _load_system_prompt(self) -> str:
        knowledge = ""
        if os.path.exists(self.knowledge_file):
            with open(self.knowledge_file, "r", encoding="utf-8") as f:
                knowledge = f.read()

        return (
            "You are 'Alessandro', an AI companion playing 'Don't "
            "Starve Together' with Alicia.\n"
            "Your role: Monitor the game state and help the user via console commands or "
            "strategic advice.\n"
            "或者仅仅是陪她闲聊，闲聊时保持轻松愉快的氛围，即使危险也不要催促或情绪激动。你暂时无法操控游戏角色，但你拥有控制台模式。chat "
            "时保持语言精炼，**只允许输出单句**。\n\n"
            f"{knowledge}\n\n"
            "Guidelines:\n"
            "1. Be concise. The user is playing a real-time game. Only output one short sentence.\n"
            "2. If you want to execute a command, wrap it in [EXEC] tags.\n"
            "3. CRITICAL LUA COMMANDS (DO NOT INVENT OTHERS):\n"
            "- Heal: [EXEC] c_sethealth(1) [/EXEC]\n"
            "- Feed: [EXEC] c_sethunger(1) [/EXEC]\n"
            "- Sanity: [EXEC] c_setsanity(1) [/EXEC]\n"
            "- Give item: [EXEC] c_give(\"log\", 5) [/EXEC]\n"
            "- NEVER use `ThePlayer:SetHealth()` as it does not exist. Use the `c_` commands above.\n"
            "4. DO NOT repeat system logs, triggers, or \"[DST ChatWatcher]\" warnings "
            "in your dialogue. Address Alicia naturally.\n"
        )

    # ------------------------------------------------------------------
    # Raw event handlers
    # ------------------------------------------------------------------

    def _on_raw_state_line(self, data: dict | None) -> None:
        if data is None:
            return
        line: str = data.get("line", "")
        shard: str = data.get("shard", "Master")

        try:
            json_str = line.split("[EXO_STATE]")[1].strip()
            state = json.loads(json_str)
        except Exception as e:
            print(f"[DSTController] Error parsing EXO_STATE line: {e}")
            return

        # Per-shard tracking (isolated — no cross-contamination)
        if shard not in self._shard_state:
            self._shard_state[shard] = {"last_health": 100, "last_phase": None}
        tracker = self._shard_state[shard]

        self.context.update_state(state)
        event_bus.publish(DST_STATE_CHANGED, {"shard": shard, "state": state})

        self._evaluate_state_triggers(state, tracker)

    def _on_raw_chat_line(self, data: dict | None) -> None:
        if data is None:
            return
        line: str = data.get("line", "").strip()
        if not line:
            return

        is_system = any(kw in line for kw in self._SYSTEM_CHAT_KEYWORDS)
        is_player_chat = self._PLAYER_CHAT_KEYWORD in line
        label = "CHAT" if is_player_chat else ("EVENT" if is_system else "LOG")

        self.context.add_event(f"{label}: {line}")
        print(f"[DSTController] {line}")

        if is_system:
            event_bus.publish(DST_SYSTEM_EVENT, {"kind": label, "line": line})

        if is_player_chat:
            event_bus.publish(DST_CHAT_MESSAGE, {"player": "", "message": line})

            now = time.time()
            if now - self._last_chat_trigger_time > 5:
                self._last_chat_trigger_time = now
                self._last_trigger_time = now
                self.context.add_event("SYSTEM_TRIGGER: Player sent a chat message")
                self._consult_ai("Player sent a chat message")

    # ------------------------------------------------------------------
    # State evaluation
    # ------------------------------------------------------------------

    def _evaluate_state_triggers(self, state: dict, tracker: dict) -> None:
        now = time.time()
        reasons: list[str] = []

        if state.get("is_forced"):
            reasons.append("User requested immediate check (F8)")

        current_phase = state.get("time")
        if current_phase != tracker["last_phase"]:
            if current_phase in ("dusk", "night"):
                reasons.append(f"Phase changed to {current_phase}")
            tracker["last_phase"] = current_phase

        health = state.get("health", 100)
        if health < 40 and tracker["last_health"] >= 40:
            reasons.append("Health dropped to dangerous levels")
        tracker["last_health"] = health

        if reasons and (now - self._last_trigger_time > 10):
            # Accumulate reasons instead of overwriting
            combined = "; ".join(reasons)
            print(f"[DSTController] AI Trigger: {combined}")
            self._last_trigger_time = now
            self.context.add_event(f"SYSTEM_TRIGGER: {combined}")
            event_bus.publish(DST_AI_TRIGGER, {"reason": combined})
            self._consult_ai(combined)

    # ------------------------------------------------------------------
    # AI consultation
    # ------------------------------------------------------------------

    def _consult_ai(self, reason: str) -> None:
        def _task():
            prompt = self.context.get_prompt_context()
            history = self.context.get_conversation_history()
            agent_name = self._agent_name or agent_registry.get_default_name()
            model = agent_registry.get_agent_model(agent_name)
            print(f"[DSTController] Consulting ExoCore ({len(history)} prior turns, "
                  f"reason: {reason}) with model {model}...")

            try:
                reply = self.client.fast_inference(
                    prompt=prompt,
                    system_prompt=self._system_prompt,
                    history=history,
                    model=model,
                    agent_name=self._agent_name,
                )
                if reply:
                    # Guard: don't store error strings as AI replies
                    if reply.startswith("[ExoCore]"):
                        print(f"[DSTController] API returned error, not storing: {reply[:80]}")
                        event_bus.publish(DST_AI_ERROR, {"error": reply})
                        return

                    print(f"[Alessandro] {reply}")
                    self.context.add_turn("user", prompt)
                    self.context.add_turn("assistant", reply)
                    event_bus.publish(DST_AI_REPLY, {"reply": reply, "prompt": prompt})
                    self._process_reply(reply)
            except Exception as e:
                print(f"[DSTController] API Error: {e}")
                event_bus.publish(DST_AI_ERROR, {"error": str(e)})

        threading.Thread(target=_task, daemon=True).start()

    # ------------------------------------------------------------------
    # Reply processing
    # ------------------------------------------------------------------

    def _process_reply(self, reply: str) -> None:
        commands = re.findall(r"\[EXEC\](.*?)\[/EXEC\]", reply, re.DOTALL)
        for cmd in commands:
            cmd_stripped = cmd.strip().replace('\n', ' ')
            if cmd_stripped:
                self.executor.execute(cmd_stripped)
                event_bus.publish(DST_COMMAND_QUEUED, {"lua_code": cmd_stripped})

        text = re.sub(r"\[EXEC\].*?\[/EXEC\]", "", reply, flags=re.DOTALL).strip()
        if text:
            text = text[:300].replace("\n", " ").replace("\\", "\\\\").replace('"', '\\"').strip()
            if text:
                lua_cmd = f'c_announce("[Alessandro] {text}")'
                self.executor.execute(lua_cmd)
                event_bus.publish(DST_ANNOUNCE_QUEUED, {"text": text})

    # ------------------------------------------------------------------
    # Manual triggers (called from tray menu)
    # ------------------------------------------------------------------

    def manual_sync(self) -> None:
        self.context.add_event("USER_REQUEST: Check status")
        self._consult_ai("Manual sync requested")
