from typing import Any
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_auto_moderation_rule_update"
canonical_event = AntiNukeConstants.EVENT_AUTOMOD_UPDATE
description = "Anti-Nuke AutoMod rule update listener"

async def execute(ctx: Any, rule: Any) -> None:
    await AntiNukeService.on_auto_moderation_rule_update(rule)
