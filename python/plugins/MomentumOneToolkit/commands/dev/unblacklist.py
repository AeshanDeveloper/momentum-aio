import re
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.blacklist import BlacklistManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    SeparatorSpacingSize
)
from sdk.discord.response import send_response, send_ui
from discord import MessageFlags, ButtonStyle

name = "unblacklist"
aliases = ["unbl"]
description = "Remove a user or server from the global blacklist (Bot Owner Only)."
category = "Owner"
usage = "unblacklist <user|server> <targetId>"
owner_only = True

async def send_user_dm_notification(client: Any, user_id: str, title: str, description: str, color_key: str = "success") -> bool:
    if not client or not user_id:
        return False
    try:
        user = client.get_user(int(user_id)) if hasattr(client, "get_user") else None
        if not user and hasattr(client, "fetch_user"):
            try:
                user = await client.fetch_user(int(user_id))
            except Exception:
                user = None
        if not user:
            return False
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get(color_key, "#10B981"))
            .add_text_display(f"### {title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(description)
            .build()
        )
        await send_response(user, box)
        return True
    except Exception:
        return False

async def send_guild_owner_dm_notification(client: Any, guild_id: str, title: str, description_template: str, color_key: str = "success") -> tuple[bool, str]:
    if not client or not guild_id:
        return False, f"Server {guild_id}"
    try:
        guild = client.get_guild(int(guild_id)) if hasattr(client, "get_guild") else None
        guild_name = guild.name if guild else f"Server {guild_id}"
        owner = None
        if guild:
            owner = getattr(guild, "owner", None)
            if not owner and hasattr(guild, "owner_id") and guild.owner_id and hasattr(client, "fetch_user"):
                try:
                    owner = await client.fetch_user(guild.owner_id)
                except Exception:
                    pass
        elif hasattr(client, "fetch_guild"):
            try:
                fetched = await client.fetch_guild(int(guild_id))
                if fetched:
                    guild_name = fetched.name
                    if hasattr(fetched, "owner_id") and fetched.owner_id and hasattr(client, "fetch_user"):
                        owner = await client.fetch_user(fetched.owner_id)
            except Exception:
                pass

        if not owner:
            return False, guild_name

        desc = description_template.replace("{guild_name}", guild_name)
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get(color_key, "#10B981"))
            .add_text_display(f"### {title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(desc)
            .build()
        )
        await send_response(owner, box)
        return True, guild_name
    except Exception:
        return False, f"Server {guild_id}"

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
    client = getattr(ctx, "client", getattr(message, "client", None))
    if not client and hasattr(message, "_state"):
        client = getattr(message._state, "_get_client", lambda: None)()

    owner_ids = settings.OWNER_IDS

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        return await send_ui(message, "permissions.owner_only", style="error")

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
        return await send_response(message, box)

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

        dm_title = get_string("commands.blacklist.server_remove_dm_title", f"{emojis['check']} Notice of Server Blacklist Removal")
        dm_desc_tmpl = get_string(
            "commands.blacklist.server_remove_dm_desc",
            f"Your server **{{guild_name}}** (`{target_id}`) has been removed from the MomentumOne global blacklist. Services have been restored.",
            guild_id=target_id
        )
        dm_sent, resolved_name = await send_guild_owner_dm_notification(client, target_id, dm_title, dm_desc_tmpl, "success")
        dm_notice = f"{emojis['check']} Delivered to server owner" if dm_sent else f"{emojis['ban']} Undelivered (Server owner unreachable or DMs closed)"

        return await reply(
            f"{emojis['check']} Server Unblacklisted",
            f"• **Server:** **{resolved_name}** (`{target_id}`)\n"
            f"• **Status:** Restored (Removed from global blacklist)\n"
            f"• **DM Notice:** {dm_notice}",
            colors["success"]
        )
    else:
        res = BlacklistManager.unblacklist_user(target_id, author_id)
        if not res.get("success"):
            return await reply(f"{emojis['ban']} Unblacklist Failed", res.get("error", "Database error."), colors["error"])

        dm_title = get_string("commands.blacklist.user_remove_dm_title", f"{emojis['check']} Notice of Blacklist Removal")
        dm_desc = get_string(
            "commands.blacklist.user_remove_dm_desc",
            f"Your account (`{target_id}`) has been removed from the MomentumOne global blacklist. Your command privileges have been restored.",
            user_id=target_id
        )
        dm_sent = await send_user_dm_notification(client, target_id, dm_title, dm_desc, "success")
        dm_notice = f"{emojis['check']} Delivered" if dm_sent else f"{emojis['ban']} Undelivered (DMs closed or user unreachable)"

        return await reply(
            f"{emojis['check']} User Unblacklisted",
            f"• **Target User:** <@{target_id}> (`{target_id}`)\n"
            f"• **Status:** Restored (Removed from global blacklist)\n"
            f"• **DM Notice:** {dm_notice}",
            colors["success"]
        )
