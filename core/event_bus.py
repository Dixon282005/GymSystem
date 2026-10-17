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
        """Notify all subscribers of an event."""
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))

        for cb in callbacks:
            try:
                cb(data)
            except Exception as e:
                logger.error(f"[EventBus] Error executing listener for '{event_type}': {e}")


# Global singleton instance
event_bus = EventBus()
