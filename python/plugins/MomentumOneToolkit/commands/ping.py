import asyncio
import time
from typing import Any, List

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
DB_TIMEOUT = 2.0


async def execute(ctx: Any, command_type: str, message: Any, args: List[str] = None):
    slash = command_type == CommandType.SLASH or str(command_type).lower() in ("slash", "commandtype.slash")
    color = COLORS.get("default", "#FF7B00")
    ping = EMOJIS.get("ping") or EMOJIS.get("latency") or "📡"
    online = EMOJIS.get("online") or EMOJIS.get("success") or "🟢"
    ws = EMOJIS.get("latency") or "⚡"
    db = EMOJIS.get("database") or "💾"
    loading = ContainerBuilder().set_accent_color(color).add_text_display(f"### {ping} Checking Connectivity").add_separator(divider=True, spacing=SeparatorSpacingSize.Small).add_text_display("Measuring gateway and database responsiveness...").build()
    response = None
    edit_original = False
    if slash and hasattr(message, "response"):
        if message.response.is_done():
            response = await message.followup.send(view=loading, wait=True, allowed_mentions=discord.AllowedMentions.none())
        else:
            await message.response.send_message(view=loading, allowed_mentions=discord.AllowedMentions.none())
            edit_original = True
    elif hasattr(message, "reply"):
        response = await message.reply(view=loading, mention_author=False, allowed_mentions=discord.AllowedMentions.none())
    elif hasattr(message, "channel"):
        response = await message.channel.send(view=loading, allowed_mentions=discord.AllowedMentions.none())
    else:
        return
    started = time.perf_counter()
    client = getattr(ctx, "client", None) or getattr(message, "client", None)
    latency = getattr(client, "latency", None)
    gateway = f"{latency * 1000:.1f} ms" if latency is not None and latency >= 0 else "Connecting..."
    db_start = time.perf_counter()
    try:
        result = await asyncio.wait_for(database.ping(), timeout=DB_TIMEOUT)
        status = "Connected" if result is not False else "Ping failed"
    except asyncio.TimeoutError:
        status = "Timeout"
    except Exception:
        status = "Error"
    db_ms = (time.perf_counter() - db_start) * 1000
    execution_ms = (time.perf_counter() - started) * 1000
    result = ContainerBuilder().set_accent_color(color).add_text_display(f"### {ping} Bot Connectivity Status").add_separator(divider=True, spacing=SeparatorSpacingSize.Small).add_text_display(f"- {online} **Bot:** `Online`\n- {ws} **Gateway Heartbeat:** `{gateway}`\n- {db} **Database Response:** `{db_ms:.1f} ms ({status})`\n- **Command Execution:** `{execution_ms:.1f} ms`").add_separator(divider=True, spacing=SeparatorSpacingSize.Small).add_text_display("-# Database latency measures the ping operation.").build()
    if edit_original:
        await message.edit_original_response(view=result, allowed_mentions=discord.AllowedMentions.none())
    elif response is not None:
        await response.edit(view=result, allowed_mentions=discord.AllowedMentions.none())
