"""
Sentinel™ Moderation Command: Timeout & Mute.
Supports timeout durations up to 28 days (Discord API limit), unmute/untimeout, and rate-limit safe execution.
"""

from __future__ import annotations

import re
import time
import datetime
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

name = "timeout"
aliases = ["mute", "unmute", "untimeout"]
description = "Temporarily timeout or mute a member (up to 28 days), or remove an active timeout."
category = "Moderation"
usage = "timeout <@user|user_id> [duration: 5m, 1h, 1d, 7d, 28d, 0/unmute] [reason]"
cooldown = 3.0
user_permissions = [Permissions.MODERATE_MEMBERS]
bot_permissions = [Permissions.MODERATE_MEMBERS]
guild_only = True


def _parse_timeout_duration(raw_str: str) -> Optional[int]:
    """Parses duration string into seconds. Returns None if invalid. Max 28 days (2,419,200 seconds)."""
    s = raw_str.strip().lower()
    if s in ("0", "unmute", "untimeout", "remove", "off", "none"):
        return 0

    m = re.match(r"^(\d+)(s|m|h|d|w)?$", s)
    if not m:
        return None

    val = int(m.group(1))
    unit = m.group(2) or "m"

    if unit == "s":
        seconds = val
    elif unit == "m":
        seconds = val * 60
    elif unit == "h":
        seconds = val * 3600
    elif unit == "d":
        seconds = val * 86400
    elif unit == "w":
        seconds = val * 86400 * 7
    else:
        seconds = val * 60

    max_seconds = 28 * 86400  # Discord max: 28 days
    return min(seconds, max_seconds)


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

    # Determine if invoked via unmute / untimeout alias
    invoked_cmd = "timeout"
    if hasattr(message, "content") and message.content:
        first_word = message.content.split()[0].lstrip("$!/.").lower()
        if first_word in ("unmute", "untimeout"):
            invoked_cmd = "unmute"

    if not args:
        err_box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Invalid Timeout Syntax")
            .add_text_display(
                "Please specify a user and optional duration.\n\n"
                "*Usage:* `$timeout <@user|user_id> [duration: 5m, 1h, 1d, 7d] [reason]`\n"
                "*Unmute:* `$unmute <@user|user_id> [reason]`"
            )
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

    # Hierarchy validation
    if target.id == guild.owner_id:
        box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Cannot Timeout Server Owner")
            .add_text_display("The server owner cannot be timed out.")
            .build()
        )
        return await send_response(message, box, ephemeral=True)

    if bot_member and target.top_role >= bot_member.top_role:
        box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Role Hierarchy Restriction")
            .add_text_display(f"Cannot timeout `{target.name}`: their role is equal to or higher than Sentinel's role.")
            .build()
        )
        return await send_response(message, box, ephemeral=True)

    if author and author.id != guild.owner_id and hasattr(author, "top_role") and target.top_role >= author.top_role:
        box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Insufficient Hierarchy")
            .add_text_display(f"You cannot timeout `{target.name}` because their role is higher than or equal to yours.")
            .build()
        )
        return await send_response(message, box, ephemeral=True)

    # Parse duration and reason
    remaining = [a for a in args[1:] if not re.match(r"^(?:<@!?)?\d{17,20}>?$", a)]
    duration_seconds = 600  # default 10 minutes
    if invoked_cmd == "unmute":
        duration_seconds = 0
    elif remaining:
        parsed_dur = _parse_timeout_duration(remaining[0])
        if parsed_dur is not None:
            duration_seconds = parsed_dur
            remaining = remaining[1:]

    reason = " ".join(remaining).strip() or "No reason specified"

    route_key = f"guild:{guild.id}:members"
    try:
        if duration_seconds == 0:
            # Remove timeout
            await sentinel_rate_limiter.execute_safe_api_call(
                lambda: target.timeout(None, reason=f"Timeout removed by {author.name if author else 'Admin'}: {reason}"),
                route_key=route_key,
                description=f"Remove timeout for {target.name}",
            )
            success_box = (
                ContainerBuilder()
                .set_accent_color(get_color("success", "#10B981"))
                .add_text_display(f"### {get_emoji('success', '✅')} Timeout Removed")
                .add_separator(spacing=SeparatorSpacingSize.SMALL)
                .add_text_display(
                    f"Successfully removed timeout for **{target.name}** (`{target.id}`).\n\n"
                    f"**Moderator:** {author.mention if author else 'Admin'}\n"
                    f"**Reason:** {reason}"
                )
                .set_footer("Sentinel™ Enterprise Moderation Core")
                .build()
            )
            return await send_response(message, success_box)
        else:
            # Apply timeout
            until_dt = discord.utils.utcnow() + datetime.timedelta(seconds=duration_seconds)
            await sentinel_rate_limiter.execute_safe_api_call(
                lambda: target.timeout(until_dt, reason=f"Timed out by {author.name if author else 'Admin'}: {reason}"),
                route_key=route_key,
                description=f"Timeout member {target.name} for {duration_seconds}s",
            )

            # Format duration display
            if duration_seconds >= 86400:
                dur_text = f"{duration_seconds // 86400} day(s)"
            elif duration_seconds >= 3600:
                dur_text = f"{duration_seconds // 3600} hour(s)"
            elif duration_seconds >= 60:
                dur_text = f"{duration_seconds // 60} minute(s)"
            else:
                dur_text = f"{duration_seconds} second(s)"

            success_box = (
                ContainerBuilder()
                .set_accent_color(get_color("warning", "#F59E0B"))
                .add_text_display(f"### {get_emoji('mute', '🔇')} Member Timed Out")
                .add_separator(spacing=SeparatorSpacingSize.SMALL)
                .add_text_display(
                    f"Successfully applied timeout to **{target.name}** (`{target.id}`).\n\n"
                    f"**Duration:** {dur_text}\n"
                    f"**Expires:** <t:{int(time.time() + duration_seconds)}:R>\n"
                    f"**Moderator:** {author.mention if author else 'Admin'}\n"
                    f"**Reason:** {reason}"
                )
                .set_footer("Sentinel™ Enterprise Moderation Core")
                .build()
            )
            return await send_response(message, success_box)

    except Exception as err:
        err_box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display(f"### {get_emoji('error', '🚨')} Timeout Operation Failed")
            .add_text_display(f"Could not modify timeout for `{target.name}`: {err}")
            .build()
        )
        return await send_response(message, err_box, ephemeral=True)
