from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_invite_create"
description = "Dedicated logging listener for invite creation"
category = "logging"

async def execute(*args, **kwargs) -> None:
    invite = args[-1] if args else kwargs.get("invite")
    guild = getattr(invite, "guild", None) if invite else None
    if not guild or not isinstance(guild, discord.Guild):
        return
    try:
        inviter = getattr(invite, "inviter", None)
        max_uses_str = str(invite.max_uses) if getattr(invite, "max_uses", None) else "Unlimited"
        max_age_str = f"{invite.max_age}s" if getattr(invite, "max_age", None) else "Never expires"

        fields = [
            {"name": "Invite Code", "value": f"`{invite.code}`", "inline": True},
            {"name": "Channel", "value": f"<#{invite.channel.id}>" if getattr(invite, "channel", None) else "Unknown", "inline": True},
            {"name": "Max Uses", "value": f"`{max_uses_str}`", "inline": True},
            {"name": "Duration", "value": f"`{max_age_str}`", "inline": True},
            {"name": "Temporary", "value": f"`{getattr(invite, 'temporary', False)}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title="Invite Created",
            description=f"A new invite link was created by {inviter.mention if inviter else 'Unknown'}.",
            actor=inviter,
            target=f"Invite `{invite.code}`",
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:invite_create] Failed to dispatch invite create log: {err}")


class InviteCreateLoggingEvent(Event):
    def __init__(self, bot: Any = None):
        super().__init__(
            name=name,
            execute=self.execute,
            description=description,
            category=category,
        )
        self.bot = bot

    async def execute(self, *args, **kwargs):
        return await execute(*args, **kwargs)


event = InviteCreateLoggingEvent
