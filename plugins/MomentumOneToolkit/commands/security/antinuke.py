import re
import time
from typing import List, Dict, Any, Optional, Set
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from apps.bot.discord.permissions.resolver import is_bot_owner
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

name = "antinuke"
aliases = ["an"]
description = "Enterprise Anti-Nuke defense control center, interactive configuration, and monitoring."
category = "Security"
usage = "antinuke [dashboard|setup|mode|events|status]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


# In-memory staging for dashboard event management: guild_id -> set of event keys
_EVENT_MANAGER_STAGING: Dict[str, Set[str]] = {}


def get_staged_events(guild_id: str | int) -> Set[str]:
    gid = str(guild_id)
    if gid not in _EVENT_MANAGER_STAGING:
        cfg = AntiNukeManager.get_guild_config(gid)
        _EVENT_MANAGER_STAGING[gid] = set(cfg.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS))
    return _EVENT_MANAGER_STAGING[gid]


def set_staged_events(guild_id: str | int, events: Set[str]) -> None:
    _EVENT_MANAGER_STAGING[str(guild_id)] = set(events)


def clear_staged_events(guild_id: str | int) -> None:
    _EVENT_MANAGER_STAGING.pop(str(guild_id), None)


# ==============================================================================
# Compact Anti-Nuke Dashboard
# ==============================================================================
async def build_dashboard_view(guild: discord.Guild) -> Any:
    """Builds the compact, focused Anti-Nuke Dashboard Container using Discord Components V2."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    is_setup = cfg.get("setup_completed", False)
    is_enabled = cfg.get("enabled", False)
    mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)

    if not AntiNukeConstants.is_mode_enabled(mode):
        mode = AntiNukeConstants.MODE_HARD

    mode_display = AntiNukeManager.get_mode_display_name(mode)
    obs_enabled = AntiNukeManager.is_observation_system_enabled(guild.id)
    obs_name = AntiNukeManager.get_observation_system_name(guild.id)

    monitored_events = cfg.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
    log_ch_id = cfg.get("log_channel_id")
    log_ch_str = f"<#{log_ch_id}>" if log_ch_id else "*Not Configured*"
    warn_ch_id = cfg.get("warning_channel_id")
    warn_ch_str = f"<#{warn_ch_id}>" if warn_ch_id else "*Not Configured*"

    if not is_setup:
        status_line = f"{EMOJIS.get('warning', '⚠️')} Defense Status: **SETUP REQUIRED** (Monitoring Inactive)"
    elif is_enabled:
        status_line = f"{EMOJIS.get('enabled', '✅')} Defense Status: **ACTIVE & MONITORING**"
    else:
        status_line = f"{EMOJIS.get('disabled', '❌')} Defense Status: **PAUSED / DISABLED**"

    c_accent = COLORS.get("success" if (is_setup and is_enabled) else "warning", "#0844C5")

    if obs_enabled:
        obs_display = f"👁️ **{obs_name}** `[ENABLED]`\n  ↳ Real-time event normalization, sliding correlation windows, graduated attribution & automated containment."
        wl_posture = "🛡️ **Graduated Whitelist Protection**: Whitelisted actors execute normal administrative tasks freely. Destructive multi-event bursts are cross-correlated in the observation journal."
    else:
        obs_display = f"⚡ **{obs_name}** `[ACTIVE]`\n  ↳ Direct single-vector threshold gatekeeping with immediate reactive sanctions."
        wl_posture = "🛡️ **Direct Whitelist Bypass**: Whitelisted entities completely bypass event threshold checks."

    summary_text = (
        f"{status_line}\n\n"
        f"• **Active Defensive Mode:** `{mode_display}`\n"
        f"• **Observation Engine:** {obs_display}\n"
        f"• **Whitelist Protocol:** {wl_posture}\n"
        f"• **Monitored Vectors:** `{len(monitored_events)} / {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)}` events\n"
        f"• **Incident Forensics Log:** {log_ch_str}\n"
        f"• **Security Warning Channel:** {warn_ch_str}\n\n"
        f"Use the interactive controls below to configure operating modes, observation systems, and defense policies."
    )

    # Row 1: Primary Controls
    action_row_1 = ActionRowBuilder()
    if is_setup:
        action_row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"an:toggle:{guild.id}")
            .set_label("Pause Defense" if is_enabled else "Activate Defense")
            .set_style(ButtonStyle.Danger if is_enabled else ButtonStyle.Success)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    else:
        action_row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step1:{guild.id}")
            .set_label("Run Setup Wizard")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("wrench", "🔧"))
        )

    # Observation System Toggle Button
    obs_btn_label = "Aegis Engine: Active" if obs_enabled else "Aegis Engine: Off"
    obs_btn_style = ButtonStyle.Success if obs_enabled else ButtonStyle.Secondary
    action_row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an:toggle_obs:{guild.id}")
        .set_label(obs_btn_label)
        .set_style(obs_btn_style)
        .set_emoji("👁️")
    )

    # Operating Mode Switcher Button
    action_row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an:cycle_mode:{guild.id}")
        .set_label(f"Mode: {mode.title()}")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("shield", "🛡️"))
    )

    # Dedicated "Manage Events" button
    action_row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an:panel:events:{guild.id}")
        .set_label("Events")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("tools", "🔧"))
    )

    # Row 2: Secondary Controls
    action_row_2 = ActionRowBuilder()
    action_row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_pn:dashboard:{guild.id}")
        .set_label("Punishments")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("danger", "⚡"))
    )
    action_row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_th:dashboard:{guild.id}")
        .set_label("Thresholds")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("gear", "⚙️"))
    )
    action_row_2.add_button(
        ButtonBuilder()
        .set_custom_id(f"sec:hub:{guild.id}")
        .set_label("Security Command Hub")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("shield", "🛡️"))
    )

    # Row 3: "Manage Settings" String Select Menu
    settings_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an:panel_select:{guild.id}")
        .set_placeholder("Manage Settings — Select a focused control panel...")
    )
    panels = [
        ("Anti-Nuke Overview", "overview", "Full configuration and defense posture summary"),
        ("Observation Engine Controls", "observation", "Toggle Aegis Real-Time Correlation vs Standard Heuristic Engine"),
        ("Security Settings", "security", "Operating defense mode and live monitoring switch"),
        ("Event Manager", "events", "Enable or disable individual monitored vectors"),
        ("Threshold Manager", "thresholds", "Action count limits and sliding time windows"),
        ("Punishment Manager", "punishments", "Configure disciplinary action per vector"),
        ("Access Manager", "access", "Review server security authorities and roles"),
        ("Whitelist Manager", "whitelist", "Exempt trusted users, roles, and channels"),
        ("Logging & Warning Channels", "channels", "Configure incident alert and log channels"),
        ("Ticket Bot Exemptions", "ticketbots", "Exempt ticket bots from channel operations"),
        ("Extra Owners", "extraowners", "Designate high-trust security co-owners"),
        ("Permission Manager", "permissions", "Audit bot hierarchy, permissions, and roles"),
    ]
    for label, val, p_desc in panels:
        settings_select.add_option(label=label[:100], value=val, description=p_desc[:100])

    # Row 4: Utility Controls
    action_row_nav = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Whitelists")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("members", "👥"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:help:{guild.id}")
            .set_label("Help")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("help", "❓"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(c_accent)
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {settings.BOT_NAME} Anti-Nuke Control Center")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(summary_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
        .add_action_row(ActionRowBuilder().add_select_menu(settings_select))
        .add_action_row(action_row_nav)
        .add_text_display(f"-# {settings.BOT_NAME} Security Infrastructure • Enterprise Sentinel")
        .build()
    )


# ==============================================================================
# Focused Management Panels (In-Place Message Editing)
# ==============================================================================

async def build_overview_panel(guild: discord.Guild) -> Any:
    """Panel: Anti-Nuke Overview."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
    monitored = cfg.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
    eos = cfg.get("extra_owners", [])
    wls = cfg.get("whitelists", {})
    tbs = cfg.get("ticket_bots", [])
    warn_ch = cfg.get("warning_channel_id")
    log_ch = cfg.get("log_channel_id")

    desc = (
        f"**Comprehensive Server Defense Posture:**\n\n"
        f"• **Setup Status:** `{'Completed' if cfg.get('setup_completed') else 'Incomplete'}`\n"
        f"• **Defense State:** `{'Active' if cfg.get('enabled') else 'Paused'}`\n"
        f"• **Operating Mode:** `{AntiNukeManager.get_mode_display_name(mode)}`\n"
        f"• **Monitored Vectors:** `{len(monitored)} / {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)}` events\n"
        f"• **Warning Channel:** {f'<#{warn_ch}>' if warn_ch else '*Not Set*'}\n"
        f"• **Forensics Log Channel:** {f'<#{log_ch}>' if log_ch else '*Not Set*'}\n"
        f"• **Extra Owners:** `{len(eos)}` users\n"
        f"• **Exempt Ticket Bots:** `{len(tbs)}` bots\n"
        f"• **Whitelisted Entities:** `{len(wls)}` rules\n"
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:panel:overview:{guild.id}")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Anti-Nuke Overview")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Anti-Nuke Sentinel")
        .build()
    )


