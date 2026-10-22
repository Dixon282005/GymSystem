"""Thread-safe publish-subscribe Event Bus for Gymsis.

Enables real-time cross-view reactive synchronization without page reloads.
When an NFC card is tapped, a member is updated, or a sale is made, all open
views (Kiosk, Reception Access Feed, Manager Dashboard, Members list) update
their UI components instantly.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List

logger = logging.getLogger("GymsisEventBus")


class EventBus:
    """Central event broker for reactive UI updates."""

    def __init__(self):
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Register a callback for a specific event type."""
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Remove a subscriber callback."""
        with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def publish(self, event_type: str, data: Any = None) -> None:
        """Notify all subscribers of an event, automatically pruning dead callbacks."""
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        dead_callbacks = []
        for cb in callbacks:
            try:
                cb(data)
            except BaseException as e:
                err_msg = str(e).lower()
                # If subscriber belonged to a destroyed/closed/unmounted Flet page, prune it
                if (
                    "must be added to the page first" in err_msg
                    or "not added to" in err_msg
                    or "destroyed" in err_msg
                    or "closed" in err_msg
                    or "unmounted" in err_msg
                ):
                    dead_callbacks.append(cb)
                else:
                    logger.debug(f"[EventBus] Listener for '{event_type}' notice: {e}")

        if dead_callbacks:
            with self._lock:
                for dead_cb in dead_callbacks:
                    if event_type in self._subscribers and dead_cb in self._subscribers[event_type]:
                        self._subscribers[event_type].remove(dead_cb)


# Global singleton instance
event_bus = EventBus()
