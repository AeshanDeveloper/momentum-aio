from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_update"
description = "Dedicated logging listener for server updates"
category = "logging"

async def execute(*args, **kwargs) -> None:
    if len(args) == 2:
        before, after = args[0], args[1]
    elif len(args) >= 3:
        before, after = args[1], args[2]
    else:
        before = kwargs.get("before")
        after = kwargs.get("after")

    if not after:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "guild_update", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            after, audit_action, target_id=after.id
        )

        changes = []
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"• **Server Name:** `{before.name}` ➔ `{after.name}`")
        if getattr(before, "description", None) != getattr(after, "description", None):
            changes.append("• **Description modified**")
        if getattr(before, "afk_channel", None) != getattr(after, "afk_channel", None):
            b_afk = before.afk_channel.name if getattr(before, "afk_channel", None) else "None"
            a_afk = after.afk_channel.name if getattr(after, "afk_channel", None) else "None"
            changes.append(f"• **AFK Channel:** `#{b_afk}` ➔ `#{a_afk}`")
        if getattr(before, "owner_id", None) != getattr(after, "owner_id", None):
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


class GuildUpdateLoggingEvent(Event):
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


event = GuildUpdateLoggingEvent
