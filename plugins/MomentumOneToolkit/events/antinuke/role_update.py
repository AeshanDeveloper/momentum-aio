from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_role_update"
canonical_event = AntiNukeConstants.EVENT_ROLE_UPDATE
description = "Anti-Nuke role update and permission escalation listener"

async def execute(ctx: Any, before: discord.Role, after: discord.Role) -> None:
    await AntiNukeService.on_guild_role_update(before, after)
