from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_thread_delete"
canonical_event = AntiNukeConstants.EVENT_THREAD_DELETE
description = "Anti-Nuke thread deletion listener"

async def execute(ctx: Any, thread: discord.Thread) -> None:
    await AntiNukeService.on_thread_delete(thread)
