import os
from typing import List, Any
import discord
from config.settings import settings
from config.strings import get_string
from sdk.discord.response import send_response, send_ui
from sdk.discord.builders import build_ui
from shared.types.command_record import CommandType

name = "ai"
aliases = ["askai", "gemini", "chat"]
description = "Ask a question or converse with Google Gemini AI."
category = "AI"
usage = "ai <prompt>"
cooldown = 5.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    prompt = " ".join(args).strip()

    if not prompt:
        return await send_ui(message, "commands.ai.missing_prompt", ephemeral=True, style="warning")

    api_key = settings.GEMINI_API_KEY.strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return await send_ui(message, "commands.ai.no_key", ephemeral=True, style="error")

    placeholder = None
    if is_slash and hasattr(message, "response"):
        await message.response.defer()
    elif hasattr(message, "reply"):
        thinking_view = build_ui("commands.ai.thinking", style="info")
        placeholder = await send_response(message, thinking_view)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model_name = settings.GEMINI_MODEL or "gemini-3.8-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        text_out = response.text or "No response generated."

        # Truncate if over Discord component character limit
        if len(text_out) > 3800:
            text_out = text_out[:3800] + "... (truncated)"

        view = build_ui(
            "commands.ai.success",
            variables={"prompt": prompt, "response": text_out, "model": model_name},
            style="info"
        )

        if placeholder and hasattr(placeholder, "edit"):
            await placeholder.edit(view=view)
        else:
            await send_response(message, view)

    except Exception as err:
        err_str = str(err)
        err_view = build_ui(
            "commands.ai.error",
            variables={"error": err_str[:300]},
            style="error"
        )
        if placeholder and hasattr(placeholder, "edit"):
            await placeholder.edit(view=err_view)
        else:
            await send_response(message, err_view)
