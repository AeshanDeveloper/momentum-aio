from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_role_create"
description = "Dedicated logging listener for role creation"
category = "logging"

async def execute(ctx: Any, role: discord.Role) -> None:
    guild = getattr(role, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.role_create, target_id=role.id
        )

        hex_color = str(role.color) if role.color.value != 0 else "Default"
        fields = [
            {"name": "Role Name", "value": f"{role.mention} (`@{role.name}` • ID: `{role.id}`)", "inline": False},
            {"name": "Color", "value": f"`{hex_color}`", "inline": True},
            {"name": "Hoisted", "value": f"`{role.hoist}`", "inline": True},
            {"name": "Mentionable", "value": f"`{role.mentionable}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Created",
            description=f"A new role {role.mention} was created.",
            actor=actor,
            target=role,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:role_create] Failed to dispatch role creation log: {err}")
