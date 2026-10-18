import sys
import os
import time
from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType

name = "botinfo"
aliases = ["info", "stats", "system"]
description = "View systems architecture, framework specifications, and operational metrics."
category = "General"
usage = "botinfo"
cooldown = 5.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    client = getattr(ctx, "client", getattr(message, "client", None))

    guild_count = len(client.guilds) if (client and hasattr(client, "guilds")) else 0
    ping = round(client.latency * 1000, 1) if (client and hasattr(client, "latency") and client.latency is not None) else 0.0

    # Process memory
    try:
        import resource
        mem_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:
        mem_mb = 42.0

    title = get_string("commands.botinfo.title", "MomentumOne Systems Architecture")
    platform_str = get_string("commands.botinfo.platform", "• **Framework:** Modular Enterprise Engine")
    version_str = get_string("commands.botinfo.version", "• **Release:** v{version}", version="26.7.20")
    memory_str = get_string("commands.botinfo.memory", "• **Memory Allocation:** `{memory} MB`", memory=mem_mb)
    guilds_str = get_string("commands.botinfo.guilds", "• **Connected Guilds:** `{guild_count}`", guild_count=guild_count)
    ping_str = get_string("commands.botinfo.ping", "• **Gateway Socket:** `{ping}ms`", ping=ping)

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### ⚙️ {title}")
        .add_separator()
        .add_text_display(f"{platform_str}\n{version_str}\n{memory_str}\n{guilds_str}\n{ping_str}")
        .set_footer("MomentumOne Control Platform")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
    elif hasattr(message, "channel"):
        await message.channel.send(embed=embed)
