from typing import Any
import discord
from sdk.event import Event
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from core.logging.logger import logger

name = "on_member_join"
description = "Dedicated logging listener for member join"
category = "logging"

async def execute(*args, **kwargs) -> None:
    member = args[-1] if args else kwargs.get("member")
    guild = getattr(member, "guild", None) if member else None
    if not guild or not member:
        return
    try:
        created_at_str = member.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if getattr(member, "created_at", None) else "Unknown"
        m_count = getattr(guild, "member_count", "N/A")
        is_bot = getattr(member, "bot", False)

        fields = [
            {"name": "Account Created", "value": f"`{created_at_str}`", "inline": True},
            {"name": "Member Count", "value": f"`{m_count}`", "inline": True},
            {"name": "Is Bot", "value": f"`{is_bot}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MEMBERS,
            title="Member Joined",
            description=f"{getattr(member, 'mention', str(member))} (**{member}**) joined the server.",
            actor=member,
            target=member,
            fields=fields,
            severity=LogSeverity.INFO,
        )
    except Exception as err:
        logger.error(f"[LoggingEvent:member_join] Failed to dispatch member join log: {err}")


class MemberJoinLoggingEvent(Event):
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


event = MemberJoinLoggingEvent
