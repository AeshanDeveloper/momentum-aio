from typing import Any, List
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_emojis_update"
description = "Dedicated logging listener for emoji updates"
category = "logging"

async def execute(ctx: Any, guild: discord.Guild, before: List[discord.Emoji], after: List[discord.Emoji]) -> None:
    if not guild:
        return
    try:
        before_set = {e.id: e for e in before}
        after_set = {e.id: e for e in after}

        added = [e for eid, e in after_set.items() if eid not in before_set]
        removed = [e for eid, e in before_set.items() if eid not in after_set]

        if not added and not removed:
            return

        action = discord.AuditLogAction.emoji_create if added else discord.AuditLogAction.emoji_delete
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(guild, action)

        fields = []
        if added:
            added_names = ", ".join([f"`:{e.name}:`" for e in added[:10]])
            fields.append({"name": f"Added Emojis ({len(added)})", "value": added_names, "inline": False})
        if removed:
            removed_names = ", ".join([f"`:{e.name}:`" for e in removed[:10]])
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
