from typing import Any, Union
import discord
from core.logging.sentinel_event_logger import SentinelEventLogger
from sdk.event import Event

name = "on_member_unban"
description = "Dedicated logging listener for member unban"
category = "logging"

async def execute(ctx: Any, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
    await SentinelEventLogger.handle_member_unban(guild, user)

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
