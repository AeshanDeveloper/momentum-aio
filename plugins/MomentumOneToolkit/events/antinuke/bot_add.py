from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_member_join"
canonical_event = AntiNukeConstants.EVENT_BOT_ADD
description = "Anti-Nuke unauthorized bot addition interceptor"

async def execute(ctx: Any, member: discord.Member) -> None:
    await AntiNukeService.on_member_join(member)
