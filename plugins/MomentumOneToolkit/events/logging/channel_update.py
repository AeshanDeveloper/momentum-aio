from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_channel_update"
description = "Dedicated logging listener for channel update"
category = "logging"

async def execute(*args, **kwargs) -> None:
    if len(args) == 2:
        before, after = args[0], args[1]
    elif len(args) >= 3:
        before, after = args[1], args[2]
    else:
        before = kwargs.get("before")
        after = kwargs.get("after")

    guild = getattr(after, "guild", None) if after else None
    if not guild or not after:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "channel_update", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=after.id
        )

        changes = []
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"• **Name:** `#{before.name}` ➔ `#{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append("• **Topic changed**")
        if getattr(before, "nsfw", False) != getattr(after, "nsfw", False):
            changes.append(f"• **NSFW:** `{before.nsfw}` ➔ `{after.nsfw}`")
        if getattr(before, "category", None) != getattr(after, "category", None):
            b_cat = before.category.name if getattr(before, "category", None) else "None"
            a_cat = after.category.name if getattr(after, "category", None) else "None"
            changes.append(f"• **Category:** `{b_cat}` ➔ `{a_cat}`")

        if not changes:
            po_action = getattr(discord.AuditLogAction, "channel_overwrite_update", getattr(discord.AuditLogAction, "overwrite_update", None))
            actor_po, reason_po = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, po_action, target_id=after.id
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


class ChannelUpdateLoggingEvent(Event):
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


event = ChannelUpdateLoggingEvent
