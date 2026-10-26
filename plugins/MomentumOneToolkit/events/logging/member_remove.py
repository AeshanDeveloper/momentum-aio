from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_remove"
description = "Dedicated logging listener for member remove / leave / kick"
category = "logging"

async def execute(*args, **kwargs) -> None:
    member = args[-1] if args else kwargs.get("member")
    guild = getattr(member, "guild", None) if member else None
    if not guild or not member:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "kick", getattr(discord.AuditLogAction, "member_kick", None))
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=member.id
        )

        is_kick = actor is not None
        title = "Member Kicked" if is_kick else "Member Left"
        severity = LogSeverity.HIGH if is_kick else LogSeverity.INFO
        m_tag = str(member)
        m_mention = getattr(member, "mention", m_tag)
        desc = (
            f"Member {m_mention} (**{m_tag}**) was kicked from the server."
            if is_kick
            else f"Member **{m_tag}** left the server."
        )

        m_count = getattr(guild, "member_count", "N/A")
        fields = [
            {"name": "User ID", "value": f"`{member.id}`", "inline": True},
            {"name": "Remaining Members", "value": f"`{m_count}`", "inline": True},
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


class MemberRemoveLoggingEvent(Event):
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


event = MemberRemoveLoggingEvent
