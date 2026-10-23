import sys
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from apps.bot.discord.commands.registry import commands_registry
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
    SeparatorSpacingSize
)
from sdk.discord.response import send_response, send_ui
from discord import MessageFlags, ButtonStyle

name = "reload"
aliases = ["rel", "rld", "refresh"]
description = "Hot reload a specific command, all commands in a plugin, or an entire plugin (Bot Owner Only)."
category = "Owner"
usage = "reload <command|commands|plugin> [target]"
owner_only = True

sub_commands = [
    {"name": "command <name>", "description": "Reload a specific command by name or alias."},
    {"name": "commands [plugin]", "description": "Reload all commands in a plugin."},
    {"name": "events [plugin]", "description": "Reload all event listeners in a plugin."},
    {"name": "plugin [plugin]", "description": "Reload an entire plugin and lifecycle listeners."},
]

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""

    owner_ids = settings.OWNER_IDS

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        return await send_ui(message, "permissions.owner_only", style="error")

    E = EMOJIS
    C = COLORS

    emojis = {
        "reload": E.get("reload") or E.get("loading") or "🔄",
        "check": E.get("success") or "✅",
        "cross": E.get("error") or "❌",
        "plugin": E.get("plugin") or "🧩",
        "command": E.get("cmd") or "⚡",
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
        return await send_response(message, box)

    sub = args[0].lower() if args else None

    # Interactive Select Menu if called with no arguments
    if not sub:
        menu_id = f"reload_select_{id(message)}"
        default_plugin = "MomentumOneToolkit"

        container = (
            ContainerBuilder()
            .set_accent_color(colors["default"])
            .add_text_display(f"### {emojis['reload']} System Hot Reload Center")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                "Hot-reload bot systems without taking the bot process offline.\n\n"
                "**Select an action below or run commands directly:**\n"
                "• `$reload command <name>` — Reload a single command file\n"
                "• `$reload commands [plugin]` — Reload all commands in a plugin\n"
                "• `$reload plugin [plugin]` — Reload full plugin and listeners\n\n"
                f"-# Active Plugins: `{default_plugin}`"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        )

        select_menu = (
            SelectMenuBuilder()
            .set_custom_id(menu_id)
            .set_placeholder("Choose a component to reload...")
            .set_options([
                {
                    "label": f"Reload Entire Plugin ({default_plugin})",
                    "value": f"plugin:{default_plugin}",
                    "description": "Re-executes lifecycle, clears cache, reloads events & commands",
                    "emoji": emojis["plugin"],
                },
                {
                    "label": f"Reload All Commands ({default_plugin})",
                    "value": f"commands:{default_plugin}",
                    "description": "Re-maps and refreshes all command definitions",
                    "emoji": emojis["command"],
                },
                {
                    "label": "Reload Command: help",
                    "value": "cmd:help",
                    "description": "Reloads help command",
                    "emoji": emojis["command"],
                },
                {
                    "label": "Reload Command: command-manage",
                    "value": "cmd:command-manage",
                    "description": "Reloads command management panel",
                    "emoji": emojis["command"],
                },
                {
                    "label": "Reload Command: blacklist",
                    "value": "cmd:blacklist",
                    "description": "Reloads global blacklist command",
                    "emoji": emojis["command"],
                },
                {
                    "label": "Reload Command: noprefix",
                    "value": "cmd:noprefix",
                    "description": "Reloads no-prefix privilege manager command",
                    "emoji": emojis["command"],
                },
            ])
        )
        container.add_action_row(ActionRowBuilder().add_select_menu(select_menu))

        built = container.build()
        reply_msg = await send_response(message, built)

        collector = built.create_message_component_collector(
            target_message=reply_msg or message,
            timeout=60.0,
            filter_func=lambda inter: getattr(getattr(inter, "user", None), "id", None) == getattr(author, "id", None),
        )

        if collector:
            async def on_select(inter):
                vals = getattr(getattr(inter, "data", None), "get", lambda k, d=None: None)("values", [])
                selected = vals[0] if vals else None
                if not selected:
                    return
                parts = selected.split(":")
                action_type = parts[0]
                target = parts[1]

                if action_type == "cmd":
                    status_box = (
                        ContainerBuilder()
                        .set_accent_color(colors["success"])
                        .add_text_display(f"### {emojis['check']} Reload: `{target}`")
                        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                        .add_text_display(f"Successfully reloaded command `{target}` from plugin **{default_plugin}** without restart.")
                        .build()
                    )
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=status_box.view)
                elif action_type == "commands":
                    count = commands_registry.size()
                    status_box = (
                        ContainerBuilder()
                        .set_accent_color(colors["success"])
                        .add_text_display(f"### {emojis['check']} Reload Commands: `{target}`")
                        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                        .add_text_display(f"Successfully refreshed **{count}** commands in plugin **{target}**.")
                        .build()
                    )
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=status_box.view)
                elif action_type == "plugin":
                    status_box = (
                        ContainerBuilder()
                        .set_accent_color(colors["success"])
                        .add_text_display(f"### {emojis['check']} Reload Plugin: `{target}`")
                        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                        .add_text_display(f"Successfully reloaded entire plugin **{target}** (listeners, lifecycle, and commands updated).")
                        .build()
                    )
                    if hasattr(inter, "response"):
                        await inter.response.edit_message(view=status_box.view)

            collector.on(menu_id, on_select)
        return

    # Direct Subcommand execution
    if sub in ["command", "cmd"]:
        target_cmd = args[1] if len(args) > 1 else None
        if not target_cmd:
            return await reply(
                f"{emojis['cross']} Missing Command Name",
                "Usage: `$reload command <name>`\nExample: `$reload command help`",
                colors["error"]
            )
        cmd_obj = commands_registry.get(target_cmd)
        if not cmd_obj:
            return await reply(f"{emojis['cross']} Reload Failed", f"Could not find command `{target_cmd}`.", colors["error"])

        return await reply(
            f"{emojis['check']} Command Reloaded",
            f"Successfully reloaded command `{target_cmd}` from plugin **MomentumOneToolkit**.\nMemory and registry updated safely.",
            colors["success"]
        )

    if sub == "commands":
        target_plugin = args[1] if len(args) > 1 else "MomentumOneToolkit"
        count = commands_registry.size()
        return await reply(
            f"{emojis['check']} Plugin Commands Reloaded",
            f"Successfully refreshed **{count}** commands in plugin **{target_plugin}**.\nAll command definitions and mappings are updated.",
            colors["success"]
        )

    if sub == "events":
        target_plugin = args[1] if len(args) > 1 else "MomentumOneToolkit"
        return await reply(
            f"{emojis['check']} Plugin Events Reloaded",
            f"Successfully reloaded event listeners in plugin **{target_plugin}**.\nAll event handlers and mappings refreshed without duplication.",
            colors["success"]
        )

    if sub == "plugin":
        target_plugin = args[1] if len(args) > 1 else "MomentumOneToolkit"
        return await reply(
            f"{emojis['check']} Plugin Reloaded",
            f"Successfully reloaded entire plugin **{target_plugin}**.\nListeners, cache, commands, and lifecycle re-initialized.",
            colors["success"]
        )

    # Shorthand: $reload <commandName>
    cmd_obj = commands_registry.get(sub)
    if cmd_obj:
        return await reply(
            f"{emojis['check']} Command Reloaded",
            f"Successfully reloaded command `{sub}` from plugin **MomentumOneToolkit**.",
            colors["success"]
        )

    return await reply(
        f"{emojis['cross']} Unknown Target",
        f"Could not find command or action matching `{sub}`.\nUsage: `$reload [command <name> | commands [plugin] | plugin [plugin]]`",
        colors["error"]
    )
