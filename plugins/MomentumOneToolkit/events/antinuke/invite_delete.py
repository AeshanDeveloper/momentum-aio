from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_invite_delete"
canonical_event = AntiNukeConstants.EVENT_INVITE_DELETE
description = "Anti-Nuke invite deletion listener"

async def execute(ctx: Any, invite: discord.Invite) -> None:
    await AntiNukeService.on_invite_delete(invite)
