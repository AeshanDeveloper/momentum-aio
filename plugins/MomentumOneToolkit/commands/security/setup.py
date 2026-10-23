import time
from typing import List, Dict, Any, Optional, Set
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SelectMenuBuilder,
    SelectMenuTypes,
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
        enabled_modes = AntiNukeConstants.get_enabled_modes()
        cur_mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
        if cur_mode not in enabled_modes:
            cur_mode = enabled_modes[0] if enabled_modes else AntiNukeConstants.MODE_HARD

        _WIZARD_SESSIONS[gid] = {
            "guild_id": gid,
            "mode": cur_mode,
            "mode_confirmed": False,
            "monitored_events": list(cfg.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)),
            "events_confirmed": False,
            "thresholds": dict(cfg.get("thresholds") or get_default_thresholds(cur_mode)),
            "threshold_active_event": AntiNukeConstants.EVENT_CHANNEL_DELETE,
            "thresholds_confirmed": False,
            "punishments": dict(cfg.get("punishments") or get_default_punishments(cur_mode)),
            "punish_active_event": AntiNukeConstants.EVENT_CHANNEL_DELETE,
            "punishments_confirmed": False,
            "warning_channel_id": cfg.get("warning_channel_id"),
            "warning_ch_confirmed": False,
            "log_channel_id": cfg.get("log_channel_id"),
            "log_ch_confirmed": False,
            "ticket_bots": list(cfg.get("ticket_bots", [])),
            "extra_owners": list(cfg.get("extra_owners", [])),
            "whitelists": dict(cfg.get("whitelists", {})),
            "step": 1,
            "completed_steps": {1},
        }
    return _WIZARD_SESSIONS[gid]


TOTAL_STEPS = 11


# ==============================================================================
# Step 1: Pre-Flight Security Audit & Hierarchy Validation
# ==============================================================================
async def build_wizard_step1_view(guild: discord.Guild) -> Any:
    """Step 1/11: Pre-Flight Security Audit & Hierarchy Validation."""
    me = guild.me
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 1
    sess["completed_steps"].add(1)

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
        d_summary = f"{EMOJIS.get('danger', '⚠️')} **{d_count} unmanaged role(s)** hold dangerous native Discord permissions (Administrator, Manage Channels, etc.)."
    else:
        d_summary = f"{EMOJIS.get('check', '✅')} No unmanaged roles hold dangerous native permissions."

    risk_info = (
        f"**Security Architecture Notice:**\n"
        f"• Anti-Nuke operates natively through Discord gateway listeners and real-time audit log evaluation.\n"
        f"• The following 10 steps will guide you through each defense setting."
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step2:{guild.id}")
            .set_label("Continue: Operating Mode")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:cancel:{guild.id}")
            .set_label("Cancel Setup")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Setup Step 1/{TOTAL_STEPS}: Pre-Flight Security Audit")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{hierarchy_note}\n\n{bot_perms_note}\n\n{d_summary}\n\n{risk_info}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 1 of {TOTAL_STEPS}")
        .add_action_row(action_row)
        .build()
    )


