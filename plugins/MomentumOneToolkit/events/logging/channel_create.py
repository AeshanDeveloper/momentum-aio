from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_channel_create"
description = "Dedicated logging listener for channel creation"
category = "logging"

async def execute(ctx: Any, channel: discord.abc.GuildChannel) -> None:
    guild = getattr(channel, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_create, target_id=channel.id
        )
        ch_type = str(getattr(channel, "type", "text")).replace("_", " ").title()
        parent_name = channel.category.name if getattr(channel, "category", None) else "None"

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
