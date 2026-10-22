from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_channel_create"
canonical_event = AntiNukeConstants.EVENT_CHANNEL_CREATE
description = "Anti-Nuke channel creation listener"

async def execute(ctx: Any, channel: discord.abc.GuildChannel) -> None:
    await AntiNukeService.on_guild_channel_create(channel)
