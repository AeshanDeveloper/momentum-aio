from typing import Any
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_auto_moderation_rule_delete"
canonical_event = AntiNukeConstants.EVENT_AUTOMOD_DELETE
description = "Anti-Nuke AutoMod rule deletion listener"

async def execute(ctx: Any, rule: Any) -> None:
    await AntiNukeService.on_auto_moderation_rule_delete(rule)
