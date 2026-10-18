from typing import List, Any
import discord
from config.settings import settings, COLORS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "listservers"
aliases = ["guilds", "servers"]
description = "List all servers connected to this bot instance."
category = "Dev"
usage = "listservers"
cooldown = 3.0
owner_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)

    if not is_bot_owner(author.id):
        err = get_string("permissions.owner_only", "❌ Access Denied: This command is strictly reserved for the global bot owner.")
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    client = getattr(ctx, "client", getattr(message, "client", None))
    guilds = list(client.guilds) if client else []
    title = get_string("commands.dev.listservers_title", "🌐 Connected Servers ({count} Total)", count=len(guilds))

    lines = []
    for g in guilds[:25]:
        lines.append(f"• **{g.name}** (`{g.id}`) — {g.member_count or len(g.members)} members")

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display("\n".join(lines) if lines else "No connected servers.")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
