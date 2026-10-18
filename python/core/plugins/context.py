from typing import Any, Dict

class AutoLoaderConfig:
    def __init__(self):
        self.commands_enabled = False
        self.commands_directory = "commands"
        self.commands_mapper = None
        self.events_enabled = False
        self.events_directory = "events"
        self.events_mapper = None

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
