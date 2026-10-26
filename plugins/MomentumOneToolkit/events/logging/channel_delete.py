from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_channel_delete"
description = "Dedicated logging listener for channel deletion"
category = "logging"

async def execute(*args, **kwargs) -> None:
    channel = args[-1] if args else kwargs.get("channel")
    guild = getattr(channel, "guild", None) if channel else None
    if not guild or not channel:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_delete, target_id=channel.id
        )
        ch_type = str(getattr(channel, "type", "text")).replace("_", " ").title()

        fields = [
            {"name": "Channel Name", "value": f"`#{channel.name}` (ID: `{channel.id}`)", "inline": True},
            {"name": "Channel Type", "value": f"`{ch_type}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.CHANNELS,
            title="Channel Deleted",
            description=f"Channel **#{channel.name}** was deleted from the server.",
            actor=actor,
            target=f"`#{channel.name}` (`{channel.id}`)",
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:channel_delete] Failed to dispatch channel delete log: {err}")


class ChannelDeleteLoggingEvent(Event):
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


event = ChannelDeleteLoggingEvent
