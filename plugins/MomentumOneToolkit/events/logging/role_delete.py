from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_role_delete"
description = "Dedicated logging listener for role deletion"
category = "logging"

async def execute(*args, **kwargs) -> None:
    role = args[-1] if args else kwargs.get("role")
    guild = getattr(role, "guild", None) if role else None
    if not guild or not role:
        return
    try:
        audit_action = getattr(discord.AuditLogAction, "role_delete", None)
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, audit_action, target_id=role.id
        )

        fields = [
            {"name": "Deleted Role", "value": f"`@{role.name}` (ID: `{role.id}`)", "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Deleted",
            description=f"Role **@{role.name}** was deleted from the server.",
            actor=actor,
            target=f"`@{role.name}` (`{role.id}`)",
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:role_delete] Failed to dispatch role deletion log: {err}")


class RoleDeleteLoggingEvent(Event):
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


event = RoleDeleteLoggingEvent
