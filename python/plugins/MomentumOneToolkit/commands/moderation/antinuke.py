import re
import time
from typing import List, Dict, Any, Optional, Tuple, Set
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string, render_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from core.security.server_commands import ServerCommandManager
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


name = "antinuke"
aliases = ["an", "security", "wl", "unwl"]
description = "Comprehensive enterprise Anti-Nuke security platform, setup wizard, whitelists, and forensics."
category = "Moderation"
usage = "antinuke [setup|mode|whitelist|unwhitelist|extraowner|ticketbot|channel|webhook|threshold|punishment|status]"
cooldown = 2.0
guild_only = True


def _parse_entity_id(raw: str) -> Optional[str]:
    """Extracts numeric snowflake ID from mention (<@!123>, <@123>, <#123>, <@&123>) or raw digits."""
    if not raw:
        return None
    cleaned = raw.strip()
    m = re.match(r"^<[@#&]!?:?(\d{17,20})>$", cleaned)
    if m:
        return m.group(1)
    if re.match(r"^\d{17,20}$", cleaned):
        return cleaned
    return None


def _parse_events_list(args: List[str]) -> List[str]:
    """Maps user-specified event strings to canonical AntiNukeConstants events."""
    if not args:
        return ["*"]

    joined = " ".join(args).replace(",", " ").lower()
    tokens = joined.split()

    if any(t in ["all", "*", "everything"] for t in tokens):
        return ["*"]

    mapped_events: Set[str] = set()
    for t in tokens:
        if t in ["ban", "bans"]:
            mapped_events.add(AntiNukeConstants.EVENT_BAN)
        elif t in ["kick", "kicks"]:
            mapped_events.add(AntiNukeConstants.EVENT_KICK)
        elif t in ["timeout", "timeouts", "mute", "mutes"]:
            mapped_events.add(AntiNukeConstants.EVENT_TIMEOUT)
        elif t in ["bot", "bots", "bot_add", "botadd"]:
            mapped_events.add(AntiNukeConstants.EVENT_BOT_ADD)
        elif t in ["role", "roles"]:
            mapped_events.update([
                AntiNukeConstants.EVENT_ROLE_CREATE,
                AntiNukeConstants.EVENT_ROLE_DELETE,
                AntiNukeConstants.EVENT_ROLE_UPDATE,
            ])
        elif t in ["channel", "channels"]:
            mapped_events.update([
                AntiNukeConstants.EVENT_CHANNEL_CREATE,
                AntiNukeConstants.EVENT_CHANNEL_DELETE,
                AntiNukeConstants.EVENT_CHANNEL_UPDATE,
            ])
        elif t in ["webhook", "webhooks"]:
            mapped_events.update([
                AntiNukeConstants.EVENT_WEBHOOK_CREATE,
                AntiNukeConstants.EVENT_WEBHOOK_DELETE,
                AntiNukeConstants.EVENT_WEBHOOK_UPDATE,
            ])
        elif t in AntiNukeConstants.ALL_EVENTS:
            mapped_events.add(t)

    return sorted(list(mapped_events)) if mapped_events else ["*"]


