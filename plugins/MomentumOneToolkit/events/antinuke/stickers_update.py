from typing import Any, Sequence
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_stickers_update"
canonical_event = AntiNukeConstants.EVENT_STICKERS_UPDATE
description = "Anti-Nuke guild stickers update listener"

async def execute(ctx: Any, guild: discord.Guild, before: Sequence[discord.GuildSticker], after: Sequence[discord.GuildSticker]) -> None:
    await AntiNukeService.on_guild_stickers_update(guild, before, after)
