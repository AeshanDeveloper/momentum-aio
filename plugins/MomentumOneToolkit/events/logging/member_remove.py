from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_remove"
description = "Dedicated logging listener for member remove / leave / kick"
category = "logging"

async def execute(ctx: Any, member: discord.Member) -> None:
    guild = getattr(member, "guild", None)
    if not guild:
        return
    try:
        # Check if this was a kick via audit log
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.kick, target_id=member.id
        )

        is_kick = actor is not None
        title = "Member Kicked" if is_kick else "Member Left"
        severity = LogSeverity.HIGH if is_kick else LogSeverity.INFO
        desc = (
            f"Member {member.mention} (**{member}**) was kicked from the server."
            if is_kick
            else f"Member **{member}** left the server."
        )

        fields = [
            {"name": "User ID", "value": f"`{member.id}`", "inline": True},
            {"name": "Remaining Members", "value": f"`{guild.member_count}`", "inline": True},
        ]
        if is_kick:
            fields.append({"name": "Moderation Action", "value": "`KICK`", "inline": True})

        category_dest = LogCategory.MODERATION if is_kick else LogCategory.MEMBERS

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=category_dest,
            title=title,
            description=desc,
            actor=actor or member,
            target=member,
            reason=reason,
            fields=fields,
            severity=severity,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_remove] Failed to dispatch member remove log: {err}")
