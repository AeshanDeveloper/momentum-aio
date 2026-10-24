from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_update"
description = "Dedicated logging listener for member profile and role changes"
category = "logging"

async def execute(ctx: Any, before: discord.Member, after: discord.Member) -> None:
    guild = getattr(after, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.member_role_update, target_id=after.id
        )

        changes = []
        # Nickname update
        if before.nick != after.nick:
            b_nick = before.nick or before.name
            a_nick = after.nick or after.name
            changes.append(f"• **Nickname:** `{b_nick}` ➔ `{a_nick}`")

        # Roles added / removed
        before_roles = set(before.roles)
        after_roles = set(after.roles)
        added_roles = [r for r in after_roles - before_roles if r != guild.default_role]
        removed_roles = [r for r in before_roles - after_roles if r != guild.default_role]

        if added_roles:
            added_str = ", ".join([r.mention for r in added_roles])
            changes.append(f"• **Roles Added:** {added_str}")
        if removed_roles:
            removed_str = ", ".join([r.mention for r in removed_roles])
            changes.append(f"• **Roles Removed:** {removed_str}")

        # Timeout check
        b_timeout = getattr(before, "timed_out_until", None)
        a_timeout = getattr(after, "timed_out_until", None)
        if b_timeout != a_timeout:
            if a_timeout:
                changes.append(f"• **Timed Out Until:** <t:{int(a_timeout.timestamp())}:F>")
            else:
                changes.append(f"• **Timeout Cleared**")

        if not changes:
            return

        is_role_or_timeout = bool(added_roles or removed_roles or (b_timeout != a_timeout))
        cat = LogCategory.MODERATION if is_role_or_timeout else LogCategory.MEMBERS
        sev = LogSeverity.MEDIUM if is_role_or_timeout else LogSeverity.INFO

        fields = [
            {"name": "Member", "value": f"{after.mention} (`{after}` • ID: `{after.id}`)", "inline": False},
            {"name": "Modifications", "value": "\n".join(changes), "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=cat,
            title="Member Profile / Role Update",
            description=f"Member details for {after.mention} were updated.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=sev,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_update] Failed to dispatch member update log: {err}")
