from typing import Any, List
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_emojis_update"
description = "Dedicated logging listener for emoji updates"
category = "logging"

async def execute(*args, **kwargs) -> None:
    if len(args) == 3:
        guild, before, after = args[0], args[1], args[2]
    elif len(args) >= 4:
        guild, before, after = args[1], args[2], args[3]
    else:
        guild = kwargs.get("guild")
        before = kwargs.get("before", [])
        after = kwargs.get("after", [])

    if not guild:
        return
    try:
        before_set = {getattr(e, "id", i): e for i, e in enumerate(before or [])}
        after_set = {getattr(e, "id", i): e for i, e in enumerate(after or [])}

        added = [e for eid, e in after_set.items() if eid not in before_set]
        removed = [e for eid, e in before_set.items() if eid not in after_set]

        if not added and not removed:
            return

        action = getattr(discord.AuditLogAction, "emoji_create", None) if added else getattr(discord.AuditLogAction, "emoji_delete", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(guild, action)

        fields = []
        if added:
            added_names = ", ".join([f"`:{getattr(e, 'name', 'emoji')}:`" for e in added[:10]])
            fields.append({"name": f"Added Emojis ({len(added)})", "value": added_names, "inline": False})
        if removed:
            removed_names = ", ".join([f"`:{getattr(e, 'name', 'emoji')}:`" for e in removed[:10]])
            fields.append({"name": f"Removed Emojis ({len(removed)})", "value": removed_names, "inline": False})

        title = "Server Emojis Updated"
        desc = f"Emojis on **{guild.name}** were updated."

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title=title,
            description=desc,
            actor=actor,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:emojis_update] Failed to dispatch emoji update log: {err}")


class EmojisUpdateLoggingEvent(Event):
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


event = EmojisUpdateLoggingEvent
