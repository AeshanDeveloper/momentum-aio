from typing import Any
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_member_join"
description = "Dedicated logging listener for member join"
category = "logging"

async def execute(ctx: Any, member: discord.Member) -> None:
    await SentinelEventLogger.handle_member_join(member)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
