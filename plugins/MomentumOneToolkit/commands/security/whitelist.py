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

name = "whitelist"
aliases = ["wl", "trust"]
description = "Interactive Anti-Nuke Whitelist Manager for users, roles, channels, and categories."
category = "Security"
usage = "whitelist [@user|@role|#channel] [events]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True

# In-memory staging for multi-step selection before persistent confirmation
_PENDING_WHITELISTS: Dict[Tuple[str, str], List[str]] = {}

def get_pending_events(guild_id: str | int, entity_id: str) -> Optional[List[str]]:
    return _PENDING_WHITELISTS.get((str(guild_id), str(entity_id)))

def set_pending_events(guild_id: str | int, entity_id: str, events: List[str]) -> None:
    _PENDING_WHITELISTS[(str(guild_id), str(entity_id))] = events

def clear_pending_events(guild_id: str | int, entity_id: str) -> None:
    _PENDING_WHITELISTS.pop((str(guild_id), str(entity_id)), None)


def parse_entity_and_type(guild: discord.Guild, raw: str) -> Tuple[Optional[str], str, str]:
    """Returns (entity_id, entity_type, display_name)."""
    if not raw:
        return None, AntiNukeConstants.TARGET_USER, ""
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
        r = guild.get_role(eid)
        if r:
            return cleaned, AntiNukeConstants.TARGET_ROLE, f"@{r.name}"
        ch = guild.get_channel(eid)
        if ch:
            is_cat = isinstance(ch, discord.CategoryChannel)
            t_type = AntiNukeConstants.TARGET_CATEGORY if is_cat else AntiNukeConstants.TARGET_CHANNEL
            return cleaned, t_type, f"#{ch.name}"
        m = guild.get_member(eid)
        if m:
            return cleaned, AntiNukeConstants.TARGET_USER, str(m)
        return cleaned, AntiNukeConstants.TARGET_USER, f"Entity({cleaned})"

    return None, AntiNukeConstants.TARGET_USER, ""


def format_target_mention(entity_id: str, entity_type: str, name: str = "") -> str:
    if entity_type == AntiNukeConstants.TARGET_ROLE:
        return f"<@&{entity_id}>"
    elif entity_type in [AntiNukeConstants.TARGET_CHANNEL, AntiNukeConstants.TARGET_CATEGORY]:
        return f"<#{entity_id}>"
    return f"<@{entity_id}>"


def parse_events(tokens: List[str]) -> List[str]:
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


async def build_whitelist_dashboard_view(guild: discord.Guild) -> Any:
    """
    Default Whitelist Manager Dashboard: Displays existing whitelist entries
    and provides Add, Remove, Refresh, and Back to Anti-Nuke Configuration.
    """
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    whitelists = cfg.get("whitelists", {})

    lines: List[str] = []
    if not whitelists:
        content_text = (
            f"**No whitelisted entities configured.**\n\n"
            f"Only the **Server Owner** (`<@{guild.owner_id}>`) and configured **Extra Owners** "
            f"hold root administrative bypass authority.\n\n"
            f"Click **Add Exemption** below to authorize a user, role, channel, or category."
        )
    else:
        for eid, entry in list(whitelists.items())[:15]:
            t_type = entry.get("type", AntiNukeConstants.TARGET_USER) if isinstance(entry, dict) else AntiNukeConstants.TARGET_USER
            events = entry.get("events", []) if isinstance(entry, dict) else entry
            mention = format_target_mention(eid, t_type)

            if "*" in events or "all" in events:
                ev_str = "All Events (*)"
            else:
                friendly = [AntiNukeConstants.get_event_display_name(e) for e in events[:3]]
                ev_str = ", ".join(friendly)
                if len(events) > 3:
                    ev_str += f" *+{len(events) - 3} more*"

            lines.append(f"• **[{t_type.upper()}]** {mention} (`{eid}`)\n  └ Exemptions: `{ev_str}`")

        more_count = len(whitelists) - 15
        if more_count > 0:
            lines.append(f"-# *...and {more_count} more configured whitelists.*")

        content_text = f"**Configured Whitelists ({len(whitelists)}):**\n\n" + "\n".join(lines)

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:add_flow:{guild.id}")
            .set_label("Add Exemption")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("plus", "➕"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:remove_flow:{guild.id}")
            .set_label("Remove Exemption")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("trash", "🗑️"))
            .set_disabled(len(whitelists) == 0)
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Refresh")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("refresh", "🔄"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Anti-Nuke Config")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Anti-Nuke Whitelist Manager")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(content_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Authority • Scoped Exemptions")
        .add_action_row(action_row)
        .build()
    )