# ==============================================================================
# Step 2: Defensive Operating Mode Selection
# ==============================================================================
async def build_wizard_step2_view(guild: discord.Guild) -> Any:
    """Step 2/11: Operating Mode Selection (String Select Menu with enabled modes)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 2
    enabled_modes = AntiNukeConstants.get_enabled_modes()
    current_mode = sess.get("mode", AntiNukeConstants.MODE_HARD)
    if current_mode not in enabled_modes:
        current_mode = enabled_modes[0] if enabled_modes else AntiNukeConstants.MODE_HARD
        sess["mode"] = current_mode

    mode_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wiz:select_mode:{guild.id}")
        .set_placeholder("Select defensive operating mode...")
    )
    for m in enabled_modes:
        name = AntiNukeManager.get_mode_display_name(m)
        desc = get_string(f"security.antinuke.mode_descriptions.{m}", "Strict protection against destructive changes.")
        mode_select.add_option(
            label=name[:100],
            value=m,
            description=desc[:100],
            default=(m == current_mode),
        )

    mode_status = f"**Current Selection:** `{AntiNukeManager.get_mode_display_name(current_mode)}`"
    if sess.get("mode_confirmed"):
        mode_status += f" {EMOJIS.get('check', '✅')} *(User Confirmed)*"
    else:
        mode_status += " *(Click menu option or Continue to confirm)*"

    desc = (
        f"Choose the core defense posture for **{guild.name}**:\n\n"
        f"• **Hard Zero-Tolerance (`hard`):** Strict real-time sanctions against unauthorized structural alterations.\n\n"
        f"{mode_status}"
    )

    action_row = (
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
            .set_label("Continue: Monitored Events")
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
        .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} Setup Step 2/{TOTAL_STEPS}: Defensive Operating Mode")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(mode_select))
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 2 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 3: Event Monitoring Scope Selection (Multi-Select String Select Menu)
# ==============================================================================
async def build_wizard_step3_view(guild: discord.Guild) -> Any:
    """Step 3/11: Event Monitoring Scope Selection (23 configurable events from registry)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 3
    monitored = set(sess.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS))

    # Build String Select Menu for events (excluding generic internal audit log creation)
    event_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wiz:select_events:{guild.id}")
        .set_placeholder("Select monitored events (multi-selection supported)...")
        .set_min_values(1)
        .set_max_values(min(23, len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)))
    )

    # 23 Canonical user-facing events
    for ev in AntiNukeConstants.USER_CONFIGURABLE_EVENTS:
        name = AntiNukeConstants.get_event_display_name(ev)
        desc = AntiNukeConstants.get_event_description(ev)
        event_select.add_option(
            label=name[:100],
            value=ev,
            description=desc[:100],
            default=(ev in monitored),
        )

    is_all = (len(monitored) >= len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS))
    confirmed_badge = f"{EMOJIS.get('check', '✅')} *(Confirmed)*" if sess.get("events_confirmed") else "*(Unconfirmed Draft)*"

    desc = (
        f"Select the gateway events to monitor in real-time. Use the select menu to choose multiple events, "
        f"or click **Monitor All 23 Events**.\n\n"
        f"• **Active Scope:** **{len(monitored)} / {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)} events** {confirmed_badge}\n"
        f"• **Status:** Disabled events will not trigger rate-limiting or punishments."
    )

    action_row_quick = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:events_all:{guild.id}")
            .set_label("Monitor All 23 Events (Recommended)")
            .set_style(ButtonStyle.Success if is_all else ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:events_confirm:{guild.id}")
            .set_label("Confirm Current Events")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
    )

    action_row_nav = (
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
            .set_label("Continue: Thresholds")
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
        .add_text_display(f"### {EMOJIS.get('tools', '🔧')} Setup Step 3/{TOTAL_STEPS}: Monitored Events Scope")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(event_select))
        .add_action_row(action_row_quick)
        .add_action_row(action_row_nav)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 3 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 4: Thresholds Configuration
