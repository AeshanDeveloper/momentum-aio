import re
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize,
    ButtonStyle,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType


name = "unwhitelist"
aliases = ["unwl", "untrust", "dewhitelist"]
description = "Remove authorized exemptions for users, roles, channels, or categories."
category = "Security"
usage = "unwhitelist [@user|@role|#channel]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


def _parse_entity_id(raw: str) -> Optional[str]:
    """Extracts snowflake ID from mention (<@123>, <@&123>, <#123>) or raw digits."""
    if not raw:
        return None
    cleaned = raw.strip()
    m = re.match(r"^<[@#&]!?:?(\d+)>$", cleaned)
    if m:
        return m.group(1)
    if re.match(r"^\d+$", cleaned):
        return cleaned
    return None


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can remove Whitelist exemptions.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Setup enforcement
    if not AntiNukeManager.is_setup_completed(guild.id):
        view = AntiNukeManager.build_setup_required_view(guild)
        return await send_response(message, view)

    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = dict(cfg.get("whitelists", {}))

    # 1. No arguments -> list active whitelists with quick removal options
    if not args:
        if not whitelists:
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Whitelist Exemption Removal")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("No whitelisted entities exist to remove.")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel")
                .build()
            )
            return await send_response(message, box)

        lines = []
        action_row = ActionRowBuilder()
        for idx, (eid, entry) in enumerate(list(whitelists.items())[:5]):
            t_type = entry.get("type", "user") if isinstance(entry, dict) else "user"
            lines.append(f"• **[{t_type.upper()}]** `<@{eid}>` (`{eid}`)")
            action_row.add_button(
                ButtonBuilder()
                .set_custom_id(f"an_wl:delete:{eid}:{guild.id}")
                .set_label(f"Remove {eid[:6]}...")
                .set_style(ButtonStyle.Danger)
                .set_emoji(EMOJIS.get("trash", "🗑️"))
            )

        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Select Whitelist to Remove")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"**Active Whitelists:**\n{chr(10).join(lines)}\n\n"
                f"Use the buttons below to remove an entry, or run `$unwhitelist <@target>`."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .add_action_row(action_row)
            .build()
        )
        return await send_response(message, box)

    # 2. Target specified in arguments
    target_id = _parse_entity_id(args[0])
    if not target_id:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Target ID or Mention Required")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Please provide a valid user, role, channel, or category mention / snowflake ID.\n\n*Usage:* `$unwhitelist <@target>`")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Whitelist System")
            .build()
        )
        return await send_response(message, box)

    if target_id not in whitelists:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Entity Not Whitelisted")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Entity `{target_id}` is not currently present in the anti-nuke whitelist.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .build()
        )
        return await send_response(message, box)

    del whitelists[target_id]
    await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})

    box = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("success", "#3FD438"))
        .add_text_display(f"### {EMOJIS.get('check', '✅')} Whitelist Exemption Removed")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"Exemption for entity `<@{target_id}>` (`{target_id}`) has been revoked.")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel")
        .build()
    )
    return await send_response(message, box)
