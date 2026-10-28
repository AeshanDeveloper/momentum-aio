"""
Sentinel™ Emergency Lockdown, Response Policy, and Recovery Command.

Agent 5 of 8 Security Core: Dedicated command interface for server owners and
recovery administrators to inspect containment status, manually trigger lockdowns,
audit security posture, configure response policies, and execute reversible rollbacks.
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import discord

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
from core.security.antinuke import AntiNukeManager
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
)
from core.security.lockdown_journal import (
    LockdownRecord,
    JournalEntryStatus,
    lockdown_journal_manager,
)
from core.security.emergency_lockdown_manager import emergency_lockdown_manager
from core.security.protection_service import security_protection_service
from core.security.incident_manager import incident_manager
from core.security.consensus_manager import (
    incident_consensus_manager,
    IncidentReviewView,
    build_incident_review_container,
)
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType

name = "lockdown"
aliases = ["emergency", "unlock", "recover", "posture", "review", "consensus"]
description = "Sentinel™ Emergency Containment, Incident Review, Consensus, and Reversible Recovery."
category = "Security"
usage = "lockdown [status|trigger <reason>|recover [id]|posture|policy|journal|review [id]]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


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
                f"Trusted Recovery Administrators can execute emergency security commands."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Route subcommands
    invoked = (args[0].lower() if args else "status")
    
    # Handle alias shortcuts like '!unlock' or '!posture'
    content = getattr(message, "content", "").strip()
    prefix = settings.BOT_PREFIX or "$"
    raw_cmd = content.removeprefix(prefix).split()[0].lower() if content.startswith(prefix) else ""
    if raw_cmd in ("unlock", "recover"):
        invoked = "recover"
        args = [invoked] + args
    elif raw_cmd == "posture":
        invoked = "posture"
    elif raw_cmd in ("review", "consensus"):
        invoked = "review"
        args = [invoked] + args

    if invoked in ("status", "info"):
        return await _handle_status(message, guild, policy)
    elif invoked in ("trigger", "start", "lock"):
        reason = " ".join(args[1:]) if len(args) > 1 else "Manual emergency containment requested by administrator"
        return await _handle_trigger(message, guild, author, reason)
    elif invoked in ("recover", "unlock", "rollback", "restore"):
        target_id = args[1] if len(args) > 1 else None
        return await _handle_recover(message, guild, author, policy, target_id)
    elif invoked in ("posture", "audit", "check"):
        return await _handle_posture(message, guild, policy)
    elif invoked in ("policy", "config", "settings"):
        sub_args = args[1:] if len(args) > 1 else []
        return await _handle_policy(message, guild, policy, sub_args)
    elif invoked in ("journal", "log", "entries"):
        return await _handle_journal(message, guild)
    elif invoked in ("review", "consensus", "vote"):
        target_inc_id = args[1] if len(args) > 1 else None
        return await _handle_review(message, guild, policy, target_inc_id)
    else:
        return await _handle_status(message, guild, policy)


async def _handle_status(message: Any, guild: Any, policy: SecurityResponsePolicy):
    """Displays active containment status and journal metrics."""
    gid = str(guild.id)
    active_lck = lockdown_journal_manager.get_active_lockdown_for_guild(gid)

    if not active_lck:
        status_line = f"{EMOJIS.get('check', '✅')} **No Active Emergency Containment**"
        desc = (
            f"The server is running under normal operational conditions.\n\n"
            f"• **Configured Response Level:** `{policy.response_level.upper()}`\n"
            f"• **Shadow Mode:** `{'Enabled (Simulation Only)' if policy.shadow_mode else 'Disabled (Live Enforcement)'}`\n"
            f"• **Auto-Lockdown:** `{'Enabled' if policy.auto_lockdown_enabled else 'Disabled (Safe Shadow)'}`\n"
            f"• **Rapid Ban Threshold:** `{policy.rapid_ban_threshold_count} bans in {int(policy.rapid_ban_threshold_window_seconds)}s`\n"
            f"• **Recovery Quorum:** `{policy.recovery_quorum} admin approvals required`"
        )
        color = COLORS.get("info", "#0844C5")
    else:
        status_line = f"🚨 **EMERGENCY CONTAINMENT {active_lck.status.upper()}**"
        mode_str = "SHADOW (Simulation)" if active_lck.is_shadow_mode else "LIVE ENFORCEMENT"
        desc = (
            f"**Lockdown Session ID:** `{active_lck.lockdown_id}`\n"
            f"**Status:** `{active_lck.status.upper()}` | **Mode:** `{mode_str}`\n"
            f"**Trigger Pattern:** `{active_lck.trigger_pattern or 'Emergency Burst'}`\n"
            f"**Baseline Checksum:** `{active_lck.checksum[:16]}...`\n"
            f"**Contained Resources:** `{active_lck.summary.get('applied', 0) + active_lck.summary.get('verified', 0)}` applied\n"
            f"**Skipped (Hierarchy):** `{active_lck.summary.get('skipped_hierarchy', 0)}`\n"
            f"**API Failures:** `{active_lck.summary.get('failed_api', 0)}`\n\n"
            f"Use `{settings.BOT_PREFIX}lockdown recover` to restore pre-lockdown permissions."
        )
        color = COLORS.get("danger", "#ED4245") if active_lck.status != LockdownStatus.PARTIAL else COLORS.get("warning", "#F59E0B")

    action_row_top = ActionRowBuilder()
    action_row_top.add_button(
        ButtonBuilder()
        .set_custom_id(f"lck:posture:{gid}")
        .set_label("Audit Posture")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("shield", "🛡️"))
    )
    if active_lck:
        action_row_top.add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:do_recover:{gid}")
            .set_label("Begin Recovery")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("unlock", "🔓"))
        )
    else:
        action_row_top.add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:prompt_trigger:{gid}")
            .set_label("Trigger Containment")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("lock", "🔒"))
        )

    action_row_bottom = ActionRowBuilder()
    action_row_bottom.add_button(
        ButtonBuilder()
        .set_custom_id(f"lck:journal:{gid}")
        .set_label("Permission Journal")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("info", "📋"))
    )
    action_row_bottom.add_button(
        ButtonBuilder()
        .set_custom_id(f"lck:review:{gid}")
        .set_label("Consensus Review")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("balance", "⚖️"))
    )
    action_row_bottom.add_button(
        ButtonBuilder()
        .set_custom_id(f"lck:policy:{gid}")
        .set_label("Policy Settings")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("gear", "⚙️"))
    )

    box = (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {settings.BOT_NAME} Containment Status")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{status_line}\n\n{desc}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row_top)
        .add_action_row(action_row_bottom)
        .add_text_display(f"-# {settings.BOT_NAME} Reversible Emergency Infrastructure")
        .build()
    )
    return await send_response(message, box)


async def _handle_trigger(message: Any, guild: Any, author: Any, reason: str, force: bool = False):
    """Manually triggers emergency containment with safeguards and confirmation."""
    gid = str(guild.id)

    # Safeguard: Do not create two backups for a server
    active_lck = lockdown_journal_manager.get_active_lockdown_for_guild(gid)
    if active_lck and active_lck.status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Active Containment Exists")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"**Duplicate Backup Prevented**: Guild `{guild.name}` already has an active emergency lockdown "
                f"(`{active_lck.lockdown_id}`).\n\n"
                f"Sentinel safeguards server state and will not create a second conflicting backup.\n\n"
                f"• **Status:** `{active_lck.status.upper()}`\n"
                f"• **Trigger Pattern:** `{active_lck.trigger_pattern or 'Manual Containment'}`\n"
                f"• **Checksum:** `{active_lck.checksum[:16]}...`\n\n"
                f"To lift containment or recover permissions, click **Begin Recovery** below or run:\n"
                f"`{settings.BOT_PREFIX}lockdown recover {active_lck.lockdown_id}`"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_action_row(
                ActionRowBuilder()
                .add_button(
                    ButtonBuilder()
                    .set_custom_id(f"lck:do_recover:{gid}")
                    .set_label("Begin Recovery")
                    .set_style(ButtonStyle.Success)
                    .set_emoji(EMOJIS.get("unlock", "🔓"))
                )
                .add_button(
                    ButtonBuilder()
                    .set_custom_id(f"lck:posture:{gid}")
                    .set_label("Audit Posture")
                    .set_style(ButtonStyle.Secondary)
                    .set_emoji(EMOJIS.get("shield", "🛡️"))
                )
            )
            .build()
        )
        return await send_response(message, box)

    # Confirmation safeguard if not forced
    if not force:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("danger", "#ED4245"))
            .add_text_display(f"### 🚨 Confirmation: Emergency Containment")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"You are about to initiate an **Emergency Server Lockdown** for **{guild.name}**.\n\n"
                f"**Protective Safeguards Enforced:**\n"
                f"• Strips dangerous administrative permissions from non-whitelisted roles.\n"
                f"• Locks channels to contain active threats or permission tampering.\n"
                f"• Creates a single cryptographic SHA-256 permission backup.\n"
                f"• Protects Sentinel and recovery staff roles.\n\n"
                f"**Reason:** *{reason}*\n"
                f"**Initiator:** <@{author.id}>\n\n"
                f"⚠️ *Click Confirm below to proceed with emergency containment.*"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_action_row(
                ActionRowBuilder()
                .add_button(
                    ButtonBuilder()
                    .set_custom_id(f"lck:confirm_trigger:{gid}")
                    .set_label("Confirm Emergency Lockdown")
                    .set_style(ButtonStyle.Danger)
                    .set_emoji(EMOJIS.get("shield", "🛡️"))
                )
                .add_button(
                    ButtonBuilder()
                    .set_custom_id(f"lck:cancel_trigger:{gid}")
                    .set_label("Cancel")
                    .set_style(ButtonStyle.Secondary)
                    .set_emoji(EMOJIS.get("cross", "❌"))
                )
            )
            .add_text_display(f"-# {settings.BOT_NAME} Security Governance • Safeguards Active")
            .build()
        )
        return await send_response(message, box)

    rec = await security_protection_service.manual_lockdown(
        guild=guild,
        admin_id=author.id,
        reason=reason,
    )
    summary = rec.summary
    box = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("danger", "#ED4245"))
        .add_text_display(f"### 🚨 Emergency Lockdown Triggered")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"Emergency containment was manually initiated by <@{author.id}>.\n\n"
            f"• **Session ID:** `{rec.lockdown_id}`\n"
            f"• **Status:** `{rec.status.upper()}`\n"
            f"• **Reason:** *{reason}*\n"
            f"• **Resources Contained:** `{summary.get('applied', 0) + summary.get('verified', 0)}`\n"
            f"• **Hierarchy Skips:** `{summary.get('skipped_hierarchy', 0)}`\n"
            f"• **Baseline Checksum:** `{rec.checksum[:16]}...`\n\n"
            f"To restore permissions, run: `{settings.BOT_PREFIX}lockdown recover {rec.lockdown_id}`"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(
            ActionRowBuilder()
            .add_button(
                ButtonBuilder()
                .set_custom_id(f"lck:do_recover:{gid}")
                .set_label("Begin Recovery")
                .set_style(ButtonStyle.Success)
                .set_emoji(EMOJIS.get("unlock", "🔓"))
            )
            .add_button(
                ButtonBuilder()
                .set_custom_id(f"lck:journal:{gid}")
                .set_label("Inspect Journal")
                .set_style(ButtonStyle.Secondary)
                .set_emoji(EMOJIS.get("info", "📋"))
            )
        )
        .add_text_display(f"-# {settings.BOT_NAME} Reversible Protection")
        .build()
    )
    return await send_response(message, box)


async def _handle_recover(
    message: Any,
    guild: Any,
    author: Any,
    policy: SecurityResponsePolicy,
    target_id: Optional[str] = None,
):
    """Executes or approves recovery rollback with quorum enforcement."""
    gid = str(guild.id)
    active_lck = None
    if target_id:
        active_lck = lockdown_journal_manager.get_lockdown(target_id)
    if not active_lck:
        active_lck = lockdown_journal_manager.get_active_lockdown_for_guild(gid)

    if not active_lck:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('info', 'ℹ️')} No Active Lockdown Found")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("There is no active or pending emergency lockdown recorded for this server.")
            .build()
        )
        return await send_response(message, box)

    uid_str = str(author.id)
    is_owner = policy.is_recovery_owner(uid_str) or (guild.owner_id and str(guild.owner_id) == uid_str)

    # Recovery quorum check for non-owner admins
    if not is_owner:
        approvals = active_lck.metadata.setdefault("recovery_approvals", [])
        if uid_str not in approvals:
            approvals.append(uid_str)
            lockdown_journal_manager.save_lockdown(active_lck)

        needed = policy.recovery_quorum
        if len(approvals) < needed:
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("warning", "#F59E0B"))
                .add_text_display(f"### ⏳ Recovery Approval Registered")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(
                    f"Approval logged for <@{uid_str}> (`{len(approvals)}/{needed}` required approvals).\n\n"
                    f"Waiting for additional trusted recovery administrators to approve before unlocking server."
                )
                .build()
            )
            return await send_response(message, box)

    # Execute recovery rollback
    try:
        rec = await emergency_lockdown_manager.restore_lockdown(
            guild=guild,
            lockdown_id=active_lck.lockdown_id,
            admin_user_id=uid_str,
            policy=policy,
        )

        conflicts = rec.summary.get("conflict_detected", 0)
        conflict_msg = (
            f"\n\n⚠️ **Human Changes Preserved:** `{conflicts}` resource(s) were modified by admins post-lockdown; "
            f"Sentinel preserved these changes without overwriting them."
            if conflicts > 0
            else ""
        )

        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("success", "#3FD438"))
            .add_text_display(f"### {EMOJIS.get('check', '✅')} Server Recovery Completed")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"Emergency containment for `{rec.lockdown_id}` has been lifted by <@{uid_str}>.\n\n"
                f"• **Status:** `{rec.status.upper()}`\n"
                f"• **Restored Resources:** `{rec.summary.get('restored', 0)}`\n"
                f"• **Conflict Preserved:** `{conflicts}`\n"
                f"• **Failed Rollbacks:** `{rec.summary.get('failed_restore', 0)}`{conflict_msg}"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Recovery Verification")
            .build()
        )
        return await send_response(message, box)
    except Exception as err:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('cross', '❌')} Recovery Execution Failed")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"An error occurred while restoring server permissions:\n`{err}`")
            .build()
        )
        return await send_response(message, box)


def build_posture_view(guild: Any, policy: SecurityResponsePolicy) -> Any:
    """Builds interactive posture container with real-time audit score and diagnostic breakdown."""
    report = emergency_lockdown_manager.audit_guild_security_posture(guild, policy)
    gid = str(guild.id if guild else "0")

    score = report.get("score", 100)
    grade = report.get("grade", "A")
    overall = report.get("overall_posture", "SECURE")
    dangerous_roles = report.get("dangerous_roles", [])

    findings_text = []
    for item in report.get("checklist", []):
        icon = (
            EMOJIS.get("check", "✅")
            if item.get("passed")
            else (EMOJIS.get("cross", "❌") if item.get("status") == "CRITICAL" else EMOJIS.get("warning", "⚠️"))
        )
        remediation = f"\n  ↳ *Remedy: {item.get('remediation')}*" if item.get("remediation") else ""
        findings_text.append(f"{icon} **{item.get('item')}** [{item.get('status')}]{remediation}")

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:posture_refresh:{gid}")
            .set_label("Recheck Posture")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:posture_dangerous:{gid}")
            .set_label(f"Dangerous Roles ({len(dangerous_roles)})")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("danger", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"sec_wiz:quick_confirm:{gid}")
            .set_label("Quick Setup")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("zap", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"sec:hub:{gid}")
            .set_label("Security Hub")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    )

    summary_desc = (
        f"**Security Score:** `{score} / 100` (Grade `{grade}`)\n"
        f"**Overall Health:** `{overall}`\n"
        f"**Monitored Roles:** `{len(dangerous_roles)}` holding dangerous administrative permissions\n\n"
        + "\n".join(findings_text[:6])
    )

    color = COLORS.get("success", "#3FD438") if overall == "SECURE" else COLORS.get("warning", "#F59E0B")
    return (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Security Posture Diagnostic")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(summary_desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Live State Recheck • Hierarchy & Permission Verifier")
        .build()
    )


def build_dangerous_permissions_view(guild: Any, policy: SecurityResponsePolicy) -> Any:
    """Builds itemized breakdown of all roles possessing dangerous permissions."""
    report = emergency_lockdown_manager.audit_guild_security_posture(guild, policy)
    gid = str(guild.id if guild else "0")
    roles = report.get("dangerous_roles", [])

    lines = []
    if not roles:
        lines.append(f"{EMOJIS.get('check', '✅')} **No unmanaged roles possess dangerous administrative permissions.**")
    else:
        for r in roles[:8]:
            manage_icon = "🟢" if r.get("can_manage") else "🔴"
            perms_str = ", ".join(f"`{p}`" for p in r.get("dangerous_permissions", []))
            lines.append(
                f"• {manage_icon} **{r.get('role_name')}** (Pos `{r.get('position')}` • ID `{r.get('role_id')}`)\n"
                f"  Dangerous: {perms_str}\n"
                f"  Manageable by Sentinel: `{'Yes' if r.get('can_manage') else 'NO - Above Bot Role'}`\n"
                f"  *Remedy: {r.get('remediation')}*"
            )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"lck:posture_refresh:{gid}")
            .set_label("Back to Posture")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"sec:hub:{gid}")
            .set_label("Security Hub")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B") if any(not r.get("can_manage") for r in roles) else COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('danger', '⚡')} Dangerous Role Permissions Breakdown")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display("\n\n".join(lines))
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Role Hierarchy Audit Trail")
        .build()
    )


async def _handle_posture(message: Any, guild: Any, policy: SecurityResponsePolicy):
    """Executes full diagnostic posture audit."""
    box = build_posture_view(guild, policy)
    return await send_response(message, box)


async def _handle_policy(
    message: Any,
    guild: Any,
    policy: SecurityResponsePolicy,
    sub_args: List[str],
):
    """Configures response levels, shadow mode, thresholds, and recovery staff."""
    gid = str(guild.id)
    if not sub_args:
        # Display current policy
        desc = (
            f"**Current Security Response Policy:**\n\n"
            f"• **Response Level:** `{policy.response_level.upper()}`\n"
            f"• **Shadow Mode:** `{'Enabled (Simulation Only)' if policy.shadow_mode else 'Disabled (Live Enforcement)'}`\n"
            f"• **Auto-Lockdown:** `{'Enabled' if policy.auto_lockdown_enabled else 'Disabled (Safe Shadow)'}`\n"
            f"• **Rapid Ban Threshold:** `{policy.rapid_ban_threshold_count} bans in {int(policy.rapid_ban_threshold_window_seconds)}s`\n"
            f"• **Rapid Kick Threshold:** `{policy.rapid_kick_threshold_count} kicks in {int(policy.rapid_kick_threshold_window_seconds)}s`\n"
            f"• **Rapid Channel Deletion:** `{policy.rapid_channel_delete_threshold_count} in {int(policy.rapid_channel_delete_threshold_window_seconds)}s`\n"
            f"• **Rapid Role Deletion:** `{policy.rapid_role_delete_threshold_count} in {int(policy.rapid_role_delete_threshold_window_seconds)}s`\n"
            f"• **Recovery Owner:** {f'<@{policy.recovery_owner_id}>' if policy.recovery_owner_id else 'Server Owner'}\n"
            f"• **Trusted Recovery Admins:** `{len(policy.trusted_recovery_admin_ids)}` configured\n"
            f"• **Recovery Quorum:** `{policy.recovery_quorum}` approval(s)\n\n"
            f"**Configuration Commands:**\n"
            f"`{settings.BOT_PREFIX}lockdown policy level [observe|investigate|alert|lockdown]`\n"
            f"`{settings.BOT_PREFIX}lockdown policy shadow [on|off]`\n"
            f"`{settings.BOT_PREFIX}lockdown policy threshold bans <count> <seconds>`\n"
            f"`{settings.BOT_PREFIX}lockdown policy quorum <number>`"
        )
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} Security Response Policy")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(desc)
            .build()
        )
        return await send_response(message, box)

    action = sub_args[0].lower()
    if action == "level" and len(sub_args) > 1:
        target_lvl = sub_args[1].lower()
        if target_lvl in ResponseLevel.ALL:
            policy.response_level = target_lvl
            security_protection_service.save_policy(policy)
            return await send_response(
                message,
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"✅ Response Level updated to `{target_lvl.upper()}`.")
                .build()
            )
    elif action == "shadow" and len(sub_args) > 1:
        is_on = sub_args[1].lower() in ("on", "true", "1", "enable")
        policy.shadow_mode = is_on
        policy.auto_lockdown_enabled = not is_on
        security_protection_service.save_policy(policy)
        mode_str = "SHADOW (Simulation Only)" if is_on else "LIVE ENFORCEMENT"
        return await send_response(
            message,
            ContainerBuilder()
            .set_accent_color(COLORS.get("success", "#3FD438"))
            .add_text_display(f"✅ Enforcement mode updated to `{mode_str}`.")
            .build()
        )
    elif action == "threshold" and len(sub_args) > 3:
        target_vector = sub_args[1].lower()
        try:
            cnt = int(sub_args[2])
            win = float(sub_args[3])
            if target_vector in ("ban", "bans"):
                policy.rapid_ban_threshold_count = cnt
                policy.rapid_ban_threshold_window_seconds = win
            elif target_vector in ("kick", "kicks"):
                policy.rapid_kick_threshold_count = cnt
                policy.rapid_kick_threshold_window_seconds = win
            elif target_vector in ("channel", "channels"):
                policy.rapid_channel_delete_threshold_count = cnt
                policy.rapid_channel_delete_threshold_window_seconds = win
            elif target_vector in ("role", "roles"):
                policy.rapid_role_delete_threshold_count = cnt
                policy.rapid_role_delete_threshold_window_seconds = win
            security_protection_service.save_policy(policy)
            return await send_response(
                message,
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"✅ Threshold updated: `{target_vector}` -> `{cnt}` within `{int(win)}s`.")
                .build()
            )
        except ValueError:
            pass
    elif action == "quorum" and len(sub_args) > 1:
        try:
            q = int(sub_args[1])
            policy.recovery_quorum = max(1, q)
            security_protection_service.save_policy(policy)
            return await send_response(
                message,
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"✅ Recovery quorum set to `{policy.recovery_quorum}` approval(s).")
                .build()
            )
        except ValueError:
            pass

    return await send_response(
        message,
        ContainerBuilder()
        .set_accent_color(COLORS.get("error", "#B21F1F"))
        .add_text_display(f"❌ Invalid policy argument. Use `{settings.BOT_PREFIX}lockdown policy` to view options.")
        .build()
    )


async def _handle_journal(message: Any, guild: Any):
    """Displays recent containment journal entries."""
    gid = str(guild.id)
    active_lck = lockdown_journal_manager.get_active_lockdown_for_guild(gid)
    if not active_lck:
        records = [
            l for l in lockdown_journal_manager._lockdowns.values()
            if str(l.guild_id) == gid
        ]
        active_lck = records[-1] if records else None

    if not active_lck:
        return await send_response(
            message,
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"No lockdown journal entries recorded for this server.")
            .build()
        )

    entry_lines = []
    for e in active_lck.entries[:10]:
        status_icon = {
            JournalEntryStatus.APPLIED: "🔒",
            JournalEntryStatus.VERIFIED: "✅",
            JournalEntryStatus.SKIPPED_HIERARCHY: "⚠️",
            JournalEntryStatus.SKIPPED_PRESERVED: "🛡️",
            JournalEntryStatus.RESTORED: "🔓",
            JournalEntryStatus.CONFLICT_DETECTED: "⚡",
            JournalEntryStatus.FAILED_API: "❌",
        }.get(e.status, "•")
        entry_lines.append(f"{status_icon} `{e.target_name or e.target_id}`: `{e.status}`")

    box = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### 📋 Permission Journal: `{active_lck.lockdown_id}`")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"**Baseline Checksum:** `{active_lck.checksum}`\n"
            f"**Total Entries:** {len(active_lck.entries)}\n\n"
            + "\n".join(entry_lines)
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Immutable Journal Proof")
        .build()
    )
    return await send_response(message, box)


async def _handle_review(
    message: Any,
    guild: Any,
    policy: SecurityResponsePolicy,
    incident_id: Optional[str] = None,
):
    """Displays incident consensus review interface with interactive voting controls."""
    gid = str(guild.id)
    target_inc = None

    if incident_id:
        target_inc = incident_manager.get_incident(incident_id)
    else:
        # Check active emergency lockdown first
        active_lck = lockdown_journal_manager.get_active_lockdown_for_guild(gid)
        if active_lck and active_lck.incident_id:
            target_inc = incident_manager.get_incident(active_lck.incident_id)
        if not target_inc:
            active_incs = incident_manager.get_active_incidents(gid)
            if active_incs:
                target_inc = active_incs[-1]

    if not target_inc:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('info', 'ℹ️')} No Active Incident Found")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                "No active security incidents found for this server to review.\n\n"
                f"To inspect or cast votes on a specific historical incident, use:\n"
                f"`{settings.BOT_PREFIX}lockdown review <incident_id>`"
            )
            .build()
        )
        return await send_response(message, box)

    summary = incident_consensus_manager.get_consensus_summary(target_inc.incident_id)
    box = build_incident_review_container(target_inc, policy, summary)
    view = IncidentReviewView(target_inc, policy=policy)
    return await send_response(message, box, view=view)
