import re
import time
from typing import List, Dict, Any, Optional
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
aliases = ["an", "security"]
description = "Enterprise Anti-Nuke defense control center, interactive configuration, and monitoring."
category = "Security"
usage = "antinuke [status|setup|mode|ticketbot|extraowner]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


def parse_entity_id(raw: str) -> Optional[str]:
    """Extracts numeric snowflake ID from mention or raw digits."""
    if not raw:
        return None
    cleaned = raw.strip()
    m = re.match(r"^<[@#&]!?:?(\d+)>$", cleaned)
    if m:
        return m.group(1)
    if re.match(r"^\d+$", cleaned):
        return cleaned
    return None


async def build_dashboard_view(guild: discord.Guild) -> Any:
    """Builds the comprehensive interactive Anti-Nuke Dashboard Container using Discord Components V2."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    is_setup = cfg.get("setup_completed", False)
    is_enabled = cfg.get("enabled", False)
    mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)

    # Validate mode against enabled feature flags
    if not AntiNukeConstants.is_mode_enabled(mode):
        mode = AntiNukeConstants.MODE_HARD

    mode_display = AntiNukeManager.get_mode_display_name(mode)
    monitored_events = cfg.get("monitored_events", AntiNukeConstants.ALL_EVENTS)
    extra_owners = cfg.get("extra_owners", [])
    whitelists = cfg.get("whitelists", {})
    ticket_bots = cfg.get("ticket_bots", [])

    warning_ch_id = cfg.get("warning_channel_id")
    warning_ch_str = f"<#{warning_ch_id}>" if warning_ch_id else "*Not Configured*"
    log_ch_id = cfg.get("log_channel_id")
    log_ch_str = f"<#{log_ch_id}>" if log_ch_id else "*Not Configured*"

    if not is_setup:
        status_line = f"{EMOJIS.get('warning', '⚠️')} Defense Status: **INCOMPLETE SETUP** (Monitoring Inactive)"
    elif is_enabled:
        status_line = f"{EMOJIS.get('enabled', '✅')} Defense Status: **ACTIVE & MONITORING**"
    else:
        status_line = f"{EMOJIS.get('disabled', '❌')} Defense Status: **PAUSED / DISABLED**"

    mode_desc = get_string(
        f"security.antinuke.mode_descriptions.{mode}",
        "Strict protection against suspicious destructive server changes, applying the configured thresholds and punishments."
    )

    overview_text = (
        f"• **Active Security Mode:** `{mode_display}`\n"
        f"• **Monitored Vectors:** `{len(monitored_events)}` / 24 gateway events actively guarded\n"
        f"• **Whitelisted Entities:** `{len(whitelists)}` authorized\n"
        f"• **Extra Owners:** `{len(extra_owners)}` configured\n"
        f"• **Exempt Ticket Bots:** `{len(ticket_bots)}` approved\n"
        f"• **Alert Channel:** {warning_ch_str}\n"
        f"• **Log Channel:** {log_ch_str}"
    )

    c_accent = COLORS.get("success" if (is_setup and is_enabled) else "warning", "#0844C5")

    # Row 1: Core Navigation & Toggle Buttons
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

    action_row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_wl:main:{guild.id}")
        .set_label("Whitelists")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("members", "👥"))
    )
    action_row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_pn:dashboard:{guild.id}")
        .set_label("Punishments")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("danger", "⚡"))
    )
    action_row_1.add_button(
        ButtonBuilder()
        .set_custom_id(f"an_th:dashboard:{guild.id}")
        .set_label("Thresholds")
        .set_style(ButtonStyle.Primary)
        .set_emoji(EMOJIS.get("gear", "⚙️"))
    )

    # Row 2: Native Channel Select for Warning / Alert Channel
    sel_warn = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.CHANNEL)
        .set_custom_id(f"an:set_warning_ch:{guild.id}")
        .set_placeholder("Set alert / warning channel...")
    )

    # Row 3: Native Channel Select for Log Channel
    sel_log = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.CHANNEL)
        .set_custom_id(f"an:set_log_ch:{guild.id}")
        .set_placeholder("Set incident forensics log channel...")
    )

    # Row 4: Native User Select for Ticket Bot
    sel_tb = (
        SelectMenuBuilder()
        .set_type(SelectMenuTypes.USER)
        .set_custom_id(f"an:add_ticket_bot:{guild.id}")
        .set_placeholder("Exempt a ticket bot from channel churn...")
    )

    # Row 5: Operating Mode String Select (Enabled modes only)
    sel_mode = (
        SelectMenuBuilder()
        .set_custom_id(f"an:select_mode:{guild.id}")
        .set_placeholder("Change operating mode...")
    )
    enabled_modes = AntiNukeConstants.get_enabled_modes()
    for m in enabled_modes:
        sel_mode.add_option(
            label=AntiNukeManager.get_mode_display_name(m),
            value=m,
            description="Strict protection against suspicious destructive server changes",
            default=(m == mode)
        )

    # Row 6: Utility Buttons
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
            .set_custom_id(f"an:view_eo:{guild.id}")
            .set_label("Extra Owners")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("crown", "👑"))
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
        .add_text_display(
            f"{status_line}\n\n"
            f"{overview_text}\n\n"
            f"**Operating Mode Details:**\n"
            f"> {mode_desc}\n\n"
            f"-# *Notice: Bot enforces actions within Discord's native permission and role hierarchy.*"
        )
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_action_row(action_row_1)
        .add_action_row(ActionRowBuilder().add_select_menu(sel_warn))
        .add_action_row(ActionRowBuilder().add_select_menu(sel_log))
        .add_action_row(ActionRowBuilder().add_select_menu(sel_tb))
        .add_action_row(ActionRowBuilder().add_select_menu(sel_mode))
        .add_action_row(action_row_nav)
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

    # Check root authority: Server Owner, Extra Owner, or Bot Owner
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
    sub_args = args[1:]

    # 1. SETUP WIZARD SHORTCUT
    if sub in ["setup", "wizard", "audit"]:
        from plugins.MomentumOneToolkit.commands.security.setup import build_wizard_step1_view
        view = await build_wizard_step1_view(guild)
        return await send_response(message, view)

    # 2. STATUS / DASHBOARD
    if sub in ["dashboard", "status", "info"]:
        view = await build_dashboard_view(guild)
        return await send_response(message, view)

    # All management commands require setup to be completed first!
    if not AntiNukeManager.is_setup_completed(guild.id):
        view = AntiNukeManager.build_setup_required_view(guild)
        return await send_response(message, view)

    # 3. TOGGLE DEFENSE
    if sub in ["toggle", "enable", "disable"]:
        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        cur = cfg.get("enabled", False)
        new_state = (not cur) if sub == "toggle" else (sub == "enable")
        await AntiNukeManager.save_guild_config(str(guild.id), {"enabled": new_state})
        view = await build_dashboard_view(guild)
        return await send_response(message, view)

    # 4. OPERATING MODE
    elif sub in ["mode", "setmode"]:
        if not sub_args:
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

        target_mode = sub_args[0].lower()
        if not AntiNukeConstants.is_mode_enabled(target_mode):
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("warning", "#F59E0B"))
                .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Mode Unavailable")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(
                    get_string(
                        f"security.antinuke.mode_descriptions.{target_mode}",
                        f"The mode `{target_mode}` is reserved for a future protection system; currently unavailable."
                    )
                )
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Settings")
                .build()
            )
            return await send_response(message, box)

        new_thresholds = get_default_thresholds(target_mode)
        new_punishments = get_default_punishments(target_mode)
        await AntiNukeManager.save_guild_config(str(guild.id), {
            "mode": target_mode,
            "thresholds": new_thresholds,
            "punishments": new_punishments,
        })
        view = await build_dashboard_view(guild)
        return await send_response(message, view)

    # 5. TICKET BOT EXEMPTIONS
    elif sub in ["ticketbot", "tb", "ticketbots"]:
        action = sub_args[0].lower() if sub_args else "list"
        target_str = sub_args[1] if len(sub_args) > 1 else None

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        ticket_bots = list(cfg.get("ticket_bots", []))

        if action in ["list", "show"]:
            lines = [f"• <@{bid}> (`{bid}`)" for bid in ticket_bots] if ticket_bots else ["No ticket bots configured."]
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Approved Ticket Bot Exemptions")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(
                    f"{chr(10).join(lines)}\n\n"
                    f"-# *Note:* Approved ticket bots are exempt from channel creation/deletion churn "
                    f"for ticket channels, while retaining strict protection against bans, kicks, and role deletes."
                )
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                .build()
            )
            return await send_response(message, box)

        target_id = parse_entity_id(target_str) if target_str else None
        if not target_id:
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

        if action in ["add", "set"]:
            if target_id not in ticket_bots:
                ticket_bots.append(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": ticket_bots})
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

        elif action in ["remove", "del", "delete"]:
            if target_id in ticket_bots:
                ticket_bots.remove(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": ticket_bots})
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

    # 6. EXTRA OWNERS
    elif sub in ["extraowner", "eo", "owner"]:
        action = sub_args[0].lower() if sub_args else "list"
        target_str = sub_args[1] if len(sub_args) > 1 else None

        cfg = AntiNukeManager.get_guild_config(str(guild.id))
        extra_owners = list(cfg.get("extra_owners", []))

        if action in ["list", "show"]:
            lines = [f"• Root Owner: <@{guild.owner_id}> (`{guild.owner_id}`)"]
            for uid in extra_owners:
                lines.append(f"• Extra Owner: <@{uid}> (`{uid}`)")

            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("info", "#0844C5"))
                .add_text_display(f"### {EMOJIS.get('crown', '👑')} Anti-Nuke Extra Owners")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display("\n".join(lines))
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# Server Owner has absolute root revocation authority.")
                .build()
            )
            return await send_response(message, box)

        if author.id != guild.owner_id and not is_bot_owner(str(author.id)):
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("error", "#B21F1F"))
                .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Root Owner Only")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Only the server owner (`<@{guild.owner_id}>`) can manage Extra Owners.")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Hierarchy")
                .build()
            )
            return await send_response(message, box)

        target_id = parse_entity_id(target_str) if target_str else None
        if not target_id:
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

        if action in ["add", "set"]:
            if target_id not in extra_owners:
                extra_owners.append(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": extra_owners})
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

        elif action in ["remove", "del", "delete"]:
            if target_id in extra_owners:
                extra_owners.remove(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": extra_owners})
            view = await build_dashboard_view(guild)
            return await send_response(message, view)

    # Default fallback
    view = await build_dashboard_view(guild)
    return await send_response(message, view)
