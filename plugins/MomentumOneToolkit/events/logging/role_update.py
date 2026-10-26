from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_role_update"
description = "Dedicated logging listener for role updates"
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
        audit_action = getattr(discord.AuditLogAction, "role_update", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=after.id
        )

        changes = []
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"• **Name:** `@{before.name}` ➔ `@{after.name}`")
        if getattr(before, "color", None) != getattr(after, "color", None):
            changes.append(f"• **Color:** `{before.color}` ➔ `{after.color}`")
        if getattr(before, "hoist", False) != getattr(after, "hoist", False):
            changes.append(f"• **Hoisted:** `{before.hoist}` ➔ `{after.hoist}`")
        if getattr(before, "mentionable", False) != getattr(after, "mentionable", False):
            changes.append(f"• **Mentionable:** `{before.mentionable}` ➔ `{after.mentionable}`")

        # Compare permissions
        b_p = getattr(before, "permissions", None)
        a_p = getattr(after, "permissions", None)
        has_perm_changes = False
        if b_p != a_p and hasattr(b_p, "__iter__") and hasattr(a_p, "__iter__"):
            b_perms = {p for p, val in b_p if val}
            a_perms = {p for p, val in a_p if val}
            added = a_perms - b_perms
            removed = b_perms - a_perms
            if added:
                changes.append(f"• **Permissions Granted:** {', '.join([f'`{p}`' for p in added])}")
                has_perm_changes = True
            if removed:
                changes.append(f"• **Permissions Revoked:** {', '.join([f'`{p}`' for p in removed])}")
                has_perm_changes = True

        if not changes:
            return

        sev = LogSeverity.HIGH if has_perm_changes else LogSeverity.LOW
        role_mention = getattr(after, "mention", f"@{after.name}")
        fields = [
            {"name": "Role", "value": f"{role_mention} (`@{after.name}` • ID: `{after.id}`)", "inline": False},
            {"name": "Modifications", "value": "\n".join(changes), "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Updated",
            description=f"Role {role_mention} was modified.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=sev,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:role_update] Failed to dispatch role update log: {err}")


class RoleUpdateLoggingEvent(Event):
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


event = RoleUpdateLoggingEvent
