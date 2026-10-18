from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from apps.bot.discord.permissions.permission import Permissions
from shared.types.command_record import CommandType

name = "announce"
aliases = ["broadcast"]
description = "Broadcast a stylized announcement to a designated channel."
category = "Moderation"
usage = "announce <#channel> <message>"
cooldown = 5.0
user_permissions = [Permissions.MANAGE_GUILD]
bot_permissions = [Permissions.SEND_MESSAGES, Permissions.EMBED_LINKS]
guild_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return

    target_channel = None
    if getattr(message, "channel_mentions", None) and len(message.channel_mentions) > 0:
        target_channel = message.channel_mentions[0]
        announcement_text = " ".join(args[1:]).strip()
    else:
        target_channel = message.channel
        announcement_text = " ".join(args).strip()

    if not announcement_text:
        err = "Please provide the announcement message content."
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    title = get_string("commands.announce.title", "📢 Server Announcement")
    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display(announcement_text)
        .set_footer(f"Announced by {message.author.name if hasattr(message, 'author') else message.user.name}")
        .build()
    )

    await target_channel.send(embed=embed)
    sent_msg = get_string("commands.announce.sent", "✅ Announcement successfully published to <#{channel_id}>.", channel_id=target_channel.id)

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(sent_msg, ephemeral=True)
    elif hasattr(message, "reply"):
        await message.reply(sent_msg)
