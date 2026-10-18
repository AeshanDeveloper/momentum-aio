import re
from typing import List, Dict, Any, Optional
import discord

from config.settings import config, COLORS, EMOJIS
from core.security.blacklist import BlacklistManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    SeparatorSpacingSize,
    MessageFlags,
)

name = "unblacklist"
aliases = ["unbl"]
description = "Remove a user or server from the global blacklist (Bot Owner Only)."
category = "Owner"
usage = "unblacklist <user|server> <targetId>"
owner_only = True

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
        "check": E.get("success") or "✅",
        "ban": E.get("ban") or E.get("error") or "🚫",
    }

    colors = {
        "success": C.get("success", "#10B981"),
        "error": C.get("error", "#EF4444"),
    }

    async def reply(title: str, description: str, color: str = None):
        if color is None:
            color = colors["success"]
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

    target_type = args[0].lower() if args else None
    target_raw = args[1] if len(args) > 1 else None

    # If user only passed target ID (or mention): `$unblacklist @user`
    if target_type and target_type not in ["user", "server", "guild"]:
        target_raw = args[0]
        target_type = "user"

    target_id = resolve_target_id(target_raw)
    if not target_id:
        return await reply(
            f"{emojis['ban']} Invalid Target",
            "Usage: `$unblacklist <user|server> <targetId>`\nExample: `$unblacklist user @john` or `$unblacklist server 123456789`",
            colors["error"]
        )

    if target_type in ["server", "guild"]:
        res = BlacklistManager.unblacklist_guild(target_id, author_id)
        if not res.get("success"):
            return await reply(f"{emojis['ban']} Unblacklist Failed", res.get("error", "Database error."), colors["error"])
        return await reply(
            f"{emojis['check']} Server Unblacklisted",
            f"Successfully removed server `{target_id}` from the global blacklist.",
            colors["success"]
        )
    else:
        res = BlacklistManager.unblacklist_user(target_id, author_id)
        if not res.get("success"):
            return await reply(f"{emojis['ban']} Unblacklist Failed", res.get("error", "Database error."), colors["error"])
        return await reply(
            f"{emojis['check']} User Unblacklisted",
            f"Successfully removed user <@{target_id}> (`{target_id}`) from the global blacklist.",
            colors["success"]
        )
