from typing import Dict, Any, Callable, Optional

class Container:
    """
    IoC Dependency Injection Container.
    Supports singleton service binding and transient factory providers.
    """
    def __init__(self):
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[["Container"], Any]] = {}

    def bind(self, name: str, instance: Any) -> "Container":
        self._services[name] = instance
        return self

    def factory(self, name: str, factory_fn: Callable[["Container"], Any]) -> "Container":
        self._factories[name] = factory_fn
        return self

    def get(self, name: str) -> Optional[Any]:
        if name in self._services:
            return self._services[name]
        if name in self._factories:
            instance = self._factories[name](self)
            self._services[name] = instance
            return instance
        return None

    def has(self, name: str) -> bool:
        return (name in self._services) or (name in self._factories)

container = Container()