# ==============================================================================
async def build_wizard_step4_view(guild: discord.Guild) -> Any:
    """Step 4/11: Thresholds Configuration for Enabled Events."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 4
    active_ev = sess.get("threshold_active_event", AntiNukeConstants.EVENT_CHANNEL_DELETE)
    thresholds = sess.get("thresholds", {})
    cur_th = thresholds.get(active_ev, {"count": 1, "window": 60})
    cur_cnt = cur_th.get("count", 1)
    cur_win = cur_th.get("window", 60)

    friendly_name = AntiNukeConstants.get_event_display_name(active_ev)
    win_str = "Lifetime" if cur_win == 0 else f"{cur_win}s"

    # Event Picker String Select Menu
    ev_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wiz:th_pick_event:{guild.id}")
        .set_placeholder("Select event to adjust threshold...")
    )
    monitored = sess.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
    for ev in monitored[:25]:
        name = AntiNukeConstants.get_event_display_name(ev)
        th = thresholds.get(ev, {"count": 1, "window": 60})
        ev_select.add_option(
            label=name[:100],
            value=ev,
            description=f"Limit: {th.get('count', 1)} action(s) / {th.get('window', 60)}s"[:100],
            default=(ev == active_ev),
        )

    # Action count quick-buttons
    count_row = ActionRowBuilder()
    for c_val in [1, 2, 3, 5]:
        is_cur = (cur_cnt == c_val)
        count_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:th_set_count:{active_ev}:{c_val}:{guild.id}")
            .set_label(f"{c_val} Action{'s' if c_val > 1 else ' (Instant)'}")
            .set_style(ButtonStyle.Primary if is_cur else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("check" if is_cur else "bullet", "•"))
        )

    # Time window quick-buttons
    window_row = ActionRowBuilder()
    for w_val, w_label in [(10, "10s"), (30, "30s"), (60, "60s"), (0, "Lifetime")]:
        is_cur = (cur_win == w_val)
        window_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:th_set_window:{active_ev}:{w_val}:{guild.id}")
            .set_label(w_label)
            .set_style(ButtonStyle.Primary if is_cur else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("check" if is_cur else "clock", "⏱️"))
        )

    confirmed_status = f"{EMOJIS.get('check', '✅')} *(Confirmed)*" if sess.get("thresholds_confirmed") else "*(Unconfirmed)*"

    desc = (
        f"Configure threshold limits for monitored events.\n\n"
        f"• **Inspecting:** **{friendly_name}** (`{active_ev}`)\n"
        f"• **Current Limit:** `{cur_cnt}` action(s) per `{win_str}` {confirmed_status}\n"
        f"-# Adjust count and window below, or click **Confirm & Use Defaults**."
    )

    action_row_nav = (
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
            .set_custom_id(f"an_wiz:th_confirm:{guild.id}")
            .set_label("Confirm Thresholds")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step5:{guild.id}")
            .set_label("Continue: Punishments")
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
        .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} Setup Step 4/{TOTAL_STEPS}: Action Thresholds")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(ev_select))
        .add_text_display("**Action Limit Count:**")
        .add_action_row(count_row)
        .add_text_display("**Time Window:**")
        .add_action_row(window_row)
        .add_action_row(action_row_nav)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 4 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 5: Punishments Configuration
# ==============================================================================
async def build_wizard_step5_view(guild: discord.Guild) -> Any:
    """Step 5/11: Punishment Selection for Enabled Events."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 5
    active_ev = sess.get("punish_active_event", AntiNukeConstants.EVENT_CHANNEL_DELETE)
    punishments = sess.get("punishments", {})
    cur_punish = punishments.get(active_ev, AntiNukeConstants.PUNISH_BAN)
    friendly_name = AntiNukeConstants.get_event_display_name(active_ev)

    ev_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wiz:pn_pick_event:{guild.id}")
        .set_placeholder("Select event to configure disciplinary action...")
    )
    monitored = sess.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
    for ev in monitored[:25]:
        name = AntiNukeConstants.get_event_display_name(ev)
        p = punishments.get(ev, "ban")
        ev_select.add_option(
            label=name[:100],
            value=ev,
            description=f"Action: {p.upper()}"[:100],
            default=(ev == active_ev),
        )

    # Punishment buttons: Ban, Kick, Timeout, Prune, Strip Roles (Quarantine disabled)
    btn_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:pn_set:{active_ev}:ban:{guild.id}")
            .set_label("Ban" + (" (Active)" if cur_punish == "ban" else ""))
            .set_style(ButtonStyle.Danger if cur_punish == "ban" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("ban", "🚫"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:pn_set:{active_ev}:kick:{guild.id}")
            .set_label("Kick" + (" (Active)" if cur_punish == "kick" else ""))
            .set_style(ButtonStyle.Primary if cur_punish == "kick" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("danger", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:pn_set:{active_ev}:timeout:{guild.id}")
            .set_label("Mute / Timeout" + (" (Active)" if cur_punish == "timeout" else ""))
            .set_style(ButtonStyle.Primary if cur_punish == "timeout" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("clock", "⏳"))
        )
    )

    btn_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:pn_set:{active_ev}:strip_roles:{guild.id}")
            .set_label("Strip Roles" + (" (Active)" if cur_punish == "strip_roles" else ""))
            .set_style(ButtonStyle.Primary if cur_punish == "strip_roles" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("role", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:pn_set:{active_ev}:prune:{guild.id}")
            .set_label("Prune" + (" (Active)" if cur_punish == "prune" else ""))
            .set_style(ButtonStyle.Primary if cur_punish == "prune" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("trash", "✂️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:pn_quarantine:{guild.id}")
            .set_label("Quarantine (Unavailable)")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("lock", "🔒"))
            .set_disabled(True)
        )
    )

    confirmed_status = f"{EMOJIS.get('check', '✅')} *(Confirmed)*" if sess.get("punishments_confirmed") else "*(Unconfirmed)*"

    desc = (
        f"Select the disciplinary sanction for unauthorized operations:\n\n"
        f"• **Inspecting:** **{friendly_name}** (`{active_ev}`)\n"
        f"• **Current Action:** **`{cur_punish.upper()}`** {confirmed_status}\n"
        f"-# Select punishment buttons below to update."
    )

    nav_row = (
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
            .set_custom_id(f"an_wiz:pn_confirm:{guild.id}")
            .set_label("Confirm Punishments")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step6:{guild.id}")
            .set_label("Continue: Warning Channel")
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
        .add_text_display(f"### {EMOJIS.get('danger', '⚡')} Setup Step 5/{TOTAL_STEPS}: Disciplinary Sanctions")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(ev_select))
        .add_action_row(btn_row_1)
        .add_action_row(btn_row_2)
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 5 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 6: Security Warning / Alert Channel (Native Channel Select Menu)
# ==============================================================================
async def build_wizard_step6_view(guild: discord.Guild) -> Any:
    """Step 6/11: Security Warning Channel (Native Channel Select Menu)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 6
    warn_ch = sess.get("warning_channel_id")
    warn_str = f"<#{warn_ch}> (`{warn_ch}`)" if warn_ch else "*Not Selected Yet*"
    confirmed = bool(sess.get("warning_ch_confirmed") and warn_ch)
    status_icon = EMOJIS.get("check", "✅") if confirmed else EMOJIS.get("warning", "⚠️")

    # Native Channel Select Menu
    ch_select = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.CHANNEL)
        .set_custom_id(f"an_wiz:set_warning_ch:{guild.id}")
        .set_placeholder("Select Security Warning Channel from list...")
    )

    desc = (
        f"Select the channel where immediate real-time forensic warnings and incident alerts will be posted.\n\n"
        f"• **Selected Warning Channel:** {status_icon} {warn_str}\n\n"
        f"-# *Notice: Use the native channel selector below to choose the target channel.*"
    )

    nav_row = ActionRowBuilder()
    nav_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wiz:step5:{guild.id}")
        .set_label("Back")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
    )
    if warn_ch:
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step7:{guild.id}")
            .set_label("Continue: Log Channel")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
    else:
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:warn_ch_missing:{guild.id}")
            .set_label("Select a Channel to Continue")
            .set_style(ButtonStyle.Secondary)
            .set_disabled(True)
        )
    nav_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wiz:cancel:{guild.id}")
        .set_label("Cancel")
        .set_style(ButtonStyle.Danger)
        .set_emoji(EMOJIS.get("cross", "❌"))
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('channel', '📢')} Setup Step 6/{TOTAL_STEPS}: Security Warning Channel")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(ch_select))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 6 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 7: Incident Forensics Log Channel (Native Channel Select Menu)
# ==============================================================================
async def build_wizard_step7_view(guild: discord.Guild) -> Any:
    """Step 7/11: Incident Forensics Log Channel (Native Channel Select Menu)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 7
    log_ch = sess.get("log_channel_id")
    log_str = f"<#{log_ch}> (`{log_ch}`)" if log_ch else "*Not Selected Yet*"
    confirmed = bool(sess.get("log_ch_confirmed") and log_ch)
    status_icon = EMOJIS.get("check", "✅") if confirmed else EMOJIS.get("warning", "⚠️")

    # Native Channel Select Menu
    ch_select = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.CHANNEL)
        .set_custom_id(f"an_wiz:set_log_ch:{guild.id}")
        .set_placeholder("Select Forensic Audit Log Channel from list...")
    )

    desc = (
        f"Select the channel where complete forensic audit logs, non-punitive audit records, and security telemetry are logged.\n\n"
        f"• **Selected Log Channel:** {status_icon} {log_str}\n\n"
        f"-# *Notice: Use the native channel selector below to choose the target channel.*"
    )

    nav_row = ActionRowBuilder()
    nav_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wiz:step6:{guild.id}")
        .set_label("Back")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
    )
    if log_ch:
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step8:{guild.id}")
            .set_label("Continue: Ticket Bots")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_right", "➡️"))
        )
    else:
        nav_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:log_ch_missing:{guild.id}")
            .set_label("Select a Channel to Continue")
            .set_style(ButtonStyle.Secondary)
            .set_disabled(True)
        )
    nav_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wiz:cancel:{guild.id}")
        .set_label("Cancel")
        .set_style(ButtonStyle.Danger)
        .set_emoji(EMOJIS.get("cross", "❌"))
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('channel', '📝')} Setup Step 7/{TOTAL_STEPS}: Forensic Log Channel")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(ch_select))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 7 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 8: Trusted Ticket Bots (Native User Select Menu, with Skip)
# ==============================================================================
async def build_wizard_step8_view(guild: discord.Guild) -> Any:
    """Step 8/11: Trusted Ticket Bots Exemption (Native User Select Menu)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 8
    tbs = sess.get("ticket_bots", [])

    user_select = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an_wiz:pick_ticket_bot:{guild.id}")
        .set_placeholder("Select trusted ticket bot to exempt...")
    )

    tb_lines = [f"• <@{b_id}> (`{b_id}`)" for b_id in tbs]
    tb_summary = "\n".join(tb_lines) if tb_lines else "*No ticket bots configured (Optional)*"

    desc = (
        f"Exempt ticket bot accounts from false-positive rate-limiting when they rapidly create or delete support ticket channels.\n\n"
        f"**Currently Exempted Ticket Bots ({len(tbs)}):**\n"
        f"{tb_summary}\n\n"
        f"-# *This step is optional. Click Skip if no ticket bots operate in this server.*"
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step7:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step9:{guild.id}")
            .set_label("Continue: Extra Owners" if tbs else "Skip: Extra Owners")
            .set_style(ButtonStyle.Primary if tbs else ButtonStyle.Secondary)
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
        .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Setup Step 8/{TOTAL_STEPS}: Ticket Bot Exemptions")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(user_select))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 8 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 9: Extra Owners (Native User Select Menu, with Warnings & Skip)
# ==============================================================================
async def build_wizard_step9_view(guild: discord.Guild) -> Any:
    """Step 9/11: Extra Owners (Native User Select Menu)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 9
    eos = sess.get("extra_owners", [])

    user_select = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an_wiz:pick_extra_owner:{guild.id}")
        .set_placeholder("Select trusted administrator as Extra Owner...")
    )

    eo_lines = [f"• Root Owner: <@{guild.owner_id}> (`{guild.owner_id}`)"]
    for uid in eos:
        eo_lines.append(f"• Extra Owner: <@{uid}> (`{uid}`)")
    eo_summary = "\n".join(eo_lines)

    desc = (
        f"{EMOJIS.get('warning', '⚠️')} **High-Privilege Authorization Notice:**\n"
        f"Extra Owners bypass anti-nuke sanctions and have full authorization to modify security settings, whitelists, and thresholds.\n\n"
        f"**Configured Security Owners:**\n"
        f"{eo_summary}\n\n"
        f"-# *This step is optional. Click Skip if only the Server Owner should hold security rights.*"
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step8:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step10:{guild.id}")
            .set_label("Continue: Whitelists" if eos else "Skip: Whitelists")
            .set_style(ButtonStyle.Primary if eos else ButtonStyle.Secondary)
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
        .add_text_display(f"### {EMOJIS.get('crown', '👑')} Setup Step 9/{TOTAL_STEPS}: Security Extra Owners")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(user_select))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 9 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 10: Whitelist Configuration (User Select Menu, with Skip)
