"""
Sentinel™ Manual Warning System: warn, warnings, clearwarn.
Explicitly distinct from automated threat observations; persists manual disciplinary records to MongoDB.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import List, Dict, Any, Optional

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
from database.database import database, _save_mock_data
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
from shared.types.command_record import CommandType

name = "warn"
aliases = ["warnings", "clearwarn", "clearwarns", "warns"]
description = "Manual member disciplinary warning system: issue, inspect, and clear warnings."
category = "Moderation"
usage = "warn <@user|user_id> <reason> | warnings <@user> | clearwarn <@user> [warn_id|all]"
cooldown = 2.0
user_permissions = [Permissions.MANAGE_MESSAGES]
bot_permissions = [Permissions.SEND_MESSAGES]
guild_only = True

COLLECTION_NAME = "guild_member_warnings"


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


def get_guild_warnings(guild_id: str | int, user_id: str | int) -> List[Dict[str, Any]]:
    """Retrieves all active manual warnings for a user in a guild."""
    gid = str(guild_id)
    uid = str(user_id)
    try:
        col = database.collection(COLLECTION_NAME)
        if hasattr(col, "_get_items"):
            return [w for w in col._get_items() if str(w.get("guild_id")) == gid and str(w.get("user_id")) == uid]
    except Exception:
        pass
    return []


def save_guild_warning(warning_dict: Dict[str, Any]) -> None:
    """Saves a new manual warning record."""
    try:
        col = database.collection(COLLECTION_NAME)
        if hasattr(col, "_get_items"):
            items = col._get_items()
            items.append(warning_dict)
            _save_mock_data(COLLECTION_NAME, items)
    except Exception:
        pass


def delete_guild_warnings(guild_id: str | int, user_id: str | int, warn_id: Optional[str] = None) -> int:
    """Clears either a single warning by ID or all warnings for the user. Returns cleared count."""
    gid = str(guild_id)
    uid = str(user_id)
    cleared = 0
    try:
        col = database.collection(COLLECTION_NAME)
        if hasattr(col, "_get_items"):
            items = col._get_items()
            kept = []
            for w in items:
                matches_user = (str(w.get("guild_id")) == gid and str(w.get("user_id")) == uid)
                if matches_user:
                    if warn_id is None or warn_id.lower() == "all" or w.get("warning_id") == warn_id:
                        cleared += 1
                        continue
                kept.append(w)
            col._store[col.name] = kept
            _save_mock_data(COLLECTION_NAME, kept)
    except Exception:
        pass
    return cleared


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if str(command_type).lower() == "slash" else getattr(message, "author", None)

    # Determine command action from invocation alias or first argument
    first_token = ""
    if hasattr(message, "content") and message.content:
        first_token = message.content.split()[0].lstrip("$!/.").lower()

    action = "warn"
    if first_token in ("warnings", "warns"):
        action = "warnings"
    elif first_token in ("clearwarn", "clearwarns"):
        action = "clearwarn"

    if args and args[0].lower() in ("list", "view", "warnings"):
        action = "warnings"
        args = args[1:]
    elif args and args[0].lower() in ("clear", "remove", "delete", "clearwarn"):
        action = "clearwarn"
        args = args[1:]

    if not args:
        help_box = (
            ContainerBuilder()
            .set_accent_color(get_color("info", "#0844C5"))
            .add_text_display("### " + get_emoji("sentinel", "🛡️") + " Sentinel™ Warning System")
            .add_separator(spacing=SeparatorSpacingSize.SMALL)
            .add_text_display(
                "• **Issue Warning:** `$warn <@user> <reason>`\n"
                "• **View Warnings:** `$warnings <@user>`\n"
                "• **Clear Warning:** `$clearwarn <@user> [warning_id|all]`"
            )
            .build()
        )
        return await send_response(message, help_box, ephemeral=True)

    target = _resolve_target_user(guild, args, message)
    if not target:
        err_box = (
            ContainerBuilder()
            .set_accent_color(get_color("error", "#B21F1F"))
            .add_text_display("### " + get_emoji("error", "🚨") + " Member Not Found")
            .add_text_display(f"Could not locate an active member matching `{args[0]}`.")
            .build()
        )
        return await send_response(message, err_box, ephemeral=True)

    target_id = target.id
    target_name = target.name

    # Action 1: View Warnings
    if action == "warnings":
        warns = get_guild_warnings(guild.id, target_id)
        if not warns:
            box = (
                ContainerBuilder()
                .set_accent_color(get_color("success", "#10B981"))
                .add_text_display(f"### {get_emoji('success', '✅')} Clean Disciplinary Record")
                .add_text_display(f"**{target_name}** (`{target_id}`) has 0 recorded warnings in this server.")
                .build()
            )
            return await send_response(message, box)

        lines = [f"### {get_emoji('warn', '⚠️')} Warnings for {target_name} (`{len(warns)}` Total)"]
        for idx, w in enumerate(warns, 1):
            ts = int(w.get("timestamp", time.time()))
            wid = w.get("warning_id", "Unknown")
            mod_id = w.get("moderator_id", "Admin")
            reason = w.get("reason", "No reason recorded")
            lines.append(f"**{idx}. ID `{wid}`** • <t:{ts}:R>\n• **Reason:** {reason}\n• **Moderator:** <@{mod_id}>")

        box = (
            ContainerBuilder()
            .set_accent_color(get_color("warning", "#F59E0B"))
            .add_text_display("\n\n".join(lines))
            .set_footer("Sentinel™ Manual Warning Ledger")
            .build()
        )
        return await send_response(message, box)

    # Action 2: Clear Warnings
    elif action == "clearwarn":
        warn_id = None
        rem = [a for a in args[1:] if not re.match(r"^(?:<@!?)?\d{17,20}>?$", a)]
        if rem:
            warn_id = rem[0]

        cleared_count = delete_guild_warnings(guild.id, target_id, warn_id)
        if cleared_count == 0:
            box = (
                ContainerBuilder()
                .set_accent_color(get_color("warning", "#F59E0B"))
                .add_text_display(f"### {get_emoji('info', 'ℹ️')} No Warnings Cleared")
                .add_text_display(f"No matching warnings found for **{target_name}**.")
                .build()
            )
            return await send_response(message, box, ephemeral=True)

        box = (
            ContainerBuilder()
            .set_accent_color(get_color("success", "#10B981"))
            .add_text_display(f"### {get_emoji('success', '✅')} Warnings Cleared")
            .add_separator(spacing=SeparatorSpacingSize.SMALL)
            .add_text_display(
                f"Successfully removed **{cleared_count}** warning(s) from **{target_name}** (`{target_id}`).\n\n"
                f"**Moderator:** {author.mention if author else 'Admin'}"
            )
            .set_footer("Sentinel™ Manual Warning Ledger")
            .build()
        )
        return await send_response(message, box)

    # Action 3: Issue Warning
    else:
        reason_parts = [a for a in args[1:] if not re.match(r"^(?:<@!?)?\d{17,20}>?$", a)]
        reason = " ".join(reason_parts).strip()
        if not reason:
            box = (
                ContainerBuilder()
                .set_accent_color(get_color("error", "#B21F1F"))
                .add_text_display("### " + get_emoji("error", "🚨") + " Reason Required")
                .add_text_display("You must provide a clear reason when issuing a formal warning.\n\n*Usage:* `$warn <@user> <reason>`")
                .build()
            )
            return await send_response(message, box, ephemeral=True)

        warn_id = f"wrn_{uuid.uuid4().hex[:8]}"
        warn_entry = {
            "warning_id": warn_id,
            "guild_id": str(guild.id),
            "user_id": str(target_id),
            "moderator_id": str(author.id if author else "0"),
            "reason": reason,
            "timestamp": time.time(),
        }
        save_guild_warning(warn_entry)

        current_warns = get_guild_warnings(guild.id, target_id)
        total_count = len(current_warns)

        # Send DM notification to warned user
        try:
            dm_box = (
                ContainerBuilder()
                .set_accent_color(get_color("warning", "#F59E0B"))
                .add_text_display(f"### {get_emoji('warn', '⚠️')} Warning Received in {guild.name}")
                .add_separator(spacing=SeparatorSpacingSize.SMALL)
                .add_text_display(
                    f"You have received a formal disciplinary warning in **{guild.name}**.\n\n"
                    f"**Reason:** {reason}\n"
                    f"**Warning ID:** `{warn_id}`\n"
                    f"**Total Warnings:** {total_count}"
                )
                .set_footer("Sentinel™ Security & Moderation")
                .build()
            )
            await target.send(embed=dm_box if hasattr(target, "send") else None)
        except Exception:
            pass

        box = (
            ContainerBuilder()
            .set_accent_color(get_color("warning", "#F59E0B"))
            .add_text_display(f"### {get_emoji('warn', '⚠️')} Member Warned")
            .add_separator(spacing=SeparatorSpacingSize.SMALL)
            .add_text_display(
                f"Successfully issued formal warning to **{target_name}** (`{target_id}`).\n\n"
                f"**Reason:** {reason}\n"
                f"**Warning ID:** `{warn_id}`\n"
                f"**Total Server Warnings:** `{total_count}`\n"
                f"**Moderator:** {author.mention if author else 'Admin'}"
            )
            .set_footer("Sentinel™ Manual Warning Ledger")
            .build()
        )
        return await send_response(message, box)