async def build_security_panel(guild: discord.Guild) -> Any:
    """Panel: Security Settings (Mode & Active Toggle)."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    cur_mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
    is_enabled = cfg.get("enabled", False)

    mode_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an:select_mode:{guild.id}")
        .set_placeholder("Select defensive operating mode...")
    )
    for m in AntiNukeConstants.get_enabled_modes():
        mode_select.add_option(
            label=AntiNukeManager.get_mode_display_name(m),
            value=m,
            description="Strict protection against destructive changes.",
            default=(m == cur_mode)
        )

    toggle_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:toggle:{guild.id}")
            .set_label("Deactivate Defense" if is_enabled else "Activate Defense")
            .set_style(ButtonStyle.Danger if is_enabled else ButtonStyle.Success)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    desc = (
        f"Manage global defense switch and security mode:\n\n"
        f"• **Current State:** `{'Active & Guarding' if is_enabled else 'Paused / Disabled'}`\n"
        f"• **Active Mode:** `{AntiNukeManager.get_mode_display_name(cur_mode)}`\n"
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} Security Settings")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(mode_select))
        .add_action_row(toggle_row)
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Anti-Nuke Sentinel")
        .build()
    )


async def build_event_manager_panel(guild: discord.Guild, staged_events: Optional[Set[str]] = None) -> Any:
    """
    Panel: Focused Event Manager.
    Allows enabling/disabling monitored events with String Select Menu, Save, Cancel, and Back.
    """
    if staged_events is None:
        staged_events = get_staged_events(guild.id)

    # String select menu for monitored events
    event_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an:ev_menu:{guild.id}")
        .set_placeholder("Select events to monitor (multi-selection supported)...")
        .set_min_values(1)
        .set_max_values(min(25, len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)))
    )

    for ev in AntiNukeConstants.USER_CONFIGURABLE_EVENTS:
        name = AntiNukeConstants.get_event_display_name(ev)
        desc = AntiNukeConstants.get_event_description(ev)
        event_select.add_option(
            label=name[:100],
            value=ev,
            description=desc[:100],
            default=(ev in staged_events)
        )

    is_all = (len(staged_events) >= len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS))

    action_row_quick = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:ev_select_all:{guild.id}")
            .set_label(f"Select All {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)} Events")
            .set_style(ButtonStyle.Success if is_all else ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:ev_save:{guild.id}")
            .set_label("Save Event Configuration")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
    )

    action_row_nav = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:ev_cancel:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    desc = (
        f"Configure which gateway events are monitored in real-time.\n\n"
        f"• **Currently Selected:** **{len(staged_events)} / {len(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)} events**\n"
        f"• **Enforcement Notice:** Disabled events will be ignored by anti-nuke monitors.\n\n"
        f"-# *Select the desired events from the menu, then click **Save Event Configuration** to persist.*"
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('tools', '🔧')} Monitored Event Manager")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(event_select))
        .add_action_row(action_row_quick)
        .add_action_row(action_row_nav)
        .add_text_display(f"-# {settings.BOT_NAME} Event Management")
        .build()
    )


async def build_channels_panel(guild: discord.Guild) -> Any:
    """Panel: Logging & Warning Channels."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    warn_ch = cfg.get("warning_channel_id")
    log_ch = cfg.get("log_channel_id")

    warn_str = f"<#{warn_ch}> (`{warn_ch}`)" if warn_ch else "*Not Assigned*"
    log_str = f"<#{log_ch}> (`{log_ch}`)" if log_ch else "*Not Assigned*"

    sel_warn = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.CHANNEL)
        .set_custom_id(f"an:set_warning_ch:{guild.id}")
        .set_placeholder("Select Security Warning Channel...")
    )

    sel_log = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.CHANNEL)
        .set_custom_id(f"an:set_log_ch:{guild.id}")
        .set_placeholder("Select Incident Forensics Log Channel...")
    )

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    desc = (
        f"Configure destination channels for real-time security alerts and audit logging:\n\n"
        f"• **Security Warning Channel:** {warn_str}\n"
        f"• **Incident Forensics Log:** {log_str}\n\n"
        f"-# *Select a channel using the native menus below to update immediately.*"
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('channel', '📢')} Security Channels")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(sel_warn))
        .add_action_row(ActionRowBuilder().add_select_menu(sel_log))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Forensic Dispatch")
        .build()
    )


