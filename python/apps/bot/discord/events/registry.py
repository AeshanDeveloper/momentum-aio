from typing import Dict, Any, List, Optional
from sdk.event import Event

class EventRegistry:
    def __init__(self):
        self._events: Dict[str, List[Event]] = {}

    def register(self, event: Event) -> bool:
        name = event.name
        if name not in self._events:
            self._events[name] = []
        self._events[name].append(event)
        return True

    def get(self, name: str) -> List[Event]:
        return self._events.get(name, [])

    def list_all(self) -> List[Event]:
        res = []
        for l in self._events.values():
            res.extend(l)
        return res

    def clear(self) -> None:
        self._events.clear()

events_registry = EventRegistry()
