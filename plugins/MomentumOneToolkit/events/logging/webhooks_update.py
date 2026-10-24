from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_webhooks_update"
description = "Dedicated logging listener for webhook modifications in channels"
category = "logging"

async def execute(ctx: Any, channel: discord.abc.GuildChannel) -> None:
    guild = getattr(channel, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.webhook_create, target_id=channel.id
        )
        if not actor:
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, discord.AuditLogAction.webhook_update, target_id=channel.id
            )
        if not actor:
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, discord.AuditLogAction.webhook_delete, target_id=channel.id
            )

        fields = [
            {"name": "Channel", "value": f"<#{channel.id}> (`#{channel.name}`)", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title="Channel Webhooks Modified",
            description=f"Webhooks in <#{channel.id}> were created, updated, or deleted.",
            actor=actor,
            target=channel,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:webhooks_update] Failed to dispatch webhook update log: {err}")
