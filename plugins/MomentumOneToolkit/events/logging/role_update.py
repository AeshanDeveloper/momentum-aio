from typing import Any
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_guild_role_update"
description = "Dedicated logging listener for role update"
category = "logging"

async def execute(ctx: Any, before: discord.Role, after: discord.Role) -> None:
    await SentinelEventLogger.handle_role_update(before, after)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
