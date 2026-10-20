from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
from sdk.discord.response import send_response
from shared.types.command_record import CommandType

name = "server"
aliases = ["serverinfo", "guildinfo", "guild"]
description = "Display detailed statistics and information about the server."
category = "General"
usage = "server"
cooldown = 5.0
guild_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)

    if not guild:
        err = get_string("permissions.guild_only", "❌ This command can only be used inside a Discord server.")
        return await send_response(message, err, ephemeral=True)

    created_sec = int(guild.created_at.timestamp()) if hasattr(guild, "created_at") else 0
    members = getattr(guild, "member_count", None) or len(guild.members) if hasattr(guild, "members") else 1
    roles_count = len(guild.roles) if hasattr(guild, "roles") else 1

    text_channels = 0
    voice_channels = 0
    if hasattr(guild, "channels"):
        for ch in guild.channels:
            if isinstance(ch, discord.TextChannel):
                text_channels += 1
            elif isinstance(ch, discord.VoiceChannel):
                voice_channels += 1

    boost_level = getattr(guild, "premium_tier", 0)
    boost_count = getattr(guild, "premium_subscription_count", 0) or 0
    desc = getattr(guild, "description", None) or f"Welcome to **{guild.name}**!"

    view = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#3B82F6"))
        .add_text_display(f"### 🌐 Server Information: {guild.name}")
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"**General**\n"
            f"• **Server ID:** `{guild.id}`\n"
            f"• **Owner:** <@{guild.owner_id}>\n"
            f"• **Created:** <t:{created_sec}:F> (<t:{created_sec}:R>)\n"
            f"• **Verification Level:** `{str(guild.verification_level).title()}`"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"**Members & Channels**\n"
            f"• **Total Members:** `{members:,}`\n"
            f"• **Roles:** `{roles_count}`\n"
            f"• **Text Channels:** `{text_channels}` • **Voice Channels:** `{voice_channels}`"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"**Server Boost Status**\n"
            f"• **Boost Level:** `Tier {boost_level}`\n"
            f"• **Total Boosts:** `{boost_count}`"
        )
        .set_footer(f"{guild.name} • Server Overview")
        .build()
    )

    return await send_response(message, view)
