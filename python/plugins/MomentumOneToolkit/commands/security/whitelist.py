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
    SeparatorSpacingSize,
    ButtonStyle,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType


name = "whitelist"
aliases = ["wl", "trust"]
description = "Authorize trusted users, roles, channels, or categories to bypass anti-nuke rules."
category = "Security"
usage = "whitelist [@user|@role|#channel] [events]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


def _parse_entity_and_type(guild: discord.Guild, raw: str) -> Tuple[Optional[str], str, str]:
    """Returns (entity_id, entity_type, display_name)."""
    if not raw:
        return None, "user", ""
    cleaned = raw.strip()

    # User mention <@!123> or <@123>
    m_user = re.match(r"^<@!?(\d+)>$", cleaned)
    if m_user:
        uid = m_user.group(1)
        m = guild.get_member(int(uid))
        return uid, AntiNukeConstants.TARGET_USER, (str(m) if m else f"User({uid})")

    # Role mention <@&123>
    m_role = re.match(r"^<@&(\d+)>$", cleaned)
    if m_role:
        rid = m_role.group(1)
        r = guild.get_role(int(rid))
        return rid, AntiNukeConstants.TARGET_ROLE, (f"@{r.name}" if r else f"Role({rid})")

    # Channel mention <#123>
    m_ch = re.match(r"^<#(\d+)>$", cleaned)
    if m_ch:
        cid = m_ch.group(1)
        ch = guild.get_channel(int(cid))
        is_cat = isinstance(ch, discord.CategoryChannel)
        t_type = AntiNukeConstants.TARGET_CATEGORY if is_cat else AntiNukeConstants.TARGET_CHANNEL
        return cid, t_type, (f"#{ch.name}" if ch else f"Channel({cid})")

    # Raw digits: inspect guild cache to identify type
    if re.match(r"^\d+$", cleaned):
        eid = int(cleaned)
        # Check roles
        r = guild.get_role(eid)
        if r:
            return cleaned, AntiNukeConstants.TARGET_ROLE, f"@{r.name}"
        # Check channels
        ch = guild.get_channel(eid)
        if ch:
            is_cat = isinstance(ch, discord.CategoryChannel)
            t_type = AntiNukeConstants.TARGET_CATEGORY if is_cat else AntiNukeConstants.TARGET_CHANNEL
            return cleaned, t_type, f"#{ch.name}"
        # Check members
        m = guild.get_member(eid)
        if m:
            return cleaned, AntiNukeConstants.TARGET_USER, str(m)
        # Default assume user
        return cleaned, AntiNukeConstants.TARGET_USER, f"Entity({cleaned})"

    return None, "user", ""


def _parse_events(tokens: List[str]) -> List[str]:
    """Maps raw event tokens to canonical Anti-Nuke event keys."""
    raw_subtokens: List[str] = []
    for t in tokens:
        for sub in t.split(","):
            s = sub.strip()
            if s:
                raw_subtokens.append(s)

    if not raw_subtokens or any(t.lower() in ["all", "*", "everything"] for t in raw_subtokens):
        return ["*"]

    mapped: Set[str] = set()
    for t in raw_subtokens:
        canonical = AntiNukeConstants.normalize_event(t)
        if canonical:
            mapped.add(canonical)
        elif t.lower() in ["ban", "bans"]:
            mapped.add(AntiNukeConstants.EVENT_BAN_ADD)
        elif t.lower() in ["kick", "kicks"]:
            mapped.add(AntiNukeConstants.EVENT_MEMBER_REMOVE)
        elif t.lower() in ["channel", "channels"]:
            mapped.update([
                AntiNukeConstants.EVENT_CHANNEL_CREATE,
                AntiNukeConstants.EVENT_CHANNEL_DELETE,
                AntiNukeConstants.EVENT_CHANNEL_UPDATE,
            ])
        elif t.lower() in ["role", "roles"]:
            mapped.update([
                AntiNukeConstants.EVENT_ROLE_CREATE,
                AntiNukeConstants.EVENT_ROLE_DELETE,
                AntiNukeConstants.EVENT_ROLE_UPDATE,
            ])
        elif t.lower() in ["webhook", "webhooks"]:
            mapped.add(AntiNukeConstants.EVENT_WEBHOOKS_UPDATE)

    return sorted(list(mapped)) if mapped else ["*"]


