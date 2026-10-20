import re
import math
import time
from typing import List, Dict, Any, Optional
import discord

from config.settings import COLORS, EMOJIS
from core.security.noprefix import NoPrefixManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    SeparatorSpacingSize
)
from discord import MessageFlags, ButtonStyle

name = "noprefix"
aliases = ["np", "noprefixuser"]
description = "Grant or revoke persistent no-prefix command access for users (Bot Owner Only)."
category = "Owner"
usage = "noprefix <add|remove|list> <@user/id> [duration]"
owner_only = True

sub_commands = [
    {"name": "add <@user> [duration]", "description": "Grant no-prefix command privileges to a user."},
    {"name": "remove <@user>", "description": "Revoke no-prefix command privileges from a user."},
    {"name": "list", "description": "List all users with active no-prefix access."},
]

def resolve_target_id(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"[<@!>]", "", raw).strip()
    if re.match(r"^\d{17,20}$", cleaned):
        return cleaned
    return None

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""

    bot_cfg = getattr(config, "settings", {}).get("bot", {}) if isinstance(getattr(config, "settings", {}), dict) else {}
    owner_ids = [str(o) for o in (bot_cfg.get("owner_ids") or [getattr(config, "OWNER_ID", "")])]

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_msg = "❌ **Access Denied**: This command is restricted to the bot owner."
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(denied_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(denied_msg)
        return

    E = EMOJIS
    C = COLORS

    emojis = {
        "key": E.get("key") or E.get("mod") or "🔑",
        "check": E.get("success") or "✅",
        "cross": E.get("error") or "❌",
        "info": E.get("info") or "ℹ️",
        "time": E.get("time") or "⏱️",
        "user": E.get("user") or "👤",
    }

    colors = {
        "default": C.get("default", "#3B82F6"),
        "success": C.get("success", "#10B981"),
        "error": C.get("error", "#EF4444"),
    }

    async def reply(title: str, description: str, color: str = None):
        if color is None:
            color = colors["default"]
        box = (
            ContainerBuilder()
            .set_accent_color(color)
            .add_text_display(f"### {title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(description)
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=box.embed)
        elif hasattr(message, "reply"):
            return await message.reply(embed=box.embed)

    action = args[0].lower() if args else None

    # Interactive Overview / List if no arguments provided or action == "list"
    if not action or action == "list":
        entries = NoPrefixManager.list()
        bot_prefix = bot_cfg.get("prefix", "$")
        if not entries:
            return await reply(
                f"{emojis['info']} No-Prefix System",
                "No users currently have no-prefix privileges.\n\n"
                "**Usage:**\n"
                "> `$noprefix add <@user|id> [duration]` (e.g. `1h`, `7d`, `permanent`)\n"
                "> `$noprefix remove <@user|id>`\n"
                "> `$noprefix list [page]`",
                colors["default"]
            )

        page_arg = 1
        if len(args) > 1:
            try:
                page_arg = int(args[1])
            except ValueError:
                page_arg = 1

        page_size = 10
        total_pages = max(1, math.ceil(len(entries) / page_size))
        safe_page = max(1, min(page_arg, total_pages))
        page_items = entries[(safe_page - 1) * page_size : safe_page * page_size]

        lines = []
        for idx, e in enumerate(page_items):
            exp_ts = e.get("expiresAt") or e.get("expires_at")
            exp = f"<t:{int(exp_ts)}:F> (<t:{int(exp_ts)}:R>)" if exp_ts else "`Permanent`"
            status = "Temporary" if exp_ts else "Permanent"
            u_id = e.get("userId") or e.get("user_id")
            added_by = e.get("addedBy") or e.get("added_by")
            lines.append(f"{(safe_page - 1) * page_size + idx + 1}. <@{u_id}> (`{u_id}`)\n   > **Status:** Active ({status})\n   > **Expires:** {exp}\n   > **Granted by:** <@{added_by}>")
        desc = "\n\n".join(lines)

        footer = f"\n\n-# View other pages with `$noprefix list <page>`" if total_pages > 1 else ""

        container = (
            ContainerBuilder()
            .set_accent_color(colors["default"])
            .add_text_display(f"### {emojis['key']} Authorized No-Prefix Users ({len(entries)}) — Page {safe_page}/{total_pages}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{desc}\n\n"
                "**Usage:**\n"
                "> `$noprefix add <@user|id> [duration]` (e.g. `1h`, `7d`, `permanent`)\n"
                "> `$noprefix remove <@user|id>`\n"
                "> `$noprefix list [page]`"
                f"{footer}"
            )
            .build()
        )

        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(view=container)
        elif hasattr(message, "reply"):
            return await message.reply(view=container)
        return

    if action == "add":
        target_raw = args[1] if len(args) > 1 else None
        target_id = resolve_target_id(target_raw)
        if not target_id:
            return await reply(
                f"{emojis['cross']} Missing User",
                "Please mention a user or provide their Discord ID.\nExample: `$noprefix add @user 7d`",
                colors["error"]
            )

        duration_str = args[2] if len(args) > 2 else "permanent"
        res = NoPrefixManager.add(target_id, duration_str, author_id)
        if not res.get("success"):
            return await reply(f"{emojis['cross']} Failed to Add", res.get("error", "Database error."), colors["error"])

        exp_val = res.get("entry", {}).get("expiresAt")
        expiry_text = f"<t:{int(exp_val)}:F> (<t:{int(exp_val)}:R>)" if exp_val else "`Permanent`"
        bot_prefix = bot_cfg.get("prefix", "$")

        return await reply(
            f"{emojis['check']} No-Prefix Access Granted",
            f"• **User:** <@{target_id}> (`{target_id}`)\n"
            f"• **Duration:** {expiry_text}\n"
            f"• **Status:** Active (can execute bot prefix commands without `{bot_prefix}`)",
            colors["success"]
        )

    if action in ["remove", "delete", "revoke"]:
        target_raw = args[1] if len(args) > 1 else None
        target_id = resolve_target_id(target_raw)
        if not target_id:
            return await reply(
                f"{emojis['cross']} Missing User",
                "Please mention a user or provide their Discord ID.\nExample: `$noprefix remove @user`",
                colors["error"]
            )

        res = NoPrefixManager.remove(target_id, author_id)
        if not res.get("success"):
            return await reply(f"{emojis['cross']} Failed to Remove", res.get("error", "Database error."), colors["error"])

        return await reply(
            f"{emojis['check']} No-Prefix Access Revoked",
            f"Successfully removed no-prefix privileges from <@{target_id}> (`{target_id}`).",
            colors["success"]
        )

    return await reply(
        f"{emojis['cross']} Unknown Action",
        "Available actions: `add`, `remove`, `list`.\nExample: `$noprefix add @user 3d`",
        colors["error"]
    )
