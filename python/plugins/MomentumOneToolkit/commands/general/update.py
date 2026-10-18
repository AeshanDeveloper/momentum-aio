from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from config.changelog import get_latest_release
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType

name = "update"
aliases = ["changelog", "news"]
description = "View the latest MomentumOne system changelog and release notes."
category = "General"
usage = "update"
cooldown = 5.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    latest = get_latest_release()

    title = get_string("commands.update.title", "🚀 MomentumOne System Changelog")
    version_label = get_string("commands.update.latest_version", "Latest Release: v{version}", version=latest["version"])

    features_formatted = "\n".join(f"• {f}" for f in latest["features"])

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("default", "#FF7B00"))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display(
            f"**{version_label} — {latest['codename']}**\n"
            f"_{latest['headline']}_\n\n"
            f"**Key Capabilities:**\n{features_formatted}"
        )
        .set_footer(f"Released: {latest['releasedAt']}")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
