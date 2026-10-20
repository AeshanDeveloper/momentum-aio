import re
import math
import time
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from core.security.blacklist import BlacklistManager, parse_duration_str
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response
from discord import MessageFlags, ButtonStyle

name = "blacklist"
aliases = ["bl", "globalblacklist", "gbl"]
description = "Manage global persistent user and server blacklists (Bot Owner Only)."
category = "Owner"
usage = "blacklist <user|server> <add|remove|list> <targetId> [duration] [reason]"
owner_only = True

sub_commands = [
    {"name": "user add <target> [duration] [reason]", "description": "Blacklist a user globally."},
    {"name": "user remove <target>", "description": "Remove a user from global blacklist."},
    {"name": "user list", "description": "List all globally blacklisted users."},
    {"name": "server add <guildId> [duration] [reason]", "description": "Blacklist a server globally."},
    {"name": "server remove <guildId>", "description": "Remove a server from global blacklist."},
    {"name": "server list", "description": "List all globally blacklisted servers."},
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

    owner_ids = settings.OWNER_IDS

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_msg = "❌ **Access Denied**: This command is restricted to the bot owner."
        return await send_response(message, denied_msg, ephemeral=True)

    E = EMOJIS
    C = COLORS

    emojis = {
        "shield": E.get("shield") or E.get("mod") or "🛡️",
        "ban": E.get("ban") or E.get("error") or "🚫",
        "check": E.get("success") or "✅",
        "info": E.get("info") or "ℹ️",
        "time": E.get("time") or E.get("history") or "⏱️",
        "server": E.get("server") or "🌐",
        "user": E.get("user") or "👤",
    }

    colors = {
        "default": C.get("default", "#3B82F6"),
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

    sub = args[0].lower() if args else None

    # Interactive Overview Panel if no args or invalid target
    if not sub or sub not in ["user", "server", "guild", "list"]:
        users = BlacklistManager.list_blacklists("user")
        guilds = BlacklistManager.list_blacklists("guild")
        user_count = len(users)
        guild_count = len(guilds)
        menu_id = f"bl_menu_{id(message)}"

        container = (
            ContainerBuilder()
            .set_accent_color(colors["default"])
            .add_text_display(f"### {emojis['shield']} Global Blacklist System")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                "Manage persistent global restrictions across the entire bot platform.\n\n"
                f"• **Active Blacklisted Users:** `{user_count}`\n"
                f"• **Active Blacklisted Servers:** `{guild_count}`\n\n"
                "**Command Usage:**\n"
                "> `$blacklist user add <@user|id> [duration] [reason]`\n"
                "> `$blacklist user remove <@user|id>`\n"
                "> `$blacklist server add <guildId> [duration] [reason]`\n"
                "> `$blacklist server remove <guildId>`\n"
                "> `$blacklist list`"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("-# Durations: 10m, 1h, 1d, 7d, permanent, or ISO date")
        )

        menu = (
            SelectMenuBuilder()
            .set_custom_id(menu_id)
            .set_placeholder("Select Blacklist View...")
            .set_min_values(1)
            .set_max_values(1)
            .set_options([
                {
                    "label": "View Blacklisted Users",
                    "value": "view_users",
                    "description": f"View currently blacklisted users ({user_count} active)"[:100],
                    "emoji": emojis["user"],
                },
                {
                    "label": "View Blacklisted Servers",
                    "value": "view_servers",
                    "description": f"View currently blacklisted servers ({guild_count} active)"[:100],
                    "emoji": emojis["server"],
                },
            ])
        )
        container.add_action_row(ActionRowBuilder().add_select_menu(menu))

        built = container.build()
        reply_msg = await send_response(message, built)

        view_page = 0
        VIEW_PAGE_SIZE = 10

        async def render_view_container(target_type: str, page_idx: int):
            entries = BlacklistManager.list_blacklists(target_type)
            total_pages = max(1, math.ceil(len(entries) / VIEW_PAGE_SIZE))
            safe_page = max(0, min(page_idx, total_pages - 1))
            page_entries = entries[safe_page * VIEW_PAGE_SIZE : (safe_page + 1) * VIEW_PAGE_SIZE]

            if not entries:
                desc = f"{emojis['check']} No {target_type}s are currently blacklisted."
            else:
                lines = []
                for idx, e in enumerate(page_entries):
                    num = safe_page * VIEW_PAGE_SIZE + idx + 1
                    exp_ts = e.get("expiresAt") or e.get("expires_at")
                    exp = f"<t:{int(exp_ts)}:R>" if exp_ts else "`Permanent`"
                    t_id = e.get("targetId") or e.get("target_id")
                    target = f"<@{t_id}> (`{t_id}`)" if target_type == "user" else f"Guild `{t_id}`"
                    reason_val = e.get("reason", "Violation of terms")
                    lines.append(f"**{num}.** {target}\n  > **Reason:** {reason_val}\n  > **Expires:** {exp}")
                desc = "\n\n".join(lines)

            title = (
                f"{emojis['ban']} Globally Blacklisted Users ({len(entries)}) — Page {safe_page + 1}/{total_pages}"
                if target_type == "user"
                else f"{emojis['server']} Globally Blacklisted Servers ({len(entries)}) — Page {safe_page + 1}/{total_pages}"
            )

            box = (
                ContainerBuilder()
                .set_accent_color(colors["default"])
                .add_text_display(f"### {title}")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(desc)
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            )

            btn_row = ActionRowBuilder()
            btn_row.add_button(
                ButtonBuilder()
                .set_custom_id(f"{menu_id}:prev:{target_type}")
                .set_label("◀ Previous")
                .set_style(ButtonStyle.Secondary)
                .set_disabled(safe_page <= 0)
            )
            btn_row.add_button(
                ButtonBuilder()
                .set_custom_id(f"{menu_id}:next:{target_type}")
                .set_label("Next ▶")
                .set_style(ButtonStyle.Secondary)
                .set_disabled(safe_page >= total_pages - 1)
            )
            btn_row.add_button(
                ButtonBuilder()
                .set_custom_id(f"{menu_id}:back")
                .set_label("Back to Menu")
                .set_style(ButtonStyle.Secondary)
            )
            box.add_action_row(btn_row)
            return box.build(), safe_page

        collector = built.create_message_component_collector(
            target_message=reply_msg or message,
            timeout=120.0,
            filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == getattr(author, "id", None),
        )

        if collector:
            async def on_menu_change(inter):
                nonlocal view_page
                vals = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("values", [])
                val = vals[0] if vals else None
                if val == "view_users":
                    view_page = 0
                    b_cont, view_page = await render_view_container("user", 0)
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=b_cont.view)
                elif val == "view_servers":
                    view_page = 0
                    b_cont, view_page = await render_view_container("guild", 0)
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=b_cont.view)

            async def on_back(inter):
                if hasattr(inter, "response"):
                    await inter.response.edit_message(view=built.view)

            async def on_prev(inter):
                nonlocal view_page
                view_page = max(0, view_page - 1)
                t_type = "user" if "user" in getattr(inter, "data", {}).get("custom_id", "") else "guild"
                b_cont, view_page = await render_view_container(t_type, view_page)
                if hasattr(inter, "response"):
                    await inter.response.edit_message(view=b_cont.view)

            async def on_next(inter):
                nonlocal view_page
                view_page += 1
                t_type = "user" if "user" in getattr(inter, "data", {}).get("custom_id", "") else "guild"
                b_cont, view_page = await render_view_container(t_type, view_page)
                if hasattr(inter, "response"):
                    await inter.response.edit_message(view=b_cont.view)

            collector.on(menu_id, on_menu_change)
            collector.on(f"{menu_id}:back", on_back)
            collector.on(re.compile(rf"^{menu_id}:prev:"), on_prev)
            collector.on(re.compile(rf"^{menu_id}:next:"), on_next)
        return

    if sub == "list":
        users = BlacklistManager.list_blacklists("user")
        guilds = BlacklistManager.list_blacklists("guild")

        if not users and not guilds:
            return await reply(f"{emojis['check']} Empty Blacklist", "There are currently no users or servers blacklisted.", colors["success"])

        if not users:
            user_lines = "None"
        else:
            u_list = []
            for u in users[:10]:
                exp_ts = u.get("expiresAt") or u.get("expires_at")
                exp = f"<t:{int(exp_ts)}:R>" if exp_ts else "`Permanent`"
                t_id = u.get("targetId") or u.get("target_id")
                u_list.append(f"• <@{t_id}> (`{t_id}`)\n  > **Reason:** {u.get('reason')}\n  > **Status:** Active ({exp}) | Added by <@{u.get('adminId', author_id)}>")
            user_lines = "\n\n".join(u_list)

        if not guilds:
            guild_lines = "None"
        else:
            g_list = []
            for g in guilds[:10]:
                exp_ts = g.get("expiresAt") or g.get("expires_at")
                exp = f"<t:{int(exp_ts)}:R>" if exp_ts else "`Permanent`"
                t_id = g.get("targetId") or g.get("target_id")
                g_list.append(f"• Server `{t_id}`\n  > **Reason:** {g.get('reason')}\n  > **Status:** Active ({exp}) | Added by <@{g.get('adminId', author_id)}>")
            guild_lines = "\n\n".join(g_list)

        footer = "\n\n-# Showing top 10. Use `$blacklist user list [page]` or `$blacklist server list [page]` for more." if (len(users) > 10 or len(guilds) > 10) else ""

        return await reply(
            f"{emojis['shield']} Active Global Blacklists",
            f"**Blacklisted Users ({len(users)}):**\n{user_lines}\n\n**Blacklisted Servers ({len(guilds)}):**\n{guild_lines}{footer}",
            colors["default"]
        )

    is_user_target = (sub == "user")
    is_guild_target = (sub in ["server", "guild"])

    action = args[1].lower() if len(args) > 1 else None
    target_raw = args[2] if len(args) > 2 else None
    duration_arg = args[3] if len(args) > 3 else None
    reason_start_index = 4

    # Handle shorthand: `$blacklist user <@target> [duration] [reason]`
    if action and action not in ["add", "remove", "unblacklist", "list"]:
        target_raw = args[1]
        action = "add"
        duration_arg = args[2] if len(args) > 2 else None
        reason_start_index = 3

    if action == "list":
        t_type = "user" if is_user_target else "guild"
        entries = BlacklistManager.list_blacklists(t_type)
        if not entries:
            return await reply(f"{emojis['check']} Empty Blacklist", f"No {t_type}s are currently blacklisted in database.", colors["success"])

        safe_page = 1
        if len(args) > 2:
            try:
                safe_page = int(args[2])
            except ValueError:
                safe_page = 1

        page_size = 10
        total_pages = max(1, math.ceil(len(entries) / page_size))
        safe_page = max(1, min(safe_page, total_pages))

        def build_list_page(page_num: int):
            page_items = entries[(page_num - 1) * page_size : page_num * page_size]
            item_lines = []
            for idx, e in enumerate(page_items):
                exp_ts = e.get("expiresAt") or e.get("expires_at")
                exp = f"<t:{int(exp_ts)}:F> (<t:{int(exp_ts)}:R>)" if exp_ts else "`Permanent`"
                t_id = e.get("targetId") or e.get("target_id")
                target = f"<@{t_id}> (`{t_id}`)" if t_type == "user" else f"Server `{t_id}`"
                status = "Temporary" if exp_ts else "Permanent"
                item_lines.append(
                    f"**{(page_num - 1) * page_size + idx + 1}.** {target}\n"
                    f"   > **Reason:** {e.get('reason')}\n"
                    f"   > **Status:** Active ({status})\n"
                    f"   > **Admin:** <@{e.get('adminId', author_id)}>\n"
                    f"   > **Expires:** {exp}"
                )
            text = "\n\n".join(item_lines)

            box = (
                ContainerBuilder()
                .set_accent_color(colors["default"])
                .add_text_display(f"### {emojis['ban']} Blacklisted {'Users' if t_type == 'user' else 'Servers'} ({len(entries)}) — Page {page_num}/{total_pages}")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(text)
            )

            if total_pages > 1:
                box.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                row = ActionRowBuilder()
                row.add_button(
                    ButtonBuilder()
                    .set_custom_id(f"bl_sub_prev_{id(message)}")
                    .set_label("◀ Previous")
                    .set_style(ButtonStyle.Secondary)
                    .set_disabled(page_num <= 1)
                )
                row.add_button(
                    ButtonBuilder()
                    .set_custom_id(f"bl_sub_next_{id(message)}")
                    .set_label("Next ▶")
                    .set_style(ButtonStyle.Secondary)
                    .set_disabled(page_num >= total_pages)
                )
                box.add_action_row(row)

            return box.build()

        first_built = build_list_page(safe_page)
        list_msg = await send_response(message, first_built)

        if total_pages > 1:
            col = first_built.create_message_component_collector(
                target_message=list_msg or message,
                timeout=120.0,
                filter_func=lambda i: getattr(getattr(i, "user", None), "id", None) == getattr(author, "id", None),
            )
            if col:
                async def sub_prev(inter):
                    nonlocal safe_page
                    safe_page = max(1, safe_page - 1)
                    new_b = build_list_page(safe_page)
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=new_b.view)

                async def sub_next(inter):
                    nonlocal safe_page
                    safe_page = min(total_pages, safe_page + 1)
                    new_b = build_list_page(safe_page)
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=new_b.view)

                col.on(f"bl_sub_prev_{id(message)}", sub_prev)
                col.on(f"bl_sub_next_{id(message)}", sub_next)
        return

    target_id = resolve_target_id(target_raw)
    if not target_id:
        return await reply(
            f"{emojis['ban']} Invalid Target",
            f"Please provide a valid Discord {'user mention or ID' if is_user_target else 'guild ID'}.\nExample: `$blacklist {sub} add 123456789012345678 1d Spamming`",
            colors["error"]
        )

    if is_user_target and target_id in owner_ids:
        return await reply(f"{emojis['ban']} Action Disallowed", "You cannot blacklist a bot owner.", colors["error"])

    # REMOVE / UNBLACKLIST
    if action in ["remove", "unblacklist"]:
        if is_user_target:
            res = BlacklistManager.unblacklist_user(target_id, author_id)
            if not res.get("success"):
                return await reply(f"{emojis['ban']} Unblacklist Failed", res.get("error", "Failed to unblacklist user."), colors["error"])
            return await reply(
                f"{emojis['check']} User Unblacklisted",
                f"Successfully removed <@{target_id}> (`{target_id}`) from the global blacklist.",
                colors["success"]
            )
        else:
            res = BlacklistManager.unblacklist_guild(target_id, author_id)
            if not res.get("success"):
                return await reply(f"{emojis['ban']} Unblacklist Failed", res.get("error", "Failed to unblacklist server."), colors["error"])
            return await reply(
                f"{emojis['check']} Server Unblacklisted",
                f"Successfully removed server `{target_id}` from the global blacklist.",
                colors["success"]
            )

    # ADD BLACKLIST
    duration_str = None
    reason = "Violation of bot rules / terms of service"

    parsed_exp = parse_duration_str(duration_arg)
    if parsed_exp or (duration_arg and duration_arg.lower() in ["perm", "permanent", "never", "forever", "0"]):
        duration_str = duration_arg
        reason = " ".join(args[reason_start_index:]).strip() or reason
    else:
        reason = " ".join(args[reason_start_index - 1:]).strip() or reason

    if is_user_target:
        res = BlacklistManager.blacklist_user(target_id, duration=duration_str, reason=reason, admin_id=author_id)
        if not res.get("success"):
            return await reply(f"{emojis['ban']} Blacklist Failed", res.get("error", "Database error."), colors["error"])

        exp_val = res.get("entry", {}).get("expiresAt")
        expiry_text = f"<t:{int(exp_val)}:F> (<t:{int(exp_val)}:R>)" if exp_val else "`Permanent`"

        return await reply(
            f"{emojis['ban']} User Blacklisted Globally",
            f"• **Target User:** <@{target_id}> (`{target_id}`)\n"
            f"• **Reason:** {res.get('entry', {}).get('reason')}\n"
            f"• **Expires:** {expiry_text}\n"
            f"• **DM Notice:** Sent explanation message to the user.",
            colors["success"]
        )
    else:
        res = BlacklistManager.blacklist_guild(target_id, duration=duration_str, reason=reason, admin_id=author_id)
        if not res.get("success"):
            return await reply(f"{emojis['ban']} Blacklist Failed", res.get("error", "Database error."), colors["error"])

        exp_val = res.get("entry", {}).get("expiresAt")
        expiry_text = f"<t:{int(exp_val)}:F> (<t:{int(exp_val)}:R>)" if exp_val else "`Permanent`"

        return await reply(
            f"{emojis['ban']} Server Blacklisted Globally",
            f"• **Server ID:** `{target_id}`\n"
            f"• **Reason:** {res.get('entry', {}).get('reason')}\n"
            f"• **Expires:** {expiry_text}\n"
            f"• **DM Notice:** Sent explanation message to the server owner.",
            colors["success"]
        )
