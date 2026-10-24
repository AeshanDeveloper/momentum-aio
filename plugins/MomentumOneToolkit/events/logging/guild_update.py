from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_update"
description = "Dedicated logging listener for server updates"
category = "logging"

async def execute(ctx: Any, before: discord.Guild, after: discord.Guild) -> None:
    if not after:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            after, discord.AuditLogAction.guild_update, target_id=after.id
        )

        changes = []
        if before.name != after.name:
            changes.append(f"• **Server Name:** `{before.name}` ➔ `{after.name}`")
        if before.description != after.description:
            changes.append(f"• **Description modified**")
        if before.afk_channel != after.afk_channel:
            b_afk = before.afk_channel.name if before.afk_channel else "None"
            a_afk = after.afk_channel.name if after.afk_channel else "None"
            changes.append(f"• **AFK Channel:** `#{b_afk}` ➔ `#{a_afk}`")
        if before.owner_id != after.owner_id:
            changes.append(f"• **Server Ownership Transferred:** `<@{before.owner_id}>` ➔ `<@{after.owner_id}>`")

        if not changes:
            changes.append("• **Server settings or vanity URL modified**")

        fields = [
            {"name": "Server", "value": f"**{after.name}** (`{after.id}`)", "inline": False},
            {"name": "Modifications", "value": "\n".join(changes), "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=after,
            category=LogCategory.SERVER,
            title="Server Updated",
            description=f"Server settings for **{after.name}** were updated.",
            actor=actor,
            target=after.name,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:guild_update] Failed to dispatch guild update log: {err}")
