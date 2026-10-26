from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_invite_delete"
description = "Dedicated logging listener for invite deletion"
category = "logging"

async def execute(*args, **kwargs) -> None:
    invite = args[-1] if args else kwargs.get("invite")
    guild = getattr(invite, "guild", None) if invite else None
    if not guild or not isinstance(guild, discord.Guild):
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "invite_delete", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action
        )

        ch_id = invite.channel.id if getattr(invite, "channel", None) else None
        fields = [
            {"name": "Invite Code", "value": f"`{invite.code}`", "inline": True},
            {"name": "Channel", "value": f"<#{ch_id}>" if ch_id else "Unknown", "inline": True},
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


class InviteDeleteLoggingEvent(Event):
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


event = InviteDeleteLoggingEvent
