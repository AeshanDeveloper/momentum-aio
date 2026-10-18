import time
import math
from typing import List, Dict, Any, Optional
import discord
from config.settings import config
from core.logging.logger import logger
from core.security.server_commands import ServerCommandManager
from apps.bot.discord.permissions.permission import Permissions
from apps.bot.discord.commands.registry import commands_registry
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    ButtonStyle,
    SeparatorSpacingSize,
    MessageFlags,
    attach_collector,
)
from shared.types.command_record import CommandType

PAGE_SIZE = 8

name = "command-manage"
aliases = ["command", "cmdmanage", "cmds", "commandmanage"]
description = "Configure which bot commands are enabled or disabled in this server."
category = "Moderation"
usage = "command-manage [list [page] | disable <cmd> | enable <cmd>]"
user_permissions = [Permissions.MANAGE_GUILD]
bot_permissions = [Permissions.SEND_MESSAGES]
cooldown = 3.0
guild_only = True

sub_commands = [
    {"name": "list [page]", "description": "List all commands and their per-server enabled/disabled status."},
    {"name": "disable <command>", "description": "Disable a command for regular members in this server."},
    {"name": "enable <command>", "description": "Re-enable a previously disabled command in this server."},
]

async def execute(ctx: Any, commandType: Any, message: Any, args: Optional[List[str]] = None):
    args = args or []
    isSlash = (commandType == CommandType.SLASH or str(commandType).lower() == "slash")

    guild = getattr(message, "guild", None)
    if not guild:
        text = "❌ This command can only be used inside a Discord server."
        if isSlash and hasattr(message, "response"):
            await message.response.send_message(text, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(text)
        return

    if isSlash:
        user = getattr(message, "user", None)
        member = getattr(message, "member", None) or getattr(guild, "get_member", lambda _: None)(user.id if user else 0)
    else:
        user = getattr(message, "author", None)
        member = getattr(message, "author", None)

    userId = str(user.id) if user else "system"

    # Permission check: Manage Server or Administrator
    hasAdmin = False
    if hasattr(member, "guild_permissions"):
        gp = member.guild_permissions
        hasAdmin = bool(getattr(gp, "administrator", False) or getattr(gp, "manage_guild", False))
    elif hasattr(member, "permissions"):
        p = member.permissions
        hasAdmin = bool(getattr(p, "administrator", False) or getattr(p, "manage_guild", False))
    else:
        # Fallback to true if bot owner or direct permissions check
        from apps.bot.discord.permissions.resolver import is_bot_owner
        hasAdmin = is_bot_owner(userId)

    colors = config.Colors or {}

    if not hasAdmin:
        deny_color = colors.get("error", "#EF4444")
        denyBox = (
            ContainerBuilder()
            .setAccentColor(deny_color)
            .addTextDisplay("### 🚫 Permission Denied")
            .addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
            .addTextDisplay("You need **Manage Server** or **Administrator** permissions to manage server commands.")
            .build()
        )
        if isSlash and hasattr(message, "response"):
            await message.response.send_message(embed=denyBox, view=denyBox.view, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(embed=denyBox, view=denyBox.view)
        return

    # Handle direct subcommands
    subcommand = None
    targetCmd = None

    if isSlash and hasattr(message, "data") and isinstance(message.data, dict):
        options = message.data.get("options", [])
        if options and isinstance(options[0], dict) and options[0].get("type") == 1:
            subcommand = options[0].get("name", "").lower()
            sub_opts = options[0].get("options", [])
            for opt in sub_opts:
                if opt.get("name") == "command":
                    targetCmd = str(opt.get("value", "")).lower()

    if not subcommand and args:
        subcommand = args[0].lower()
        if len(args) > 1:
            targetCmd = args[1].lower()

    success_color = colors.get("success", "#10B981")
    error_color = colors.get("error", "#EF4444")

    if subcommand == "disable" and targetCmd:
        result = ServerCommandManager.disable_command(str(guild.id), targetCmd, userId)
        is_succ = bool(result.get("success", False)) if isinstance(result, dict) else bool(result)
        msg_text = result.get("message", "") if isinstance(result, dict) else str(result)
        box = (
            ContainerBuilder()
            .setAccentColor(success_color if is_succ else error_color)
            .addTextDisplay(f"### {'✅ Command Disabled' if is_succ else '❌ Action Failed'}")
            .addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
            .addTextDisplay(msg_text)
            .build()
        )
        if isSlash and hasattr(message, "response"):
            await message.response.send_message(embed=box, view=box.view)
        elif hasattr(message, "reply"):
            await message.reply(embed=box, view=box.view)
        return

    if subcommand == "enable" and targetCmd:
        result = ServerCommandManager.enable_command(str(guild.id), targetCmd, userId)
        is_succ = bool(result.get("success", False)) if isinstance(result, dict) else bool(result)
        msg_text = result.get("message", "") if isinstance(result, dict) else str(result)
        box = (
            ContainerBuilder()
            .setAccentColor(success_color if is_succ else error_color)
            .addTextDisplay(f"### {'✅ Command Re-Enabled' if is_succ else '❌ Action Failed'}")
            .addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
            .addTextDisplay(msg_text)
            .build()
        )
        if isSlash and hasattr(message, "response"):
            await message.response.send_message(embed=box, view=box.view)
        elif hasattr(message, "reply"):
            await message.reply(embed=box, view=box.view)
        return

    # Interactive Panel
    page = 0
    if subcommand == "list" and len(args) > 1:
        try:
            p = int(args[1])
            if p >= 1:
                page = p - 1
        except ValueError:
            pass

    prefix = f"cmdmgmt_{userId}_{int(time.time() * 1000)}"

    def renderPanel(current_page: int) -> Any:
        allCommands = ServerCommandManager.get_all_manageable_commands()
        settings = ServerCommandManager.get_guild_settings(str(guild.id))
        disabledCommands = settings.get("disabledCommands", set())

        totalPages = max(1, math.ceil(len(allCommands) / PAGE_SIZE))
        active_page = max(0, min(current_page, totalPages - 1))

        pageCommands = allCommands[active_page * PAGE_SIZE : (active_page + 1) * PAGE_SIZE]

        default_color = colors.get("default", "#5865F2")
        container = (
            ContainerBuilder()
            .setAccentColor(default_color)
            .addTextDisplay(f"### ⚙️ Server Command Management — {guild.name}")
            .addTextDisplay(
                f"Configure which commands are active in **{guild.name}**.\n\n"
                f"• **Total Manageable Commands:** `{len(allCommands)}`\n"
                f"• **Currently Disabled in Server:** `{len(disabledCommands)}`\n"
                f"• **Page:** `{active_page + 1} of {totalPages}`"
            )
            .addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
        )

        container.addTextDisplay("**Command Status Table**")
        for cmd in pageCommands:
            isDis = (cmd["name"].lower() in disabledCommands)
            if cmd["essential"]:
                statusBadge = "🔒 `ESSENTIAL (Protected)`"
            elif isDis:
                statusBadge = "🔴 `DISABLED`"
            else:
                statusBadge = "🟢 `ENABLED`"

            container.addTextDisplay(
                f"• **/{cmd['name']}** [{cmd['category']}] — {statusBadge}\n"
                f"  -# {cmd['description'][:100]}"
            )

        # Interactive Select Menu for quick toggling on current page
        toggleable = [c for c in pageCommands if not c["essential"]]
        if toggleable:
            container.addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
            container.addTextDisplay(
                "**Quick Toggle Command**\n"
                "Select a command from this page to toggle its enabled/disabled status in this server."
            )

            options_list = []
            for c in toggleable:
                is_dis = (c["name"].lower() in disabledCommands)
                options_list.append({
                    "label": f"/{c['name']} ({'Disabled' if is_dis else 'Enabled'})",
                    "description": f"Click to {'enable' if is_dis else 'disable'} /{c['name']}",
                    "value": c["name"],
                    "emoji": "🟢" if is_dis else "🔴",
                })

            def populate_select(row: ActionRowBuilder) -> ActionRowBuilder:
                row.addSelectMenu({
                    "custom_id": f"{prefix}:toggle_select",
                    "type": SelectMenuTypes.CUSTOM,
                    "placeholder": "Select command to toggle...",
                    "minValues": 1,
                    "maxValues": 1,
                    "options": options_list,
                })
                return row

            container.addActionRow(populate_select)

        # Navigation row
        container.addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})

        def populate_nav(row: ActionRowBuilder) -> ActionRowBuilder:
            row.addButton({
                "custom_id": f"{prefix}:prev",
                "label": "◀ Previous",
                "style": ButtonStyle.Secondary,
                "disabled": active_page <= 0,
            })
            row.addButton({
                "custom_id": f"{prefix}:next",
                "label": "Next ▶",
                "style": ButtonStyle.Secondary,
                "disabled": active_page >= totalPages - 1,
            })
            row.addButton({
                "custom_id": f"{prefix}:refresh",
                "label": "Refresh",
                "style": ButtonStyle.Secondary,
            })
            return row

        container.addActionRow(populate_nav)

        container.addSeparator({"divider": True, "spacing": SeparatorSpacingSize.Small})
        container.addTextDisplay(
            "-# Essential moderation and configuration commands are locked and cannot be disabled to prevent accidental lockouts."
        )

        return container.build(), active_page

    initial_panel, current_page = renderPanel(page)

    sent = None
    if isSlash and hasattr(message, "response"):
        if message.response.is_done():
            sent = await message.followup.send(embed=initial_panel, view=initial_panel.view)
        else:
            await message.response.send_message(embed=initial_panel, view=initial_panel.view)
            sent = message
    elif hasattr(message, "reply"):
        sent = await message.reply(embed=initial_panel, view=initial_panel.view)
    elif hasattr(message, "channel"):
        sent = await message.channel.send(embed=initial_panel, view=initial_panel.view)

    # Attach interactive collector
    state = {"page": current_page, "panel": initial_panel}

    def interaction_filter(i: Any) -> bool:
        u_id = getattr(i.user, "id", None)
        return str(u_id) == str(userId)

    collector = attach_collector(
        sent,
        view=initial_panel.view,
        time_ms=300_000,
        filter_fn=interaction_filter
    )

    async def on_collect(i: Any):
        try:
            custom_id = getattr(i, "customId", "") or i.data.get("custom_id", "")
            if not custom_id.startswith(prefix):
                return

            parts = custom_id.split(":")
            if len(parts) < 2:
                return
            action = parts[1]

            if action == "prev":
                state["page"] = max(0, state["page"] - 1)
                new_panel, state["page"] = renderPanel(state["page"])
                state["panel"] = new_panel
                await i.update({"components": [new_panel]})
                collector.view = new_panel.view
                collector._wire_view(new_panel.view)
                return

            if action == "next":
                allCommands = ServerCommandManager.get_all_manageable_commands()
                totalPages = max(1, math.ceil(len(allCommands) / PAGE_SIZE))
                if state["page"] < totalPages - 1:
                    state["page"] += 1
                new_panel, state["page"] = renderPanel(state["page"])
                state["panel"] = new_panel
                await i.update({"components": [new_panel]})
                collector.view = new_panel.view
                collector._wire_view(new_panel.view)
                return

            if action == "refresh":
                new_panel, state["page"] = renderPanel(state["page"])
                state["panel"] = new_panel
                await i.update({"components": [new_panel]})
                collector.view = new_panel.view
                collector._wire_view(new_panel.view)
                return

            if action == "toggle_select":
                vals = getattr(i, "values", []) or i.data.get("values", [])
                if vals:
                    selectedCmd = vals[0]
                    settings = ServerCommandManager.get_guild_settings(str(guild.id))
                    disabledCommands = settings.get("disabledCommands", set())
                    if selectedCmd.lower() in disabledCommands:
                        ServerCommandManager.enable_command(str(guild.id), selectedCmd, userId)
                    else:
                        ServerCommandManager.disable_command(str(guild.id), selectedCmd, userId)

                    new_panel, state["page"] = renderPanel(state["page"])
                    state["panel"] = new_panel
                    await i.update({"components": [new_panel]})
                    collector.view = new_panel.view
                    collector._wire_view(new_panel.view)
                    return

        except Exception as err:
            logger.error(f"[CommandManage] Interaction error: {err}")
            if not i.response.is_done():
                await i.response.send_message("An error occurred while updating the panel.", ephemeral=True)

    collector.on("collect", on_collect)
    return sent
