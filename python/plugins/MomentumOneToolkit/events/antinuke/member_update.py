from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_member_update"
canonical_event = AntiNukeConstants.EVENT_MEMBER_UPDATE
description = "Anti-Nuke member dangerous role and timeout update listener"

async def execute(ctx: Any, before: discord.Member, after: discord.Member) -> None:
    await AntiNukeService.on_member_update(before, after)