async def build_whitelist_type_picker_view(guild: discord.Guild) -> Any:
    """Step 1: String Select Menu with User, Role, Channel, and Category."""
    select_builder = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wl:select_target_type:{guild.id}")
        .set_placeholder("Select target entity type...")
        .add_option(
            label="User / Bot Account",
            value=AntiNukeConstants.TARGET_USER,
            description="Exempt a specific member or automated bot account",
            emoji=EMOJIS.get("user", "👤")
        )
        .add_option(
            label="Server Role",
            value=AntiNukeConstants.TARGET_ROLE,
            description="Exempt all members holding a specific server role",
            emoji=EMOJIS.get("role", "🛡️")
        )
        .add_option(
            label="Channel",
            value=AntiNukeConstants.TARGET_CHANNEL,
            description="Exempt actions occurring inside a specific channel",
            emoji=EMOJIS.get("channel", "📢")
        )
        .add_option(
            label="Category",
            value=AntiNukeConstants.TARGET_CATEGORY,
            description="Exempt channel creation/deletion within an entire category",
            emoji=EMOJIS.get("tools", "📁")
        )
    )

    cancel_row = (
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
        f"**Step 1 of 4: Select Target Entity Type**\n\n"
        f"Choose whether you want to exempt a **User**, **Role**, **Channel**, or **Category**.\n"
        f"In the next step, a native Discord entity picker will appear."
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Whitelist Wizard: Step 1/4")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_action_row(ActionRowBuilder().add_select_menu(select_builder))
        .add_action_row(cancel_row)
        .build()
    )

build_target_type_picker_view = build_whitelist_type_picker_view


async def build_target_picker_view(guild: discord.Guild, target_type: str) -> Any:
    """Step 2: Show appropriate native Discord entity select menu."""
    type_names = {
        AntiNukeConstants.TARGET_USER: "User or Bot",
        AntiNukeConstants.TARGET_ROLE: "Server Role",
        AntiNukeConstants.TARGET_CHANNEL: "Channel",
        AntiNukeConstants.TARGET_CATEGORY: "Category",
    }
    t_label = type_names.get(target_type, "Entity")

    sel = SelectMenuBuilder().set_custom_id(f"an_wl:picked_target:{target_type}:{guild.id}")

    if target_type == AntiNukeConstants.TARGET_USER:
        sel.set_type(SelectMenuTypes.USER).set_placeholder("Select a user or bot to exempt...")
    elif target_type == AntiNukeConstants.TARGET_ROLE:
        sel.set_type(SelectMenuTypes.ROLE).set_placeholder("Select a server role to exempt...")
    elif target_type == AntiNukeConstants.TARGET_CATEGORY:
        sel.set_type(SelectMenuTypes.CHANNEL).set_channel_types([discord.ChannelType.category]).set_placeholder("Select a channel category to exempt...")
    else:
        sel.set_type(SelectMenuTypes.CHANNEL).set_placeholder("Select a channel to exempt...")

    back_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:add_flow:{guild.id}")
            .set_label("Back to Target Type")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    desc = (
        f"**Step 2 of 4: Select Target {t_label}**\n\n"
        f"Use the native Discord select menu below to pick the **{t_label}** you want to whitelist."
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Whitelist Wizard: Step 2/4")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_action_row(back_row)
        .build()
    )


