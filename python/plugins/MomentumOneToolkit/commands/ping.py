import time
from typing import List, Any
import discord

from config.settings import COLORS, EMOJIS
from database.database import database
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
from shared.types.command_record import CommandType

name = "ping"
aliases = ["latency", "pong"]
description = "Check bot connectivity, gateway latency, and database responsiveness."
category = "Utility"
usage = "ping"
cooldown = 3.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    colors = COLORS
    c_default = colors.get("default", "#FF7B00")

    online_icon = EMOJIS.get("online") or EMOJIS.get("success") or "🟢"
    ping_icon = EMOJIS.get("ping") or EMOJIS.get("latency") or "📡"
    ws_icon = EMOJIS.get("latency") or "⚡"
    db_icon = EMOJIS.get("database") or "💾"

    client = getattr(ctx, "client", getattr(message, "client", None))
    start = time.time()

    # Measure real database ping
    db_start = time.time()
    db_ok = await database.ping()
    db_ms = round((time.time() - db_start) * 1000, 1) if db_ok else None

    roundtrip = round((time.time() - start) * 1000, 1)
    gateway_ping = (
        f"{round(client.latency * 1000, 1)}ms"
        if (client and hasattr(client, "latency") and client.latency is not None and client.latency >= 0)
        else "Connecting..."
    )
    db_ping_str = f"{db_ms}ms" if db_ms is not None else "Unavailable"

    container = (
        ContainerBuilder()
        .set_accent_color(c_default)
        .add_text_display(f"### {ping_icon} Bot Connectivity Status")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"• **Status:** {online_icon} `Online`\n"
            f"• **Message Roundtrip:** `{roundtrip}ms`\n"
            f"• **Gateway Heartbeat:** {ws_icon} `{gateway_ping}`\n"
            f"• **Database Response:** {db_icon} `{db_ping_str}`"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display("-# Metrics represent live cluster & socket health.")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        if message.response.is_done():
            await message.followup.send(embed=container.embed)
        else:
            await message.response.send_message(embed=container.embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=container.embed)
    elif hasattr(message, "channel"):
        await message.channel.send(embed=container.embed)
