import re
import math
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from core.security.server_commands import ServerCommandManager
from apps.bot.discord.permissions.permission import Permissions
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    SeparatorSpacingSize,
)

from discord import MessageFlags, ButtonStyle

PAGE_SIZE = 8

name = "command-manage"
aliases = ["command", "cmdmanage", "cmds", "commandmanage"]
description = "Configure which bot commands are enabled or disabled in this server."
category = "Moderation"
usage = "command-manage [list [page] | disable <cmd> | enable <cmd>]"
user_permissions = [Permissions.MANAGE_GUILD]
bot_permissions = [Permissions.SEND_MESSAGES]
cooldown = 3.0

sub_commands = [
    {"name": "list [page]", "description": "List all commands and their per-server enabled/disabled status."},
    {"name": "disable <command>", "description": "Disable a command for regular members in this server."},
    {"name": "enable <command>", "description": "Re-enable a previously disabled command in this server."},
]

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    guild = getattr(message, "guild", None)

    if not guild:
        text = "❌ This command can only be used inside a Discord server."
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(text, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(text)
        return

    user = getattr(message, "author", None) or getattr(message, "user", None)
    member = getattr(message, "member", None) or (await guild.fetch_member(user.id) if user and hasattr(guild, "fetch_member") else None)

    # Permission check: ManageGuild or Administrator
    has_admin = False
    if member:
        perms = getattr(member, "guild_permissions", None) or getattr(member, "permissions", None)
        if perms:
            has_admin = bool(getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False))

    colors = COLORS
    c_error = colors.get("error", "#EF4444")
    c_success = colors.get("success", "#10B981")
    c_default = colors.get("default", "#5865F2")

    if not has_admin:
        deny_box = (
            ContainerBuilder()
            .set_accent_color(c_error)
            .add_text_display("### 🚫 Permission Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("You need **Manage Server** or **Administrator** permissions to manage server commands.")
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=deny_box.embed, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(embed=deny_box.embed)
        return

    subcommand = args[0].lower() if args else None
    target_cmd = args[1].lower() if len(args) > 1 else None

    # Handle direct subcommands: disable / enable
    if subcommand == "disable" and target_cmd:
        result = ServerCommandManager.disable_command(str(guild.id), target_cmd, str(user.id) if user else None)
        box = (
            ContainerBuilder()
            .set_accent_color(c_success if result.get("success") else c_error)
            .add_text_display(f"### {'✅ Command Disabled' if result.get('success') else '❌ Action Failed'}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(result.get("message", ""))
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=box.embed)
        elif hasattr(message, "reply"):
            return await message.reply(embed=box.embed)
        return

    if subcommand == "enable" and target_cmd:
        result = ServerCommandManager.enable_command(str(guild.id), target_cmd, str(user.id) if user else None)
        box = (
            ContainerBuilder()
            .set_accent_color(c_success if result.get("success") else c_error)
            .add_text_display(f"### {'✅ Command Re-Enabled' if result.get('success') else '❌ Action Failed'}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(result.get("message", ""))
            .build()
        )
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(embed=box.embed)
        elif hasattr(message, "reply"):
            return await message.reply(embed=box.embed)
        return

    # Interactive Panel with Pagination & Select Menu
    page = 0
    if subcommand == "list" and len(args) > 1:
        try:
            p = int(args[1])
            if p >= 1:
                page = p - 1
        except ValueError:
            pass

    prefix = f"cmdmgmt_{user.id if user else '0'}_{id(message)}"

    async def render_panel(current_page: int):
        all_commands = ServerCommandManager.get_all_manageable_commands()
        guild_settings = ServerCommandManager.get_guild_settings(str(guild.id))
        disabled_commands = guild_settings.get("disabledCommands", set())

        total_pages = max(1, math.ceil(len(all_commands) / PAGE_SIZE))
        safe_page = max(0, min(current_page, total_pages - 1))

        page_commands = all_commands[safe_page * PAGE_SIZE : (safe_page + 1) * PAGE_SIZE]

        container = (
            ContainerBuilder()
            .set_accent_color(c_default)
            .add_text_display(f"### ⚙️ Server Command Management — {guild.name}")
            .add_text_display(
                f"Configure which commands are active in **{guild.name}**.\n\n"
                f"• **Total Manageable Commands:** `{len(all_commands)}`\n"
                f"• **Currently Disabled in Server:** `{len(disabled_commands)}`\n"
                f"• **Page:** `{safe_page + 1} of {total_pages}`"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("**Command Status Table**")
        )

        for cmd in page_commands:
            c_name = cmd.get("name", "")
            is_disabled = (c_name.lower() in disabled_commands)
            status_badge = (
                "🔒 `ESSENTIAL (Protected)`"
                if cmd.get("essential")
                else ("🔴 `DISABLED`" if is_disabled else "🟢 `ENABLED`")
            )
            desc_text = cmd.get("description", "")[:100]
            container.add_text_display(
                f"• **/{c_name}** [{cmd.get('category', 'General')}] — {status_badge}\n"
                f"  -# {desc_text}"
            )

        # Quick Toggle Select Menu on current page
        toggleable = [c for c in page_commands if not c.get("essential")]
        if toggleable:
            container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            container.add_text_display(
                "**Quick Toggle Command**\nSelect a command from this page to toggle its enabled/disabled status in this server."
            )
            menu_options = []
            for c in toggleable:
                c_name = c.get("name", "")
                is_dis = (c_name.lower() in disabled_commands)
                menu_options.append({
                    "label": f"/{c_name} ({'Disabled' if is_dis else 'Enabled'})",
                    "description": f"Click to enable /{c_name}" if is_dis else f"Click to disable /{c_name}",
                    "value": c_name,
                    "emoji": "🟢" if is_dis else "🔴",
                })

            container.add_action_row(
                ActionRowBuilder().add_select_menu(
                    SelectMenuBuilder()
                    .set_custom_id(f"{prefix}:toggle_select")
                    .set_menu_type(SelectMenuTypes.CUSTOM)
                    .set_placeholder("Select command to toggle...")
                    .set_min_values(1)
                    .set_max_values(1)
                    .set_options(menu_options)
                )
            )

        # Navigation row
        container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        nav_row = ActionRowBuilder()
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{prefix}:prev")
            .set_label("◀ Previous")
            .set_style(ButtonStyle.Secondary)
            .set_disabled(safe_page <= 0)
        )
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{prefix}:next")
            .set_label("Next ▶")
            .set_style(ButtonStyle.Secondary)
            .set_disabled(safe_page >= total_pages - 1)
        )
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"{prefix}:refresh")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
        )
        container.add_action_row(nav_row)

        container.add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        container.add_text_display(
            "-# Essential moderation and configuration commands are locked and cannot be disabled to prevent accidental lockouts."
        )

        return container.build(), safe_page, total_pages

    built, page, total_pages = await render_panel(page)

    view = built.view
    reply_msg = None
    if is_slash and hasattr(message, "response") and not message.response.is_done():
        reply_msg = await message.response.send_message(embed=built.embed, view=view)
    elif hasattr(message, "reply"):
        reply_msg = await message.reply(embed=built.embed, view=view)

    target_msg = reply_msg or message
    collector = built.create_message_component_collector(
        target_message=target_msg,
        timeout=300.0,
        filter_func=lambda inter: (getattr(getattr(inter, "user", None), "id", None) == getattr(user, "id", None)),
    )

    if collector:
        async def on_prev(inter):
            nonlocal page
            page = max(0, page - 1)
            updated, page, _ = await render_panel(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        async def on_next(inter):
            nonlocal page
            all_cmds = ServerCommandManager.get_all_manageable_commands()
            t_pages = max(1, math.ceil(len(all_cmds) / PAGE_SIZE))
            if page < t_pages - 1:
                page += 1
            updated, page, _ = await render_panel(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        async def on_refresh(inter):
            updated, page_val, _ = await render_panel(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        async def on_toggle(inter):
            values = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("values", [])
            selected_cmd = values[0] if values else None
            if selected_cmd:
                guild_settings = ServerCommandManager.get_guild_settings(str(guild.id))
                disabled_commands = guild_settings.get("disabledCommands", set())
                if selected_cmd.lower() in disabled_commands:
                    ServerCommandManager.enable_command(str(guild.id), selected_cmd, str(user.id) if user else None)
                else:
                    ServerCommandManager.disable_command(str(guild.id), selected_cmd, str(user.id) if user else None)
            updated, page_val, _ = await render_panel(page)
            if hasattr(inter, "response"):
                await inter.response.edit_message(embed=updated.embed, view=updated.view)

        collector.on(f"{prefix}:prev", on_prev)
        collector.on(f"{prefix}:next", on_next)
        collector.on(f"{prefix}:refresh", on_refresh)
        collector.on(f"{prefix}:toggle_select", on_toggle)
