from typing import Any, Dict, Optional, Callable

class LoaderTarget:
    def __init__(self):
        self.enabled: bool = False
        self.directory: str = ""
        self.mapper: Optional[Callable[[Any], Any]] = None

    def set_enabled(self, val: bool) -> "LoaderTarget":
        self.enabled = val
        return self
    setEnabled = set_enabled

    def set_directory(self, d: str) -> "LoaderTarget":
        self.directory = d
        return self
    setDirectory = set_directory

    def set_mapper(self, fn: Callable[[Any], Any]) -> "LoaderTarget":
        self.mapper = fn
        return self
    setMapper = set_mapper

class AutoLoaderConfig:
    def __init__(self):
        self.commands = LoaderTarget()
        self.events = LoaderTarget()

class PluginContext:
    """
    Context provided to every plugin on initialization.
    Supplies shared infrastructure: event bus, logger, database, cache, client, and autoloader.
    """
    def __init__(
        self,
        event_bus: Any,
        client: Any,
        logger: Any,
        cache: Any,
        database_manager: Any
    ):
        self.event_bus = event_bus
        self.client = client
        self.logger = logger
        self.cache = cache
        self.database_manager = database_manager
        self.auto_loader = AutoLoaderConfig()
