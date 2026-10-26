from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_webhooks_update"
description = "Dedicated logging listener for webhook modifications in channels"
category = "logging"

async def execute(*args, **kwargs) -> None:
    channel = args[-1] if args else kwargs.get("channel")
    guild = getattr(channel, "guild", None) if channel else None
    if not guild or not channel:
        return
    try:
        wh_create = getattr(discord.AuditLogAction, "webhook_create", None)
        wh_update = getattr(discord.AuditLogAction, "webhook_update", None)
        wh_delete = getattr(discord.AuditLogAction, "webhook_delete", None)

        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, wh_create, target_id=channel.id
        )
        if not actor and wh_update:
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, wh_update, target_id=channel.id
            )
        if not actor and wh_delete:
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, wh_delete, target_id=channel.id
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


class WebhooksUpdateLoggingEvent(Event):
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


event = WebhooksUpdateLoggingEvent
