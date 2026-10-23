from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_member_unban"
canonical_event = AntiNukeConstants.EVENT_BAN_REMOVE
description = "Anti-Nuke member unban listener"

async def execute(ctx: Any, guild: discord.Guild, user: discord.User | discord.Member) -> None:
    await AntiNukeService.on_member_unban(guild, user)