async def _build_dashboard_view(guild: discord.Guild) -> Any:
    """Builds the main interactive Anti-Nuke Dashboard Container."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    is_enabled = cfg.get("enabled", False)
    mode = cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE)
    mode_display = AntiNukeManager.get_mode_display_name(mode)

    extra_owners = cfg.get("extra_owners", [])
    whitelists = cfg.get("whitelists", {})
    ticket_bots = cfg.get("ticket_bots", [])

    warning_ch_id = cfg.get("warning_channel_id")
    warning_ch_str = f"<#{warning_ch_id}>" if warning_ch_id else "*Not Configured*"
    log_ch_id = cfg.get("log_channel_id")
    log_ch_str = f"<#{log_ch_id}>" if log_ch_id else "*Not Configured*"
    webhook_status = "Configured" if cfg.get("webhook_url") else "Disabled"

    status_str = get_string(
        "security.antinuke.status_active" if is_enabled else "security.antinuke.status_disabled",
        f"{EMOJIS.get('enabled', '✅')} Anti-Nuke is **ACTIVE** (Mode: `{mode_display}`)" if is_enabled else f"{EMOJIS.get('disabled', '❌')} Anti-Nuke is currently **DISABLED**",
        mode=mode_display
    )

    overview_text = get_string(
        "security.antinuke.overview_fields",
        (
            f"• **Operating Mode:** `{mode_display}`\n"
            f"• **Extra Owners:** `{len(extra_owners)}` configured\n"
            f"• **Whitelisted Entities:** `{len(whitelists)}` configured\n"
            f"• **Approved Ticket Bots:** `{len(ticket_bots)}` configured\n"
            f"• **Warning Channel:** {warning_ch_str}\n"
            f"• **Log Channel:** {log_ch_str}\n"
            f"• **Webhook:** `{webhook_status}`"
        ),
        mode_name=mode_display,
        extra_owners_count=len(extra_owners),
        whitelists_count=len(whitelists),
        ticket_bots_count=len(ticket_bots),
        warning_channel=warning_ch_str,
        log_channel=log_ch_str,
        webhook_status=webhook_status,
    )

    mode_desc = get_string(f"security.antinuke.mode_descriptions.{mode}", "High-security defensive monitoring.")

    c_accent = COLORS.get("success" if is_enabled else "warning", "#0844C5")

    # Interactive Action Buttons
    action_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:toggle:{guild.id}")
            .set_label("Disable Anti-Nuke" if is_enabled else "Enable Anti-Nuke")
            .set_style(ButtonStyle.Danger if is_enabled else ButtonStyle.Success)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:wizard:{guild.id}")
            .set_label("Run Setup Wizard")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("wrench", "🔧"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:mode_menu:{guild.id}")
            .set_label("Switch Mode")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("gear", "⚙️"))
        )
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:view_wl:{guild.id}")
            .set_label("Whitelists")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("members", "👥"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:view_eo:{guild.id}")
            .set_label("Extra Owners")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("crown", "👑"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:view_tb:{guild.id}")
            .set_label("Ticket Bots")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("ticket", "🎫"))
        )
    )

    container = (
        ContainerBuilder()
        .set_accent_color(c_accent)
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {get_string('security.antinuke.title', 'Anti-Nuke Security System')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{status_str}\n\n{overview_text}\n\n**Mode Details ({mode_display}):**\n{mode_desc}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# Use buttons below or commands: `$an setup`, `$an mode`, `$wl @user`, `$an ticketbot`")
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
        .set_footer(f"Guild: {guild.name} • Root Security Authority")
        .build()
    )
    return container


async def _build_setup_wizard_view(guild: discord.Guild) -> Any:
    """
    Builds the interactive Setup Wizard:
    1. Audits native Discord roles for dangerous permissions.
    2. Audits bot role hierarchy and permissions.
    3. Explains risks through configurable security notes from Strings.json.
    4. Provides interactive remediation and mode selection.
    """
    me = guild.me

    # 1. Audit Native Role Permissions
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

    # 2. Audit Role Hierarchy vs Bot
    higher_roles = [r for r in guild.roles if r.position >= me.top_role.position and not r.is_default()]
    hierarchy_is_safe = (len(higher_roles) <= 1)  # only bot's own role or server owner

    if hierarchy_is_safe:
        hierarchy_note = get_string(
            "security.antinuke.hierarchy_safe",
            f"{EMOJIS.get('check', '✅')} **Hierarchy Check Passed**: Bot role `{me.top_role.name}` is positioned above monitored roles.",
            bot_role=me.top_role.name
        )
    else:
        higher_names = ", ".join([f"`{r.name}`" for r in higher_roles[:5]])
        hierarchy_note = get_string(
            "security.antinuke.hierarchy_warning",
            (
                f"{EMOJIS.get('warning', '⚠️')} **Role Hierarchy Warning**: Bot role `{me.top_role.name}` (pos: {me.top_role.position}) "
                f"is **lower** than {len(higher_roles)} role(s) ({higher_names}).\n"
                f"*Note:* The bot **cannot** restrict or protect against users in higher roles."
            ),
            bot_role=me.top_role.name,
            bot_pos=me.top_role.position,
            higher_roles_count=len(higher_roles),
            higher_roles=higher_names,
        )

    # 3. Audit Bot Native Permissions
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
        bot_perms_note = get_string("security.antinuke.bot_perms_safe", f"{EMOJIS.get('check', '✅')} **Bot Permissions**: Bot holds all required administrative permissions.")
    else:
        bot_perms_note = get_string(
            "security.antinuke.bot_perms_missing",
            f"{EMOJIS.get('cross', '❌')} **Bot Missing Permissions**: Bot is missing: `{', '.join(missing_bot_perms)}`.",
            missing_perms=", ".join(missing_bot_perms)
        )

    # 4. Dangerous Roles Summary
    if dangerous_roles:
        d_lines = []
        for r, p_list in dangerous_roles[:6]:
            d_lines.append(f"• <@&{r.id}> (`{r.name}`) — Holds: `{', '.join(p_list)}`")
        if len(dangerous_roles) > 6:
            d_lines.append(f"-# ...and {len(dangerous_roles) - 6} other role(s) hold dangerous permissions.")
        dangerous_roles_text = "\n".join(d_lines)
    else:
        dangerous_roles_text = get_string("security.antinuke.dangerous_roles_clean", f"{EMOJIS.get('check', '✅')} No unmanaged roles hold dangerous administrative permissions.")

    # 5. Risk Explanations from Strings.json
    risk_notes = [
        get_string("security.antinuke.risk_administrator", "• **Administrator**: Bypasses all permissions and overwrites."),
        get_string("security.antinuke.risk_manage_roles", "• **Manage Roles**: Allows editing roles and granting dangerous permissions."),
        get_string("security.antinuke.risk_manage_channels", "• **Manage Channels**: Allows bulk deletion or modification of channels."),
        get_string("security.antinuke.risk_manage_webhooks", "• **Manage Webhooks**: Can create rogue webhooks to spam phishing links."),
    ]
    risks_text = "\n".join(risk_notes)

    # 6. Virtualization Notice
    virt_note = get_string(
        "security.antinuke.virtualization_notice",
        f"{EMOJIS.get('wrench', '🔧')} **Security Recommendation**: Restrict native dangerous permissions from moderators and authorize them via MomentumOne commands (`$channel`, `$announce`)."
    )

    action_row_1 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:set_mode:ultimate:{guild.id}")
            .set_label("Ultimate Defence Wall")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:set_mode:hard:{guild.id}")
            .set_label("Hard Zero-Tolerance")
            .set_style(ButtonStyle.Danger)
            .set_emoji(EMOJIS.get("danger", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:set_mode:hybrid:{guild.id}")
            .set_label("Hybrid Mode")
            .set_style(ButtonStyle.Success)
            .set_emoji(EMOJIS.get("sparkles", "✨"))
        )
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:dashboard:{guild.id}")
            .set_label("Back to Dashboard")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("back", "⬅️"))
        )
    )

    wizard_box = (
        ContainerBuilder()
        .set_accent_color(COLORS.get("warning", "#F59E0B"))
        .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {get_string('security.antinuke.wizard_title', 'Security Audit & Setup Wizard')}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"{hierarchy_note}\n\n{bot_perms_note}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"**Native Roles with Dangerous Permissions ({len(dangerous_roles)}):**\n{dangerous_roles_text}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"**High-Risk Permissions Analysis:**\n{risks_text}\n\n{virt_note}")
        .add_action_row(action_row_1)
        .add_action_row(action_row_2)
        .set_footer(f"MomentumOne Security Audit • Non-Disruptive Virtualization")
        .build()
    )
    return wizard_box


async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (str(command_type).lower() == "slash" or command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        return await send_ui(message, "permissions.guild_only", style="warning")

    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    if not author:
        return

    # Check root permission: Server Owner, Extra Owner, or Bot Owner
    if not AntiNukeManager.is_owner_or_extra_owner(guild, author.id):
        return await send_ui(message, "security.antinuke.extra_owner_only", style="error")

    # Detect alias shortcuts (e.g. `$wl @user` or `$unwl @user`)
    invoked_cmd = str(getattr(message, "content", "")).split()[0].lower() if hasattr(message, "content") else ""
    if invoked_cmd.endswith("wl") and not invoked_cmd.endswith("unwl"):
        args = ["whitelist"] + args
    elif invoked_cmd.endswith("unwl"):
        args = ["unwhitelist"] + args

    sub = args[0].lower() if args else "dashboard"
    sub_args = args[1:]

    # 1. DASHBOARD / STATUS
    if sub in ["dashboard", "status", "info"]:
        view = await _build_dashboard_view(guild)
        return await send_response(message, view)

    # 2. SETUP WIZARD
    elif sub in ["setup", "wizard", "audit"]:
        wizard = await _build_setup_wizard_view(guild)
        return await send_response(message, wizard)

    # 3. TOGGLE ENABLE / DISABLE
    elif sub in ["toggle", "enable", "disable"]:
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        cur = cfg.get("enabled", False)
        new_state = (not cur) if sub == "toggle" else (sub == "enable")
        await AntiNukeManager.save_guild_config(str(guild.id), {"enabled": new_state})
        msg_key = "security.antinuke.toggle_enabled" if new_state else "security.antinuke.toggle_disabled"
        return await send_ui(message, msg_key, style="success" if new_state else "warning")

    # 4. OPERATING MODE
    elif sub in ["mode", "setmode"]:
        if not sub_args:
            cur_mode = AntiNukeManager.get_guild_config(str(guild.id)).get("mode", AntiNukeConstants.MODE_ULTIMATE)
            cur_name = AntiNukeManager.get_mode_display_name(cur_mode)
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('gear', '⚙️')} Anti-Nuke Operating Modes")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(
                    f"Current Mode: **{cur_name}** (`{cur_mode}`)\n\n"
                    f"• **Hard (`hard`):** Zero-tolerance. 1 unauthorized action triggers immediate permanent ban.\n"
                    f"• **Ultimate Defence Wall (`ultimate`):** Configurable sliding burst thresholds with quarantine.\n"
                    f"• **Hybrid (`hybrid`):** Instant bans on bot additions & dangerous permissions, sliding burst defense on channels/roles.\n\n"
                    f"-# *Rule: Only one mode may be active at a time unless Hybrid is selected.*"
                )
                .set_footer("Usage: $antinuke mode <hard|ultimate|hybrid>")
                .build()
            )
            return await send_response(message, box)

        target_mode = sub_args[0].lower()
        if target_mode not in AntiNukeConstants.VALID_MODES:
            return await send_ui(message, "security.antinuke.mode_invalid", style="error")

        # Apply mode presets consistently
        new_thresholds = get_default_thresholds(target_mode)
        new_punishments = get_default_punishments(target_mode)
        await AntiNukeManager.save_guild_config(str(guild.id), {
            "mode": target_mode,
            "thresholds": new_thresholds,
            "punishments": new_punishments,
        })
        mode_display = AntiNukeManager.get_mode_display_name(target_mode)
        return await send_ui(
            message,
            "security.antinuke.mode_updated",
            variables={"mode_name": mode_display},
            style="success"
        )

    # 5. WHITELIST MANAGEMENT
    elif sub in ["whitelist", "wl"]:
        if not sub_args or sub_args[0].lower() in ["list", "show"]:
            cfg = AntiNukeManager.get_guild_config(str(guild.id))
            whitelists = cfg.get("whitelists", {})
            if not whitelists:
                return await send_ui(message, "security.antinuke.whitelist_empty", style="info")

            lines = []
            for eid, events in whitelists.items():
                ev_str = ", ".join(events) if isinstance(events, list) else str(events)
                lines.append(f"• `<@{eid}>` (`{eid}`) — Events: `{ev_str}`")

            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {get_string('security.antinuke.whitelist_list_title', 'Configured Anti-Nuke Whitelists')}")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("\n".join(lines))
                .set_footer(f"Total: {len(whitelists)} entity/entities")
                .build()
            )
            return await send_response(message, box)

        # Parse target user/bot
        target_str = sub_args[0]
        entity_id = _parse_entity_id(target_str)
        if not entity_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        event_args = sub_args[1:]
        chosen_events = _parse_events_list(event_args)

        # Update whitelist in guild config
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        whitelists = dict(cfg.get("whitelists", {}))
        whitelists[entity_id] = chosen_events
        await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})

        # Resolve entity name if in guild
        target_obj = guild.get_member(int(entity_id))
        t_name = str(target_obj) if target_obj else f"User/Bot({entity_id})"
        t_type = "Bot" if (target_obj and target_obj.bot) else "User"

        return await send_ui(
            message,
            "security.antinuke.whitelist_added",
            variables={
                "target_type": t_type,
                "target_name": t_name,
                "target_id": entity_id,
                "events": ", ".join(chosen_events),
            },
            style="success"
        )

    # 6. UNWHITELIST
    elif sub in ["unwhitelist", "unwl", "dewhitelist"]:
        if not sub_args:
            return await send_ui(message, "security.antinuke.whitelist_syntax", style="warning")

        entity_id = _parse_entity_id(sub_args[0])
        if not entity_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        whitelists = dict(cfg.get("whitelists", {}))
        if entity_id not in whitelists:
            return await send_ui(message, "security.antinuke.whitelist_not_found", variables={"target_id": entity_id}, style="warning")

        del whitelists[entity_id]
        await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})

        target_obj = guild.get_member(int(entity_id))
        t_name = str(target_obj) if target_obj else f"ID({entity_id})"
        t_type = "Bot" if (target_obj and target_obj.bot) else "User"

        return await send_ui(
            message,
            "security.antinuke.whitelist_removed",
            variables={"target_type": t_type, "target_name": t_name, "target_id": entity_id},
            style="success"
        )

    # 7. EXTRA OWNERS
    elif sub in ["extraowner", "eo", "owner"]:
        action = sub_args[0].lower() if sub_args else "list"
        target_str = sub_args[1] if len(sub_args) > 1 else None

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        extra_owners = list(cfg.get("extra_owners", []))

        if action in ["list", "show"]:
            if not extra_owners:
                return await send_ui(
                    message,
                    "security.antinuke.extra_owner_empty",
                    variables={"owner_id": str(guild.owner_id)},
                    style="info"
                )

            lines = [f"• Root Owner: <@{guild.owner_id}> (`{guild.owner_id}`)"]
            for uid in extra_owners:
                lines.append(f"• Extra Owner: <@{uid}> (`{uid}`)")

            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('crown', '👑')} {get_string('security.antinuke.extra_owner_title', 'Anti-Nuke Extra Owners')}")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("\n".join(lines))
                .set_footer(f"Server Owner has absolute root revocation authority.")
                .build()
            )
            return await send_response(message, box)

        # Only Server Owner or Bot Owner can add/remove Extra Owners
        if author.id != guild.owner_id and not is_bot_owner(str(author.id)):
            return await send_ui(message, "security.antinuke.extra_owner_only", style="error")

        target_id = _parse_entity_id(target_str) if target_str else None
        if not target_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        if action in ["add", "set"]:
            if target_id not in extra_owners:
                extra_owners.append(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": extra_owners})
            u_obj = guild.get_member(int(target_id))
            u_name = str(u_obj) if u_obj else f"User({target_id})"
            return await send_ui(
                message,
                "security.antinuke.extra_owner_added",
                variables={"user_name": u_name, "user_id": target_id},
                style="success"
            )

        elif action in ["remove", "del", "delete"]:
            if target_id in extra_owners:
                extra_owners.remove(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": extra_owners})
                u_obj = guild.get_member(int(target_id))
                u_name = str(u_obj) if u_obj else f"User({target_id})"
                return await send_ui(
                    message,
                    "security.antinuke.extra_owner_removed",
                    variables={"user_name": u_name, "user_id": target_id},
                    style="success"
                )
            else:
                return await send_ui(message, "security.antinuke.extra_owner_not_found", variables={"user_id": target_id}, style="warning")

    # 8. TICKET BOT EXEMPTIONS
    elif sub in ["ticketbot", "tb", "ticketbots"]:
        action = sub_args[0].lower() if sub_args else "list"
        target_str = sub_args[1] if len(sub_args) > 1 else None

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        ticket_bots = list(cfg.get("ticket_bots", []))

        if action in ["list", "show"]:
            if not ticket_bots:
                return await send_ui(message, "security.antinuke.ticket_bot_empty", style="info")

            lines = []
            for bid in ticket_bots:
                lines.append(f"• Approved Ticket Bot: <@{bid}> (`{bid}`)")

            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} {get_string('security.antinuke.ticket_bot_title', 'Ticket Bot Exemptions')}")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("\n".join(lines))
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(
                    f"-# Approved bots are exempt from channel churn false positives for ticket channels "
                    f"(`ticket-`, `tickets-`, etc.), while retaining strict protection against bans, kicks, and role deletes."
                )
                .build()
            )
            return await send_response(message, box)

        target_id = _parse_entity_id(target_str) if target_str else None
        if not target_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        if action in ["add", "set"]:
            if target_id not in ticket_bots:
                ticket_bots.append(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": ticket_bots})
            b_obj = guild.get_member(int(target_id))
            b_name = str(b_obj) if b_obj else f"Bot({target_id})"
            return await send_ui(
                message,
                "security.antinuke.ticket_bot_added",
                variables={"bot_name": b_name, "bot_id": target_id},
                style="success"
            )

        elif action in ["remove", "del", "delete"]:
            if target_id in ticket_bots:
                ticket_bots.remove(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": ticket_bots})
                b_obj = guild.get_member(int(target_id))
                b_name = str(b_obj) if b_obj else f"Bot({target_id})"
                return await send_ui(
                    message,
                    "security.antinuke.ticket_bot_removed",
                    variables={"bot_name": b_name, "bot_id": target_id},
                    style="success"
                )
            else:
                return await send_ui(message, "security.antinuke.not_found", style="warning")

    # 9. WARNING / LOG CHANNELS
    elif sub in ["channel", "setchannel"]:
        ch_type = sub_args[0].lower() if sub_args else "warning"
        target_str = sub_args[1] if len(sub_args) > 1 else None

        ch_id = _parse_entity_id(target_str) if target_str else getattr(message.channel, "id", None)
        if not ch_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        if ch_type in ["warning", "warn", "alert"]:
            await AntiNukeManager.save_guild_config(str(guild.id), {"warning_channel_id": str(ch_id)})
            return await send_ui(message, "security.antinuke.warning_channel_set", variables={"channel_id": str(ch_id)}, style="success")
        else:
            await AntiNukeManager.save_guild_config(str(guild.id), {"log_channel_id": str(ch_id)})
            return await send_ui(message, "security.antinuke.log_channel_set", variables={"channel_id": str(ch_id)}, style="success")

    # 10. WEBHOOK CONFIGURATION
    elif sub in ["webhook", "setwebhook"]:
        url = sub_args[0] if sub_args else None
        if not url or url.lower() in ["none", "remove", "disable"]:
            await AntiNukeManager.save_guild_config(str(guild.id), {"webhook_url": None})
            return await send_ui(message, "common.success", variables={"message": "Security logging webhook removed."}, style="success")

        if not (url.startswith("https://discord.com/api/webhooks/") or url.startswith("https://discordapp.com/api/webhooks/")):
            return await send_ui(message, "common.error", variables={"message": "Invalid Discord webhook URL format."}, style="error")

        await AntiNukeManager.save_guild_config(str(guild.id), {"webhook_url": url})
        return await send_ui(message, "security.antinuke.webhook_set", variables={"url": url[:30] + "..."}, style="success")

    # 11. THRESHOLD CONFIGURATION
    elif sub in ["threshold", "limit"]:
        if len(sub_args) < 3:
            return await send_response(
                message,
                f"**Usage:** `$antinuke threshold <event> <count> <window_seconds>`\n"
                f"**Events:** {', '.join(AntiNukeConstants.ALL_EVENTS)}"
            )

        event = sub_args[0].lower()
        if event not in AntiNukeConstants.ALL_EVENTS:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        try:
            count = max(1, int(sub_args[1]))
            window = max(5, int(sub_args[2]))
        except ValueError:
            return await send_ui(message, "common.error", variables={"message": "Count and window must be valid integers."}, style="error")

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        thresholds = dict(cfg.get("thresholds", {}))
        thresholds[event] = {"count": count, "window": window}
        await AntiNukeManager.save_guild_config(str(guild.id), {"thresholds": thresholds})

        return await send_ui(
            message,
            "security.antinuke.threshold_updated",
            variables={"event": event, "count": count, "window": window},
            style="success"
        )

    # 12. PUNISHMENT CONFIGURATION
    elif sub in ["punishment", "action"]:
        if len(sub_args) < 2:
            return await send_response(
                message,
                f"**Usage:** `$antinuke punishment <event> <ban|kick|quarantine|timeout>`\n"
                f"**Events:** {', '.join(AntiNukeConstants.ALL_EVENTS)}"
            )

        event = sub_args[0].lower()
        punish = sub_args[1].lower()

        if event not in AntiNukeConstants.ALL_EVENTS:
            return await send_ui(message, "security.antinuke.not_found", style="warning")
        if punish not in AntiNukeConstants.VALID_PUNISHMENTS:
            return await send_ui(message, "common.error", variables={"message": f"Punishment must be one of: {', '.join(AntiNukeConstants.VALID_PUNISHMENTS)}"}, style="error")

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        punishments = dict(cfg.get("punishments", {}))
        punishments[event] = punish
        await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": punishments})

        return await send_ui(
            message,
            "security.antinuke.punishment_updated",
            variables={"event": event, "punishment": punish.upper()},
            style="success"
        )

    # 13. VIRTUAL MODERATOR ROLE AUTHORIZATION (Requirement 7)
    elif sub in ["authorize", "auth"]:
        if not sub_args:
            auth_roles = ServerCommandManager.get_authorized_roles(str(guild.id))
            lines = [f"• <@&{rid}> (`{rid}`)" for rid in auth_roles] if auth_roles else ["No virtual moderator roles configured."]
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('lock', '🔒')} MomentumOne Authorized Virtual Moderator Roles")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("\n".join(lines))
                .set_footer("Usage: $antinuke authorize <@role> | $antinuke deauthorize <@role>")
                .build()
            )
            return await send_response(message, box)

        role_id = _parse_entity_id(sub_args[0])
        if not role_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        res = ServerCommandManager.authorize_moderator_role(str(guild.id), role_id)
        return await send_ui(message, "common.success", variables={"message": res.get("message")}, style="success")

    elif sub in ["deauthorize", "deauth"]:
        if not sub_args:
            return await send_response(message, "**Usage:** `$antinuke deauthorize <@role>`")

        role_id = _parse_entity_id(sub_args[0])
        if not role_id:
            return await send_ui(message, "security.antinuke.not_found", style="warning")

        res = ServerCommandManager.deauthorize_moderator_role(str(guild.id), role_id)
        return await send_ui(message, "common.success", variables={"message": res.get("message")}, style="success")

    else:
        # Default fallback to dashboard
        view = await _build_dashboard_view(guild)
        return await send_response(message, view)