# ==============================================================================
async def build_wizard_step10_view(guild: discord.Guild) -> Any:
    """Step 10/11: Whitelist Exemption Configuration (Optional)."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 10
    whitelists = sess.get("whitelists", {})

    user_select = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an_wiz:pick_wl_user:{guild.id}")
        .set_placeholder("Select user or bot to grant whitelist exemption...")
    )

    wl_lines = [f"• `{e_id}`: {d.get('name', 'Entity')} (All Events)" for e_id, d in list(whitelists.items())[:5]]
    wl_summary = "\n".join(wl_lines) if wl_lines else "*No entity whitelists configured (Optional)*"

    desc = (
        f"Whitelists exempt trusted moderators or automation bots from anti-nuke sanctions.\n\n"
        f"**Configured Whitelists ({len(whitelists)}):**\n"
        f"{wl_summary}\n\n"
        f"-# *You can fine-tune role, channel, and category exemptions later via `$whitelist`. Click Skip to proceed.*"
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step9:{guild.id}")
            .set_label("Back")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step11:{guild.id}")
            .set_label("Continue: Final Review")
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
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Setup Step 10/{TOTAL_STEPS}: Whitelist Exemptions")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(user_select))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 10 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Step 11: Final Review & Confirmation
# ==============================================================================
async def build_wizard_step11_view(guild: discord.Guild) -> Any:
    """Step 11/11: Final Review & Confirmation."""
    sess = get_or_create_wizard_session(guild)
    sess["step"] = 11

    mode = sess.get("mode", AntiNukeConstants.MODE_HARD)
    monitored = sess.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
    warn_ch = sess.get("warning_channel_id")
    log_ch = sess.get("log_channel_id")
    tbs = sess.get("ticket_bots", [])
    eos = sess.get("extra_owners", [])
    wls = sess.get("whitelists", {})

    can_activate = bool(warn_ch and log_ch)

    warn_str = f"<#{warn_ch}>" if warn_ch else f"{EMOJIS.get('cross', '❌')} **Missing Required Selection**"
    log_str = f"<#{log_ch}>" if log_ch else f"{EMOJIS.get('cross', '❌')} **Missing Required Selection**"

    me = guild.me
    higher_roles = [r for r in guild.roles if r.position >= me.top_role.position and not r.is_default() and r != me.top_role]
    hierarchy_str = f"{EMOJIS.get('check', '✅')} Safe" if not higher_roles else f"{EMOJIS.get('warning', '⚠️')} {len(higher_roles)} higher role(s)"

    summary_text = (
        f"**Final Security Configuration Review:**\n\n"
        f"• **Operating Mode:** `{AntiNukeManager.get_mode_display_name(mode)}`\n"
        f"• **Monitored Vectors:** `{len(monitored)} / {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)}` events\n"
        f"• **Role Hierarchy Check:** {hierarchy_str}\n"
        f"• **Warning Channel:** {warn_str}\n"
        f"• **Log Channel:** {log_str}\n"
        f"• **Ticket Bots:** `{len(tbs)}` approved\n"
        f"• **Extra Owners:** `{len(eos)}` authorized\n"
        f"• **Whitelists:** `{len(wls)}` entities\n\n"
    )

    if can_activate:
        summary_text += f"{EMOJIS.get('check', '✅')} All required settings have been explicitly configured. Click **Confirm & Activate Anti-Nuke** to save permanently."
    else:
        summary_text += f"{EMOJIS.get('cross', '❌')} Both Warning and Log channels are strictly required before activation. Click below to configure the missing channels."

    action_row = ActionRowBuilder()
    if can_activate:
        action_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:complete:{guild.id}")
            .set_label("Confirm & Activate Anti-Nuke")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    else:
        if not warn_ch:
            action_row.add_button(
                ButtonBuilder()
                .set_custom_id(f"an_wiz:step7:{guild.id}")
                .set_label("Configure Warning Channel")
                .set_style(ButtonStyle.Primary)
                .set_emoji(EMOJIS.get("warning", "⚠️"))
            )
        if not log_ch:
            action_row.add_button(
                ButtonBuilder()
                .set_custom_id(f"an_wiz:step8:{guild.id}")
                .set_label("Configure Log Channel")
                .set_style(ButtonStyle.Primary)
                .set_emoji(EMOJIS.get("channel", "📁"))
            )
    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wiz:step10:{guild.id}")
        .set_label("Back")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
    )
    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wiz:cancel:{guild.id}")
        .set_label("Cancel")
        .set_style(ButtonStyle.Danger)
        .set_emoji(EMOJIS.get("cross", "❌"))
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("success" if can_activate else "error", "#3FD438"))
        .add_text_display(f"### {EMOJIS.get('check', '✅')} Setup Step 11/{TOTAL_STEPS}: Review & Confirm Activation")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(summary_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Wizard • Step 11 of {TOTAL_STEPS}")
        .build()
    )


# ==============================================================================
# Command Entrypoint
# ==============================================================================
async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Restrict to Server Owner or Extra Owners
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
    cfg = AntiNukeManager.get_guild_config(gid)
    enabled_modes = AntiNukeConstants.get_enabled_modes()
    cur_mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
    if cur_mode not in enabled_modes:
        cur_mode = enabled_modes[0] if enabled_modes else AntiNukeConstants.MODE_HARD

    _WIZARD_SESSIONS[gid] = {
        "guild_id": gid,
        "mode": cur_mode,
        "mode_confirmed": False,
        "monitored_events": list(cfg.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)),
        "events_confirmed": False,
        "thresholds": dict(cfg.get("thresholds") or get_default_thresholds(cur_mode)),
        "threshold_active_event": AntiNukeConstants.EVENT_CHANNEL_DELETE,
        "thresholds_confirmed": False,
        "punishments": dict(cfg.get("punishments") or get_default_punishments(cur_mode)),
        "punish_active_event": AntiNukeConstants.EVENT_CHANNEL_DELETE,
        "punishments_confirmed": False,
        "warning_channel_id": cfg.get("warning_channel_id"),
        "warning_ch_confirmed": False,
        "log_channel_id": cfg.get("log_channel_id"),
        "log_ch_confirmed": False,
        "ticket_bots": list(cfg.get("ticket_bots", [])),
        "extra_owners": list(cfg.get("extra_owners", [])),
        "whitelists": dict(cfg.get("whitelists", {})),
        "step": 1,
        "completed_steps": {1},
    }

    view = await build_wizard_step1_view(guild)
    return await send_response(message, view)
