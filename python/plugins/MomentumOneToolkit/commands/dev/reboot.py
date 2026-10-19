import sys
import asyncio
from typing import List, Dict, Any, Optional
import discord

from config.settings import COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize
)
from discord import MessageFlags, ButtonStyle

name = "reboot"
aliases = ["shutdown", "restart", "reloadbot"]
category = "Owner"
description = "Restarts the bot process."
owner_only = True

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""
    client = getattr(ctx, "client", getattr(message, "client", None))

    bot_cfg = getattr(config, "settings", {}).get("bot", {}) if isinstance(getattr(config, "settings", {}), dict) else {}
    owner_ids = [str(o) for o in (bot_cfg.get("owner_ids") or [getattr(config, "OWNER_ID", "")])]
    bot_name = bot_cfg.get("name", "MomentumOne")

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_msg = "❌ **Access Denied**: This command is restricted to the bot owner."
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(denied_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(denied_msg)
        return

    reload_emoji = EMOJIS.get("reload") or EMOJIS.get("reboot") or EMOJIS.get("loading") or "🔄"
    dot_emoji = EMOJIS.get("dot") or EMOJIS.get("info") or "•"
    accent_color = COLORS.get("cmd_reboot") or COLORS.get("default") or "#3B82F6"

    confirm_id = f"reboot_confirm_{id(message)}"
    cancel_id = f"reboot_cancel_{id(message)}"

    container = (
        ContainerBuilder()
        .add_text_display(f"### {reload_emoji} Restart {bot_name}?")
        .add_separator(divider=True)
        .add_text_display(f"{dot_emoji} This will restart the bot process.")
        .add_separator(divider=True)
        .add_text_display(f"-# {bot_name} • Reboot")
        .set_accent_color(accent_color)
    )

    action_row = ActionRowBuilder()
    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(confirm_id)
        .set_label("Confirm Reboot")
        .set_style(ButtonStyle.Danger)
    )
    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(cancel_id)
        .set_label("Cancel")
        .set_style(ButtonStyle.Secondary)
    )
    container.add_action_row(action_row)

    built = container.build()
    reply_msg = None
    if is_slash and hasattr(message, "response") and not message.response.is_done():
        reply_msg = await message.response.send_message(embed=built.embed, view=built.view)
    elif hasattr(message, "reply"):
        reply_msg = await message.reply(embed=built.embed, view=built.view)

    target_msg = reply_msg or message
    collector = built.create_message_component_collector(
        target_message=target_msg,
        timeout=600.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == getattr(author, "id", None),
    )

    if collector:
        async def on_cancel(inter):
            if hasattr(inter, "response"):
                await inter.response.edit_message(content="Reboot cancelled.", embed=None, view=None)

        async def on_confirm(inter):
            restarting_container = (
                ContainerBuilder()
                .add_text_display(f"### {reload_emoji} Restarting {bot_name}...")
                .add_separator(divider=True)
                .add_text_display(f"{dot_emoji} Hold on, rebooting the bot...")
                .add_separator(divider=True)
                .add_text_display(f"-# {bot_name} • Reboot")
                .set_accent_color(accent_color)
                .build()
            )
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=restarting_container.embed, view=None)

            if client:
                await client.close()

        collector.on(cancel_id, on_cancel)
        collector.on(confirm_id, on_confirm)
