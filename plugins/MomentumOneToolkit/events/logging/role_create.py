from typing import Any
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_guild_role_create"
description = "Dedicated logging listener for role create"
category = "logging"

async def execute(ctx: Any, role: discord.Role) -> None:
    await SentinelEventLogger.handle_role_create(role)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
