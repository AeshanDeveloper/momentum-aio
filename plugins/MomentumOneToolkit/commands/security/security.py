"""
Sentinel™ Master Security Command & Enterprise Defense Hub.

Unified interface bringing together:
- Autonomous Anti-Nuke Protection & Operating Modes (Hard, Ultimate, Hybrid)
- Aegis Real-Time Correlation Observation Engine vs Standard Heuristic Engine
- Emergency Containment, Idempotent Lockdowns, & Quorum-Gated Recovery
- Multi-Admin Incident Review & Consensus Voting Workflows
- Security Posture Diagnostics, Whitelists, and Extra Owner Governance
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import discord

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji, get_image
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants
from core.security.response_policy import SecurityResponsePolicy, LockdownStatus, ResponseLevel
from core.security.lockdown_journal import LockdownRecord, lockdown_journal_manager
from core.security.emergency_lockdown_manager import emergency_lockdown_manager
from core.security.protection_service import security_protection_service
from core.security.incident_manager import incident_manager
from core.security.consensus_manager import incident_consensus_manager
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType

name = "security"
aliases = ["sec", "hub", "defense", "securityhub"]
description = "Sentinel™ Master Security Hub: Anti-Nuke, Observation Engines, Containment, & Governance."
category = "Security"
usage = "security [status|observation <on|off>|mode <hard|ultimate|hybrid>|lockdown|posture|review|help]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


async def build_security_hub_view(guild: discord.Guild) -> Any:
    """Renders the comprehensive Master Security Hub container with real-time telemetry."""
    gid = str(guild.id)
    cfg = AntiNukeManager.get_guild_config(gid)
    policy = security_protection_service.get_policy(gid)
    active_lck = lockdown_journal_manager.get_active_lockdown_for_guild(gid)
    active_incidents = incident_manager.get_active_incidents(gid)

    is_setup = cfg.get("setup_completed", False)
    is_an_enabled = cfg.get("enabled", False)
    mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
    mode_name = AntiNukeManager.get_mode_display_name(mode)

    obs_enabled = AntiNukeManager.is_observation_system_enabled(guild.id)
    obs_name = AntiNukeManager.get_observation_system_name(guild.id)

    # Posture diagnostic summary
    posture_report = emergency_lockdown_manager.audit_guild_security_posture(guild, policy)
    overall_posture = posture_report.get("overall_posture", "ATTENTION")

    # Dynamic status indicators
    if active_lck and active_lck.status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL):
        accent_color = COLORS.get("danger", "#ED4245")
        status_badge = f"🚨 **EMERGENCY CONTAINMENT ACTIVE** (`{active_lck.lockdown_id}`)"
    elif is_setup and is_an_enabled:
        accent_color = COLORS.get("success", "#3FD438")
        status_badge = f"{EMOJIS.get('check', '✅')} **DEFENSE ACTIVE & OPERATIONAL**"
    else:
        accent_color = COLORS.get("warning", "#F59E0B")
        status_badge = f"{EMOJIS.get('warning', '⚠️')} **SETUP REQUIRED / DEFENSE PAUSED**"

    # Observation engine details
    if obs_enabled:
        obs_display = (
            f"👁️ **{obs_name}** `[ENABLED]`\n"
            f"  ↳ Continuous sliding-window normalization, multi-vector threat correlation & graduated attribution."
        )
        wl_summary = "🛡️ **Graduated Whitelist**: Trusted entities bypass direct kicks; suspicious bursts remain logged in forensic journal."
    else:
        obs_display = (
            f"⚡ **{obs_name}** `[ACTIVE]`\n"
            f"  ↳ Direct single-event threshold gatekeeping with instant reactive punishment."
        )
        wl_summary = "🛡️ **Direct Whitelist Bypass**: Whitelisted entities completely bypass event count thresholds."

    # Whitelist & Extra Owner metrics
    wls_count = len(cfg.get("whitelists", {}))
    eos_count = len(cfg.get("extra_owners", []))
    events_count = len(cfg.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS))

    # Lockdown status text
    if active_lck:
        lck_info = (
            f"🚨 Active Lockdown ID: `{active_lck.lockdown_id}`\n"
            f"• Contained: `{active_lck.summary.get('applied', 0)}` items | Conflicts Preserved: `{active_lck.summary.get('conflict_detected', 0)}`\n"
            f"• Baseline Checksum: `{active_lck.checksum[:16]}...`"
        )
    else:
        lck_info = (
            f"• State: `NORMAL / SECURE`\n"
            f"• Response Level: `{policy.response_level.upper()}` | Recovery Quorum: `{policy.recovery_quorum}` approval(s)"
        )

    body_text = (
        f"{status_badge}\n\n"
        f"**1. Defensive Operating Posture:**\n"
        f"• **Anti-Nuke Mode:** `{mode_name}`\n"
        f"• **Overall Server Posture:** `{overall_posture}`\n"
        f"• **Guarded Vectors:** `{events_count} / {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)}` active\n\n"
        f"**2. Observation & Telemetry:**\n"
        f"• {obs_display}\n"
        f"• {wl_summary}\n\n"
        f"**3. Emergency Containment & Recovery:**\n"
        f"{lck_info}\n\n"
        f"**4. Governance & Access Control:**\n"
        f"• **Server Owner:** <@{guild.owner_id}>\n"
        f"• **Extra Owners:** `{eos_count}` designated\n"
        f"• **Whitelisted Entities:** `{wls_count}` rules configured\n"
        f"• **Active Incident Quorums:** `{len(active_incidents)}` under review"
    )

    # Action Row 1: Observation & Mode Switchers
    row_1 = ActionRowBuilder()
    row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an:toggle_obs:{guild.id}")
        .set_label("Aegis Engine: Active" if obs_enabled else "Aegis Engine: Off")
        .set_style(ButtonStyle.Success if obs_enabled else ButtonStyle.Secondary)
        .set_emoji("👁️")
    )
    row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an:cycle_mode:{guild.id}")
        .set_label(f"Mode: {mode.title()}")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("shield", "🛡️"))
    )
    if active_lck:
        row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:do_recover:{guild.id}")
            .set_label("Begin Recovery")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("unlock", "🔓"))
        )
    else:
        row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:prompt_trigger:{guild.id}")
            .set_label("Emergency Containment")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("lock", "🔒"))
        )

    # Action Row 2: Secondary Quick Links
    row_2 = ActionRowBuilder()
    row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"lck:posture:{guild.id}")
        .set_label("Audit Posture")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("shield", "🛡️"))
    )
    row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"an:dashboard:{guild.id}")
        .set_label("Anti-Nuke Center")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("gear", "⚙️"))
    )
    row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"lck:review:{guild.id}")
        .set_label("Incident Reviews")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("balance", "⚖️"))
    )
    row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"sec:explain:{guild.id}")
        .set_label("Keyword Glossary")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("info", "📖"))
    )

    # Action Row 3: Select Menu for Deep-Dive Navigation
    sel = (
        SelectMenuBuilder()
        .set_custom_id(f"sec:nav:{guild.id}")
        .set_placeholder("Navigate Sentinel Security Suite...")
    )
    sel.add_option(label="Security Overview Hub", value="hub", description="Full real-time defensive posture summary", emoji="🛡️")
    sel.add_option(label="Observation Engine Controls", value="observation", description="Toggle Aegis Advanced Correlation vs Standard Heuristic", emoji="👁️")
    sel.add_option(label="Anti-Nuke Control Center", value="antinuke", description="Operating modes, monitored vectors, and mitigation switches", emoji="⚙️")
    sel.add_option(label="Emergency Containment & Recovery", value="lockdown", description="Trigger containment, review rollbacks, or lift lockdown", emoji="🔒")
    sel.add_option(label="Security Posture Diagnostic", value="posture", description="Audit role hierarchies, bot permissions, and dangerous rights", emoji="📋")
    sel.add_option(label="Incident Reviews & Consensus", value="reviews", description="Cast multi-admin votes on flagged threat anomalies", emoji="⚖️")
    sel.add_option(label="Access Control & Whitelists", value="access", description="Manage trusted users, roles, extra owners, and ticket bots", emoji="👥")
    sel.add_option(label="Thresholds & Punishments", value="thresholds", description="Adjust rate limits, burst windows, and disciplinary actions", emoji="⚡")
    sel.add_option(label="Security Glossary & Explain", value="explain", description="In-depth definitions for all security terms and safeguards", emoji="📖")

    box = (
        ContainerBuilder()
        .set_accent_color(accent_color)
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {settings.BOT_NAME} Unified Security Hub")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(body_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(row_1)
        .add_action_row(row_2)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_text_display(f"-# {settings.BOT_NAME} Enterprise Security Core • Real-Time Infrastructure")
        .build()
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

    # Authority validation: must be server owner, trusted recovery admin, or extra owner
    is_authorized = (
        policy.is_trusted_recovery_actor(author.id)
        or (guild.owner_id and str(guild.owner_id) == str(author.id))
        or AntiNukeManager.is_owner_or_extra_owner(guild, author.id)
    )

    if not is_authorized:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{EMOJIS.get('cross', '❌')} Only the Server Owner, Extra Owners, or designated "
                f"Trusted Recovery Administrators can access the Sentinel Security Hub."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    sub = args[0].lower() if args else "hub"

    if sub in ["hub", "dashboard", "status", "overview"]:
        view = await build_security_hub_view(guild)
        return await send_response(message, view)

    elif sub in ["observation", "obs", "engine"]:
        arg_val = args[1].lower() if len(args) > 1 else "toggle"
        curr_obs = AntiNukeManager.is_observation_system_enabled(guild.id)
        if arg_val in ["on", "enable", "true", "1", "advanced", "aegis"]:
            new_obs = True
            mode_type = "advanced"
        elif arg_val in ["off", "disable", "false", "0", "standard"]:
            new_obs = False
            mode_type = "standard"
        else:
            new_obs = not curr_obs
            mode_type = "advanced" if new_obs else "standard"

        await AntiNukeManager.set_observation_system(guild.id, new_obs, mode_type)
        view = await build_security_hub_view(guild)
        return await send_response(message, view)

    elif sub in ["mode", "posture_mode"]:
        if len(args) > 1:
            target_mode = args[1].lower()
            if target_mode in [AntiNukeConstants.MODE_HARD, AntiNukeConstants.MODE_ULTIMATE, AntiNukeConstants.MODE_HYBRID]:
                await AntiNukeManager.save_guild_config(str(guild.id), {"mode": target_mode})
        view = await build_security_hub_view(guild)
        return await send_response(message, view)

    elif sub in ["lockdown", "emergency", "recover", "unlock"]:
        from plugins.MomentumOneToolkit.commands.security.lockdown import execute as execute_lockdown
        sub_args = args[1:] if len(args) > 1 else (["recover"] if sub in ["recover", "unlock"] else ["status"])
        return await execute_lockdown(ctx, command_type, message, sub_args)

    elif sub in ["posture", "audit", "diagnostics"]:
        from plugins.MomentumOneToolkit.commands.security.lockdown import _handle_posture
        return await _handle_posture(message, guild, policy)

    elif sub in ["review", "consensus", "votes"]:
        from plugins.MomentumOneToolkit.commands.security.lockdown import _handle_review
        target_inc = args[1] if len(args) > 1 else None
        return await _handle_review(message, guild, policy, target_inc)

    elif sub in ["antinuke", "an"]:
        from plugins.MomentumOneToolkit.commands.security.antinuke import build_dashboard_view
        view = await build_dashboard_view(guild)
        return await send_response(message, view)

    elif sub in ["whitelist", "wl"]:
        from plugins.MomentumOneToolkit.commands.security.whitelist import build_whitelist_dashboard_view
        view = await build_whitelist_dashboard_view(guild)
        return await send_response(message, view)

    elif sub in ["explain", "keywords", "glossary", "help"]:
        from plugins.MomentumOneToolkit.commands.security.explain import build_explain_view
        term = args[1].lower() if len(args) > 1 else None
        view = build_explain_view(term)
        return await send_response(message, view)

    else:
        view = await build_security_hub_view(guild)
        return await send_response(message, view)
