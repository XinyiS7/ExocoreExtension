"""
Thread-safe pub/sub event bus.

Extensions publish typed events; subscribers receive them synchronously
on the publishing thread. Subscribers that need async behaviour should
spawn their own threads.
"""
import threading
from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[tuple[int, Callable[[Any], None]]]] = defaultdict(list)
        self._id_seq = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> int:
        """Register a callback. Returns a subscription id for unsubscribe()."""
        with self._lock:
            self._id_seq += 1
            sub_id = self._id_seq
            self._subscribers[event_type].append((sub_id, callback))
            return sub_id

    def unsubscribe(self, sub_id: int) -> None:
        with self._lock:
            for evt_type, subs in list(self._subscribers.items()):
                self._subscribers[evt_type] = [(sid, cb) for sid, cb in subs if sid != sub_id]
                if not self._subscribers[evt_type]:
                    del self._subscribers[evt_type]

    def unsubscribe_all(self, event_type: str) -> None:
        with self._lock:
            self._subscribers.pop(event_type, None)

    def publish(self, event_type: str, data: Any = None) -> None:
        """Deliver an event to all subscribers. Runs callbacks synchronously."""
        with self._lock:
            subs = [cb for _, cb in self._subscribers.get(event_type, [])]
        for callback in subs:
            try:
                callback(data)
            except Exception as e:
                print(f"[EventBus] Subscriber error for '{event_type}': {e}")

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return sum(len(v) for v in self._subscribers.values())


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

event_bus = EventBus()
