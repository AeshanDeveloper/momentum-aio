import sys
import io
import contextlib
from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from apps.bot.discord.permissions.resolver import is_bot_owner
from shared.types.command_record import CommandType

name = "eval"
aliases = ["ev", "exec"]
description = "Execute Python expressions safely in the bot runtime context."
category = "Dev"
usage = "eval <code>"
cooldown = 1.0
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

    code = " ".join(args).strip()
    if code.startswith("```python"):
        code = code[9:]
    elif code.startswith("```py"):
        code = code[5:]
    elif code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    code = code.strip()

    if not code:
        err = "Please provide code to evaluate."
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err)
        return

    stdout_buf = io.StringIO()
    eval_globals = {
        "ctx": ctx,
        "client": getattr(ctx, "client", getattr(message, "client", None)),
        "message": message,
        "settings": settings,
    }

    try:
        with contextlib.redirect_stdout(stdout_buf):
            result = eval(code, eval_globals)
            if hasattr(result, "__await__"):
                result = await result
        output = stdout_buf.getvalue() or str(result)
        color = COLORS.get("success", "#3FD438")
    except Exception as err:
        output = f"Error: {err}"
        color = COLORS.get("error", "#B21F1F")

    title = get_string("commands.dev.eval_title", "⚡ Runtime Evaluation")
    embed = (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display(f"```python\n{output[:1800]}\n```")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