async def build_whitelist_type_picker_view(guild: discord.Guild) -> Any:
    """Builds interactive Whitelist Wizard Step 1: Picking target entity type."""
    desc = (
        f"**Choose the exemption type you wish to configure:**\n\n"
        f"• **{EMOJIS.get('user', '👤')} User Exemption:** Grants a specific member or automated bot account permission to perform designated actions.\n"
        f"• **{EMOJIS.get('role', '🛡️')} Role Exemption:** Grants all members assigned a server role permission to perform designated actions.\n"
        f"• **{EMOJIS.get('channel', '📢')} Channel Exemption:** Prevents anti-nuke sanctions for actions occurring inside a specific text/voice channel.\n"
        f"• **{EMOJIS.get('tools', '📁')} Category Exemption:** Prevents sanctions for channel creation/deletion within an entire category.\n\n"
        f"-# *Best Practice:* Use granular event whitelisting rather than granting universal (`*`) exemptions."
    )

    action_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:prompt:user:{guild.id}")
            .set_label("User Exemption")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("user", "👤"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:prompt:role:{guild.id}")
            .set_label("Role Exemption")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("role", "🛡️"))
        )
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:prompt:channel:{guild.id}")
            .set_label("Channel Exemption")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("channel", "📢"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:prompt:category:{guild.id}")
            .set_label("Category Exemption")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("tools", "📁"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:view_all:{guild.id}")
            .set_label("View All Whitelists")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {get_string('security.antinuke.wizard_wl_title', 'Anti-Nuke Whitelist Manager')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Authority • Scoped Exemptions")
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
        .build()
    )


async def build_entity_event_manager_view(guild: discord.Guild, entity_id: str, entity_type: str, display_name: str) -> Any:
    """Builds interactive manager for a specific entity's authorized events."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = cfg.get("whitelists", {})

    existing = whitelists.get(entity_id, {})
    current_events = existing.get("events", []) if isinstance(existing, dict) else (existing if isinstance(existing, list) else [])

    if "*" in current_events:
        event_str = "**All Events (`*`)**"
    elif current_events:
        friendly = [AntiNukeConstants.get_event_display_name(e) for e in current_events]
        event_str = ", ".join(f"`{f}`" for f in friendly)
    else:
        event_str = "*None Configured*"

    desc = (
        f"**Target:** {display_name} (`{entity_id}`)\n"
        f"**Entity Scope:** `{entity_type.upper()}`\n"
        f"**Authorized Events:** {event_str}\n\n"
        f"Use the buttons below to toggle common event permissions, grant all events, or remove this whitelist entry."
    )

    action_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:set_events:{entity_id}:all:{guild.id}")
            .set_label("Authorize All Events (*)")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:set_events:{entity_id}:channels:{guild.id}")
            .set_label("Channel Actions Only")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("channel", "📢"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:set_events:{entity_id}:roles:{guild.id}")
            .set_label("Role Actions Only")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("role", "🛡️"))
        )
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:delete:{entity_id}:{guild.id}")
            .set_label("Remove Whitelist")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Back to Manager")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Manage Whitelist: {display_name}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
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
            .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can manage Whitelists.")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
            .build()
        )
        return await send_response(message, box)

    # Setup enforcement
    if not AntiNukeManager.is_setup_completed(guild.id):
        view = AntiNukeManager.build_setup_required_view(guild)
        return await send_response(message, view)

    # 1. No arguments -> Launch Interactive Whitelist Wizard
    if not args:
        view = await build_whitelist_type_picker_view(guild)
        return await send_response(message, view)

    # 2. View/List Subcommand
    if args[0].lower() in ["list", "show", "view"]:
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        whitelists = cfg.get("whitelists", {})
        if not whitelists:
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Configured Whitelists")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("No whitelisted entities configured. Only the Server Owner and Extra Owners are exempt.")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel")
                .build()
            )
            return await send_response(message, box)

        lines = []
        for eid, entry in whitelists.items():
            t_type = entry.get("type", "user") if isinstance(entry, dict) else "user"
            events = entry.get("events", []) if isinstance(entry, dict) else entry
            ev_str = "All (*)" if ("*" in events or "all" in events) else f"{len(events)} events"

            if t_type == AntiNukeConstants.TARGET_ROLE:
                target_str = f"<@&{eid}> (`{eid}`)"
            elif t_type in [AntiNukeConstants.TARGET_CHANNEL, AntiNukeConstants.TARGET_CATEGORY]:
                target_str = f"<#{eid}> (`{eid}`)"
            else:
                target_str = f"<@{eid}> (`{eid}`)"

            lines.append(f"• **[{t_type.upper()}]** {target_str} — Events: `{ev_str}`")

        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("info", "#0844C5"))
            .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Configured Whitelists ({len(whitelists)})")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display("\n".join(lines))
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .build()
        )
        return await send_response(message, box)

    # 3. Target provided in args
    target_str = args[0]
    entity_id, entity_type, display_name = _parse_entity_and_type(guild, target_str)
    if not entity_id:
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Invalid Target Specified")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"Could not identify the target user, role, channel, or category.\n\n"
                f"*Usage:* `$whitelist @user [events]` or run `$whitelist` for the interactive wizard."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Whitelist System")
            .build()
        )
        return await send_response(message, box)

    event_args = args[1:]
    if not event_args:
        # Open interactive manager for this entity
        view = await build_entity_event_manager_view(guild, entity_id, entity_type, display_name)
        return await send_response(message, view)

    # Event args provided directly
    chosen_events = _parse_events(event_args)
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = dict(cfg.get("whitelists", {}))

    whitelists[entity_id] = {
        "id": entity_id,
        "type": entity_type,
        "name": display_name,
        "events": chosen_events,
    }
    await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})

    ev_display = "All Events (*)" if "*" in chosen_events else ", ".join(f"`{e}`" for e in chosen_events)
    box = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("success", "#3FD438"))
        .add_text_display(f"### {EMOJIS.get('check', '✅')} Whitelist Updated")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(
            f"Successfully whitelisted **[{entity_type.upper()}]** {display_name} (`{entity_id}`).\n\n"
            f"• **Authorized Events:** {ev_display}\n"
            f"• **Target Scope:** `{entity_type}` only."
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
        .build()
    )
    return await send_response(message, box)
