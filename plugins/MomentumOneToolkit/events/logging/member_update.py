from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_update"
description = "Dedicated logging listener for member profile and role changes"
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
    if not guild or not after or not before:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "member_role_update", getattr(discord.AuditLogAction, "member_update", None))
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=after.id
        )

        changes = []
        b_nick = getattr(before, "nick", None) or getattr(before, "name", "")
        a_nick = getattr(after, "nick", None) or getattr(after, "name", "")
        if b_nick != a_nick:
            changes.append(f"• **Nickname:** `{b_nick}` ➔ `{a_nick}`")

        before_roles = set(getattr(before, "roles", []))
        after_roles = set(getattr(after, "roles", []))
        default_role = getattr(guild, "default_role", None)
        added_roles = [r for r in after_roles - before_roles if r != default_role]
        removed_roles = [r for r in before_roles - after_roles if r != default_role]

        if added_roles:
            added_str = ", ".join([getattr(r, "mention", getattr(r, "name", str(r))) for r in added_roles])
            changes.append(f"• **Roles Added:** {added_str}")
        if removed_roles:
            removed_str = ", ".join([getattr(r, "mention", getattr(r, "name", str(r))) for r in removed_roles])
            changes.append(f"• **Roles Removed:** {removed_str}")

        b_timeout = getattr(before, "timed_out_until", None)
        a_timeout = getattr(after, "timed_out_until", None)
        if b_timeout != a_timeout:
            if a_timeout:
                changes.append(f"• **Timed Out Until:** <t:{int(a_timeout.timestamp())}:F>")
            else:
                changes.append("• **Timeout Cleared**")

        if not changes:
            return

        is_role_or_timeout = bool(added_roles or removed_roles or (b_timeout != a_timeout))
        cat = LogCategory.MODERATION if is_role_or_timeout else LogCategory.MEMBERS
        sev = LogSeverity.MEDIUM if is_role_or_timeout else LogSeverity.INFO

        m_tag = str(after)
        m_mention = getattr(after, "mention", m_tag)
        fields = [
            {"name": "Member", "value": f"{m_mention} (`{m_tag}` • ID: `{after.id}`)", "inline": False},
            {"name": "Modifications", "value": "\n".join(changes), "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=cat,
            title="Member Profile / Role Update",
            description=f"Member details for {m_mention} were updated.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=sev,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_update] Failed to dispatch member update log: {err}")


class MemberUpdateLoggingEvent(Event):
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


event = MemberUpdateLoggingEvent
