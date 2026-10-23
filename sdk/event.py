from typing import Any, Callable, Optional

class Event:
    def __init__(
        self,
        name: str,
        execute: Callable[..., Any],
        description: Optional[str] = None,
        enabled: bool = True,
        hidden: bool = False
    ):
        self.name = name
        self.execute = execute
        self.description = description
        self.enabled = enabled
        self.hidden = hidden
