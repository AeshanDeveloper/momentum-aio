from typing import List, Any
import discord

from config.settings import settings, COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import ContainerBuilder
from sdk.discord.response import send_response

name = "say"
aliases = ["b", "echo"]
description = "Broadcast text into the channel (Bot Owner Only)."
category = "Owner"
usage = "say <text>"
owner_only = True

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""

    owner_ids = settings.OWNER_IDS

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_msg = "❌ **Access Denied**: This command is restricted to the bot owner."
        return await send_response(message, denied_msg, ephemeral=True)

    say_message = " ".join(args).strip()
    if not say_message:
        c = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#3B82F6"))
            .add_text_display("No text provided")
            .build()
        )
        return await send_response(message, c)

    # Delete invoking message if possible
    if not is_slash and hasattr(message, "delete"):
        try:
            await message.delete()
        except Exception:
            pass

    channel = getattr(message, "channel", None)
    if channel:
        await channel.send(say_message, allowed_mentions=discord.AllowedMentions(users=True))

    if is_slash and hasattr(message, "response") and not message.response.is_done():
        await message.response.send_message("Message sent.", ephemeral=True)
