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
description = "Configure and inspect automated disciplinary actions per security event."
category = "Security"
usage = "punishment [event] [action]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


async def build_punishment_overview_view(guild: discord.Guild) -> Any:
    """Builds interactive punishment dashboard displaying responses across all events."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    mode = cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE)
    punishments = cfg.get("punishments", {})
    defaults = get_default_punishments(mode)

    # Group by punishment action
    grouped: Dict[str, List[str]] = {
        AntiNukeConstants.PUNISH_BAN: [],
        AntiNukeConstants.PUNISH_QUARANTINE: [],
        AntiNukeConstants.PUNISH_KICK: [],
        AntiNukeConstants.PUNISH_TIMEOUT: [],
    }

    for ev in AntiNukeConstants.ALL_EVENTS:
        action = punishments.get(ev) or defaults.get(ev, AntiNukeConstants.PUNISH_BAN)
        friendly_name = AntiNukeConstants.get_event_display_name(ev)
        if action in grouped:
            grouped[action].append(friendly_name)

    lines = []
    lines.append(f"**{EMOJIS.get('ban', '🚫')} BAN ({len(grouped['ban'])} events):**")
    lines.append(f"> {', '.join(grouped['ban'][:6])}" + (f" *+{len(grouped['ban']) - 6} more*" if len(grouped['ban']) > 6 else ""))

    lines.append(f"\n**{EMOJIS.get('shield', '🛡️')} QUARANTINE / STRIP ROLES ({len(grouped['quarantine'])} events):**")
    lines.append(f"> {', '.join(grouped['quarantine'][:6])}" + (f" *+{len(grouped['quarantine']) - 6} more*" if len(grouped['quarantine']) > 6 else ""))

    if grouped["timeout"]:
        lines.append(f"\n**{EMOJIS.get('clock', '⏳')} TIMEOUT ({len(grouped['timeout'])} events):**")
        lines.append(f"> {', '.join(grouped['timeout'])}")

    if grouped["kick"]:
        lines.append(f"\n**{EMOJIS.get('danger', '⚡')} KICK ({len(grouped['kick'])} events):**")
        lines.append(f"> {', '.join(grouped['kick'])}")

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set_all:ban:{guild.id}")
            .set_label("Set All to BAN")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("ban", "🚫"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:set_all:quarantine:{guild.id}")
            .set_label("Set All to QUARANTINE")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:reset:{guild.id}")
            .set_label("Reset to Mode Defaults")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('danger', '⚡')} {get_string('security.antinuke.punishment_title', 'Anti-Nuke Disciplinary Responses')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"**Operating Mode:** `{AntiNukeManager.get_mode_display_name(mode)}`\n\n"
            f"{chr(10).join(lines)}\n\n"
            f"-# *Usage:* `$punishment <event> <ban|kick|quarantine|timeout>`\n"
            f"-# *Supported Events:* `ban`, `kick`, `channel`, `role`, `webhook`, `bot_add`, etc."
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
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

    # 1. No arguments -> show interactive punishment overview
    if not args:
        view = await build_punishment_overview_view(guild)
        return await send_response(message, view)

    # 2. Configure punishment for event
    if len(args) < 2:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Incomplete Arguments")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"**Usage:** `$punishment <event> <ban|kick|quarantine|timeout>`\n"
                f"**Examples:**\n"
                f"• `$punishment ban ban`\n"
                f"• `$punishment channel quarantine`\n"
                f"• `$punishment webhook ban`"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Config")
            .build()
        )
        return await send_response(message, box)

    event_token = args[0].lower()
    action_token = args[1].lower()

    canonical_event = AntiNukeConstants.normalize_event(event_token)
    if not canonical_event:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('cross', '❌')} Unknown Event")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Event `{event_token}` could not be resolved to a monitored security event.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .build()
        )
        return await send_response(message, box)

    if action_token not in AntiNukeConstants.VALID_PUNISHMENTS:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('cross', '❌')} Invalid Punishment Action")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Allowed disciplinary actions: `ban`, `kick`, `quarantine`, `timeout`.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .build()
        )
        return await send_response(message, box)

    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    punishments = dict(cfg.get("punishments", {}))
    punishments[canonical_event] = action_token
    await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": punishments})

    friendly_name = AntiNukeConstants.get_event_display_name(canonical_event)
    box = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("success", "#3FD438"))
        .add_text_display(f"### {EMOJIS.get('check', '✅')} Punishment Updated")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"Disciplinary response for **{friendly_name}** set to: **`{action_token.upper()}`**."
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel")
        .build()
    )
    return await send_response(message, box)
