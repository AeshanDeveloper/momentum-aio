from typing import Any, Sequence
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_emojis_update"
canonical_event = AntiNukeConstants.EVENT_EMOJIS_UPDATE
description = "Anti-Nuke guild emojis update listener"

async def execute(ctx: Any, guild: discord.Guild, before: Sequence[discord.Emoji], after: Sequence[discord.Emoji]) -> None:
    await AntiNukeService.on_guild_emojis_update(guild, before, after)
