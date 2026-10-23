from typing import Any
import discord
from core.security.antinuke import AntiNukeConstants
from core.security.antinuke_service import AntiNukeService

name = "on_audit_log_entry_create"
canonical_event = AntiNukeConstants.EVENT_AUDIT_LOG_CREATE
description = "Anti-Nuke audit log entry creation listener"

async def execute(ctx: Any, entry: discord.AuditLogEntry) -> None:
    await AntiNukeService.on_audit_log_entry_create(entry)
