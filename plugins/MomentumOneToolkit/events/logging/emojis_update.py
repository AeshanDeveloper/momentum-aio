from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity

name = "on_guild_emojis_update"
description = "Dedicated logging listener for emojis update"
category = "logging"

async def execute(ctx: Any, guild: discord.Guild, before: Any, after: Any) -> None:
    if guild:
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title="Emojis Updated",
            description=f"Server emojis were updated in **{guild.name}**.",
            severity=LogSeverity.INFO,
        )

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
