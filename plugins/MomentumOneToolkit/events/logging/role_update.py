from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_role_update"
description = "Dedicated logging listener for role updates"
category = "logging"

async def execute(ctx: Any, before: discord.Role, after: discord.Role) -> None:
    guild = getattr(after, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.role_update, target_id=after.id
        )

        changes = []
        if before.name != after.name:
            changes.append(f"• **Name:** `@{before.name}` ➔ `@{after.name}`")
        if before.color != after.color:
            changes.append(f"• **Color:** `{before.color}` ➔ `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"• **Hoisted:** `{before.hoist}` ➔ `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"• **Mentionable:** `{before.mentionable}` ➔ `{after.mentionable}`")

        # Compare permissions
        if before.permissions != after.permissions:
            b_perms = {p for p, val in before.permissions if val}
            a_perms = {p for p, val in after.permissions if val}
            added = a_perms - b_perms
            removed = b_perms - a_perms
            if added:
                changes.append(f"• **Permissions Granted:** {', '.join([f'`{p}`' for p in added])}")
            if removed:
                changes.append(f"• **Permissions Revoked:** {', '.join([f'`{p}`' for p in removed])}")

        if not changes:
            return

        has_perm_changes = before.permissions != after.permissions
        sev = LogSeverity.HIGH if has_perm_changes else LogSeverity.LOW

        fields = [
            {"name": "Role", "value": f"{after.mention} (`@{after.name}` • ID: `{after.id}`)", "inline": False},
            {"name": "Modifications", "value": "\n".join(changes), "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Updated",
            description=f"Role {after.mention} was modified.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=sev,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:role_update] Failed to dispatch role update log: {err}")
