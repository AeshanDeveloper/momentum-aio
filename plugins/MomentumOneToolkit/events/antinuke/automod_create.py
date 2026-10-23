from typing import Any
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_auto_moderation_rule_create"
canonical_event = AntiNukeConstants.EVENT_AUTOMOD_CREATE
description = "Anti-Nuke AutoMod rule creation listener"

async def execute(ctx: Any, rule: Any) -> None:
    await AntiNukeService.on_auto_moderation_rule_create(rule)
