import time
from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from database.database import database
from shared.types.command_record import CommandType

name = "bug"
aliases = ["reportbug", "issue"]
description = "Submit a bug report to the bot development team."
category = "General"
usage = "bug <description>"
cooldown = 10.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    report_text = " ".join(args).strip()

    if not report_text:
        err = get_string("commands.bug.empty", "❌ Please provide a detailed description of the bug encountered.")
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    rep_id = hex(int(time.time() * 1000))[2:].upper()

    try:
        col = database.collection("bug_reports")
        await col.insert_one({
            "report_id": rep_id,
            "user_id": str(author.id),
            "username": author.name,
            "description": report_text,
            "timestamp": time.time()
        })
    except Exception:
        pass

    msg = get_string("commands.bug.submitted", "✅ Thank you! Bug report `#{report_id}` has been recorded for review.", report_id=rep_id)
    if is_slash and hasattr(message, "response"):
        await message.response.send_message(msg)
    elif hasattr(message, "reply"):
        await message.reply(msg)
