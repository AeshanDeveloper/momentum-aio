import sys
import asyncio
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize
)
from sdk.discord.response import send_response, send_ui
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

    owner_ids = settings.OWNER_IDS
    bot_name = settings.BOT_NAME

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        return await send_ui(message, "permissions.owner_only", style="error")

    reload_emoji = EMOJIS.get("reload") or EMOJIS.get("refresh") or "🔄"
    dot_emoji = EMOJIS.get("info") or "•"
    accent_color = COLORS.get("cmd_reboot") or COLORS.get("default") or "#0844C5"

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
    reply_msg = await send_response(message, built)

    target_msg = reply_msg or message
    collector = built.create_message_component_collector(
        target_message=target_msg,
        timeout=600.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == getattr(author, "id", None),
    )

    if collector:
        async def on_cancel(inter):
            if hasattr(inter, "response"):
                await inter.response.edit_message(content="Reboot cancelled.", view=None)

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
                await inter.response.edit_message(view=restarting_container)

            if client:
                await client.close()

        collector.on(cancel_id, on_cancel)
        collector.on(confirm_id, on_confirm)

