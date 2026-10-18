import time
from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from apps.bot.discord.permissions.resolver import is_bot_owner
from core.telemetry.observability import ObservabilityManager
from database.database import database
from shared.types.command_record import CommandType

name = "status"
aliases = ["clusterstatus", "diagnostics"]
description = "Comprehensive platform diagnostics, cluster metrics, and database health."
category = "Dev"
usage = "status"
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
    metrics = ObservabilityManager.get_metrics()
    db_connected = await database.ping()

    title = get_string("commands.dev.status_title", "🖥️ Platform Diagnostics & Cluster Status")
    guilds_count = len(client.guilds) if client else 0
    ws_ping = f"{round(client.latency * 1000, 1)}ms" if (client and hasattr(client, "latency") and client.latency) else "Disconnected"

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display(
            f"• **Gateway Socket:** `{ws_ping}`\n"
            f"• **Database Engine:** `{'Connected (Active)' if db_connected else 'In-Memory Mock'}`\n"
            f"• **Connected Guilds:** `{guilds_count}`\n"
            f"• **Total Executed Commands:** `{metrics.get('total_commands', 0)}`\n"
            f"• **Average Command Latency:** `{metrics.get('average_latency_ms', 0)}ms`\n"
            f"• **Failed Invocations:** `{metrics.get('failed_commands', 0)}`"
        )
        .set_footer("MomentumOne Telemetry Engine")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
