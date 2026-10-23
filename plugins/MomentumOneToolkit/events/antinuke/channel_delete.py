from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_channel_delete"
canonical_event = AntiNukeConstants.EVENT_CHANNEL_DELETE
description = "Anti-Nuke channel deletion listener"

async def execute(ctx: Any, channel: discord.abc.GuildChannel) -> None:
    await AntiNukeService.on_guild_channel_delete(channel)
