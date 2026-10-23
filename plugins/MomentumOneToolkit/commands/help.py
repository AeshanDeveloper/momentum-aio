from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, build_ui
from sdk.discord.response import send_response, send_ui
from apps.bot.discord.commands.registry import commands_registry
from shared.types.command_record import CommandType

name = "help"
aliases = ["h", "commands"]
description = "Browse commands and view detailed help."
category = "Utility"
usage = "help [command]"
cooldown = 3.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    query = (args[0].lower().strip() if args else None)

    if query:
        cmd = commands_registry.get(query)
        if cmd:
            title = get_string("commands.help.command_detail_title", name=cmd.name)
            usage_str = get_string("commands.help.usage", usage=cmd.usage or cmd.name)
            aliases_str = get_string("commands.help.aliases", aliases=", ".join(cmd.aliases) if cmd.aliases else "None")
            cooldown_str = get_string("commands.help.cooldown", cooldown=cmd.cooldown)
            perms_str = get_string("commands.help.permissions", permissions="Owner" if cmd.owner_only else "General")

            view = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", COLORS.get("default", "#0844C5")))
                .add_text_display(f"### {title}")
                .add_separator()
                .add_text_display(f"{cmd.description}\n\n{usage_str}\n{aliases_str}\n{cooldown_str}\n{perms_str}")
                .build()
            )
            return await send_response(message, view)
        else:
            return await send_ui(message, "commands.help.not_found", variables={"name": query}, ephemeral=True, style="warning")

    # Category overview
    all_cmds = commands_registry.list_all()
    categories = {}
    for c in all_cmds:
        if c.hidden:
            continue
        cat = c.category.title() or "General"
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f"`{c.name}`")

    title = get_string("commands.help.title")
    desc = get_string("commands.help.description")

    builder = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("cmd_help", COLORS.get("default", "#0844C5")))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display(desc)
    )

    for cat_name, cmd_list in sorted(categories.items()):
        label = get_string("commands.help.category_label", category=cat_name)
        builder.add_field(f"{label} ({len(cmd_list)})", " ".join(cmd_list), inline=False)

    view = builder.build()
    return await send_response(message, view)
