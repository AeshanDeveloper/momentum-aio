from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_invite_create"
description = "Dedicated logging listener for invite creation"
category = "logging"

async def execute(ctx: Any, invite: discord.Invite) -> None:
    guild = getattr(invite, "guild", None)
    if not guild or not isinstance(guild, discord.Guild):
        return
    try:
        inviter = invite.inviter
        max_uses_str = str(invite.max_uses) if invite.max_uses else "Unlimited"
        max_age_str = f"{invite.max_age}s" if invite.max_age else "Never expires"

        fields = [
            {"name": "Invite Code", "value": f"`{invite.code}`", "inline": True},
            {"name": "Channel", "value": f"<#{invite.channel.id}>" if invite.channel else "Unknown", "inline": True},
            {"name": "Max Uses", "value": f"`{max_uses_str}`", "inline": True},
            {"name": "Duration", "value": f"`{max_age_str}`", "inline": True},
            {"name": "Temporary", "value": f"`{invite.temporary}`", "inline": True},
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
