from typing import Any, List
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_bulk_message_delete"
description = "Dedicated logging listener for bulk message purges"
category = "logging"

async def execute(ctx: Any, messages: List[discord.Message], channel: discord.abc.GuildChannel) -> None:
    await SentinelEventLogger.handle_bulk_message_delete(messages, channel)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
