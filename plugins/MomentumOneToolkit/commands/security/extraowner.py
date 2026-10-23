import re
import time
from typing import List, Dict, Any, Optional
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager
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

name = "extraowner"
aliases = ["eo", "extraowners"]
description = "Interactively manage Anti-Nuke Extra Owners with native user selection and confirmations."
category = "Security"
usage = "extraowner [set|remove|list]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


def is_root_owner_or_bot_owner(guild: discord.Guild, user_id: int | str) -> bool:
    """Only the Server Owner or Bot Owners can manage Extra Owners."""
    uid = str(user_id)
    if guild and guild.owner_id and str(guild.owner_id) == uid:
        return True
    if is_bot_owner(uid):
        return True
    return False


async def build_extraowner_main_view(guild: discord.Guild) -> Any:
    """Displays the list of current extra owners with Add and Remove buttons."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    eos = cfg.get("extra_owners", [])

    lines = [f"• **Root Server Owner:** <@{guild.owner_id}> (`{guild.owner_id}`)"]
    for uid in eos:
        lines.append(f"• **Extra Owner:** <@{uid}> (`{uid}`)")

    desc = (
        f"{EMOJIS.get('crown', '👑')} **Anti-Nuke Extra Owner Management**\n\n"
        f"**Security Authority Summary:**\n"
        f"{chr(10).join(lines)}\n\n"
        f"**Application Privilege Notice:**\n"
        f"Extra Owners receive application-level anti-nuke administrative authority inside {settings.BOT_NAME}. "
        f"This privilege does **not** grant Discord guild ownership or native server permissions.\n"
        f"Only the Root Server Owner can grant or revoke Extra Owner privileges."
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_eo:flow_set:{guild.id}")
            .set_label("Add Extra Owner")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("add", "➕"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_eo:flow_remove:{guild.id}")
            .set_label("Remove Extra Owner")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
            .set_disabled(len(eos) == 0)
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
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('crown', '👑')} Anti-Nuke Extra Owners")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Governance")
        .build()
    )


async def build_extraowner_set_view(guild: discord.Guild, selected_user_id: Optional[str] = None) -> Any:
    """Interactively select a user via native User Select Menu to add as Extra Owner."""
    user_select = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an_eo:select_user_set:{guild.id}")
        .set_placeholder("Select a user to grant Extra Owner status...")
    )

    action_row = ActionRowBuilder()
    if selected_user_id:
        desc = (
            f"**Candidate Selected:** <@{selected_user_id}> (`{selected_user_id}`)\n\n"
            f"{EMOJIS.get('warning', '⚠️')} **High-Privilege Warning:**\n"
            f"Granting Extra Owner allows this user to modify anti-nuke defense modes, disable security protections, "
            f"alter threshold limits, and manage whitelists.\n\n"
            f"Click **Confirm Extra Owner** below to finalize."
        )
        action_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_eo:confirm_set:{selected_user_id}:{guild.id}")
            .set_label("Confirm Extra Owner")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
    else:
        desc = (
            f"Use the native user select menu below to choose a trusted administrator.\n\n"
            f"• Extra Owners hold application-level anti-nuke management privileges.\n"
            f"• You will be prompted to explicitly confirm your selection before it is saved."
        )

    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_eo:main:{guild.id}")
        .set_label("Cancel")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("cross", "❌"))
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('crown', '👑')} Add Extra Owner")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(user_select))
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Governance")
        .build()
    )


async def build_extraowner_remove_view(guild: discord.Guild, selected_user_id: Optional[str] = None) -> Any:
    """Interactively select an existing Extra Owner to remove."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    eos = cfg.get("extra_owners", [])

    if not eos:
        desc = "No Extra Owners are currently configured to remove."
        action_row = ActionRowBuilder().add_button(
            ButtonBuilder()
            .set_custom_id(f"an_eo:main:{guild.id}")
            .set_label("Back to Extra Owners")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        return (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('crown', '👑')} Remove Extra Owner")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(desc)
            .add_action_row(action_row)
            .build()
        )

    remove_select = (
        SelectMenuBuilder()
        .set_custom_id(f"an_eo:select_user_remove:{guild.id}")
        .set_placeholder("Select an Extra Owner to revoke...")
    )
    for uid in eos:
        remove_select.add_option(
            label=f"User ID: {uid}",
            value=uid,
            description="Revoke anti-nuke extra owner status",
            default=(uid == selected_user_id)
        )

    action_row = ActionRowBuilder()
    if selected_user_id:
        desc = (
            f"**Selected for Revocation:** <@{selected_user_id}> (`{selected_user_id}`)\n\n"
            f"Revoking this status will immediately remove all application-level anti-nuke management privileges "
            f"for this user.\n\n"
            f"Click **Confirm Revocation** below to finalize."
        )
        action_row.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_eo:confirm_remove:{selected_user_id}:{guild.id}")
            .set_label("Confirm Revocation")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
        )
    else:
        desc = "Select an active Extra Owner from the menu below to revoke their security privileges."

    action_row.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_eo:main:{guild.id}")
        .set_label("Cancel")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("cross", "❌"))
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('trash', '🗑️')} Remove Extra Owner")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(ActionRowBuilder().add_select_menu(remove_select))
        .add_action_row(action_row)
        .add_text_display(f"-# {settings.BOT_NAME} Security Governance")
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

    # Restrict strictly to Root Server Owner and Bot Owners (extra owners cannot manage extra owners)
    if not is_root_owner_or_bot_owner(guild, author.id):
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Root Authority Required")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{EMOJIS.get('cross', '❌')} Only the Root Server Owner (<@{guild.owner_id}>) can add or remove Extra Owners."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    sub = args[0].lower() if args else "list"

    if sub == "set":
        view = await build_extraowner_set_view(guild)
        return await send_response(message, view)

    if sub in ["remove", "delete", "revoke"]:
        view = await build_extraowner_remove_view(guild)
        return await send_response(message, view)

    # Default: list / overview
    view = await build_extraowner_main_view(guild)
    return await send_response(message, view)
