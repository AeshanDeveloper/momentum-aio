from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_integrations_update"
canonical_event = AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE
description = "Anti-Nuke guild integrations update listener"

async def execute(ctx: Any, guild: discord.Guild) -> None:
    await AntiNukeService.on_guild_integrations_update(guild)
