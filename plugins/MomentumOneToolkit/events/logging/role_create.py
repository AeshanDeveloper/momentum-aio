from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_role_create"
description = "Dedicated logging listener for role creation"
category = "logging"

async def execute(*args, **kwargs) -> None:
    role = args[-1] if args else kwargs.get("role")
    guild = getattr(role, "guild", None) if role else None
    if not guild or not role:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "role_create", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=role.id
        )

        role_color = getattr(role, "color", None)
        hex_color = str(role_color) if (role_color and getattr(role_color, "value", 0) != 0) else "Default"
        role_mention = getattr(role, "mention", f"@{role.name}")
        fields = [
            {"name": "Role Name", "value": f"{role_mention} (`@{role.name}` • ID: `{role.id}`)", "inline": False},
            {"name": "Color", "value": f"`{hex_color}`", "inline": True},
            {"name": "Hoisted", "value": f"`{getattr(role, 'hoist', False)}`", "inline": True},
            {"name": "Mentionable", "value": f"`{getattr(role, 'mentionable', False)}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Created",
            description=f"A new role {role_mention} was created.",
            actor=actor,
            target=role,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:role_create] Failed to dispatch role creation log: {err}")


class RoleCreateLoggingEvent(Event):
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


event = RoleCreateLoggingEvent
