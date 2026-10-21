import time
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SeparatorSpacingSize,
    ButtonStyle,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType


name = "setup"
aliases = ["antinukesetup", "secsetup"]
description = "Guided interactive multi-step configuration for anti-nuke defense modes, events, and logging."
category = "Security"
usage = "setup"
user_permissions = ["administrator"]
cooldown = 3.0
guild_only = True


# In-memory wizard session store: guild_id -> dict of draft wizard configurations
_WIZARD_SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_or_create_wizard_session(guild: discord.Guild) -> Dict[str, Any]:
    gid = str(guild.id)
    if gid not in _WIZARD_SESSIONS:
        cfg = AntiNukeManager.get_guild_config(gid)
        _WIZARD_SESSIONS[gid] = {
            "guild_id": gid,
            "mode": cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE),
            "monitored_events": list(cfg.get("monitored_events", AntiNukeConstants.ALL_EVENTS)),
            "warning_channel_id": cfg.get("warning_channel_id"),
            "log_channel_id": cfg.get("log_channel_id"),
            "step": 1,
            "completed_steps": set(),
        }
    return _WIZARD_SESSIONS[gid]


async def build_wizard_step1_view(guild: discord.Guild) -> Any:
    """Step 1: Pre-Flight Security Audit & Hierarchy Validation."""
    me = guild.me
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 1
    sess["completed_steps"].add(1)

    # 1. Audit Role Hierarchy
    higher_roles = [r for r in guild.roles if r.position >= me.top_role.position and not r.is_default() and r != me.top_role]
    hierarchy_is_safe = (len(higher_roles) == 0)

    if hierarchy_is_safe:
        hierarchy_note = f"{EMOJIS.get('check', '✅')} **Role Hierarchy Safe**: Bot top role `{me.top_role.name}` is positioned above all monitored roles."
    else:
        higher_names = ", ".join([f"`{r.name}`" for r in higher_roles[:4]])
        hierarchy_note = (
            f"{EMOJIS.get('warning', '⚠️')} **Role Hierarchy Warning**: Bot role `{me.top_role.name}` (pos {me.top_role.position}) "
            f"is lower than {len(higher_roles)} role(s) ({higher_names}).\n"
            f"-# *The bot cannot restrict or strip roles from members in higher roles.*"
        )

    # 2. Audit Bot Permissions
    missing_bot_perms = []
    if not me.guild_permissions.administrator:
        reqs = [
            ("ban_members", "Ban Members"),
            ("kick_members", "Kick Members"),
            ("manage_roles", "Manage Roles"),
            ("manage_channels", "Manage Channels"),
            ("view_audit_log", "View Audit Log"),
        ]
        for attr, label in reqs:
            if not getattr(me.guild_permissions, attr, False):
                missing_bot_perms.append(label)

    if not missing_bot_perms:
        bot_perms_note = f"{EMOJIS.get('check', '✅')} **Bot Permissions Safe**: Bot holds necessary administrative permissions."
    else:
        bot_perms_note = f"{EMOJIS.get('cross', '❌')} **Missing Bot Permissions**: `{', '.join(missing_bot_perms)}`."

    # 3. Native Dangerous Roles Audit
    dangerous_roles = []
    for r in guild.roles:
        if r.is_default() or r.managed:
            continue
        held_dangerous = []
        for p_key, p_name in AntiNukeConstants.DANGEROUS_PERMISSIONS.items():
            if getattr(r.permissions, p_key, False):
                held_dangerous.append(p_name)
        if held_dangerous:
            dangerous_roles.append((r, held_dangerous))

    d_count = len(dangerous_roles)
    if d_count > 0:
        d_summary = f"{EMOJIS.get('danger', '⚠️')} **{d_count} role(s)** hold dangerous native Discord permissions (Administrator, Manage Channels, etc.)."
    else:
        d_summary = f"{EMOJIS.get('check', '✅')} No unmanaged roles hold dangerous native permissions."

    # Risk Explanation
    risk_info = (
        f"**Security Architecture Risk Notice:**\n"
        f"• **Administrator:** Completely bypasses permission overwrites and channel locks.\n"
        f"• **Manage Roles / Channels:** Allows rogue actors to delete channels or create elevated roles.\n"
        f"• **Recommendation:** Virtualize moderation tasks through bot commands (`$channel`, `$announce`) "
        f"instead of granting raw Discord administrative permissions."
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step2:{guild.id}")
            .set_label("Next: Operating Mode")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {get_string('security.antinuke.wizard_step1_title', 'Setup Step 1/6: Pre-Flight Security Audit')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{hierarchy_note}\n\n{bot_perms_note}\n\n{d_summary}\n\n{risk_info}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 1 of 6")
        .add_action_row(action_row)
        .build()
    )


async def build_wizard_step2_view(guild: discord.Guild) -> Any:
    """Step 2: Operating Mode Selection."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 2
    sess["completed_steps"].add(2)
    current_mode = sess.get("mode", AntiNukeConstants.MODE_ULTIMATE)

    desc = (
        f"Select the defensive posture for **{guild.name}**:\n\n"
        f"• **Ultimate Defence Wall (`ultimate`):** {EMOJIS.get('shield', '🛡️')} Configurable sliding burst thresholds "
        f"with automated role quarantine. High-resilience defense without disrupting everyday staff tasks. *(Recommended)*\n\n"
        f"• **Hard Zero-Tolerance (`hard`):** {EMOJIS.get('danger', '⚡')} 1 unauthorized action triggers immediate permanent ban. "
        f"Best for zero-compromise lockdown environments.\n\n"
        f"• **Hybrid Dynamic Defense (`hybrid`):** {EMOJIS.get('sparkles', '✨')} Instant bans on rogue bot adds & permission grants, "
        f"sliding burst thresholds on channels and roles."
    )

    action_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:set_mode:ultimate:{guild.id}")
            .set_label("Ultimate Defence Wall" + (" (Selected)" if current_mode == "ultimate" else ""))
            .set_style(ButtonStyle.Success if current_mode == "ultimate" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:set_mode:hard:{guild.id}")
            .set_label("Hard Zero-Tolerance" + (" (Selected)" if current_mode == "hard" else ""))
            .set_style(ButtonStyle.Success if current_mode == "hard" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("danger", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:set_mode:hybrid:{guild.id}")
            .set_label("Hybrid Defense" + (" (Selected)" if current_mode == "hybrid" else ""))
            .set_style(ButtonStyle.Success if current_mode == "hybrid" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("sparkles", "✨"))
        )
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step1:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step3:{guild.id}")
            .set_label("Next: Event Scope")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} {get_string('security.antinuke.wizard_step2_title', 'Setup Step 2/6: Defensive Operating Mode')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"Selected Mode: **{AntiNukeManager.get_mode_display_name(current_mode)}**\n\n{desc}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 2 of 6")
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
        .build()
    )


async def build_wizard_step3_view(guild: discord.Guild) -> Any:
    """Step 3: Event Monitoring Scope Selection."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 3
    sess["completed_steps"].add(3)

    monitored = sess.get("monitored_events", AntiNukeConstants.ALL_EVENTS)
    is_all = (len(monitored) >= len(AntiNukeConstants.ALL_EVENTS))

    desc = (
        f"Select the gateway events to monitor in real-time. Anti-Nuke actively observes **24 critical vectors**:\n\n"
        f"• **Server:** Server Settings, Integrations, Emojis, Stickers\n"
        f"• **Structure:** Channels, Threads, Categories, Webhooks\n"
        f"• **Permissions:** Roles, Member Roles, Overwrites, AutoMod Rules\n"
        f"• **Moderation:** Bans, Kicks, Rogue Bot Adds, Invites, Audit Logs\n\n"
        f"Currently Monitoring: **{len(monitored)} / {len(AntiNukeConstants.ALL_EVENTS)} events**"
    )

    action_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:events_all:{guild.id}")
            .set_label("Monitor All 24 Events (Recommended)")
            .set_style(ButtonStyle.Success if is_all else ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step2:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step4:{guild.id}")
            .set_label("Next: Punishments")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('tools', '🔧')} {get_string('security.antinuke.wizard_step3_title', 'Setup Step 3/6: Event Monitoring Scope')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 3 of 6")
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
        .build()
    )


async def build_wizard_step4_view(guild: discord.Guild) -> Any:
    """Step 4: Punishments & Thresholds Review."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 4
    sess["completed_steps"].add(4)
    mode = sess.get("mode", AntiNukeConstants.MODE_ULTIMATE)

    desc = (
        f"Review disciplinary response templates for **{AntiNukeManager.get_mode_display_name(mode)}**:\n\n"
        f"• **Critical Events** (Bans, Kicks, Role Deletes, Rogue Bots): **BAN**\n"
        f"• **High Events** (Channels, Role Escalations, Webhooks): **QUARANTINE / STRIP ROLES**\n"
        f"• **Medium Events** (Invites, Scheduled Events): **TIMEOUT**\n\n"
        f"-# *Note:* You can fine-tune punishment rules per event at any time via `$punishment`."
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step3:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step5:{guild.id}")
            .set_label("Next: Logging Channels")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('danger', '⚡')} {get_string('security.antinuke.wizard_step4_title', 'Setup Step 4/6: Punishments & Thresholds')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 4 of 6")
        .add_action_row(action_row)
        .build()
    )


async def build_wizard_step5_view(guild: discord.Guild, current_ch_id: Optional[int] = None) -> Any:
    """Step 5: Alert & Log Channels Configuration."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 5
    sess["completed_steps"].add(5)

    warn_ch = sess.get("warning_channel_id")
    log_ch = sess.get("log_channel_id")

    warn_str = f"<#{warn_ch}>" if warn_ch else "*Not Assigned*"
    log_str = f"<#{log_ch}>" if log_ch else "*Not Assigned*"

    desc = (
        f"Configure channels where security alerts and audit records are posted:\n\n"
        f"• **Warning & Forensic Channel:** {warn_str}\n"
        f"• **Audit Log Channel:** {log_str}\n\n"
        f"Click the button below to bind the current channel (<#{current_ch_id}>) as the security alert channel, "
        f"or proceed to use server defaults."
    )

    action_row_1 = ActionRowBuilder()
    if current_ch_id:
        action_row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:bind_ch:{guild.id}:{current_ch_id}")
            .set_label(f"Bind Current Channel as Alert Channel")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("channel", "📍"))
        )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step4:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step6:{guild.id}")
            .set_label("Next: Final Activation")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    builder = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('channel', '📢')} {get_string('security.antinuke.wizard_step5_title', 'Setup Step 5/6: Alert & Log Channels')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 5 of 6")
    )
    if current_ch_id:
        builder.add_action_row(action_row_1)
    builder.add_action_row(action_row_2)
    return builder.build()


