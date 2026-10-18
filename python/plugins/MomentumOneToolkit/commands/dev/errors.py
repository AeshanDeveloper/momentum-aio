from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from core.logging.error_tracker import ErrorTracker
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "errors"
aliases = ["err", "errortracker"]
description = "Inspect recent unhandled command errors and exception telemetry."
category = "Dev"
usage = "errors [clear|<error_id>]"
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

    sub = args[0].lower() if args else None
    if sub == "clear":
        cleared = await ErrorTracker.clear()
        msg = f"✅ Cleared `{cleared}` error record(s) from ErrorTracker."
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(msg)
        elif hasattr(message, "reply"):
            await message.reply(msg)
        return

    if sub and sub.startswith("err-"):
        rec = await ErrorTracker.get(sub)
        if rec:
            embed = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("error", "#B21F1F"))
                .add_text_display(f"### ⚠️ Error Record `{rec.get('error_id')}`")
                .add_separator()
                .add_text_display(
                    f"• **Command:** `{rec.get('command_name')}`\n"
                    f"• **User:** <@{rec.get('user_id')}> ({rec.get('username')})\n"
                    f"• **Guild:** `{rec.get('guild_id')}`\n"
                    f"• **Summary:** `{rec.get('message')}`\n\n"
                    f"```\n{str(rec.get('stack', 'No stack trace available'))[:1000]}\n```"
                )
                .build()
            )
            if is_slash and hasattr(message, "response"):
                await message.response.send_message(embed=embed)
            elif hasattr(message, "reply"):
                await message.reply(embed=embed)
            return

    errors = await ErrorTracker.list(skip=0, limit=10)
    title = get_string("commands.dev.errors_title", "⚠️ Error Tracker Diagnostics")
    if not errors:
        msg = get_string("commands.dev.errors_empty", "✅ No recent unhandled command errors recorded.")
        embed = ContainerBuilder().set_accent_color(COLORS.get("success", "#3FD438")).add_text_display(f"### {title}").add_text_display(msg).build()
    else:
        lines = [f"• **`{e.get('error_id')}`** [{e.get('command_name')}]: {e.get('message', '')[:70]}" for e in errors]
        embed = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {title}")
            .add_separator()
            .add_text_display("\n".join(lines))
            .set_footer("Use 'errors <error_id>' for full stack details.")
            .build()
        )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
