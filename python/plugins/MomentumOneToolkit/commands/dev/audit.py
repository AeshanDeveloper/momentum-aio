from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from core.audit.audit_log import AuditLog
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "audit"
aliases = ["auditlogs", "logs"]
description = "View centralized administrative audit trail."
category = "Dev"
usage = "audit [limit]"
cooldown = 2.0
owner_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)

    if not is_bot_owner(author.id):
        err = get_string("permissions.owner_only", "❌ Access Denied: This command is strictly reserved for the global bot owner.")
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    limit = 10
    if args and args[0].isdigit():
        limit = min(25, max(1, int(args[0])))

    entries = await AuditLog.list(skip=0, limit=limit)
    title = get_string("commands.dev.audit_title", "📜 System Audit Trail (Last {count} Entries)", count=len(entries))

    lines = []
    for e in entries:
        ts = int(e.get("timestamp", 0))
        lines.append(f"• <t:{ts}:T> **{e.get('action')}** [{e.get('resource_type')}] by <@{e.get('actor_id')}>")

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display("\n".join(lines) if lines else "No audit entries recorded.")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
