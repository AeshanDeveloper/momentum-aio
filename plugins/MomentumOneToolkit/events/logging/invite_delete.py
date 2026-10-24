from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_invite_delete"
description = "Dedicated logging listener for invite deletion"
category = "logging"

async def execute(ctx: Any, invite: discord.Invite) -> None:
    guild = getattr(invite, "guild", None)
    if not guild or not isinstance(guild, discord.Guild):
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.invite_delete
        )

        fields = [
            {"name": "Invite Code", "value": f"`{invite.code}`", "inline": True},
            {"name": "Channel", "value": f"<#{invite.channel.id}>" if invite.channel else "Unknown", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title="Invite Deleted",
            description=f"Invite link `{invite.code}` was deleted or revoked.",
            actor=actor,
            target=f"Invite `{invite.code}`",
            reason=reason,
            fields=fields,
            severity=LogSeverity.LOW,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:invite_delete] Failed to dispatch invite delete log: {err}")
