from typing import Any
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_message_delete"
description = "Dedicated logging listener for message deletion & ghost ping detection"
category = "logging"

async def execute(ctx: Any, message: discord.Message) -> None:
    await SentinelEventLogger.handle_message_delete(message)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
