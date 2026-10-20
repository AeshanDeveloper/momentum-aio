import time
from typing import List, Any
import discord
from discord import ButtonStyle
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response
from database.database import database
from shared.types.command_record import CommandType

name = "notifications"
aliases = ["notifs", "dmnotifs", "notify"]
description = "Configure your DM delivery preferences for transactions and system alerts."
category = "General"
usage = "notifications [enable|disable|toggle]"
cooldown = 3.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""

    col = database.collection("user_notification_prefs")
    pref = await col.find_one({"userId": author_id})
    current_status = pref.get("dmsEnabled", True) if pref else True

    sub = args[0].lower() if args else ""
    updated = False
    if sub in ["enable", "on", "true"]:
        current_status = True
        updated = True
    elif sub in ["disable", "off", "false"]:
        current_status = False
        updated = True
    elif sub == "toggle":
        current_status = not current_status
        updated = True

    if updated:
        await col.update_one(
            {"userId": author_id},
            {"$set": {"userId": author_id, "dmsEnabled": current_status, "updatedAt": time.time()}},
            upsert=True
        )

    def render_view(status: bool):
        status_icon = "🟢" if status else "🔴"
        status_text = "Enabled" if status else "Disabled"
        color = COLORS.get("success", "#10B981") if status else COLORS.get("default", "#FF7B00")

        container = (
            ContainerBuilder()
            .set_accent_color(color)
            .add_text_display(f"### 🔔 Direct Message Notification Preferences")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"• **DM Delivery Status:** {status_icon} `{status_text}`\n\n"
                + (
                    "You will receive direct messages when tickets, automated actions, and staff updates are processed."
                    if status
                    else "Direct message alerts are muted. You will not receive private messages from the bot."
                )
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        )

        row = ActionRowBuilder()
        toggle_btn = (
            ButtonBuilder()
            .set_custom_id(f"notif_toggle_{author_id}")
            .set_label("Disable DMs" if status else "Enable DMs")
            .set_style(ButtonStyle.danger if status else ButtonStyle.success)
            .set_emoji("🔕" if status else "🔔")
        )
        row.add_button(toggle_btn)
        container.add_action_row(row)
        return container.build()

    view = render_view(current_status)
    reply_msg = await send_response(message, view)

    collector = view.create_message_component_collector(
        target_message=reply_msg or message,
        timeout=180.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == (author.id if author else None),
    )

    if collector:
        async def on_toggle(inter: discord.Interaction):
            nonlocal current_status
            current_status = not current_status
            await col.update_one(
                {"userId": author_id},
                {"$set": {"userId": author_id, "dmsEnabled": current_status, "updatedAt": time.time()}},
                upsert=True
            )
            new_view = render_view(current_status)
            if hasattr(inter, "response"):
                await inter.response.edit_message(view=new_view.view)

        collector.on(f"notif_toggle_{author_id}", on_toggle)

