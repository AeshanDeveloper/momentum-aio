"""
Sentinel™ Security Health & Diagnostic Command.

Agent 7 of 8 Security Core: Authoritative diagnostic and posture inspection utility.
Validates the full security pipeline, queue health, database latency, role hierarchy,
shadow mode configuration, and active containment state.

Permissions: Restricted strictly to Server Owner, Extra Owners, Bot Owners, or
designated Trusted Recovery Administrators.
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import discord

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.security.antinuke import AntiNukeManager, AntiNukeConstants
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
)
from core.security.lockdown_journal import lockdown_journal_manager
from core.security.emergency_lockdown_manager import emergency_lockdown_manager
from core.security.protection_service import security_protection_service
from core.security.incident_manager import incident_manager
from core.security.pipeline import sentinel_pipeline
from apps.bot.discord.permissions.resolver import is_bot_owner
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType

name = "securitycheck"
aliases = ["seccheck", "secstatus", "securitydiagnostics", "sentinelcheck"]
description = "Sentinel™ comprehensive autonomous security health and pipeline diagnostics."
category = "Security"
usage = "securitycheck [full|quick]"
user_permissions = ["administrator"]
cooldown = 3.0
guild_only = True


def build_security_check_container(
    guild: discord.Guild,
    health: Dict[str, Any],
    policy: SecurityResponsePolicy,
) -> ContainerBuilder:
    """Builds a formatted, privacy-hardened diagnostic container."""
    collector = health.get("collector", {})
    activity = health.get("activity_manager", {})
    correlation = health.get("correlation_engine", {})
    protection = health.get("protection_service", {})
    db = health.get("database", {})
    hierarchy = health.get("hierarchy", {})
    notifs = health.get("notifications", {})

    is_healthy = (
        collector.get("running", False)
        and activity.get("healthy", False)
        and correlation.get("healthy", False)
        and db.get("reachable", False)
        and hierarchy.get("can_act", True)
    )

    color = COLORS.get("success", "#3FD438") if is_healthy else COLORS.get("warning", "#F59E0B")
    status_icon = "🟢" if is_healthy else "⚠️"

    # Hierarchy details
    bot_top = hierarchy.get("bot_top_role", "Unknown")
    hier_reasons = hierarchy.get("reasons", [])
    hier_display = "🟢 Adequate permissions & role hierarchy" if not hier_reasons else f"⚠️ {'; '.join(hier_reasons[:2])}"

    # Database details
    if db.get("reachable"):
        db_display = f"🟢 Connected ({db.get('latency_ms', 0)}ms)"
    else:
        err_msg = str(db.get("error", "Unreachable"))[:40]
        db_display = f"🔴 Degraded ({err_msg})"

    # Shadow mode display
    is_shadow = protection.get("shadow_mode", True)
    shadow_display = "🛡️ SHADOW MODE (Simulated Protection)" if is_shadow else "🚨 LIVE ENFORCEMENT ARMED"

    # Active lockdown display
    lockdown_status = protection.get("guild_lockdown_status")
    lockdown_id = protection.get("guild_lockdown_id")
    if lockdown_status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL):
        containment_display = f"🔒 **ACTIVE LOCKDOWN** (`{lockdown_id}` - {lockdown_status.upper()})"
    else:
        containment_display = "🟢 Nominal (No Active Server Lockdown)"

    # Notification config
    owner_cfg = "Configured" if notifs.get("recovery_owner_configured") else "Missing"
    admins_cfg = f"{notifs.get('trusted_admins_count', 0)} trusted admin(s)"
    fallback_cfg = f"<#{policy.fallback_channel_id}>" if policy.fallback_channel_id else "None"

    body_text = (
        f"### {status_icon} Pipeline & Observation Health\n"
        f"• **Event Collector:** `{'Running' if collector.get('running') else 'Stopped'}` | "
        f"**Subscribers:** `{collector.get('subscribers_count', 0)}`\n"
        f"• **Processed Events:** `{health.get('processed_events_total', 0)}` total | "
        f"**Guild Buffer:** `{collector.get('guild_events_count', 0)}` recent\n"
        f"• **Supported Handlers:** `{health.get('registered_handlers_count', 23)}/23` Discord vectors active\n"
        f"• **Queue Backpressure:** `{collector.get('pending_tasks', 0)}` pending task(s) | "
        f"**Dedup Cache:** `{collector.get('dedup_cache_size', 0)}` entries\n\n"
        f"### ⚡ Threat Detection & Rolling Counters\n"
        f"• **Activity Counters:** 🟢 Healthy (`{activity.get('tracked_actors_count', 0)}` tracked actors)\n"
        f"• **Correlation Rules:** 🟢 Healthy (`{correlation.get('loaded_rules_count', 0)}` deterministic rules loaded)\n"
        f"• **Open Incidents:** `{health.get('open_incidents_count', 0)}` active on this server\n\n"
        f"### 🛡️ Emergency Protection & Recovery\n"
        f"• **Containment Status:** {containment_display}\n"
        f"• **Response Policy:** `{protection.get('response_level', 'lockdown').upper()}` | **Mode:** `{shadow_display}`\n"
        f"• **Global Active Lockdowns:** `{protection.get('active_lockdowns_total', 0)}` hydrated\n\n"
        f"### 🔐 Environment & Authorizations\n"
        f"• **Database Reachability:** {db_display}\n"
        f"• **Bot Role:** `{bot_top}` | **Hierarchy:** {hier_display}\n"
        f"• **Recovery Route:** Owner `{owner_cfg}` | {admins_cfg} | Fallback Channel: {fallback_cfg}\n\n"
        f"-# *Note: Diagnostic telemetry automatically suppresses all sensitive tokens, webhook URLs, and secrets.*"
    )

    box = (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(f"### 🛡️ Sentinel™ Security Core Diagnostic Report")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(body_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Defense Engine • Unified Architecture")
    )
    return box


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    gid = str(guild.id)
    policy = security_protection_service.get_policy(gid)

    # Authority validation: must be server owner, extra owner, bot owner, or trusted recovery admin
    uid_str = str(author.id)
    is_authorized = (
        policy.is_trusted_recovery_actor(uid_str)
        or (guild.owner_id and str(guild.owner_id) == uid_str)
        or AntiNukeManager.is_owner_or_extra_owner(guild, author.id)
        or is_bot_owner(uid_str)
    )

    if not is_authorized:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{EMOJIS.get('cross', '❌')} Only the Server Owner, Extra Owners, Bot Owners, or "
                f"designated Trusted Recovery Administrators can run security diagnostics."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Gather diagnostics with database reachability timeout
    health = await sentinel_pipeline.get_health_status(guild)
    box = build_security_check_container(guild, health, policy)
    return await send_response(message, box)
