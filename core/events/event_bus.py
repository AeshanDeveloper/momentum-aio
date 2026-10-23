import uuid
import time
import inspect
import asyncio
from typing import Dict, List, Callable, Any, Awaitable

class EventBus:
    """
    Event Bus matching TypeScript EventBus with sync & async subscriber support.
    """
    def __init__(self):
        self._listeners: Dict[str, List[Callable[[Any], Any]]] = {}

    def publish(self, event: str, payload: Dict[str, Any]) -> bool:
        event_str = str(event)
        record = {
            "event": event_str,
            "eventId": str(uuid.uuid4()),
            "timestamp": time.time(),
            **payload
        }

        listeners = self._listeners.get(event_str, [])
        for listener in list(listeners):
            try:
                if inspect.iscoroutinefunction(listener):
                    asyncio.create_task(listener(record))
                else:
                    listener(record)
            except Exception as err:
                print(f"[EventBus] Error executing listener for {event_str}: {err}")

        return len(listeners) > 0

    def subscribe(self, event: str, listener: Callable[[Any], Any]) -> "EventBus":
        event_str = str(event)
        if event_str not in self._listeners:
            self._listeners[event_str] = []
        self._listeners[event_str].append(listener)
        return self

    def once(self, event: str, listener: Callable[[Any], Any]) -> "EventBus":
        event_str = str(event)

        def _wrapper(payload: Any):
            self.off(event_str, _wrapper)
            if inspect.iscoroutinefunction(listener):
                return listener(payload)
            return listener(payload)

        return self.subscribe(event_str, _wrapper)

    def off(self, event: str, listener: Callable[[Any], Any]) -> "EventBus":
        event_str = str(event)
        if event_str in self._listeners:
            self._listeners[event_str] = [fn for fn in self._listeners[event_str] if fn != listener]
        return self

    def remove_all_listeners(self, event: str = None) -> "EventBus":
        if event is None:
            self._listeners.clear()
        else:
            self._listeners.pop(str(event), None)
        return self

    def listener_count(self, event: str) -> int:
        return len(self._listeners.get(str(event), []))
