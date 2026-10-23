from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_webhooks_update"
canonical_event = AntiNukeConstants.EVENT_WEBHOOKS_UPDATE
description = "Anti-Nuke channel webhooks update listener"

async def execute(ctx: Any, channel: discord.abc.GuildChannel) -> None:
    await AntiNukeService.on_webhooks_update(channel)
