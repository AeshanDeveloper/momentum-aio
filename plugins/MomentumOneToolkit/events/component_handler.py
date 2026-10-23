import time
from typing import Any, List, Dict, Optional, Set
import discord

from core.logging.logger import logger
from plugins.MomentumOneToolkit.tickets.manager import TicketManager
from sdk.discord import send_ui
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from apps.bot.discord.permissions.resolver import is_bot_owner
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)

name = "interactionComponent"
description = "Comprehensive button and select menu component dispatcher for MomentumOne"


async def execute(ctx: Any, interaction: discord.Interaction):
    try:
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        values = interaction.data.get("values", [])
        guild = interaction.guild

        # ----------------------------------------------------------------------
        # 1. Ticket Close Component
        # ----------------------------------------------------------------------
        if custom_id.startswith("ticket_close_"):
            channel_id = custom_id[len("ticket_close_"):]
            await interaction.response.defer()
            res = await TicketManager.close_ticket(
                guild=guild,
                channel=interaction.channel,
                actor_id=str(interaction.user.id),
                reason="Closed via interactive ticket button"
            )
            if not res.get("success"):
                await send_ui(
                    interaction,
                    "commands.ticket.close_failed",
                    variables={"error": res.get("error", "Failed to close ticket.")},
                    ephemeral=True,
                    style="error"
                )
            return

        # ----------------------------------------------------------------------
        # 2. Notification Toggle Component
        # ----------------------------------------------------------------------
        if custom_id.startswith("notif_toggle_"):
            target_user_id = custom_id[len("notif_toggle_"):]
            if str(interaction.user.id) != target_user_id:
                await send_ui(interaction, "permissions.owner_only", ephemeral=True, style="error")
                return

            from database.database import database
            from plugins.MomentumOneToolkit.commands.general.notifications import build_notification_view
            col = database.collection("user_notification_prefs")
            pref = await col.find_one({"userId": target_user_id})
            current_status = pref.get("dmsEnabled", True) if pref else True
            new_status = not current_status
            await col.update_one(
                {"userId": target_user_id},
                {"$set": {"userId": target_user_id, "dmsEnabled": new_status, "updatedAt": time.time()}},
                upsert=True
            )
            updated_view = build_notification_view(target_user_id, new_status)
            if hasattr(interaction, "response") and not interaction.response.is_done():
                await interaction.response.edit_message(view=updated_view.view)
            return

        # ----------------------------------------------------------------------
        # Anti-Nuke Authority Enforcement
        # ----------------------------------------------------------------------
        if custom_id.startswith(("an:", "an_wiz:", "an_wl:", "an_pn:", "an_th:", "an_perm:", "an_eo:")):
            if not guild:
                return

            # Extra Owners management is restricted strictly to Server Owner and Bot Owners
            if custom_id.startswith("an_eo:"):
                uid_str = str(interaction.user.id)
                is_root = (guild.owner_id and str(guild.owner_id) == uid_str) or is_bot_owner(uid_str)
                if not is_root:
                    box = (
                        ContainerBuilder()
                        .set_accent_color(COLORS.get("error", "#B21F1F"))
                        .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Root Authority Required")
                        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                        .add_text_display(
                            f"{EMOJIS.get('cross', '❌')} Only the Server Owner (<@{guild.owner_id}>) can grant or revoke Extra Owner privileges."
                        )
                        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                        .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                        .build()
                    )
                    if hasattr(interaction, "response") and not interaction.response.is_done():
                        await interaction.response.send_message(view=box, ephemeral=True)
                    return

            # All other anti-nuke controls require Server Owner or Extra Owner status
            elif not AntiNukeManager.is_owner_or_extra_owner(guild, interaction.user.id):
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("error", "#B21F1F"))
                    .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can interact with Anti-Nuke settings."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.send_message(view=box, ephemeral=True)
                return

        # ----------------------------------------------------------------------
        # Logging System Authority Enforcement
        # ----------------------------------------------------------------------
        if custom_id.startswith(("log_wiz:", "log_cfg:")):
            if not guild:
                return
            m_perms = interaction.user.guild_permissions if hasattr(interaction.user, "guild_permissions") else None
            is_admin = (m_perms and m_perms.manage_guild) or AntiNukeManager.is_owner_or_extra_owner(guild, interaction.user.id)
            if not is_admin:
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("error", "#B21F1F"))
                    .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"{EMOJIS.get('cross', '❌')} You must have `Manage Server` permission to configure logging.")
                    .set_footer(f"{settings.BOT_NAME} Security Authority")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.send_message(view=box, ephemeral=True)
                return

        # ----------------------------------------------------------------------
        # 3. Setup Wizard Interactions (an_wiz:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an_wiz:"):
            from plugins.MomentumOneToolkit.commands.security.setup import (
                build_wizard_step1_view,
                build_wizard_step2_view,
                build_wizard_step3_view,
                build_wizard_step4_view,
                build_wizard_step5_view,
                build_wizard_step6_view,
                build_wizard_step7_view,
                build_wizard_step8_view,
                build_wizard_step9_view,
                build_wizard_step10_view,
                build_wizard_step11_view,
                get_or_create_wizard_session,
                _WIZARD_SESSIONS,
            )
            sess = get_or_create_wizard_session(guild)
            parts = custom_id.split(":")
            sub_action = parts[1] if len(parts) > 1 else ""

            # Step 1: Pre-Flight Audit
            if sub_action in ["step1", "start"]:
                view = await build_wizard_step1_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 2: Mode Selection
            elif sub_action == "step2":
                view = await build_wizard_step2_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "select_mode":
                chosen_mode = values[0] if values else AntiNukeConstants.MODE_HARD
                if AntiNukeConstants.is_mode_enabled(chosen_mode):
                    sess["mode"] = chosen_mode
                    sess["mode_confirmed"] = True
                view = await build_wizard_step2_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 3: Events Scope Selection
            elif sub_action == "step3":
                view = await build_wizard_step3_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "select_events":
                if values:
                    sess["monitored_events"] = list(values)
                    sess["events_confirmed"] = True
                view = await build_wizard_step3_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "events_all":
                sess["monitored_events"] = list(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
                sess["events_confirmed"] = True
                view = await build_wizard_step3_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "events_confirm":
                sess["events_confirmed"] = True
                view = await build_wizard_step4_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 4: Thresholds
            elif sub_action == "step4":
                view = await build_wizard_step4_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "th_pick_event":
                chosen_ev = values[0] if values else AntiNukeConstants.EVENT_CHANNEL_DELETE
                sess["threshold_active_event"] = chosen_ev
                view = await build_wizard_step4_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "th_set_count":
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                cnt = int(parts[3]) if len(parts) > 3 else 1
                cur = dict(sess["thresholds"].get(ev, {"count": 1, "window": 60}))
                cur["count"] = cnt
                sess["thresholds"][ev] = cur
                sess["threshold_active_event"] = ev
                sess["thresholds_confirmed"] = True
                view = await build_wizard_step4_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "th_set_window":
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                win = int(parts[3]) if len(parts) > 3 else 60
                cur = dict(sess["thresholds"].get(ev, {"count": 1, "window": 60}))
                cur["window"] = win
                sess["thresholds"][ev] = cur
                sess["threshold_active_event"] = ev
                sess["thresholds_confirmed"] = True
                view = await build_wizard_step4_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "th_confirm":
                sess["thresholds_confirmed"] = True
                view = await build_wizard_step5_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 5: Punishments
            elif sub_action == "step5":
                view = await build_wizard_step5_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "pn_pick_event":
                chosen_ev = values[0] if values else AntiNukeConstants.EVENT_CHANNEL_DELETE
                sess["punish_active_event"] = chosen_ev
                view = await build_wizard_step5_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "pn_set":
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                p_act = parts[3] if len(parts) > 3 else "ban"
                if p_act != "quarantine":
                    sess["punishments"][ev] = p_act
                    sess["punish_active_event"] = ev
                    sess["punishments_confirmed"] = True
                view = await build_wizard_step5_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "pn_confirm":
                sess["punishments_confirmed"] = True
                view = await build_wizard_step6_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 6: Security Warning Channel
            elif sub_action == "step6":
                view = await build_wizard_step6_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "set_warning_ch":
                if values:
                    sess["warning_channel_id"] = str(values[0])
                    sess["warning_ch_confirmed"] = True
                view = await build_wizard_step6_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 7: Incident Forensics Log Channel
            elif sub_action == "step7":
                view = await build_wizard_step7_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "set_log_ch":
                if values:
                    sess["log_channel_id"] = str(values[0])
                    sess["log_ch_confirmed"] = True
                view = await build_wizard_step7_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 8: Ticket Bots
            elif sub_action == "step8":
                view = await build_wizard_step8_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "pick_ticket_bot":
                if values:
                    bid = str(values[0])
                    if bid not in sess["ticket_bots"]:
                        sess["ticket_bots"].append(bid)
                view = await build_wizard_step8_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 9: Extra Owners
            elif sub_action == "step9":
                view = await build_wizard_step9_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "pick_extra_owner":
                if values:
                    uid = str(values[0])
                    if uid != str(guild.owner_id) and uid not in sess["extra_owners"]:
                        sess["extra_owners"].append(uid)
                view = await build_wizard_step9_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 10: Whitelists
            elif sub_action == "step10":
                view = await build_wizard_step10_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "pick_wl_user":
                if values:
                    uid = str(values[0])
                    sess["whitelists"][uid] = {
                        "id": uid,
                        "type": AntiNukeConstants.TARGET_USER,
                        "events": ["*"],
                        "name": f"<@{uid}>",
                    }
                view = await build_wizard_step10_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 11: Final Review & Confirmation
            elif sub_action == "step11":
                view = await build_wizard_step11_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "complete":
                warn_ch = sess.get("warning_channel_id")
                log_ch = sess.get("log_channel_id")
                if not warn_ch or not log_ch:
                    view = await build_wizard_step11_view(guild)
                    if hasattr(interaction, "response") and not interaction.response.is_done():
                        await interaction.response.edit_message(view=view)
                    return

                mode = sess.get("mode", AntiNukeConstants.MODE_HARD)
                if not AntiNukeConstants.is_mode_enabled(mode):
                    mode = AntiNukeConstants.MODE_HARD

                monitored = sess.get("monitored_events", AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
                thresholds = sess.get("thresholds") or get_default_thresholds(mode)
                punishments = sess.get("punishments") or get_default_punishments(mode)

                updates = {
                    "setup_completed": True,
                    "enabled": True,
                    "mode": mode,
                    "monitored_events": monitored,
                    "thresholds": thresholds,
                    "punishments": punishments,
                    "warning_channel_id": str(warn_ch),
                    "log_channel_id": str(log_ch),
                    "ticket_bots": sess.get("ticket_bots", []),
                    "extra_owners": sess.get("extra_owners", []),
                    "whitelists": sess.get("whitelists", {}),
                }
                await AntiNukeManager.save_guild_config(str(guild.id), updates)

                if str(guild.id) in _WIZARD_SESSIONS:
                    del _WIZARD_SESSIONS[str(guild.id)]

                success_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("success", "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check', '✅')} Anti-Nuke Setup Completed & Activated")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"Anti-Nuke security platform has been fully initialized and activated for **{guild.name}**.\n\n"
                        f"• **Operating Mode:** `{AntiNukeManager.get_mode_display_name(mode)}`\n"
                        f"• **Monitored Vectors:** `{len(monitored)}` events active\n"
                        f"• **Warning Channel:** <#{warn_ch}>\n"
                        f"• **Log Channel:** <#{log_ch}>\n\n"
                        f"All gateway event monitors are now actively guarding this server."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder().add_button(
                            ButtonBuilder()
                            .set_custom_id(f"an:dashboard:{guild.id}")
                            .set_label("Open Control Center")
                            .set_style(ButtonStyle.Primary)
                            .set_emoji(EMOJIS.get("shield", "🛡️"))
                        )
                    )
                    .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel • Live Protection")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=success_box)

            elif sub_action == "cancel":
                if str(guild.id) in _WIZARD_SESSIONS:
                    del _WIZARD_SESSIONS[str(guild.id)]
                cancel_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("warning", "#F59E0B"))
                    .add_text_display(f"### {EMOJIS.get('info', 'ℹ️')} Setup Wizard Cancelled")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display("Anti-Nuke setup wizard was cancelled. Existing server configuration was preserved.")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder().add_button(
                            ButtonBuilder()
                            .set_custom_id(f"an:dashboard:{guild.id}")
                            .set_label("Back to Dashboard")
                            .set_style(ButtonStyle.Secondary)
                            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                        )
                    )
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=cancel_box)
            return

        # ----------------------------------------------------------------------
        # 4. Dashboard & Focused Panel Interactions (an:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an:"):
            from plugins.MomentumOneToolkit.commands.security.antinuke import (
                build_dashboard_view,
                build_overview_panel,
                build_security_panel,
                build_event_manager_panel,
                build_channels_panel,
                build_ticket_bots_panel,
                build_extra_owners_panel,
                build_access_panel,
                build_permission_manager_panel,
                get_staged_events,
                set_staged_events,
                clear_staged_events,
            )
            parts = custom_id.split(":")
            action = parts[1] if len(parts) > 1 else ""

            # Dashboard Home / Refresh
            if action in ["dashboard", "view"]:
                new_view = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            # Global Defense Toggle
            elif action == "toggle":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                new_state = not cfg.get("enabled", False)
                await AntiNukeManager.save_guild_config(str(guild.id), {"enabled": new_state})
                new_view = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            # "Manage Settings" Select Menu Routing
            elif action == "panel_select":
                target = values[0] if values else "overview"
                if target == "overview":
                    v = await build_overview_panel(guild)
                elif target == "security":
                    v = await build_security_panel(guild)
                elif target == "events":
                    v = await build_event_manager_panel(guild)
                elif target == "thresholds":
                    from plugins.MomentumOneToolkit.commands.security.thresholds import build_thresholds_dashboard_view
                    v = await build_thresholds_dashboard_view(guild, user_id=interaction.user.id)
                elif target == "punishments":
                    from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_panel_view
                    v = await build_punishment_panel_view(guild)
                elif target == "access":
                    v = await build_access_panel(guild)
                elif target == "whitelist":
                    from plugins.MomentumOneToolkit.commands.security.whitelist import build_whitelist_dashboard_view
                    v = await build_whitelist_dashboard_view(guild)
                elif target == "channels":
                    v = await build_channels_panel(guild)
                elif target == "ticketbots":
                    v = await build_ticket_bots_panel(guild)
                elif target == "extraowners":
                    v = await build_extra_owners_panel(guild)
                elif target == "permissions":
                    v = await build_permission_manager_panel(guild)
                else:
                    v = await build_overview_panel(guild)

                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            # Direct Panel Jump Buttons
            elif action == "panel":
                panel_name = parts[2] if len(parts) > 2 else "overview"
                if panel_name == "overview":
                    v = await build_overview_panel(guild)
                elif panel_name == "security":
                    v = await build_security_panel(guild)
                elif panel_name == "events":
                    v = await build_event_manager_panel(guild)
                elif panel_name in ["thresholds", "threshold"]:
                    from plugins.MomentumOneToolkit.commands.security.thresholds import build_thresholds_dashboard_view
                    v = await build_thresholds_dashboard_view(guild, user_id=interaction.user.id)
                elif panel_name in ["punishments", "punishment"]:
                    from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_panel_view
                    v = await build_punishment_panel_view(guild)
                elif panel_name in ["whitelist", "whitelists"]:
                    from plugins.MomentumOneToolkit.commands.security.whitelist import build_whitelist_dashboard_view
                    v = await build_whitelist_dashboard_view(guild)
                elif panel_name == "channels":
                    v = await build_channels_panel(guild)
                elif panel_name == "ticketbots":
                    v = await build_ticket_bots_panel(guild)
                elif panel_name == "extraowners":
                    v = await build_extra_owners_panel(guild)
                elif panel_name == "access":
                    v = await build_access_panel(guild)
                elif panel_name == "permissions":
                    v = await build_permission_manager_panel(guild)
                else:
                    v = await build_dashboard_view(guild)

                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            # Dedicated Event Manager controls
            elif action == "manage_events":
                v = await build_event_manager_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "ev_menu":
                if values:
                    set_staged_events(guild.id, set(values))
                v = await build_event_manager_panel(guild, set(values) if values else None)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "ev_select_all":
                all_evs = set(AntiNukeConstants.USER_CONFIGURABLE_EVENTS)
                set_staged_events(guild.id, all_evs)
                v = await build_event_manager_panel(guild, all_evs)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "ev_save":
                staged = get_staged_events(guild.id)
                sorted_evs = sorted(list(staged))
                await AntiNukeManager.save_guild_config(str(guild.id), {"monitored_events": sorted_evs})
                clear_staged_events(guild.id)
                v = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "ev_cancel":
                clear_staged_events(guild.id)
                v = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            # Security settings controls
            elif action == "select_mode":
                target_mode = values[0] if values else AntiNukeConstants.MODE_HARD
                if AntiNukeConstants.is_mode_enabled(target_mode):
                    await AntiNukeManager.save_guild_config(str(guild.id), {"mode": target_mode})
                v = await build_security_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "set_warning_ch":
                ch_id = values[0] if values else None
                if ch_id:
                    await AntiNukeManager.save_guild_config(str(guild.id), {"warning_channel_id": str(ch_id)})
                v = await build_channels_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "set_log_ch":
                ch_id = values[0] if values else None
                if ch_id:
                    await AntiNukeManager.save_guild_config(str(guild.id), {"log_channel_id": str(ch_id)})
                v = await build_channels_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "add_ticket_bot":
                bot_id = values[0] if values else None
                if bot_id:
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    tbs = list(cfg.get("ticket_bots", []))
                    if str(bot_id) not in tbs:
                        tbs.append(str(bot_id))
                        await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": tbs})
                v = await build_ticket_bots_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "clear_ticket_bots":
                await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": []})
                v = await build_ticket_bots_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "add_extra_owner":
                u_id = values[0] if values else None
                if u_id and str(u_id) != str(guild.owner_id):
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    eos = list(cfg.get("extra_owners", []))
                    if str(u_id) not in eos:
                        eos.append(str(u_id))
                        await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": eos})
                v = await build_extra_owners_panel(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)

            elif action == "help":
                back_row = ActionRowBuilder().add_button(
                    ButtonBuilder()
                    .set_custom_id(f"an:dashboard:{guild.id}")
                    .set_label("Back to Dashboard")
                    .set_style(ButtonStyle.Secondary)
                    .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                )
                help_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('help', '❓')} Anti-Nuke Security Controls")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"• **Dashboard (`$antinuke`):** Compact defense status and settings switcher.\n"
                        f"• **Setup Wizard (`$setup`):** Complete guided baseline security configuration.\n"
                        f"• **Manage Events (`$antinuke events`):** Multi-select monitored gateway vectors.\n"
                        f"• **Thresholds (`$thresholds`):** Configure action limits and sliding windows.\n"
                        f"• **Punishments (`$punishment`):** Configure disciplinary actions per vector.\n"
                        f"• **Extra Owners (`$extraowner`):** Manage trusted administrator co-owners.\n"
                        f"• **Whitelists (`$whitelist`):** Exemption rules for users, roles, and channels."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Suite")
                    .add_action_row(back_row)
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=help_box)
            return

        # ----------------------------------------------------------------------
        # 5. Punishment Interactions (an_pn:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an_pn:"):
            from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_panel_view
            parts = custom_id.split(":")
            pn_action = parts[1] if len(parts) > 1 else ""

            if pn_action in ["dashboard", "overview"]:
                view = await build_punishment_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "pick_event":
                chosen_event = values[0] if values else AntiNukeConstants.EVENT_CHANNEL_DELETE
                view = await build_punishment_panel_view(guild, selected_event=chosen_event)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "set":
                event_name = parts[2] if len(parts) > 2 else ""
                punish_action = parts[3] if len(parts) > 3 else "ban"

                if punish_action != "quarantine":
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    punishments = dict(cfg.get("punishments", {}))
                    punishments[event_name] = punish_action
                    await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": punishments})

                view = await build_punishment_panel_view(guild, selected_event=event_name)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "reset":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
                defaults = get_default_punishments(mode)
                await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": defaults})
                view = await build_punishment_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

        # ----------------------------------------------------------------------
        # 6. Thresholds Interactions (an_th:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an_th:"):
            from plugins.MomentumOneToolkit.commands.security.thresholds import (
                build_thresholds_dashboard_view,
                get_threshold_staging,
            )
            parts = custom_id.split(":")
            th_action = parts[1] if len(parts) > 1 else ""

            if th_action in ["dashboard", "overview"]:
                view = await build_thresholds_dashboard_view(guild, user_id=interaction.user.id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "pick_event":
                chosen_event = values[0] if values else AntiNukeConstants.EVENT_CHANNEL_DELETE
                view = await build_thresholds_dashboard_view(guild, selected_event=chosen_event, user_id=interaction.user.id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action in ["count", "set_count"]:
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                count_val = int(parts[3]) if len(parts) > 3 else 1
                staged = get_threshold_staging(guild.id, interaction.user.id)
                staged["event"] = ev
                staged["count"] = count_val
                view = await build_thresholds_dashboard_view(guild, selected_event=ev, user_id=interaction.user.id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action in ["window", "set_window"]:
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                win_val = int(parts[3]) if len(parts) > 3 else 60
                staged = get_threshold_staging(guild.id, interaction.user.id)
                staged["event"] = ev
                staged["window"] = win_val
                view = await build_thresholds_dashboard_view(guild, selected_event=ev, user_id=interaction.user.id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "save":
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                staged = get_threshold_staging(guild.id, interaction.user.id)
                cnt = staged.get("count", 1)
                win = staged.get("window", 60)

                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                thresholds = dict(cfg.get("thresholds", {}))
                thresholds[ev] = {"count": cnt, "window": win}
                await AntiNukeManager.save_guild_config(str(guild.id), {"thresholds": thresholds})

                view = await build_thresholds_dashboard_view(guild, selected_event=ev, user_id=interaction.user.id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "reset":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
                defaults = get_default_thresholds(mode)
                await AntiNukeManager.save_guild_config(str(guild.id), {"thresholds": defaults})
                view = await build_thresholds_dashboard_view(guild, user_id=interaction.user.id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action in ["cancel", "close", "back"]:
                v = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=v)
            return

        # ----------------------------------------------------------------------
        # 7. Permission Manager Interactions (an_perm:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an_perm:"):
            from plugins.MomentumOneToolkit.commands.security.antinuke import build_permission_manager_panel
            view = await build_permission_manager_panel(guild)
            if hasattr(interaction, "response") and not interaction.response.is_done():
                await interaction.response.edit_message(view=view)
            return

        # ----------------------------------------------------------------------
        # 8. Extra Owner Flow Interactions (an_eo:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an_eo:"):
            from plugins.MomentumOneToolkit.commands.security.extraowner import (
                build_extraowner_main_view,
                build_extraowner_set_view,
                build_extraowner_remove_view,
            )
            parts = custom_id.split(":")
            eo_action = parts[1] if len(parts) > 1 else ""

            if eo_action == "main":
                view = await build_extraowner_main_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif eo_action == "flow_set":
                view = await build_extraowner_set_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif eo_action == "select_user_set":
                chosen_user = values[0] if values else None
                view = await build_extraowner_set_view(guild, selected_user_id=chosen_user)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif eo_action == "confirm_set":
                target_uid = parts[2] if len(parts) > 2 else ""
                if target_uid and target_uid != str(guild.owner_id):
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    eos = list(cfg.get("extra_owners", []))
                    if target_uid not in eos:
                        eos.append(target_uid)
                        await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": eos})
                view = await build_extraowner_main_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif eo_action == "flow_remove":
                view = await build_extraowner_remove_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif eo_action == "select_user_remove":
                chosen_user = values[0] if values else None
                view = await build_extraowner_remove_view(guild, selected_user_id=chosen_user)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif eo_action == "confirm_remove":
                target_uid = parts[2] if len(parts) > 2 else ""
                if target_uid:
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    eos = [uid for uid in cfg.get("extra_owners", []) if uid != target_uid]
                    await AntiNukeManager.save_guild_config(str(guild.id), {"extra_owners": eos})
                view = await build_extraowner_main_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

        # ----------------------------------------------------------------------
        # 9. Whitelist Interactions (an_wl:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("an_wl:"):
            from plugins.MomentumOneToolkit.commands.security.whitelist import (
                build_whitelist_dashboard_view,
                build_whitelist_type_picker_view,
                build_target_picker_view,
                build_event_selector_view,
                build_review_and_save_view,
                get_pending_events,
                set_pending_events,
                clear_pending_events,
                format_target_mention,
            )
            from plugins.MomentumOneToolkit.commands.security.unwhitelist import (
                build_removal_target_picker_view,
                build_removal_event_selector_view,
                get_pending_removal,
                set_pending_removal,
                clear_pending_removal,
            )
            parts = custom_id.split(":")
            wl_action = parts[1] if len(parts) > 1 else ""

            if wl_action in ["main", "dashboard", "back"]:
                view = await build_whitelist_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "add_flow":
                view = await build_whitelist_type_picker_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "pick_type":
                target_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                view = await build_target_picker_view(guild, target_type)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "target_selected":
                target_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                selected_entity_id = values[0] if values else ""
                clear_pending_events(guild.id, selected_entity_id)
                view = await build_event_selector_view(guild, selected_entity_id, target_type, selected_entity_id, [])
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "pick_events":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                selected_events = list(values) if values else ["*"]
                set_pending_events(guild.id, entity_id, selected_events)
                view = await build_event_selector_view(guild, entity_id, entity_type, entity_id, selected_events)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "quick_preset":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                preset = parts[4] if len(parts) > 4 else "all"

                if preset == "all":
                    evs = ["*"]
                elif preset == "bot":
                    evs = [
                        AntiNukeConstants.EVENT_CHANNEL_CREATE,
                        AntiNukeConstants.EVENT_CHANNEL_DELETE,
                        AntiNukeConstants.EVENT_CHANNEL_UPDATE,
                        AntiNukeConstants.EVENT_ROLE_CREATE,
                        AntiNukeConstants.EVENT_ROLE_UPDATE,
                    ]
                elif preset == "channel":
                    evs = [
                        AntiNukeConstants.EVENT_CHANNEL_CREATE,
                        AntiNukeConstants.EVENT_CHANNEL_DELETE,
                        AntiNukeConstants.EVENT_CHANNEL_UPDATE,
                        AntiNukeConstants.EVENT_THREAD_DELETE,
                    ]
                else:
                    evs = [
                        AntiNukeConstants.EVENT_ROLE_CREATE,
                        AntiNukeConstants.EVENT_ROLE_DELETE,
                        AntiNukeConstants.EVENT_ROLE_UPDATE,
                    ]

                set_pending_events(guild.id, entity_id, evs)
                view = await build_review_and_save_view(guild, entity_id, entity_type, entity_id, evs)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "review":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                staged = get_pending_events(guild.id, entity_id) or ["*"]
                view = await build_review_and_save_view(guild, entity_id, entity_type, entity_id, staged)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "edit_events":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                staged = get_pending_events(guild.id, entity_id) or ["*"]
                view = await build_event_selector_view(guild, entity_id, entity_type, entity_id, staged)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "confirm_save":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                staged_events = get_pending_events(guild.id, entity_id) or ["*"]

                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = dict(cfg.get("whitelists", {}))
                whitelists[entity_id] = {
                    "id": entity_id,
                    "type": entity_type,
                    "events": staged_events,
                    "name": format_target_mention(entity_id, entity_type),
                }
                await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})
                clear_pending_events(guild.id, entity_id)

                mention = format_target_mention(entity_id, entity_type)
                ev_str = "All Events (*)" if ("*" in staged_events) else ", ".join([f"`{e}`" for e in staged_events])
                success_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("success", "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check', '✅')} Whitelist Saved Persistently")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"Successfully authorized **[{entity_type.upper()}]** {mention} (`{entity_id}`).\n\n"
                        f"• **Authorized Exemptions:** {ev_str}\n"
                        f"• **Persistence:** Saved in database."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder()
                        .add_button(
                            ButtonBuilder()
                            .set_custom_id(f"an_wl:main:{guild.id}")
                            .set_label("Back to Whitelists")
                            .set_style(ButtonStyle.Primary)
                            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                        )
                    )
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=success_box)

            elif wl_action == "remove_flow":
                view = build_removal_target_picker_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "unwl_pick_target":
                target_id = values[0] if values else ""
                clear_pending_removal(guild.id, target_id)
                view = build_removal_event_selector_view(guild, target_id, [])
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "unwl_pick_events":
                entity_id = parts[2] if len(parts) > 2 else ""
                selected_for_removal = list(values) if values else []
                set_pending_removal(guild.id, entity_id, selected_for_removal)
                view = build_removal_event_selector_view(guild, entity_id, selected_for_removal)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "unwl_confirm_selected":
                entity_id = parts[2] if len(parts) > 2 else ""
                selected_for_removal = get_pending_removal(guild.id, entity_id) or []

                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = dict(cfg.get("whitelists", {}))
                entry = whitelists.get(entity_id, {})
                t_type = entry.get("type", AntiNukeConstants.TARGET_USER) if isinstance(entry, dict) else AntiNukeConstants.TARGET_USER
                current_events = entry.get("events", []) if isinstance(entry, dict) else (entry if isinstance(entry, list) else [])

                if "*" in selected_for_removal or "*" in current_events:
                    remaining_events = []
                else:
                    remaining_events = [e for e in current_events if e not in selected_for_removal]

                if not remaining_events:
                    whitelists.pop(entity_id, None)
                    action_summary = "Removed entire whitelist entry."
                else:
                    whitelists[entity_id] = {
                        "id": entity_id,
                        "type": t_type,
                        "events": remaining_events,
                        "name": format_target_mention(entity_id, t_type),
                    }
                    action_summary = f"Revoked {len(selected_for_removal)} exemption(s). Preserved {len(remaining_events)} unrelated exemption(s)."

                await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})
                clear_pending_removal(guild.id, entity_id)

                mention = format_target_mention(entity_id, t_type)
                success_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("success", "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check', '✅')} Whitelist Updated")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"Target: {mention} (`{entity_id}`)\n\n"
                        f"• **Status:** {action_summary}\n"
                        f"• **Database:** Changes persisted."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder()
                        .add_button(
                            ButtonBuilder()
                            .set_custom_id(f"an_wl:main:{guild.id}")
                            .set_label("Back to Whitelists")
                            .set_style(ButtonStyle.Primary)
                            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                        )
                    )
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=success_box)

            elif wl_action in ["unwl_confirm_all", "delete"]:
                entity_id = parts[2] if len(parts) > 2 else ""
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = dict(cfg.get("whitelists", {}))
                whitelists.pop(entity_id, None)
                await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})
                clear_pending_removal(guild.id, entity_id)

                success_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("success", "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check', '✅')} Whitelist Entry Deleted")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"Exemption for entity `<@{entity_id}>` was completely revoked.")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder()
                        .add_button(
                            ButtonBuilder()
                            .set_custom_id(f"an_wl:main:{guild.id}")
                            .set_label("Back to Whitelists")
                            .set_style(ButtonStyle.Primary)
                            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                        )
                    )
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=success_box)
            return

        # ----------------------------------------------------------------------
        # 11. Logging Setup Wizard Interactions (log_wiz:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("log_wiz:"):
            from plugins.MomentumOneToolkit.commands.general.logging import (
                build_wizard_step1_view,
                build_wizard_step2_view,
                build_wizard_preview_view,
                build_logging_panel_view,
                get_or_create_logging_wizard_session,
                clear_logging_wizard_session,
            )
            from core.logging.webhook_logger import UnifiedWebhookLogger

            sess = get_or_create_logging_wizard_session(guild)
            parts = custom_id.split(":")
            wiz_action = parts[1] if len(parts) > 1 else ""

            if wiz_action in ["start", "step1"]:
                view = await build_wizard_step1_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wiz_action == "set_mode":
                mode = parts[2] if len(parts) > 2 else "category"
                sess["mode"] = mode
                view = await build_wizard_step1_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wiz_action == "toggle_an":
                sess["separate_antinuke"] = not sess.get("separate_antinuke", True)
                view = await build_wizard_step1_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wiz_action == "step2":
                view = await build_wizard_step2_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wiz_action == "set_layout":
                layout = parts[2] if len(parts) > 2 else "category"
                sess["layout"] = layout
                view = await build_wizard_step2_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wiz_action == "preview":
                view = await build_wizard_preview_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wiz_action == "confirm_execute":
                res = await UnifiedWebhookLogger.create_logging_setup_workflow(
                    guild=guild,
                    layout=sess.get("layout", "category"),
                    create_category=(sess.get("mode") == "category"),
                    category_name=sess.get("category_name"),
                    separate_antinuke=sess.get("separate_antinuke", True),
                )
                clear_logging_wizard_session(guild.id)

                if res.get("success"):
                    ch_count = len(res.get("channels", []))
                    msg = (
                        f"Logging system successfully deployed!\n\n"
                        f"• Created `{ch_count}` dedicated private logging channels.\n"
                        f"• Configured `{len(res.get('destinations', {}))}` webhook routes.\n"
                        f"• Validated delivery endpoints and locked permissions."
                    )
                    c_style = "success"
                else:
                    msg = f"Setup encountered errors: {res.get('error', 'Failed to complete channel/webhook provisioning.')}"
                    c_style = "error"

                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get(c_style, "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check' if res.get('success') else 'cross', '✅')} Logging Setup Result")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(msg)
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder().add_button(
                            ButtonBuilder()
                            .set_custom_id(f"log_cfg:panel:{guild.id}")
                            .set_label("Open Logging Panel")
                            .set_style(ButtonStyle.Primary)
                            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                        )
                    )
                    .set_footer(f"{settings.BOT_NAME} Unified Logger")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=box)

            elif wiz_action == "cancel":
                clear_logging_wizard_session(guild.id)
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

        # ----------------------------------------------------------------------
        # 12. Logging Control Panel Interactions (log_cfg:)
        # ----------------------------------------------------------------------
        if custom_id.startswith("log_cfg:"):
            from plugins.MomentumOneToolkit.commands.general.logging import (
                build_logging_panel_view,
                build_assign_channel_view,
            )
            from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory

            parts = custom_id.split(":")
            cfg_action = parts[1] if len(parts) > 1 else ""

            if cfg_action in ["panel", "refresh"]:
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "toggle_active":
                cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                new_state = not cfg.get("enabled", False)
                await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"enabled": new_state})
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "toggle_an":
                cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                new_state = not cfg.get("separate_antinuke", True)
                await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"separate_antinuke": new_state})
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "toggle_cat":
                target_cat = values[0] if values else None
                if target_cat:
                    cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                    disabled = list(cfg.get("disabled_categories", []))
                    if target_cat in disabled:
                        disabled.remove(target_cat)
                    else:
                        disabled.append(target_cat)
                    await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"disabled_categories": disabled})
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "create_one":
                ch, wh, err = await UnifiedWebhookLogger.create_logging_channel_with_webhook(
                    guild=guild,
                    channel_name="server-logs",
                    topic=f"{settings.BOT_NAME} Unified Audit & Server Logs",
                )
                if ch and wh:
                    cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                    dests = dict(cfg.get("destinations", {}))
                    entry = {
                        "channel_id": str(ch.id),
                        "channel_name": ch.name,
                        "webhook_id": str(wh.id),
                        "webhook_url": wh.url,
                    }
                    dests["general"] = entry
                    for c in [LogCategory.MODERATION, LogCategory.CHANNELS, LogCategory.ROLES, LogCategory.MEMBERS, LogCategory.SERVER, LogCategory.CONFIG]:
                        if c not in dests:
                            dests[c] = entry
                    await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"destinations": dests, "enabled": True})
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "create_two":
                ch1, wh1, _ = await UnifiedWebhookLogger.create_logging_channel_with_webhook(
                    guild=guild,
                    channel_name="moderation-logs",
                    topic=f"{settings.BOT_NAME} Moderation & Member Audit Logs",
                )
                ch2, wh2, _ = await UnifiedWebhookLogger.create_logging_channel_with_webhook(
                    guild=guild,
                    channel_name="server-logs",
                    topic=f"{settings.BOT_NAME} Server & Integration Logs",
                )
                if ch1 and ch2 and wh1 and wh2:
                    cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                    dests = dict(cfg.get("destinations", {}))
                    mod_entry = {"channel_id": str(ch1.id), "channel_name": ch1.name, "webhook_id": str(wh1.id), "webhook_url": wh1.url}
                    srv_entry = {"channel_id": str(ch2.id), "channel_name": ch2.name, "webhook_id": str(wh2.id), "webhook_url": wh2.url}
                    dests[LogCategory.MODERATION] = mod_entry
                    dests[LogCategory.MEMBERS] = mod_entry
                    dests[LogCategory.CHANNELS] = srv_entry
                    dests[LogCategory.ROLES] = srv_entry
                    dests[LogCategory.SERVER] = srv_entry
                    dests[LogCategory.CONFIG] = srv_entry
                    dests["general"] = srv_entry
                    await UnifiedWebhookLogger.save_guild_logging_config(str(guild.id), {"destinations": dests, "layout": "dual", "enabled": True})
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "test_webhooks":
                cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                dests = cfg.get("destinations", {})
                ch_tested = set()
                results = []
                for cat, d in dests.items():
                    if isinstance(d, dict) and d.get("channel_id") and d.get("channel_id") not in ch_tested:
                        cid = d.get("channel_id")
                        ch_tested.add(cid)
                        ok, msg = await UnifiedWebhookLogger.test_webhook(guild, cid)
                        results.append(f"• <#{cid}>: {'✅ Success' if ok else f'❌ Failed ({msg})'}")

                summary_msg = "\n".join(results) if results else "No channel destinations configured to test."
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('rocket', '🚀')} Webhook Delivery Test Results")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(summary_msg)
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_action_row(
                        ActionRowBuilder().add_button(
                            ButtonBuilder()
                            .set_custom_id(f"log_cfg:panel:{guild.id}")
                            .set_label("Back to Logging Panel")
                            .set_style(ButtonStyle.Primary)
                            .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                        )
                    )
                    .set_footer(f"{settings.BOT_NAME} Diagnostic Tester")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=box)

            elif cfg_action == "repair_all":
                cfg = UnifiedWebhookLogger.get_guild_logging_config(str(guild.id))
                dests = cfg.get("destinations", {})
                repaired = 0
                for d in dests.values():
                    if isinstance(d, dict) and d.get("channel_id"):
                        ok, _ = await UnifiedWebhookLogger.repair_webhook(guild, d.get("channel_id"))
                        if ok:
                            repaired += 1
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif cfg_action == "do_assign":
                cat = parts[2] if len(parts) > 2 else LogCategory.MODERATION
                ch_id = values[0] if values else None
                if ch_id:
                    target_ch = guild.get_channel(int(ch_id))
                    if isinstance(target_ch, discord.TextChannel):
                        await UnifiedWebhookLogger.assign_category_channel(guild, cat, target_ch)
                view = await build_logging_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

    except Exception as err:
        logger.error(f"[ComponentHandler] Component execution error: {err}", exc_info=True)
