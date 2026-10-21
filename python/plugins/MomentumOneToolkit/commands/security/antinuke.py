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
    SeparatorSpacingSize,
    ButtonStyle,
)
from sdk.discord.response import send_response, send_ui
from shared.types.command_record import CommandType


name = "antinuke"
aliases = ["an", "security"]
description = "Enterprise Anti-Nuke defense control center, status overview, and forensics."
category = "Security"
usage = "antinuke [status|setup|mode|ticketbot|extraowner]"
user_permissions = ["administrator"]
cooldown = 2.0
guild_only = True


def _parse_entity_id(raw: str) -> Optional[str]:
    """Extracts numeric snowflake ID from mention (<@!123>, <@123>, <#123>, <@&123>) or raw digits."""
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
    """Builds the main interactive Anti-Nuke Dashboard Container."""
    cfg = AntiNukeManager.get_guild_config(str(guild.id))
    is_setup = cfg.get("setup_completed", False)
    is_enabled = cfg.get("enabled", False)
    mode = cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE)
    mode_display = AntiNukeManager.get_mode_display_name(mode)

    monitored_events = cfg.get("monitored_events", AntiNukeConstants.ALL_EVENTS)
    extra_owners = cfg.get("extra_owners", [])
    whitelists = cfg.get("whitelists", {})
    ticket_bots = cfg.get("ticket_bots", [])

    warning_ch_id = cfg.get("warning_channel_id")
    warning_ch_str = f"<#{warning_ch_id}>" if warning_ch_id else "*Not Configured*"
    log_ch_id = cfg.get("log_channel_id")
    log_ch_str = f"<#{log_ch_id}>" if log_ch_id else "*Not Configured*"
    webhook_status = "Active" if cfg.get("webhook_url") else "Disabled"

    if not is_setup:
        status_line = f"{EMOJIS.get('warning', '⚠️')} Setup Status: **INCOMPLETE** (Defense Inactive)"
    elif is_enabled:
        status_line = f"{EMOJIS.get('enabled', '✅')} Defense Status: **ACTIVE & MONITORING** (Mode: `{mode_display}`)"
    else:
        status_line = f"{EMOJIS.get('disabled', '❌')} Defense Status: **PAUSED / DISABLED**"

    overview_text = (
        f"• **Operating Mode:** `{mode_display}`\n"
        f"• **Monitored Vectors:** `{len(monitored_events)}` event(s) actively guarded\n"
        f"• **Whitelisted Entities:** `{len(whitelists)}` configured\n"
        f"• **Extra Owners:** `{len(extra_owners)}` configured\n"
        f"• **Approved Ticket Bots:** `{len(ticket_bots)}` exempted\n"
        f"• **Alert Channel:** {warning_ch_str}\n"
        f"• **Log Channel:** {log_ch_str}\n"
        f"• **Webhook Sentinel:** `{webhook_status}`"
    )

    mode_desc = get_string(
        f"security.antinuke.mode_descriptions.{mode}",
        "High-performance automated defensive monitoring and role virtualization."
    )

    c_accent = COLORS.get("success" if (is_setup and is_enabled) else "warning", "#0844C5")

    # Interactive Action Buttons
    action_row_1 = ActionRowBuilder()
    if is_setup:
        action_row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"an:toggle:{guild.id}")
            .set_label("Disable Defense" if is_enabled else "Enable Defense")
            .set_style(ButtonStyle.Danger if is_enabled else ButtonStyle.Success)
            .set_emoji(EMOJIS.get("shield", "🛡️"))
        )
        action_row_1.add_button(
            ButtonBuilder()
            .set_custom_id(f"an_wiz:step1:{guild.id}")
            .set_label("Re-Run Wizard")
            .set_style(ButtonStyle.Primary)
            .set_emoji(EMOJIS.get("wrench", "🔧"))
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
        .set_custom_id(f"an_wl:manage:{guild.id}")
        .set_label("Whitelists")
        .set_style(ButtonStyle.Secondary)
        .set_emoji(EMOJIS.get("members", "👥"))
    )

    action_row_2 = (
        ActionRowBuilder()
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an_pn:dashboard:{guild.id}")
            .set_label("Punishments")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("danger", "⚡"))
        )
        .add_button(
            ButtonBuilder()
            .set_custom_id(f"an:view_tb:{guild.id}")
            .set_label("Ticket Bots")
            .set_style(ButtonStyle.Secondary)
            .set_emoji(EMOJIS.get("ticket", "🎫"))
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
        .add_text_display(f"{status_line}\n\n{overview_text}\n\n**Mode Details ({mode_display}):**\n{mode_desc}")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Platform • Non-Disruptive Virtualization")
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

        c_accent = COLORS.get("success" if new_state else "warning", "#0844C5")
        state_str = "ENABLED" if new_state else "PAUSED / DISABLED"
        box = (
            ContainerBuilder()
            .set_accent_color(c_accent)
            .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Anti-Nuke Status Updated")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"{EMOJIS.get('check', '✅') if new_state else EMOJIS.get('warning', '⚠️')} "
                f"Anti-Nuke real-time defense is now **{state_str}** for **{guild.name}**."
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel")
            .build()
        )
        return await send_response(message, box)

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
                    f"• **Ultimate Defence Wall (`ultimate`):** Configurable sliding burst thresholds with automated quarantine.\n"
                    f"• **Hybrid (`hybrid`):** Instant bans on bot additions & dangerous permissions, sliding burst defense on channels/roles.\n\n"
                    f"-# *Rule: Only one mode may be active at a time unless Hybrid is selected.*"
                )
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# Usage: `$antinuke mode <hard|ultimate|hybrid>`")
                .build()
            )
            return await send_response(message, box)

        target_mode = sub_args[0].lower()
        if target_mode not in AntiNukeConstants.VALID_MODES:
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("error", "#B21F1F"))
                .add_text_display(f"### {EMOJIS.get('cross', '❌')} Invalid Operating Mode")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Supported modes: `hard`, `ultimate` (Ultimate Defence Wall), `hybrid`.")
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
        mode_display = AntiNukeManager.get_mode_display_name(target_mode)
        box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("success", "#3FD438"))
            .add_text_display(f"### {EMOJIS.get('check', '✅')} Operating Mode Updated")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"Anti-Nuke operating mode for **{guild.name}** set to: **{mode_display}** (`{target_mode}`).")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
            .build()
        )
        return await send_response(message, box)

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
                    f"for ticket channels (`ticket-`, `tickets-`, etc.), while retaining strict protection against bans, kicks, and role deletes."
                )
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# Usage: `$antinuke ticketbot add <@bot>` | `$antinuke ticketbot remove <@bot>`")
                .build()
            )
            return await send_response(message, box)

        target_id = _parse_entity_id(target_str) if target_str else None
        if not target_id:
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("warning", "#F59E0B"))
                .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} Bot Mention or ID Required")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Please specify a valid bot mention or snowflake ID.\n\n*Usage:* `$antinuke ticketbot add <@bot>`")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Ticket Protection")
                .build()
            )
            return await send_response(message, box)

        if action in ["add", "set"]:
            if target_id not in ticket_bots:
                ticket_bots.append(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": ticket_bots})
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"### {EMOJIS.get('check', '✅')} Ticket Bot Approved")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Bot <@{target_id}> (`{target_id}`) has been granted ticket channel exemption.")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
                .build()
            )
            return await send_response(message, box)

        elif action in ["remove", "del", "delete"]:
            if target_id in ticket_bots:
                ticket_bots.remove(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": ticket_bots})
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"### {EMOJIS.get('check', '✅')} Ticket Bot Exemption Revoked")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Removed ticket channel exemption from <@{target_id}> (`{target_id}`).")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
                .build()
            )
            return await send_response(message, box)

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

        target_id = _parse_entity_id(target_str) if target_str else None
        if not target_id:
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("warning", "#F59E0B"))
                .add_text_display(f"### {EMOJIS.get('warning', '⚠️')} User Mention or ID Required")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Please provide a valid user mention or ID.\n\n*Usage:* `$antinuke extraowner add <@user>`")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Root Authority")
                .build()
            )
            return await send_response(message, box)

        if action in ["add", "set"]:
            if target_id not in extra_owners:
                extra_owners.append(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": extra_owners})
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"### {EMOJIS.get('check', '✅')} Extra Owner Added")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Granted Extra Owner authority to <@{target_id}> (`{target_id}`).")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                .build()
            )
            return await send_response(message, box)

        elif action in ["remove", "del", "delete"]:
            if target_id in extra_owners:
                extra_owners.remove(target_id)
                await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": extra_owners})
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#3FD438"))
                .add_text_display(f"### {EMOJIS.get('check', '✅')} Extra Owner Removed")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Revoked Extra Owner authority from <@{target_id}> (`{target_id}`).")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                .build()
            )
            return await send_response(message, box)

    # Default fallback
    view = await build_dashboard_view(guild)
    return await send_response(message, view)
