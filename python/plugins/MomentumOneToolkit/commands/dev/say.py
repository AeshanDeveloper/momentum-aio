from typing import List, Any
import discord
from config.settings import settings
from config.strings import get_string
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "say"
aliases = ["echo"]
description = "Dispatch a message to a specific channel."
category = "Dev"
usage = "say [#channel] <text>"
cooldown = 1.0
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

    if not args:
        return

    target_channel = message.channel
    content_words = args
    if getattr(message, "channel_mentions", None) and len(message.channel_mentions) > 0:
        target_channel = message.channel_mentions[0]
        content_words = args[1:]

    text = " ".join(content_words).strip()
    if text:
        await target_channel.send(text)
        confirm = get_string("commands.dev.say_sent", "💬 Message dispatched to <#{channel_id}>.", channel_id=target_channel.id)
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(confirm, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(confirm)
