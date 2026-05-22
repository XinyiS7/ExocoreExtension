"""
DST Bridge event type constants.

Published by watchers and consumed by the controller.
Using a flat namespace prefixed 'dst.' to avoid collisions
with events from other extensions.
"""

# Raw log lines (published by DSTWatcher instances)
DST_STATE_LINE = "dst.raw_state_line"        # data: {"shard": str, "line": str}
DST_CHAT_LINE = "dst.raw_chat_line"          # data: {"line": str}

# Parsed events (published by DSTController after parsing)
DST_STATE_CHANGED = "dst.state_changed"      # data: {"shard": str, "state": dict}
DST_CHAT_MESSAGE = "dst.chat_message"        # data: {"player": str, "message": str}
DST_SYSTEM_EVENT = "dst.system_event"        # data: {"kind": str, "line": str}

# AI pipeline (published by DSTController)
DST_AI_TRIGGER = "dst.ai_trigger"            # data: {"reason": str}
DST_AI_REPLY = "dst.ai_reply"                # data: {"reply": str, "prompt": str}
DST_AI_ERROR = "dst.ai_error"                # data: {"error": str}

# Command execution (published by DSTController)
DST_COMMAND_QUEUED = "dst.command_queued"    # data: {"lua_code": str}
DST_ANNOUNCE_QUEUED = "dst.announce_queued"  # data: {"text": str}

# Lifecycle
DST_BRIDGE_STARTED = "dst.bridge_started"    # data: None
DST_BRIDGE_STOPPED = "dst.bridge_stopped"    # data: None
