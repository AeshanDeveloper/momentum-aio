from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_member_remove"
canonical_event = AntiNukeConstants.EVENT_MEMBER_REMOVE
description = "Anti-Nuke member kick and prune detection listener"

async def execute(ctx: Any, member: discord.Member) -> None:
    await AntiNukeService.on_member_remove(member)