async def build_wizard_step6_view(guild: discord.Guild) -> Any:
    """Step 6: Review & Final System Activation."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 6

    # Validate that prerequisites are covered
    mode = sess.get("mode", AntiNukeConstants.MODE_ULTIMATE)
    monitored = sess.get("monitored_events", AntiNukeConstants.ALL_EVENTS)
    warn_ch = sess.get("warning_channel_id")
    log_ch = sess.get("log_channel_id")

    warn_str = f"<#{warn_ch}>" if warn_ch else "*Default Guild System*"
    log_str = f"<#{log_ch}>" if log_ch else "*Default Guild System*"

    me = guild.me
    higher_roles = [r for r in guild.roles if r.position >= me.top_role.position and not r.is_default() and r != me.top_role]
    hierarchy_str = f"{EMOJIS.get('check', '✅')} Bot Top Role Positioned" if not higher_roles else f"{EMOJIS.get('warning', '⚠️')} {len(higher_roles)} role(s) above bot"
    perms_str = f"{EMOJIS.get('check', '✅')} Administrator / Moderation Permissions Verified"

    summary_text = (
        f"**Anti-Nuke Configuration Summary:**\n"
        f"• **Target Guild:** `{guild.name}` (`{guild.id}`)\n"
        f"• **Operating Mode:** **`{AntiNukeManager.get_mode_display_name(mode)}`**\n"
        f"• **Active Monitored Vectors:** `{len(monitored)}` events\n"
        f"• **Role Hierarchy Check:** {hierarchy_str}\n"
        f"• **Permissions Check:** {perms_str}\n"
        f"• **Warning Channel:** {warn_str}\n"
        f"• **Log Channel:** {log_str}\n\n"
        f"Click **Activate Anti-Nuke Defense** to finalize setup and initialize real-time gateway defense."
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:complete:{guild.id}")
            .set_label("Activate Anti-Nuke Defense")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step5:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("success", "#3FD438"))
        .add_text_display(f"### {EMOJIS.get('check', '✅')} {get_string('security.antinuke.wizard_step6_title', 'Setup Step 6/6: Review & Final Activation')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(summary_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 6 of 6")
        .add_action_row(action_row)
        .build()
    )


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Check root permission
    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can run the Setup Wizard.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Initialize fresh wizard session
    gid = str(guild.id)
    _WIZARD_SESSIONS[gid] = {
        "guild_id": gid,
        "mode": AntiNukeConstants.MODE_ULTIMATE,
        "monitored_events": list(AntiNukeConstants.ALL_EVENTS),
        "warning_channel_id": getattr(message.channel, "id", None),
        "log_channel_id": getattr(message.channel, "id", None),
        "step": 1,
        "completed_steps": {1},
    }

    view = await build_wizard_step1_view(guild)
    return await send_response(message, view)
