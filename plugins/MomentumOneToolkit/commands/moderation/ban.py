"""
Sentinel™ Moderation Command: Ban.
Components V2 interactive confirmation, role hierarchy enforcement, and rate-limit safe execution.
"""

from __future__ import annotations

import re
import time
from typing import List, Any, Optional

import discord

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
from config.strings import get_string
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response, send_ui
from apps.bot.discord.permissions.permission import Permissions
from apps.bot.discord.permissions.resolver import has_permission
from core.security.rate_limiter import sentinel_rate_limiter
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from shared.types.command_record import CommandType

name = "ban"
aliases = ["hackban", "forceban"]
description = "Ban a member from the server with hierarchy validation and interactive confirmation."
category = "Moderation"
usage = "ban <@user|user_id> [reason]"
cooldown = 3.0
user_permissions = [Permissions.BAN_MEMBERS]
bot_permissions = [Permissions.BAN_MEMBERS]
guild_only = True


def _resolve_target_user(guild: discord.Guild, args: List[str], message: Any) -> Optional[Any]:
    if getattr(message, "mentions", None) and len(message.mentions) > 0:
        return message.mentions[0]

    for arg in args:
        m = re.match(r"^<@!?(\d{17,20})>$", arg)
        if m:
            uid = int(m.group(1))
            member = guild.get_member(uid)
            return member

        if re.match(r"^\d{17,20}$", arg):
            uid = int(arg)
            member = guild.get_member(uid)
            return member

    return None


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if str(command_type).lower() == "slash" else getattr(message, "author", None)
    bot_member = getattr(guild, "me", None)

    if not args:
        err_box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Invalid Ban Syntax")
            .add_text_display("Please specify a user to ban.\n\n*Usage:* `$ban <@user|user_id> [reason]`")
            .build()
        )
        return await send_response(message, err_box, ephemeral=True)

    target = _resolve_target_user(guild, args, message)
    raw_target_id = None
    m_id = re.match(r"^(?:<@!?)?(\d{17,20})>?$", args[0])
    if m_id:
        raw_target_id = int(m_id.group(1))

    if not target and not raw_target_id:
        err_box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " User Not Found")
            .add_text_display(f"Could not locate a user matching `{args[0]}`.")
            .build()
        )
        return await send_response(message, err_box, ephemeral=True)

    target_id = target.id if target else raw_target_id
    target_name = target.name if target else f"User {target_id}"

    # Extract reason
    reason_args = [a for a in args[1:] if not re.match(r"^(?:<@!?)?\d{17,20}>?$", a)]
    reason = " ".join(reason_args).strip() or "No reason specified"

    # Hierarchy validation
    if target and isinstance(target, discord.Member):
        if target.id == guild.owner_id:
            box = (
                ContainerBuilder()
                .set_accent_color(get_color("error", "#B21F1F"))
                .add_text_display("### " + get_emoji("error", "🚨") + " Cannot Ban Server Owner")
                .add_text_display("The server owner cannot be banned.")
                .build()
            )
            return await send_response(message, box, ephemeral=True)

        if bot_member and target.top_role >= bot_member.top_role:
            box = (
                ContainerBuilder()
                .set_accent_color(get_color("error", "#B21F1F"))
                .add_text_display("### " + get_emoji("error", "🚨") + " Role Hierarchy Restriction")
                .add_text_display(f"Cannot ban `{target_name}`: their highest role is equal to or higher than Sentinel's role.")
                .build()
            )
            return await send_response(message, box, ephemeral=True)

        if author and author.id != guild.owner_id and hasattr(author, "top_role") and target.top_role >= author.top_role:
            box = (
                ContainerBuilder()
                .set_accent_color(get_color("error", "#B21F1F"))
                .add_text_display("### " + get_emoji("error", "🚨") + " Insufficient Hierarchy")
                .add_text_display(f"You cannot ban `{target_name}` because their role is higher than or equal to yours.")
                .build()
            )
            return await send_response(message, box, ephemeral=True)

    # Components V2 Interactive Confirmation Dialogue
    confirm_custom_id = f"mod_confirm:ban:{guild.id}:{target_id}:{int(time.time())}"
    cancel_custom_id = f"mod_cancel:ban:{guild.id}:{target_id}:{int(time.time())}"

    confirm_box = (
        ContainerBuilder()
        .set_accent_color(get_color("warning", "#F59E0B"))
        .add_text_display(f"### {get_emoji('warn', '⚠️')} Confirm Moderation Ban")
        .add_separator(spacing=SeparatorSpacingSize.SMALL)
        .add_text_display(
            f"Are you sure you want to ban **{target_name}** (`{target_id}`)?\n\n"
            f"**Reason:** {reason}\n"
            f"**Moderator:** {author.mention if author else 'Admin'}"
        )
        .add_action_row(
            ActionRowBuilder()
            .add_button(
                ButtonBuilder()
                .set_label("Confirm Ban")
                .set_style(ButtonStyle.DANGER)
                .set_custom_id(confirm_custom_id)
                .set_emoji(get_emoji("hammer", "🔨"))
            )
            .add_button(
                ButtonBuilder()
                .set_label("Cancel")
                .set_style(ButtonStyle.SECONDARY)
                .set_custom_id(cancel_custom_id)
            )
        )
        .set_footer("Sentinel™ Enterprise Moderation Core")
        .build()
    )

    return await send_response(message, confirm_box)
