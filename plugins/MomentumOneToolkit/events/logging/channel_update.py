from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_channel_update"
description = "Dedicated logging listener for channel update"
category = "logging"

async def execute(ctx: Any, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
    guild = getattr(after, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_update, target_id=after.id
        )

        changes = []
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"• **Name:** `#{before.name}` ➔ `#{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"• **Topic changed**")
        if getattr(before, "nsfw", False) != getattr(after, "nsfw", False):
            changes.append(f"• **NSFW:** `{before.nsfw}` ➔ `{after.nsfw}`")
        if getattr(before, "category", None) != getattr(after, "category", None):
            b_cat = before.category.name if before.category else "None"
            a_cat = after.category.name if after.category else "None"
            changes.append(f"• **Category:** `{b_cat}` ➔ `{a_cat}`")

        # If no identifiable changes, could be permission overwrite change
        if not changes:
            actor_po, reason_po = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, discord.AuditLogAction.overwrite_update, target_id=after.id
            )
            if actor_po:
                actor = actor_po
                reason = reason_po
                changes.append("• **Permissions / Overwrites modified**")
            else:
                changes.append("• **Channel settings / permissions updated**")

        fields = [
            {"name": "Channel", "value": f"<#{after.id}> (`#{after.name}`)", "inline": True},
            {"name": "Modifications", "value": "\n".join(changes), "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.CHANNELS,
            title="Channel Updated",
            description=f"Channel **#{after.name}** was modified.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=LogSeverity.LOW,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:channel_update] Failed to dispatch channel update log: {err}")
