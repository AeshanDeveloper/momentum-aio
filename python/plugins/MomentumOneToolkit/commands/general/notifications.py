from typing import List, Any
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
from shared.types.command_record import CommandType

name = "notifications"
aliases = ["notifs", "alerts"]
description = "View global platform notifications and announcements."
category = "General"
usage = "notifications"
cooldown = 5.0

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    title = get_string("commands.notifications.title", "🔔 System Notifications")
    none_msg = get_string("commands.notifications.none", "No active platform broadcasts at this time.")

    embed = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#3B82F6"))
        .add_text_display(f"### {title}")
        .add_separator()
        .add_text_display(f"🟢 **Status:** All systems operational.\n\n{none_msg}")
        .build()
    )

    if is_slash and hasattr(message, "response"):
        await message.response.send_message(embed=embed)
    elif hasattr(message, "reply"):
        await message.reply(embed=embed)
