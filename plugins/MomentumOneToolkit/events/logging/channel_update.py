from typing import Any
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_guild_channel_update"
description = "Dedicated logging listener for channel update"
category = "logging"

async def execute(ctx: Any, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
    await SentinelEventLogger.handle_channel_update(before, after)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
