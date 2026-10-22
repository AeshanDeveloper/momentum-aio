from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_channel_update"
canonical_event = AntiNukeConstants.EVENT_CHANNEL_UPDATE
description = "Anti-Nuke channel update listener"

async def execute(ctx: Any, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
    await AntiNukeService.on_guild_channel_update(before, after)