async def build_ticket_bots_panel(guild: discord.Guild) -> Any:
    """Panel: Ticket Bot Exemptions."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    tbs = cfg.get("ticket_bots", [])

    sel_user = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an:add_ticket_bot:{guild.id}")
        .set_placeholder("Select ticket bot to add or exempt...")
    )

    tb_lines = [f"• <@{b_id}> (`{b_id}`)" for b_id in tbs]
    tb_summary = "\n".join(tb_lines) if tb_lines else "*No ticket bots currently exempted.*"

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:clear_ticket_bots:{guild.id}")
            .set_label("Clear All Ticket Bots")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    desc = (
        f"Exempt ticket bot accounts from channel creation and deletion rate-limits:\n\n"
        f"**Approved Ticket Bots ({len(tbs)}):**\n"
        f"{tb_summary}\n\n"
        f"-# *Select a bot from the user menu below to grant exemption.*"
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Ticket Bot Exemptions")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(sel_user))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Ticket Protection")
        .build()
    )


async def build_extra_owners_panel(guild: discord.Guild) -> Any:
    """Panel: Extra Owners."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    eos = cfg.get("extra_owners", [])

    sel_user = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an:add_extra_owner:{guild.id}")
        .set_placeholder("Select user to grant Extra Owner status...")
    )

    eo_lines = [f"• Root Owner: <@{guild.owner_id}> (`{guild.owner_id}`)"]
    for uid in eos:
        eo_lines.append(f"• Extra Owner: <@{uid}> (`{uid}`)")
    eo_summary = "\n".join(eo_lines)

    nav_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    desc = (
        f"{EMOJIS.get('warning', '⚠️')} **Application Privilege Notice:**\n"
        f"Extra Owners hold application-level anti-nuke administrative privileges within {settings.BOT_NAME}. "
        f"They do **not** receive Discord guild ownership or native server permissions.\n\n"
        f"**Security Authorities:**\n"
        f"{eo_summary}\n\n"
        f"-# *Select a user below to designate an Extra Owner. Only the Server Owner can grant or revoke this status.*"
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('crown', '👑')} Anti-Nuke Extra Owners")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(sel_user))
        .add_action_row(nav_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Governance")
        .build()
    )


