from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_update"
canonical_event = AntiNukeConstants.EVENT_GUILD_UPDATE
description = "Anti-Nuke guild settings update listener"

async def execute(ctx: Any, before: discord.Guild, after: discord.Guild) -> None:
    await AntiNukeService.on_guild_update(before, after)
