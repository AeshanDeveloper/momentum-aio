from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity

name = "on_invite_delete"
description = "Dedicated logging listener for invite deletion"
category = "logging"

async def execute(ctx: Any, invite: discord.Invite) -> None:
    guild = getattr(invite, "guild", None)
    if guild:
        fields = [
            {"name": "Code", "value": f"`{getattr(invite, 'code', 'Unknown')}`", "inline": True},
        ]
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title="Invite Deleted",
            description=f"Invite `{getattr(invite, 'code', 'Unknown')}` was deleted or revoked.",
            fields=fields,
            severity=LogSeverity.INFO,
        )

class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description, category="logging")
        self.bot = bot
