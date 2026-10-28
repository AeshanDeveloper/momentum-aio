from typing import Any
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_webhooks_update"
description = "Dedicated logging listener for webhook update"
category = "logging"

async def execute(ctx: Any, channel: discord.abc.GuildChannel) -> None:
    await SentinelEventLogger.handle_webhooks_update(channel)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
