from typing import List, Any
from config.settings import settings
from config.strings import get_string
from apps.bot.discord.permissions.resolver import is_bot_owner
from apps.bot.discord.commands.registry import commands_registry
from shared.types.command_record import CommandType

name = "reload"
aliases = ["refresh"]
description = "Reload commands and active plugins dynamically."
category = "Dev"
usage = "reload"
cooldown = 5.0
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

    # Trigger reload
    msg = get_string(
        "commands.dev.reload_success",
        "✅ Reloaded {commands_count} commands and {plugins_count} plugins.",
        commands_count=commands_registry.size(),
        plugins_count=1
    )
    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)
