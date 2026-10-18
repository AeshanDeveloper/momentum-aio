import time
import discord
from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from database.database import database
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType

name = "ping"
aliases = ["latency", "pong"]
description = "Check bot connectivity, gateway latency, and database responsiveness."
category = "Utility"
usage = "ping"
cooldown = 3.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    client = getattr(ctx, "client", getattr(message, "client", None))
    start = time.time()

    # Measure DB latency
    db_start = time.time()
    db_ok = await database.ping()
    db_ms = round((time.time() - db_start) * 1000, 1) if db_ok else "Unavailable"

    roundtrip = round((time.time() - start) * 1000, 1)
    gateway_ping = (
        f"{round(client.latency * 1000, 1)}ms"
        if (client and hasattr(client, "latency") and client.latency is not None and client.latency >= 0)
        else "Connecting..."
    )

    title = get_string("commands.ping.title", "🟢 Systems Operational")
    roundtrip_str = get_string("commands.ping.roundtrip", "• **Message Roundtrip:** `{roundtrip}ms`", roundtrip=roundtrip)
    gateway_str = get_string("commands.ping.gateway", "• **Gateway Heartbeat:** `{heartbeat}`", heartbeat=gateway_ping)
    db_str = get_string("commands.ping.database", "• **Database Response:** `{db_latency}`", db_latency=f"{db_ms}ms" if isinstance(db_ms, (int, float)) else str(db_ms))
    footer_str = get_string("commands.ping.footer", "Metrics represent live cluster & socket health.")

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {EMOJIS.get('ping', '📡')} {title}")
        .add_separator()
        .add_text_display(f"{roundtrip_str}\n{gateway_str}\n{db_str}")
        .add_separator()
        .set_footer(footer_str)
        .build()
    )

    if is_slash and hasattr(message, "response"):
        if message.response.is_done():
            await message.followup.send(embed=embed)
        else:
            await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
    elif hasattr(message, "channel"):
        await message.channel.send(embed=embed)
