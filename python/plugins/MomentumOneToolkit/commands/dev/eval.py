import os
import io
import time
import contextlib
import traceback
from typing import List, Dict, Any, Optional
import discord

from config.settings import COLORS, EMOJIS
from apps.bot.discord.permissions.resolver import is_bot_owner
from database.database import database
from shared.types.command_record import CommandType
from sdk.discord.builders import (
    ContainerBuilder,
    SeparatorSpacingSize
)
from discord import MessageFlags, ButtonStyle


name = "eval"
aliases = ["evaluate", "e", "js", "py"]
description = "Execute and evaluate arbitrary Python or JavaScript in the runtime bot process (Bot Owner Only)."
category = "Owner"
usage = "eval <code>"
owner_only = True

sub_commands = [
    {"name": "<code>", "description": "Expression or statement to evaluate."},
]

def redact_secrets(text: str) -> str:
    if not text or not isinstance(text, str):
        return text

    sensitive_keys = [
        "BOT_TOKEN",
        "CLIENT_SECRET",
        "API_SECRET",
        "MONGODB_URI",
        "MONGO_URL",
        "DATABASE_URL",
        "TOKEN",
        "SECRET",
        "PASSWORD",
    ]

    sanitized = text
    for key in sensitive_keys:
        val = os.getenv(key)
        if val and len(val.strip()) > 3:
            sanitized = sanitized.replace(val.strip(), f"[REDACTED_{key}]")

    cfg_token = getattr(config, "BOT_TOKEN", "") or getattr(config, "settings", {}).get("bot", {}).get("token", "")
    if cfg_token and len(str(cfg_token).strip()) > 3:
        sanitized = sanitized.replace(str(cfg_token).strip(), "[REDACTED_BOT_TOKEN]")

    return sanitized

def truncate_string(s: str, max_length: int = 1800) -> str:
    if len(s) <= max_length:
        return s
    return s[:max_length] + "\n... (truncated for component limit)"

async def execute(ctx: Any, command_type: Any, message: Any, args: List[str] = None):
    if args is None:
        args = []

    is_slash = (command_type == CommandType.SLASH or str(command_type).lower() == "slash")
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    author_id = str(author.id) if author else ""
    client = getattr(ctx, "client", getattr(message, "client", None))

    bot_cfg = getattr(config, "settings", {}).get("bot", {}) if isinstance(getattr(config, "settings", {}), dict) else {}
    owner_ids = [str(o) for o in (bot_cfg.get("owner_ids") or [getattr(config, "OWNER_ID", "")])]

    if not is_bot_owner(author_id) and author_id not in owner_ids:
        denied_text = "❌ **Access Denied**: The `eval` command is strictly restricted to authorized bot owners."
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(denied_text, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(denied_text)
        return

    raw_code = " ".join(args).strip()
    clean_code = raw_code
    if clean_code.startswith("```"):
        lines = clean_code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].endswith("```"):
            lines = lines[:-1]
        clean_code = "\n".join(lines).strip()

    if not clean_code:
        err_text = "❌ **Missing Code**: Please provide a Python expression or script to evaluate."
        if is_slash and hasattr(message, "response") and not message.response.is_done():
            return await message.response.send_message(err_text, ephemeral=True)
        elif hasattr(message, "reply"):
            return await message.reply(err_text)
        return

    start_time = time.perf_counter()
    result = None
    is_error = False
    stdout_buf = io.StringIO()

    eval_scope = {
        "client": client,
        "message": message,
        "ctx": ctx,
        "args": args,
        "db": database,
        "config": config,
        "os": os,
        "sys": sys,
        "time": time,
        "discord": discord,
    }

    try:
        with contextlib.redirect_stdout(stdout_buf):
            # Try eval first for expressions
            try:
                result = eval(clean_code, eval_scope)
                if hasattr(result, "__await__"):
                    result = await result
            except SyntaxError:
                # If not an expression, execute as statements
                exec(clean_code, eval_scope)
                result = stdout_buf.getvalue() or "Done (no output)"
    except Exception as err:
        is_error = True
        result = traceback.format_exc()
    finally:
        end_time = time.perf_counter()
        execution_time_ms = f"{(end_time - start_time) * 1000:.2f}"

    result_type = type(result).__name__
    captured_stdout = stdout_buf.getvalue()
    if captured_stdout and not is_error and str(result) != captured_stdout:
        output_str = f"{captured_stdout}\n{result}"
    else:
        output_str = str(result)

    sanitized_input = redact_secrets(truncate_string(clean_code, 500))
    sanitized_output = redact_secrets(truncate_string(output_str, 1500))

    colors = COLORS
    c_success = colors.get("success", "#10B981")
    c_error = colors.get("error", "#EF4444")

    title_icon = "❌ Evaluation Error" if is_error else "⚡ Python Evaluation"
    container = (
        ContainerBuilder()
        .set_accent_color(c_error if is_error else c_success)
        .add_text_display(
            f"### {title_icon} ({execution_time_ms}ms)\n"
            f"• **Executor:** <@{author_id}> • **Type:** `{result_type}`"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"**Input:**\n```python\n{sanitized_input}\n```")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"**Output:**\n```python\n{sanitized_output}\n```")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# MomentumOne Eval • Execution Time: {execution_time_ms}ms • Confidential")
        .build()
    )

    if is_slash and hasattr(message, "response") and not message.response.is_done():
        return await message.response.send_message(embed=container.embed, ephemeral=True)
    elif hasattr(message, "reply"):
        return await message.reply(embed=container.embed)
    elif hasattr(message, "channel"):
        return await message.channel.send(embed=container.embed)
