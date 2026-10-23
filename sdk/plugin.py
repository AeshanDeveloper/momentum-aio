from typing import Any, Optional

class Plugin:
    def __init__(self, ctx: Any):
        self.ctx = ctx
        self.client = getattr(ctx, "client", None)
        self.event_bus = getattr(ctx, "event_bus", None)
        self.logger = getattr(ctx, "logger", None)
        self.cache = getattr(ctx, "cache", None)
        self.db = getattr(ctx, "database_manager", None)
        self.auto_loader = getattr(ctx, "auto_loader", None)

    async def on_load(self) -> None:
        pass

    async def on_ready(self) -> None:
        pass

    async def on_enable(self) -> None:
        pass

    async def on_disable(self) -> None:
        pass
