from typing import Any
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_scheduled_event_delete"
canonical_event = AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE
description = "Anti-Nuke scheduled event deletion listener"

async def execute(ctx: Any, event: Any) -> None:
    await AntiNukeService.on_scheduled_event_delete(event)
