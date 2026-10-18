from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType

name = "server"
aliases = ["serverinfo", "guildinfo", "guild"]
description = "Display server metrics, channel statistics, and role allocation."
category = "General"
usage = "server"
cooldown = 5.0
guild_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)

    if not guild:
        err = get_string("permissions.guild_only", "❌ This command can only be used inside a Discord server.")
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    title = get_string("commands.server.title", "Server Overview: {name}", name=guild.name)
    id_str = get_string("commands.server.id", "• **Server ID:** `{server_id}`", server_id=guild.id)
    owner_str = get_string("commands.server.owner", "• **Server Owner:** <@{owner_id}>", owner_id=guild.owner_id or "Unknown")
    members_str = get_string("commands.server.members", "• **Members:** `{member_count}` total", member_count=guild.member_count or len(guild.members))
    channels_str = get_string("commands.server.channels", "• **Channels:** `{channel_count}` text/voice", channel_count=len(guild.channels))
    roles_str = get_string("commands.server.roles", "• **Roles:** `{role_count}` configured", role_count=len(guild.roles))

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### 🌐 {title}")
        .add_separator()
        .add_text_display(f"{id_str}\n{owner_str}\n{members_str}\n{channels_str}\n{roles_str}")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
    elif hasattr(message, "channel"):
        await message.channel.send(embed=embed)
