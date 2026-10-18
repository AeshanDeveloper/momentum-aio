import os
from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
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
        err_msg = "Please provide a prompt or question for Gemini."
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(err_msg, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(err_msg)
        return

    api_key = settings.GEMINI_API_KEY.strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        no_key = get_string("commands.ai.no_key", "❌ **Gemini AI Not Configured**: Please configure `GEMINI_API_KEY` in your environment settings.")
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(no_key, ephemeral=True)
        elif hasattr(message, "reply"):
            await message.reply(no_key)
        return

    # Defer or indicate thinking
    thinking_str = get_string("commands.ai.thinking", "🧠 Analyzing prompt with Google Gemini...")
    placeholder = None
    if is_slash and hasattr(message, "response"):
        await message.response.defer()
    elif hasattr(message, "reply"):
        placeholder = await message.reply(thinking_str)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model_name = settings.GEMINI_MODEL or "gemini-3.8-flash"
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
        text_out = response.text or "No response generated."

        # Truncate if over Discord embed character limit (4096)
        if len(text_out) > 3800:
            text_out = text_out[:3800] + "... (truncated)"

        title = get_string("commands.ai.title", "✨ Google Gemini Intelligence")
        embed = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#3B82F6"))
            .add_text_display(f"### {title}")
            .add_separator()
            .add_text_display(f"**Prompt:** {prompt}\n\n{text_out}")
            .set_footer(f"Model: {model_name}")
            .build()
        )

        if is_slash and hasattr(message, "followup"):
            await message.followup.send(embed=embed)
        elif placeholder:
            await placeholder.edit(content=None, embed=embed)
        elif hasattr(message, "reply"):
            await message.reply(embed=embed)

    except Exception as err:
        err_str = str(err)
        err_title = get_string("commands.ai.error_title", "❌ AI Generation Error")
        embed = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {err_title}")
            .add_separator()
            .add_text_display(f"Failed to generate response: `{err_str[:300]}`")
            .build()
        )
        if is_slash and hasattr(message, "followup"):
            await message.followup.send(embed=embed)
        elif placeholder:
            await placeholder.edit(content=None, embed=embed)
        elif hasattr(message, "reply"):
            await message.reply(embed=embed)
