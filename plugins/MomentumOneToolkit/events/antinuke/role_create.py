from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_role_create"
canonical_event = AntiNukeConstants.EVENT_ROLE_CREATE
description = "Anti-Nuke role creation listener"

async def execute(ctx: Any, role: discord.Role) -> None:
    await AntiNukeService.on_guild_role_create(role)
