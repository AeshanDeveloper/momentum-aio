"""
Sentinel™ Moderation Command: Kick.
Components V2 interactive confirmation, role hierarchy enforcement, and rate-limit safe execution.
"""

from __future__ import annotations

import re
import time
from typing import List, Any, Optional

import discord

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response, send_ui
from apps.bot.discord.permissions.permission import Permissions
from core.security.rate_limiter import sentinel_rate_limiter
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from shared.types.command_record import CommandType

name = "kick"
aliases = ["boot"]
description = "Kick a member from the server with hierarchy validation and interactive confirmation."
category = "Moderation"
usage = "kick <@user|user_id> [reason]"
cooldown = 3.0
user_permissions = [Permissions.KICK_MEMBERS]
bot_permissions = [Permissions.KICK_MEMBERS]
guild_only = True


def _resolve_target_user(guild: discord.Guild, args: List[str], message: Any) -> Optional[Any]:
    if getattr(message, "mentions", None) and len(message.mentions) > 0:
        return message.mentions[0]

    for arg in args:
        m = re.match(r"^<@!?(\d{17,20})>$", arg)
        if m:
            uid = int(m.group(1))
            return guild.get_member(uid)
        if re.match(r"^\d{17,20}$", arg):
            uid = int(arg)
            return guild.get_member(uid)

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
            .add_text_display("### " + get_emoji("error", "🚨") + " Invalid Kick Syntax")
            .add_text_display("Please specify a user to kick.\n\n*Usage:* `$kick <@user|user_id> [reason]`")
            .build()
        )
        return await send_response(message, err_box, ephemeral=True)

    target = _resolve_target_user(guild, args, message)
    if not target:
        err_box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Member Not Found")
            .add_text_display(f"Could not locate an active server member matching `{args[0]}`.")
            .build()
        )
        return await send_response(message, err_box, ephemeral=True)

    # Extract reason
    reason_args = [a for a in args[1:] if not re.match(r"^(?:<@!?)?\d{17,20}>?$", a)]
    reason = " ".join(reason_args).strip() or "No reason specified"

    # Hierarchy validation
    if target.id == guild.owner_id:
        box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Cannot Kick Server Owner")
            .add_text_display("The server owner cannot be kicked.")
            .build()
        )
        return await send_response(message, box, ephemeral=True)

    if bot_member and target.top_role >= bot_member.top_role:
        box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Role Hierarchy Restriction")
            .add_text_display(f"Cannot kick `{target.name}`: their role is equal to or higher than Sentinel's role.")
            .build()
        )
        return await send_response(message, box, ephemeral=True)

    if author and author.id != guild.owner_id and hasattr(author, "top_role") and target.top_role >= author.top_role:
        box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Insufficient Hierarchy")
            .add_text_display(f"You cannot kick `{target.name}` because their role is higher than or equal to yours.")
            .build()
        )
        return await send_response(message, box, ephemeral=True)

    confirm_custom_id = f"mod_confirm:kick:{guild.id}:{target.id}:{int(time.time())}"
    cancel_custom_id = f"mod_cancel:kick:{guild.id}:{target.id}:{int(time.time())}"

    confirm_box = (
        ContainerBuilder()
        .set_accent_color(get_color("warning", "#F59E0B"))
        .add_text_display(f"### {get_emoji('warn', '⚠️')} Confirm Moderation Kick")
        .add_separator(spacing=SeparatorSpacingSize.SMALL)
        .add_text_display(
            f"Are you sure you want to kick **{target.name}** (`{target.id}`)?\n\n"
            f"**Reason:** {reason}\n"
            f"**Moderator:** {author.mention if author else 'Admin'}"
        )
        .add_action_row(
            ActionRowBuilder()
            .add_button(
                ButtonBuilder()
                .set_label("Confirm Kick")
                .set_style(ButtonStyle.DANGER)
                .set_custom_id(confirm_custom_id)
                .set_emoji(get_emoji("boot", "👢"))
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
