from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_guild_role_delete"
canonical_event = AntiNukeConstants.EVENT_ROLE_DELETE
description = "Anti-Nuke role deletion listener"

async def execute(ctx: Any, role: discord.Role) -> None:
    guild = getattr(role, "guild", None)
    if not guild and ctx and hasattr(ctx, "client"):
        for g in getattr(ctx.client, "guilds", []):
            if any(getattr(r, "id", None) == getattr(role, "id", None) for r in getattr(g, "roles", [])):
                guild = g
                break
    await AntiNukeService.on_guild_role_delete(role, guild=guild)
