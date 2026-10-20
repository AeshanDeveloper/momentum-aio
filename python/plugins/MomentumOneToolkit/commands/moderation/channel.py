from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
from sdk.discord.response import send_response
from apps.bot.discord.permissions.permission import Permissions
from shared.types.command_record import CommandType

name = "channel"
aliases = ["ch", "channelctl"]
description = "Manage channel state (lock, unlock, or view metrics)."
category = "Moderation"
usage = "channel <lock|unlock|info> [#channel]"
cooldown = 3.0
user_permissions = [Permissions.MANAGE_CHANNELS]
bot_permissions = [Permissions.MANAGE_CHANNELS]
guild_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        err = get_string("permissions.guild_only", "❌ This command can only be used inside a Discord server.")
        return await send_response(message, err, ephemeral=True)

    sub = args[0].lower() if args else "info"
    target_channel = message.channel_mentions[0] if (getattr(message, "channel_mentions", None) and len(message.channel_mentions) > 0) else message.channel

    if sub == "lock":
        try:
            await target_channel.set_permissions(guild.default_role, send_messages=False)
            msg = get_string("commands.channel.locked", "🔒 Channel <#{channel_id}> has been locked.", channel_id=target_channel.id)
            view = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("warn", "#F59E0B"))
                .add_text_display(f"### 🔒 Channel Locked")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(msg)
                .build()
            )
            return await send_response(message, view)
        except Exception as err:
            return await send_response(message, f"❌ Failed to lock channel: {err}", ephemeral=True)

    elif sub == "unlock":
        try:
            await target_channel.set_permissions(guild.default_role, send_messages=True)
            msg = get_string("commands.channel.unlocked", "🔓 Channel <#{channel_id}> has been unlocked.", channel_id=target_channel.id)
            view = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#10B981"))
                .add_text_display(f"### 🔓 Channel Unlocked")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(msg)
                .build()
            )
            return await send_response(message, view)
        except Exception as err:
            return await send_response(message, f"❌ Failed to unlock channel: {err}", ephemeral=True)

    else:
        # Info
        title = get_string("commands.channel.info_title", "Channel Metrics: #{name}", name=target_channel.name)
        id_str = get_string("commands.channel.id", "• **Channel ID:** `{channel_id}`", channel_id=target_channel.id)
        type_str = get_string("commands.channel.type", "• **Type:** `{channel_type}`", channel_type=str(target_channel.type))
        created_ts = int(target_channel.created_at.timestamp()) if hasattr(target_channel, "created_at") else 0
        created_str = get_string("commands.channel.created", "• **Created:** <t:{timestamp}:R>", timestamp=created_ts)

        view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#3B82F6"))
            .add_text_display(f"### 📊 {title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{id_str}\n{type_str}\n{created_str}")
            .set_footer(f"Guild: {guild.name}")
            .build()
        )
        return await send_response(message, view)
