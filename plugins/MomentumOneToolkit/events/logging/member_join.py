from typing import Any
import discord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_join"
description = "Dedicated logging listener for member join"
category = "logging"

async def execute(ctx: Any, member: discord.Member) -> None:
    guild = getattr(member, "guild", None)
    if not guild:
        return
    try:
        created_at_str = member.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if getattr(member, "created_at", None) else "Unknown"

        fields = [
            {"name": "Account Created", "value": f"`{created_at_str}`", "inline": True},
            {"name": "Member Count", "value": f"`{guild.member_count}`", "inline": True},
            {"name": "Is Bot", "value": f"`{member.bot}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MEMBERS,
            title="Member Joined",
            description=f"{member.mention} (**{member}**) joined the server.",
            actor=member,
            target=member,
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_join] Failed to dispatch member join log: {err}")
