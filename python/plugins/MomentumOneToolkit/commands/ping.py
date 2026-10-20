import time
from typing import List, Any
import discord

from database.database import database
from sdk.discord.response import send_ui
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

    return await send_ui(
        message,
        "commands.ping.status",
        variables={
            "roundtrip": roundtrip,
            "gateway_ping": gateway_ping,
            "db_ping": db_ping_str,
        },
        style="info"
    )
