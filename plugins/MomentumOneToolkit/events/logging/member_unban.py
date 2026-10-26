from typing import Any, Union
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_unban"
description = "Dedicated logging listener for member unban"
category = "logging"

async def execute(*args, **kwargs) -> None:
    if len(args) == 2:
        guild, user = args[0], args[1]
    elif len(args) >= 3:
        guild, user = args[1], args[2]
    else:
        guild = kwargs.get("guild")
        user = kwargs.get("user")

    if not guild or not user:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "unban", getattr(discord.AuditLogAction, "member_ban_remove", None))
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=user.id
        )

        user_tag = str(user)
        fields = [
            {"name": "Pardoned User", "value": f"{getattr(user, 'mention', user_tag)} (`{user_tag}` • ID: `{getattr(user, 'id', 'N/A')}`)", "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Member Unbanned",
            description=f"User **{user_tag}** was unbanned from the server.",
            actor=actor,
            target=user,
            reason=reason or "No reason provided",
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_unban] Failed to dispatch member unban log: {err}")


class MemberUnbanLoggingEvent(Event):
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


event = MemberUnbanLoggingEvent
