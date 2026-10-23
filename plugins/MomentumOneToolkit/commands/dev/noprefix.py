import re
import math
import time
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.noprefix import NoPrefixManager
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    SeparatorSpacingSize,
    ActionRowBuilder,
    ButtonBuilder,
)
from sdk.discord.response import send_response, send_ui
from discord import MessageFlags, ButtonStyle

name = "noprefix"
aliases = ["np", "noprefixuser", "noprefixguild"]
description = "Manage persistent no-prefix command authorization for users and servers (Bot Owner Only)."
category = "Owner"
usage = "noprefix <status|add|remove|list> [user|server] <targetId> [duration]"
owner_only = True

sub_commands = [
    {"name": "status [enable|disable|toggle]", "description": "View or toggle global runtime no-prefix evaluation."},
    {"name": "add <@user> [duration]", "description": "Grant no-prefix privileges to a user."},
    {"name": "remove <@user>", "description": "Revoke no-prefix privileges from a user."},
    {"name": "server add <guildId> [duration]", "description": "Grant server-wide no-prefix privileges."},
    {"name": "server remove <guildId>", "description": "Revoke server-wide no-prefix privileges."},
    {"name": "list [user|server] [page]", "description": "List authorized users or servers."},
]


def resolve_target_id(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    cleaned = re.sub(r"[<@!>]", "", raw).strip()
    if re.match(r"^\d{17,20}$", cleaned):
        return cleaned
    return None


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
        "key": E.get("key") or "🔑",
        "check": E.get("success") or "✅",
        "cross": E.get("error") or "❌",
        "info": E.get("info") or "ℹ️",
        "time": E.get("time") or "⏱️",
        "user": E.get("user") or "👤",
        "server": E.get("server") or "🌐",
        "enabled": E.get("enabled") or "🟢",
        "disabled": E.get("disabled") or "🔴",
    }

    colors = {
        "default": C.get("default", "#0844C5"),
        "success": C.get("success", "#10B981"),
        "error": C.get("error", "#EF4444"),
        "warning": C.get("warning", "#F59E0B"),
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
        return await send_response(message, box)

    action = args[0].lower() if args else None

    # 1. STATUS SUBCOMMAND
    if action == "status":
        sub_arg = args[1].lower() if len(args) > 1 else None
        if sub_arg in ["enable", "on", "true", "start"]:
            NoPrefixManager.set_enabled(True)
            return await reply(
                f"{emojis['key']} No-Prefix System Enabled",
                f"{emojis['check']} Global no-prefix evaluation is now **ACTIVE**.\nAuthorized users and servers can trigger commands without a prefix.",
                colors["success"]
            )
        elif sub_arg in ["disable", "off", "false", "stop"]:
            NoPrefixManager.set_enabled(False)
            return await reply(
                f"{emojis['key']} No-Prefix System Disabled",
                f"{emojis['cross']} Global no-prefix evaluation is now **INACTIVE**.\nCommands will require the bot prefix until re-enabled.",
                colors["warning"]
            )
        elif sub_arg in ["toggle"]:
            new_state = not NoPrefixManager.is_enabled()
            NoPrefixManager.set_enabled(new_state)
            state_text = "ACTIVE" if new_state else "INACTIVE"
            icon = emojis["check"] if new_state else emojis["cross"]
            return await reply(
                f"{emojis['key']} No-Prefix System Toggled",
                f"{icon} Global no-prefix evaluation is now **{state_text}**.",
                colors["success"] if new_state else colors["warning"]
            )
        else:
            # Inspection view
            status_active = NoPrefixManager.is_enabled()
            status_icon = emojis["enabled"] if status_active else emojis["disabled"]
            status_label = "Active / Enabled" if status_active else "Inactive / Disabled"
            user_entries = NoPrefixManager.list("user")
            guild_entries = NoPrefixManager.list("guild")

            desc = (
                f"• **Runtime State:** {status_icon} `{status_label}`\n"
                f"• **Authorized User Records:** `{len(user_entries)}`\n"
                f"• **Authorized Server Overrides:** `{len(guild_entries)}`\n\n"
                "**Control Commands:**\n"
                "> `$noprefix status enable` — Enable runtime no-prefix evaluation\n"
                "> `$noprefix status disable` — Temporarily disable without altering records\n"
                "> `$noprefix status toggle` — Flip current runtime state"
            )
            return await reply(f"{emojis['key']} No-Prefix System Status", desc, colors["default"])

    # Target Type Resolution
    is_server = False
    target_raw = None
    duration_str = None

    if action in ["server", "guild"]:
        is_server = True
        sub_action = args[1].lower() if len(args) > 1 else "list"
        target_raw = args[2] if len(args) > 2 else None
        duration_str = args[3] if len(args) > 3 else "permanent"
        action = sub_action
    elif action in ["user"]:
        is_server = False
        sub_action = args[1].lower() if len(args) > 1 else "list"
        target_raw = args[2] if len(args) > 2 else None
        duration_str = args[3] if len(args) > 3 else "permanent"
        action = sub_action

    # 2. LIST SUBCOMMAND
    if not action or action == "list":
        t_type = "guild" if is_server else "user"
        entries = NoPrefixManager.list(t_type)
        type_label = "Servers" if is_server else "Users"

        if not entries:
            return await reply(
                f"{emojis['info']} No-Prefix {type_label}",
                f"No {type_label.lower()} currently have active no-prefix privileges.\n\n"
                "**Usage:**\n"
                f"> `$noprefix {'server ' if is_server else ''}add <{'guildId' if is_server else '@user'}> [duration]`\n"
                f"> `$noprefix {'server ' if is_server else ''}remove <{'guildId' if is_server else '@user'}>`\n"
                f"> `$noprefix status [enable|disable]`",
                colors["default"]
            )

        page_arg = 1
        page_candidates = [a for a in args if a.isdigit()]
        if page_candidates:
            page_arg = int(page_candidates[0])

        page_size = 10
        total_pages = max(1, math.ceil(len(entries) / page_size))
        safe_page = max(1, min(page_arg, total_pages))
        page_items = entries[(safe_page - 1) * page_size : safe_page * page_size]

        lines = []
        for idx, e in enumerate(page_items):
            exp_ts = e.get("expiresAt") or e.get("expires_at")
            exp = f"<t:{int(exp_ts)}:F> (<t:{int(exp_ts)}:R>)" if exp_ts else "`Permanent`"
            status = "Temporary" if exp_ts else "Permanent"
            tid = e.get("targetId") or e.get("target_id")
            added_by = e.get("addedBy") or e.get("added_by")
            target_str = f"Guild `{tid}`" if is_server else f"<@{tid}> (`{tid}`)"
            lines.append(f"**{(safe_page - 1) * page_size + idx + 1}.** {target_str}\n   > **Status:** Active ({status})\n   > **Expires:** {exp}\n   > **Granted by:** <@{added_by}>")
        desc = "\n\n".join(lines)

        footer = f"\n\n-# View other pages with `$noprefix {'server ' if is_server else ''}list <page>`" if total_pages > 1 else ""

        box = (
            ContainerBuilder()
            .set_accent_color(colors["default"])
            .add_text_display(f"### {emojis['key']} Authorized No-Prefix {type_label} ({len(entries)}) — Page {safe_page}/{total_pages}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{desc}{footer}")
            .build()
        )
        return await send_response(message, box)

    # 3. ADD SUBCOMMAND
    if action == "add":
        if target_raw is None and len(args) > 1:
            target_raw = args[1]
            duration_str = args[2] if len(args) > 2 else "permanent"

        target_id = resolve_target_id(target_raw)
        if not target_id:
            target_hint = "guild ID" if is_server else "@user mention or Discord ID"
            return await reply(
                f"{emojis['cross']} Missing Target",
                f"Please provide a valid {target_hint}.\nExample: `$noprefix {'server ' if is_server else ''}add {123456789 if is_server else '@user'} 7d`",
                colors["error"]
            )

        t_type = "guild" if is_server else "user"
        res = NoPrefixManager.add(target_id, duration_str, author_id, target_type=t_type)
        if not res.get("success"):
            return await reply(f"{emojis['cross']} Failed to Add", res.get("error", "Database error."), colors["error"])

        exp_val = res.get("entry", {}).get("expiresAt")
        expiry_text = f"<t:{int(exp_val)}:F> (<t:{int(exp_val)}:R>)" if exp_val else "`Permanent`"

        if is_server:
            dm_title = get_string("commands.noprefix.server_add_dm_title", f"{emojis['key']} Server No-Prefix Enabled")
            dm_desc_tmpl = get_string(
                "commands.noprefix.server_add_dm_desc",
                f"Your server **{{guild_name}}** (`{target_id}`) has been granted server-wide **No-Prefix** privileges for MomentumOne commands.",
                guild_id=target_id
            )
            dm_sent, resolved_name = await send_guild_owner_dm_notification(client, target_id, dm_title, dm_desc_tmpl, "success")
            dm_notice = f"{emojis['check']} Delivered to server owner" if dm_sent else f"{emojis['cross']} Undelivered (Owner unreachable or DMs closed)"

            return await reply(
                f"{emojis['check']} Server No-Prefix Granted",
                f"• **Server:** **{resolved_name}** (`{target_id}`)\n"
                f"• **Duration:** {expiry_text}\n"
                f"• **Status:** Active (members can execute commands without prefix in this server)\n"
                f"• **DM Notice:** {dm_notice}",
                colors["success"]
            )
        else:
            dm_title = get_string("commands.noprefix.user_add_dm_title", f"{emojis['key']} No-Prefix Access Granted")
            dm_desc = get_string(
                "commands.noprefix.user_add_dm_desc",
                f"You have been granted **No-Prefix** command execution privileges on MomentumOne.\n\n• **Duration:** {expiry_text}\n• **Granted by:** <@{author_id}>\n\nYou may now execute bot commands without prepending the bot prefix.",
                duration=expiry_text,
                admin_id=author_id
            )
            dm_sent = await send_user_dm_notification(client, target_id, dm_title, dm_desc, "success")
            dm_notice = f"{emojis['check']} Delivered" if dm_sent else f"{emojis['cross']} Undelivered (DMs closed or user unreachable)"

            return await reply(
                f"{emojis['check']} User No-Prefix Granted",
                f"• **User:** <@{target_id}> (`{target_id}`)\n"
                f"• **Duration:** {expiry_text}\n"
                f"• **Status:** Active (can execute bot commands without a prefix)\n"
                f"• **DM Notice:** {dm_notice}",
                colors["success"]
            )

    # 4. REMOVE SUBCOMMAND
    if action in ["remove", "delete", "revoke"]:
        if target_raw is None and len(args) > 1:
            target_raw = args[1]

        target_id = resolve_target_id(target_raw)
        if not target_id:
            target_hint = "guild ID" if is_server else "@user mention or Discord ID"
            return await reply(
                f"{emojis['cross']} Missing Target",
                f"Please provide a valid {target_hint}.\nExample: `$noprefix {'server ' if is_server else ''}remove {123456789 if is_server else '@user'}`",
                colors["error"]
            )

        t_type = "guild" if is_server else "user"
        res = NoPrefixManager.remove(target_id, author_id, target_type=t_type)
        if not res.get("success"):
            return await reply(f"{emojis['cross']} Failed to Remove", res.get("error", "Database error."), colors["error"])

        if is_server:
            dm_title = get_string("commands.noprefix.server_remove_dm_title", f"{emojis['key']} Server No-Prefix Removed")
            dm_desc_tmpl = get_string(
                "commands.noprefix.server_remove_dm_desc",
                f"Server-wide **No-Prefix** privileges for **{{guild_name}}** (`{target_id}`) have been revoked.",
                guild_id=target_id
            )
            dm_sent, resolved_name = await send_guild_owner_dm_notification(client, target_id, dm_title, dm_desc_tmpl, "warning")
            dm_notice = f"{emojis['check']} Delivered to server owner" if dm_sent else f"{emojis['cross']} Undelivered (Owner unreachable or DMs closed)"

            return await reply(
                f"{emojis['check']} Server No-Prefix Revoked",
                f"• **Server:** **{resolved_name}** (`{target_id}`)\n"
                f"• **Status:** Revoked (Server members now require the bot prefix)\n"
                f"• **DM Notice:** {dm_notice}",
                colors["success"]
            )
        else:
            dm_title = get_string("commands.noprefix.user_remove_dm_title", f"{emojis['key']} No-Prefix Access Revoked")
            dm_desc = get_string(
                "commands.noprefix.user_remove_dm_desc",
                "Your **No-Prefix** privileges on MomentumOne have ended. Please use the server prefix to execute commands."
            )
            dm_sent = await send_user_dm_notification(client, target_id, dm_title, dm_desc, "warning")
            dm_notice = f"{emojis['check']} Delivered" if dm_sent else f"{emojis['cross']} Undelivered (DMs closed or user unreachable)"

            return await reply(
                f"{emojis['check']} User No-Prefix Revoked",
                f"• **Target User:** <@{target_id}> (`{target_id}`)\n"
                f"• **Status:** Revoked (User must now use the bot prefix)\n"
                f"• **DM Notice:** {dm_notice}",
                colors["success"]
            )

    return await reply(
        f"{emojis['cross']} Unknown Action",
        "Available actions: `status [enable|disable|toggle]`, `add`, `remove`, `list`.\nExample: `$noprefix status` or `$noprefix add @user 7d`",
        colors["error"]
    )