async def build_event_selector_view(
    guild: discord.Guild,
    entity_id: str,
    entity_type: str,
    display_name: str,
    selected_events: Optional[List[str]] = None
) -> Any:
    """
    Step 3: String Select Menu populated with human-readable monitored event names.
    Supports multi-select, event-by-event selection, preset buttons, and review.
    """
    if selected_events is None:
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        whitelists = cfg.get("whitelists", {})
        existing = whitelists.get(entity_id, {})
        selected_events = existing.get("events", []) if isinstance(existing, dict) else (existing if isinstance(existing, list) else [])

    mention = format_target_mention(entity_id, entity_type, display_name)

    sel = (
        SelectMenuBuilder()
        .set_custom_id(f"an_wl:picked_events:{entity_type}:{entity_id}:{guild.id}")
        .set_placeholder("Select event exemptions to grant...")
        .set_min_values(1)
        .set_max_values(24)
        .add_option(
            label="All Events (*)",
            value="*",
            description="Universal bypass for all 24 monitored anti-nuke events",
            emoji=EMOJIS.get("check", "✅"),
            default=("*" in selected_events)
        )
    )

    vector_events = [
        (AntiNukeConstants.EVENT_CHANNEL_DELETE, "Channel Deleted", "Exempt channel deletions"),
        (AntiNukeConstants.EVENT_CHANNEL_CREATE, "Channel Created", "Exempt channel creations"),
        (AntiNukeConstants.EVENT_CHANNEL_UPDATE, "Channel Updated", "Exempt channel permissions/topic edits"),
        (AntiNukeConstants.EVENT_ROLE_DELETE, "Role Deleted", "Exempt role deletions"),
        (AntiNukeConstants.EVENT_ROLE_CREATE, "Role Created", "Exempt role creations"),
        (AntiNukeConstants.EVENT_ROLE_UPDATE, "Role Updated", "Exempt role permissions/position edits"),
        (AntiNukeConstants.EVENT_BAN_ADD, "Member Banned", "Exempt member ban actions"),
        (AntiNukeConstants.EVENT_MEMBER_REMOVE, "Member Kicked", "Exempt member kicks"),
        (AntiNukeConstants.EVENT_BOT_ADD, "Bot Account Added", "Exempt inviting bot accounts"),
        (AntiNukeConstants.EVENT_WEBHOOKS_UPDATE, "Webhooks Updated", "Exempt creating/deleting webhooks"),
        (AntiNukeConstants.EVENT_GUILD_UPDATE, "Server Settings Updated", "Exempt server name/vanity updates"),
        (AntiNukeConstants.EVENT_BAN_REMOVE, "Member Unbanned", "Exempt member unban actions"),
        (AntiNukeConstants.EVENT_MEMBER_UPDATE, "Member Roles Updated", "Exempt modifying member roles"),
        (AntiNukeConstants.EVENT_AUTOMOD_CREATE, "AutoMod Created", "Exempt creating AutoMod rules"),
        (AntiNukeConstants.EVENT_AUTOMOD_DELETE, "AutoMod Deleted", "Exempt deleting AutoMod rules"),
        (AntiNukeConstants.EVENT_INVITE_CREATE, "Invite Created", "Exempt creating server invites"),
        (AntiNukeConstants.EVENT_INVITE_DELETE, "Invite Deleted", "Exempt deleting server invites"),
        (AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE, "Integrations Updated", "Exempt updating bot integrations"),
        (AntiNukeConstants.EVENT_THREAD_DELETE, "Thread Deleted", "Exempt deleting forum/text threads"),
        (AntiNukeConstants.EVENT_EMOJIS_UPDATE, "Emojis Updated", "Exempt emoji additions/deletions"),
        (AntiNukeConstants.EVENT_STICKERS_UPDATE, "Stickers Updated", "Exempt sticker additions/deletions"),
        (AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE, "Event Deleted", "Exempt deleting scheduled events"),
        (AntiNukeConstants.EVENT_AUDIT_LOG_CREATE, "Audit Log Created", "Exempt audit log churn"),
    ]

    for ev_key, ev_label, ev_desc in vector_events:
        sel.add_option(
            label=ev_label,
            value=ev_key,
            description=ev_desc,
            default=(ev_key in selected_events and "*" not in selected_events)
        )

    action_row_presets = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:preset_events:{entity_type}:{entity_id}:all:{guild.id}")
            .set_label("All Events (*)")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:preset_events:{entity_type}:{entity_id}:channels:{guild.id}")
            .set_label("Channels Only")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("channel", "📢"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:preset_events:{entity_type}:{entity_id}:roles:{guild.id}")
            .set_label("Roles Only")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("role", "🛡️"))
        )
    )

    action_row_nav = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:review:{entity_type}:{entity_id}:{guild.id}")
            .set_label("Review & Save")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    cur_str = "All Events (*)" if ("*" in selected_events) else (", ".join(selected_events) if selected_events else "*None Selected*")

    desc = (
        f"**Step 3 of 4: Select Event Exemptions**\n\n"
        f"• **Target:** {mention} (`{entity_id}`)\n"
        f"• **Scope:** `{entity_type.upper()}`\n"
        f"• **Currently Staged:** `{cur_str}`\n\n"
        f"Select one or more events from the menu below, or use the quick preset buttons."
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("info", "#0844C5"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Whitelist Wizard: Step 3/4")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_action_row(ActionRowBuilder().add_select_menu(sel))
        .add_action_row(action_row_presets)
        .add_action_row(action_row_nav)
        .build()
    )


async def build_review_and_save_view(
    guild: discord.Guild,
    entity_id: str,
    entity_type: str,
    display_name: str,
    events: List[str]
) -> Any:
    """
    Step 4: Review selected target, event exemptions, and available actions.
    Saves changes persistently ONLY after user confirmation.
    """
    mention = format_target_mention(entity_id, entity_type, display_name)

    if "*" in events or "all" in events:
        ev_str = "All Monitored Events (`*`) — Universal Exemption"
    elif events:
        friendly = [AntiNukeConstants.get_event_display_name(e) for e in events]
        ev_str = "\n".join([f"• `{f}`" for f in friendly])
    else:
        ev_str = "*No events selected (Exemption will be cleared)*"

    desc = (
        f"**Step 4 of 4: Review Whitelist Exemption**\n\n"
        f"• **Target:** {mention} (`{entity_id}`)\n"
        f"• **Target Scope:** `{entity_type.upper()}`\n\n"
        f"**Authorized Events ({len(events)}):**\n"
        f"{ev_str}\n\n"
        f"{EMOJIS.get('info', 'ℹ️')} *No changes will be saved to the database until you click **Confirm & Save**.*"
    )

    action_row = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:confirm_save:{entity_type}:{entity_id}:{guild.id}")
            .set_label("Confirm & Save")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("check", "✅"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:edit_events:{entity_type}:{entity_id}:{guild.id}")
            .set_label("Edit Events")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("wrench", "🔧"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wl:main:{guild.id}")
            .set_label("Cancel")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("cross", "❌"))
        )
    )

    return (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Review Whitelist Changes")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(desc)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Authority • Confirmation Required")
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

    # 1. No arguments -> Open the interactive Whitelist Manager Dashboard
    if not args:
        view = await build_whitelist_dashboard_view(guild)
        return await send_response(message, view)

    # 2. Add subcommand shortcut
    if args[0].lower() in ["add", "new", "create"]:
        if len(args) == 1:
            view = await build_target_type_picker_view(guild)
            return await send_response(message, view)
        target_str = args[1]
        event_args = args[2:]
    else:
        target_str = args[0]
        event_args = args[1:]

    # 3. Target provided directly: open interactive event selection for that target
    entity_id, entity_type, display_name = parse_entity_and_type(guild, target_str)
    if not entity_id:
        view = await build_whitelist_dashboard_view(guild)
        return await send_response(message, view)

    if not event_args:
        # Fetch current events or default
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        existing = cfg.get("whitelists", {}).get(entity_id, {})
        current_events = existing.get("events", ["*"]) if isinstance(existing, dict) else (existing if isinstance(existing, list) else ["*"])

        set_pending_events(guild.id, entity_id, current_events)
        view = await build_event_selector_view(guild, entity_id, entity_type, display_name, current_events)
        return await send_response(message, view)

    # Event args provided directly in command: save persistently and return confirmation
    chosen_events = parse_events(event_args)
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