async def build_access_panel(guild: discord.Guild) -> Any:
    """Panel: Access Manager."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    eos = cfg.get("extra_owners", [])
    wls = cfg.get("whitelists", {})
    tbs = cfg.get("ticket_bots", [])

    desc = (
        f"**Security Access & Authority Governance:**\n\n"
        f"• **Root Server Owner:** <@{guild.owner_id}> (`{guild.owner_id}`)\n"
        f"• **Configured Extra Owners:** `{len(eos)}` users\n"
        f"• **Whitelisted Entities:** `{len(wls)}` rules\n"
        f"• **Exempt Ticket Bots:** `{len(tbs)}` bots\n\n"
        f"Click the buttons below to manage individual access layers."
    )

    nav_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Manage Whitelists")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("members", "👥"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:panel:extraowners:{guild.id}")
            .set_label("Manage Extra Owners")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("crown", "👑"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:panel:ticketbots:{guild.id}")
            .set_label("Manage Ticket Bots")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("ticket", "🎫"))
        )
    )

    nav_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('lock', '🔒')} Security Access Manager")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(nav_row_1)
        .add_action_row(nav_row_2)
        .add_text_display(f"-# {settings.BOT_NAME} Access Governance")
        .build()
    )


async def build_permission_manager_panel(guild: discord.Guild) -> Any:
    """Panel: Permission Manager (Bot Hierarchy, Discord Permissions & Dangerous Native Roles)."""
    me = guild.me

    # 1. Bot Discord permissions check
    perm_checks = [
        ("administrator", "Administrator"),
        ("ban_members", "Ban Members"),
        ("kick_members", "Kick Members"),
        ("manage_roles", "Manage Roles"),
        ("manage_channels", "Manage Channels"),
        ("view_audit_log", "View Audit Log"),
    ]
    perm_lines = []
    for attr, name in perm_checks:
        has_it = getattr(me.guild_permissions, attr, False) or me.guild_permissions.administrator
        icon = EMOJIS.get("check", "✅") if has_it else EMOJIS.get("cross", "❌")
        perm_lines.append(f"{icon} `{name}`")

    # 2. Hierarchy position check
    higher_roles = [r for r in guild.roles if r.position >= me.top_role.position and not r.is_default() and r != me.top_role]
    if not higher_roles:
        hierarchy_str = f"{EMOJIS.get('check', '✅')} **Safe**: Bot role `{me.top_role.name}` is positioned above all monitored roles."
    else:
        higher_names = ", ".join([f"`{r.name}`" for r in higher_roles[:4]])
        hierarchy_str = (
            f"{EMOJIS.get('warning', '⚠️')} **Warning**: Bot role `{me.top_role.name}` is lower than {len(higher_roles)} role(s) ({higher_names})."
        )

    # 3. Channel access check
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    warn_ch_id = cfg.get("warning_channel_id")
    log_ch_id = cfg.get("log_channel_id")

    ch_access_lines = []
    for label, ch_id in [("Warning Channel", warn_ch_id), ("Log Channel", log_ch_id)]:
        if ch_id:
            ch = guild.get_channel(int(ch_id))
            if ch:
                perms = ch.permissions_for(me)
                can_post = perms.send_messages and perms.view_channel
                ch_icon = EMOJIS.get("check", "✅") if can_post else EMOJIS.get("cross", "❌")
                ch_access_lines.append(f"{ch_icon} {label} (<#{ch_id}>): `{'Can Post' if can_post else 'Missing Permissions'}`")
            else:
                ch_access_lines.append(f"{EMOJIS.get('warning', '⚠️')} {label} (`{ch_id}`): Channel deleted or inaccessible")
        else:
            ch_access_lines.append(f"{EMOJIS.get('warning', '⚠️')} {label}: Not configured")

    desc = (
        f"**1. Bot Role Hierarchy:**\n"
        f"{hierarchy_str}\n\n"
        f"**2. Bot Administrative Permissions:**\n"
        f"{' • '.join(perm_lines)}\n\n"
        f"**3. Security Channel Access:**\n"
        f"{chr(10).join(ch_access_lines)}\n"
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_perm:refresh:{guild.id}")
            .set_label("Re-Audit Permissions")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Anti-Nuke Permission Manager")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Permission Governance")
        .build()
    )


# ==============================================================================
# Command Execution Entrypoint
# ==============================================================================
async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Restrict to Server Owner, Extra Owner, or Bot Owner
    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can access Anti-Nuke management.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    sub = args[0].lower() if args else "dashboard"

    # Setup Wizard Shortcut
    if sub in ["setup", "wizard", "audit"]:
        from plugins.MomentumOneToolkit.commands.security.setup import build_wizard_step1_view
        view = await build_wizard_step1_view(guild)
        return await send_response(message, view)

    # Event Manager Shortcut
    if sub in ["events", "event"]:
        view = await build_event_manager_panel(guild)
        return await send_response(message, view)

    # Observation System Switcher
    if sub in ["obs", "observation", "engine"]:
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
        eng_name = AntiNukeManager.get_observation_system_name(guild.id)
        status_word = "Activated" if new_obs else "Set to Standard Heuristic"
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("success", "#3FD438"))
            .add_text_display(f"### 👁️ Observation Engine {status_word}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"Defensive observation system for **{guild.name}** updated:\n\n"
                f"• **Active Engine:** `{eng_name}`\n"
                f"• **Correlation Pipeline:** `{'Aegis Real-Time Correlation' if new_obs else 'Standard Event Gatekeeper'}`\n"
                f"• **Whitelist Protocol:** `{'Graduated Trust & Anomaly Telemetry' if new_obs else 'Direct Action Threshold Bypass'}`\n\n"
                f"The Anti-Nuke Dashboard and threat telemetry will adapt immediately to this engine."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_action_row(
                ActionRowBuilder()
                .add_button(
                    ButtonBuilder()
                    .set_custom_id(f"an:dashboard:{guild.id}")
                    .set_label("View Dashboard")
                    .set_style(ButtonStyle.Primary)
                    .set_emoji(EMOJIS.get("shield", "🛡️"))
                )
            )
            .build()
        )
        return await send_response(message, box)

    # Defensive Operating Mode Switcher
    if sub in ["mode", "posture"]:
        if len(args) > 1:
            target_mode = args[1].lower()
            if target_mode in [AntiNukeConstants.MODE_HARD, AntiNukeConstants.MODE_ULTIMATE, AntiNukeConstants.MODE_HYBRID]:
                await AntiNukeManager.save_guild_config(str(guild.id), {"mode": target_mode})
                mode_disp = AntiNukeManager.get_mode_display_name(target_mode)
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("success", "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check', '✅')} Operating Mode Updated")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"Defensive posture for **{guild.name}** updated to: `{mode_disp}`.\n\n"
                        f"All dashboard threshold defaults and mitigation response algorithms are adjusted."
                    )
                    .build()
                )
                return await send_response(message, box)

    # Default: Show Compact Dashboard
    view = await build_dashboard_view(guild)
    return await send_response(message, view)
