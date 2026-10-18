from typing import List, Any
import discord
from config.settings import settings
from config.strings import get_string
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "botprofile"
aliases = ["setpresence", "setactivity"]
description = "Update bot status and playing presence."
category = "Dev"
usage = "botprofile <status_text>"
cooldown = 3.0
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

    text = " ".join(args).strip() or "MomentumOne Control Platform"
    client = getattr(ctx, "client", getattr(message, "client", None))
    if client:
        await client.change_presence(activity=discord.Game(name=text))

    msg = get_string("commands.dev.botprofile_updated", "✅ Bot presence and profile updated successfully.")
    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)
