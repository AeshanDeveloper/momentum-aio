from typing import Any, Union
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_ban"
description = "Dedicated logging listener for member ban"
category = "logging"

async def execute(*args, **kwargs) -> None:
    # Flexible signature: execute(guild, user) or execute(ctx, guild, user)
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
        audit_action = getattr(discord.AuditLogAction, "ban", getattr(discord.AuditLogAction, "member_ban_add", None))
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=user.id
        )

        user_tag = str(user)
        actor_tag = str(actor) if actor else "Unknown / Unverified"

        fields = [
            {"name": "Banned User", "value": f"{getattr(user, 'mention', user_tag)} (`{user_tag}` • ID: `{getattr(user, 'id', 'N/A')}`)", "inline": False},
        ]

        payload = {
            "title": "Member Banned",
            "description": f"User **{user_tag}** was banned from the server by **{actor_tag}**.",
            "actor": actor,
            "target": user,
            "reason": reason or "No reason provided",
            "fields": fields,
            "severity": LogSeverity.HIGH,
        }

        await UnifiedWebhookLogger.dispatch_log(
            guild,
            LogCategory.MODERATION,
            payload,
            f"User **{user_tag}** was banned from the server by **{actor_tag}**.",
            actor=actor,
            target=user,
            reason=reason or "No reason provided",
            fields=fields,
            severity=LogSeverity.HIGH,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_ban] Failed to dispatch member ban log: {err}")


class MemberBanLoggingEvent(Event):
    def __init__(self, bot: Any = None):
        super().__init__(
            name="on_member_ban",
            execute=self.execute,
            description="Dedicated logging listener for member ban",
            category="logging",
        )
        self.bot = bot

    async def execute(self, *args, **kwargs):
        return await execute(*args, **kwargs)


event = MemberBanLoggingEvent
