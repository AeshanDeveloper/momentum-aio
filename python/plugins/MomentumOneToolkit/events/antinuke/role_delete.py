from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_role_delete"
canonical_event = AntiNukeConstants.EVENT_ROLE_DELETE
description = "Anti-Nuke role deletion listener"

async def execute(ctx: Any, role: discord.Role) -> None:
    await AntiNukeService.on_guild_role_delete(role)
