from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_punishments
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

name = "punishment"
aliases = ["punish", "action"]
description = "Dedicated Interactive Anti-Nuke Disciplinary Response Configuration Panel."
category = "Security"
usage = "punishment [event] [ban|kick|timeout|prune|strip_roles]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True

VALID_CONFIGURABLE_PUNISHMENTS = ["ban", "kick", "timeout", "prune", "strip_roles"]

async def build_punishment_panel_view(guild: discord.Guild, selected_event: Optional[str] = None) -> Any:
    """
    Builds the interactive Punishment Panel with event string select menu,
    action buttons (Ban, Kick, Mute/Timeout, Prune, Strip Roles, with Quarantine visibly disabled),
    reset controls, and role hierarchy safety notices.
    """
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
    mode_name = AntiNukeManager.get_mode_display_name(mode)
    punishments = cfg.get("punishments", {})
    defaults = get_default_punishments(mode)

    if not selected_event or selected_event not in AntiNukeConstants.ALL_EVENTS:
        selected_event = AntiNukeConstants.EVENT_CHANNEL_DELETE

    current_action = punishments.get(selected_event) or defaults.get(selected_event, AntiNukeConstants.PUNISH_BAN)
    friendly_selected = AntiNukeConstants.get_event_display_name(selected_event)
    event_desc = AntiNukeConstants.get_event_description(selected_event)

    # 1. Monitored Events String Select Menu (24 events)
    sel = (
        SelectMenuBuilder()
        .set_custom_id(f"an_pn:pick_event:{guild.id}")
        .set_placeholder("Select monitored security vector to configure...")
    )

    for ev in AntiNukeConstants.ALL_EVENTS[:25]:
        friendly_name = AntiNukeConstants.get_event_display_name(ev)
        act = punishments.get(ev) or defaults.get(ev, "ban")
        sel.add_option(
            label=friendly_name[:100],
            value=ev,
            description=f"Action: {act.upper()}"[:100],
            default=(ev == selected_event)
        )

    # 2. Punishment Buttons
    action_row_buttons_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set:{selected_event}:ban:{guild.id}")
            .set_label("Ban" + (" (Active)" if current_action == "ban" else ""))
            .set_style(ButtonStyle.Danger if current_action == "ban" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("ban", "🚫"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set:{selected_event}:kick:{guild.id}")
            .set_label("Kick" + (" (Active)" if current_action == "kick" else ""))
            .set_style(ButtonStyle.Primary if current_action == "kick" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("danger", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set:{selected_event}:timeout:{guild.id}")
            .set_label("Mute / Timeout" + (" (Active)" if current_action == "timeout" else ""))
            .set_style(ButtonStyle.Primary if current_action == "timeout" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("clock", "⏳"))
        )
    )

    action_row_buttons_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set:{selected_event}:strip_roles:{guild.id}")
            .set_label("Strip Roles" + (" (Active)" if current_action == "strip_roles" else ""))
            .set_style(ButtonStyle.Primary if current_action == "strip_roles" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("role", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set:{selected_event}:prune:{guild.id}")
            .set_label("Prune" + (" (Active)" if current_action == "prune" else ""))
            .set_style(ButtonStyle.Primary if current_action == "prune" else ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("trash", "✂️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:disabled_quarantine:{guild.id}")
            .set_label("Quarantine (Unavailable)")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("lock", "🔒"))
            .set_disabled(True)
        )
    )

    action_row_nav = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:reset:{guild.id}")
            .set_label("Reset to Mode Defaults")
            .set_style(ButtonStyle.Secondary)
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

    # Overview text
    desc = (
        f"**Selected Event:** `{friendly_selected}`\n"
        f"• **Description:** {event_desc}\n"
        f"• **Current Disciplinary Action:** **`{current_action.upper()}`**\n"
        f"• **Active Mode:** `{mode_name}`\n\n"
        f"**Role Hierarchy Safety Notice:**\n"
        f"Discord's native role hierarchy is strictly enforced: {settings.BOT_NAME} cannot sanction the Server Owner "
        f"or members holding roles higher than or equal to {settings.BOT_NAME}'s highest role."
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('danger', '⚡')} Anti-Nuke Disciplinary Configuration")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_action_row(action_row_buttons_1)
        .add_action_row(action_row_buttons_2)
        .add_action_row(action_row_nav)
        .build()
    )


build_punishment_overview_view = build_punishment_panel_view


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Check root authority
    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can configure Punishments.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Setup enforcement
    if not AntiNukeManager.is_setup_completed(guild.id):
        view = AntiNukeManager.build_setup_required_view(guild)
        return await send_response(message, view)

    # 1. No arguments -> Show interactive punishment panel
    if not args:
        view = await build_punishment_panel_view(guild)
        return await send_response(message, view)

    # 2. Event argument provided
    event_token = args[0].lower()
    canonical_event = AntiNukeConstants.normalize_event(event_token)

    if not canonical_event:
        view = await build_punishment_panel_view(guild)
        return await send_response(message, view)

    if len(args) == 1:
        # Focus on this event
        view = await build_punishment_panel_view(guild, selected_event=canonical_event)
        return await send_response(message, view)

    # 3. Event and Action provided
    action_token = args[1].lower()
    if action_token == "quarantine":
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Action Unavailable")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                get_string(
                    "security.antinuke.punishments.quarantine",
                    "Quarantine is reserved for a future role-based containment system; currently unavailable."
                )
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Settings")
            .build()
        )
        return await send_response(message, box)

    if action_token not in VALID_CONFIGURABLE_PUNISHMENTS:
        view = await build_punishment_panel_view(guild, selected_event=canonical_event)
        return await send_response(message, view)

    # Update in config
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    punishments = dict(cfg.get("punishments", {}))
    punishments[canonical_event] = action_token
    await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": punishments})

    view = await build_punishment_panel_view(guild, selected_event=canonical_event)
    return await send_response(message, view)
