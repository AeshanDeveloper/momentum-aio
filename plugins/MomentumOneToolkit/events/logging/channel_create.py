from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_channel_create"
description = "Dedicated logging listener for channel creation"
category = "logging"

async def execute(*args, **kwargs) -> None:
    channel = args[-1] if args else kwargs.get("channel")
    guild = getattr(channel, "guild", None) if channel else None
    if not guild or not channel:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_create, target_id=channel.id
        )
        ch_type = str(getattr(channel, "type", "text")).replace("_", " ").title()
        cat_obj = getattr(channel, "category", None)
        parent_name = cat_obj.name if cat_obj else "None"

        fields = [
            {"name": "Channel Name", "value": f"`#{channel.name}` (<#{channel.id}>)", "inline": True},
            {"name": "Channel Type", "value": f"`{ch_type}`", "inline": True},
            {"name": "Category", "value": f"`{parent_name}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.CHANNELS,
            title="Channel Created",
            description=f"A new channel **#{channel.name}** was created.",
            actor=actor,
            target=channel,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:channel_create] Failed to dispatch channel creation log: {err}")


class ChannelCreateLoggingEvent(Event):
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


event = ChannelCreateLoggingEvent
