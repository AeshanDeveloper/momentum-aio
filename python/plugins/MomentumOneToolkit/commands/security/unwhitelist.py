import re
from typing import List, Dict, Any, Optional, Set, Tuple
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants
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
from .whitelist import parse_entity_and_type, format_target_mention

name = "unwhitelist"
aliases = ["unwl", "untrust", "dewhitelist"]
description = "Interactive removal of Anti-Nuke whitelist entries and event exemptions."
category = "Security"
usage = "unwhitelist [@user|@role|#channel]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True

# In-memory staging for multi-step removal
_PENDING_REMOVALS: Dict[Tuple[str, str], List[str]] = {}

def get_pending_removal(guild_id: str | int, entity_id: str) -> Optional[List[str]]:
    return _PENDING_REMOVALS.get((str(guild_id), str(entity_id)))

def set_pending_removal(guild_id: str | int, entity_id: str, events: List[str]) -> None:
    _PENDING_REMOVALS[(str(guild_id), str(entity_id))] = events

def clear_pending_removal(guild_id: str | int, entity_id: str) -> None:
    _PENDING_REMOVALS.pop((str(guild_id), str(entity_id)), None)


def build_removal_target_picker_view(guild: discord.Guild) -> Any:
    """Shows String Select Menu of existing whitelisted entities to remove."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = cfg.get("whitelists", {})

    if not whitelists:
        back_row = (
            ActionRowBuilder()
            .add_button(
                ButtonBuilder()
                .set_custom_id(f"an_wl:main:{guild.id}")
                .set_label("Back to Whitelist Manager")
                .set_style(ButtonStyle.Secondary)
                .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
            )
        )
        return (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} No Whitelists Configured")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("There are no whitelisted entities in this server to remove.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .add_action_row(back_row)
            .build()
        )

    sel = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wl:unwl_pick_target:{guild.id}")
        .set_placeholder("Select whitelisted entity to remove...")
    )

    lines: List[str] = []
    for eid, entry in list(whitelists.items())[:25]:
        t_type = entry.get("type", AntiNukeConstants.TARGET_USER) if isinstance(entry, dict) else AntiNukeConstants.TARGET_USER
        events = entry.get("events", []) if isinstance(entry, dict) else entry
        mention = format_target_mention(eid, t_type)

        if "*" in events or "all" in events:
            ev_desc = "All Events (*)"
        else:
            friendly = [AntiNukeConstants.get_event_display_name(e) for e in events[:3]]
            ev_desc = f"{len(events)} events: " + ", ".join(friendly)

        sel.add_option(
            label=f"[{t_type.upper()}] {eid}",
            value=eid,
            description=ev_desc[:100]
        )
        lines.append(f"• **[{t_type.upper()}]** {mention} (`{eid}`) — `{ev_desc[:60]}`")

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    desc = (
        f"**Select Whitelist Entry to Remove:**\n\n"
        f"Choose an entity from the menu below to revoke specific exemptions or remove the entire whitelist entry.\n\n"
        f"**Active Entries:**\n" + "\n".join(lines[:10])
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("danger", "#B21F1F"))
        .add_text_display(f"### {EMOJIS.get('trash', '🗑️')} Revoke Whitelist Exemptions")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_action_row(action_row)
        .build()
    )


def build_removal_event_selector_view(
    guild: discord.Guild,
    entity_id: str,
    selected_for_removal: Optional[List[str]] = None
) -> Any:
    """
    Shows specific exemptions for an entity, allowing selective removal.
    Preserves unrelated exemptions when editing an entry.
    """
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = cfg.get("whitelists", {})
    entry = whitelists.get(entity_id, {})
    t_type = entry.get("type", AntiNukeConstants.TARGET_USER) if isinstance(entry, dict) else AntiNukeConstants.TARGET_USER
    current_events = entry.get("events", []) if isinstance(entry, dict) else (entry if isinstance(entry, list) else [])

    mention = format_target_mention(entity_id, t_type)

    if selected_for_removal is None:
        selected_for_removal = []

    sel = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wl:unwl_pick_events:{entity_id}:{guild.id}")
        .set_placeholder("Select specific exemptions to REMOVE...")
        .set_min_values(1)
    )

    if "*" in current_events:
        sel.add_option(
            label="Universal All-Events (*)",
            value="*",
            description="Remove universal bypass exemption",
            emoji=EMOJIS.get("trash", "🗑️"),
            default=("*" in selected_for_removal)
        )
        sel.set_max_values(1)
    else:
        for ev in current_events[:25]:
            friendly = AntiNukeConstants.get_event_display_name(ev)
            sel.add_option(
                label=friendly,
                value=ev,
                description=f"Revoke exemption for {friendly}",
                default=(ev in selected_for_removal)
            )
        sel.set_max_values(min(25, len(current_events)))

    action_row_actions = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:unwl_confirm_selected:{entity_id}:{guild.id}")
            .set_label("Remove Selected Exemptions")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
            .set_disabled(len(selected_for_removal) == 0)
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:unwl_confirm_all:{entity_id}:{guild.id}")
            .set_label("Remove Entire Entry")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    ev_display = "All Events (*)" if ("*" in current_events) else ", ".join([f"`{AntiNukeConstants.get_event_display_name(e)}`" for e in current_events])
    staged_display = ", ".join([f"`{e}`" for e in selected_for_removal]) if selected_for_removal else "*None selected yet*"

    desc = (
        f"**Target:** {mention} (`{entity_id}`) — **Scope:** `{t_type.upper()}`\n\n"
        f"• **Current Authorized Exemptions:** {ev_display}\n"
        f"• **Staged for Removal:** {staged_display}\n\n"
        f"Select the specific events you want to remove from the menu below.\n"
        f"{EMOJIS.get('info', 'ℹ️')} *Unrelated exemptions will remain active.*"
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("danger", "#B21F1F"))
        .add_text_display(f"### {EMOJIS.get('trash', '🗑️')} Manage Whitelist Removal: {eid if (eid := entity_id) else ''}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_action_row(action_row_actions)
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

    # Check root authority
    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can remove Whitelists.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Setup enforcement
    if not AntiNukeManager.is_setup_completed(guild.id):
        view = AntiNukeManager.build_setup_required_view(guild)
        return await send_response(message, view)

    # 1. No arguments: open interactive removal picker
    if not args:
        view = build_removal_target_picker_view(guild)
        return await send_response(message, view)

    # 2. Target provided in arguments: jump directly to event removal for that entity
    target_str = args[0]
    entity_id, entity_type, display_name = parse_entity_and_type(guild, target_str)
    if not entity_id:
        view = build_removal_target_picker_view(guild)
        return await send_response(message, view)

    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = cfg.get("whitelists", {})
    if entity_id not in whitelists:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Entity Not Whitelisted")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Entity `<@{entity_id}>` (`{entity_id}`) is not in the whitelist.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    clear_pending_removal(guild.id, entity_id)
    view = build_removal_event_selector_view(guild, entity_id, [])
    return await send_response(message, view)
