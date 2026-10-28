from typing import Any, Union
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_member_remove"
description = "Dedicated logging listener for member departure/kick"
category = "logging"

async def execute(ctx: Any, member: Union[discord.Member, discord.User]) -> None:
    await SentinelEventLogger.handle_member_remove(member)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
