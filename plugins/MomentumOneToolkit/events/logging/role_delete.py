from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_guild_role_delete"
description = "Dedicated logging listener for role deletion"
category = "logging"

async def execute(ctx: Any, role: discord.Role) -> None:
    guild = getattr(role, "guild", None)
    if not guild:
        return
    try:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.role_delete, target_id=role.id
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
