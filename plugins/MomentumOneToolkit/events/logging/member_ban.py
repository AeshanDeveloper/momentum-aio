from typing import Any, Union
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_ban"
description = "Dedicated logging listener for member ban"
category = "logging"

async def execute(ctx: Any, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.ban, target_id=user.id
        )

        fields = [
            {"name": "Banned User", "value": f"{user.mention} (`{user}` • ID: `{user.id}`)", "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Member Banned",
            description=f"User **{user}** was banned from the server.",
            actor=actor,
            target=user,
            reason=reason or "No reason provided",
            fields=fields,
            severity=LogSeverity.HIGH,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_ban] Failed to dispatch member ban log: {err}")
