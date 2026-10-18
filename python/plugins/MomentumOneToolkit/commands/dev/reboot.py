import sys
from typing import List, Any
from config.settings import settings
from config.strings import get_string
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "reboot"
aliases = ["restart"]
description = "Reboot the MomentumOne bot process."
category = "Dev"
usage = "reboot"
cooldown = 10.0
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

    msg = get_string("commands.dev.reboot_scheduled", "🔄 System reboot initiated...")
    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)

    client = getattr(ctx, "client", getattr(message, "client", None))
    if client:
        await client.close()
