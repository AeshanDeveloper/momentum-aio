import time
from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
    ComponentLayoutView,
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

def build_notification_view(author_id: str, status: bool) -> ComponentLayoutView:
    status_icon = EMOJIS.get("enabled") if status else EMOJIS.get("disabled")
    status_text = get_string("commands.notifications.enabled_label", default="Enabled") if status else get_string("commands.notifications.disabled_label", default="Disabled")
    color = COLORS.get("success", "#10B981") if status else COLORS.get("default", "#FF7B00")

    status_line = get_string(
        "commands.notifications.status_line",
        default="• **DM Delivery Status:** {status_icon} `{status_text}`",
        status_icon=status_icon,
        status_text=status_text,
    )
    desc_text = (
        get_string("commands.notifications.desc_enabled", default="You will receive direct messages when tickets, automated actions, and staff updates are processed.")
        if status
        else get_string("commands.notifications.desc_disabled", default="Direct message alerts are muted. You will not receive private messages from the bot.")
    )
    title = get_string("commands.notifications.title", default="Direct Message Notification Preferences")
    btn_label = (
        get_string("commands.notifications.btn_disable", default="Disable DMs")
        if status
        else get_string("commands.notifications.btn_enable", default="Enable DMs")
    )

    container = (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(f"### {title}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{status_line}\n\n{desc_text}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
    )

    row = ActionRowBuilder()
    toggle_btn = (
        ButtonBuilder()
        .set_custom_id(f"notif_toggle_{author_id}")
        .set_label(btn_label)
        .set_style(ButtonStyle.Danger if status else ButtonStyle.Success)
        .set_emoji(EMOJIS.get("bell_slash") if status else EMOJIS.get("bell"))
    )
    row.add_button(toggle_btn)
    container.add_action_row(row)
    return container.build()

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

    view = build_notification_view(author_id, current_status)
    reply_msg = await send_response(message, view)

    collector = view.create_message_component_collector(
        target_message=reply_msg or message,
        timeout=300.0,
        filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == (author.id if author else None),
    )

    if collector:
        async def on_toggle(inter: discord.Interaction):
            pref_doc = await col.find_one({"userId": author_id})
            latest_status = pref_doc.get("dmsEnabled", True) if pref_doc else True
            new_status = not latest_status
            await col.update_one(
                {"userId": author_id},
                {"$set": {"userId": author_id, "dmsEnabled": new_status, "updatedAt": time.time()}},
                upsert=True
            )
            new_view = build_notification_view(author_id, new_status)
            collector.update_view(new_view)
            if hasattr(inter, "response"):
                await inter.response.edit_message(view=new_view.view)

        collector.on(f"notif_toggle_{author_id}", on_toggle)
