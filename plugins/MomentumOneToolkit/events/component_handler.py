import time
from typing import Any, List, Dict, Optional
import discord

from core.logging.logger import logger
from plugins.MomentumOneToolkit.tickets.manager import TicketManager
from sdk.discord import send_ui
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)

name = "interactionComponent"
description = "Button and select menu component dispatcher for MomentumOne"


async def execute(ctx: Any, interaction: discord.Interaction):
    try:
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        values = interaction.data.get("values", [])
        guild = interaction.guild

        # 1. Ticket Close
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

        # 2. Notification Toggle
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

        # Anti-Nuke Authority Check for all anti-nuke interaction namespaces
        if custom_id.startswith(("an:", "an_wiz:", "an_wl:", "an_pn:", "an_th:")):
            if not guild:
                return
            if not AntiNukeManager.is_owner_or_extra_owner(guild, interaction.user.id):
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("error", "#B21F1F"))
                    .add_text_display(f"### {EMOJIS.get('denied', '🔒')} Access Denied")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"{EMOJIS.get('cross', '❌')} Only the Server Owner or configured Extra Owners can interact with Anti-Nuke settings.")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.send_message(view=box, ephemeral=True)
                return

        # 3. Setup Wizard Interactions (an_wiz:)
        if custom_id.startswith("an_wiz:"):
            from plugins.MomentumOneToolkit.commands.security.setup import (
                build_wizard_step1_view,
                build_wizard_step2_view,
                build_wizard_step3_view,
                build_wizard_step4_view,
                build_wizard_step5_view,
                build_wizard_step6_view,
                get_or_create_wizard_session,
                _WIZARD_SESSIONS,
            )
            sess = get_or_create_wizard_session(guild)
            parts = custom_id.split(":")
            sub_action = parts[1] if len(parts) > 1 else ""

            if sub_action in ["step1", "start"]:
                view = await build_wizard_step1_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "step2":
                view = await build_wizard_step2_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "set_mode":
                new_mode = parts[2] if len(parts) > 2 else "hard"
                # Validate against enabled feature flags
                if AntiNukeConstants.is_mode_enabled(new_mode):
                    sess["mode"] = new_mode
                else:
                    sess["mode"] = AntiNukeConstants.MODE_HARD
                view = await build_wizard_step2_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "step3":
                view = await build_wizard_step3_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "events_all":
                sess["monitored_events"] = list(AntiNukeConstants.ALL_EVENTS)
                view = await build_wizard_step3_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "step4":
                view = await build_wizard_step4_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "step5":
                ch_id = getattr(interaction.channel, "id", None)
                view = await build_wizard_step5_view(guild, ch_id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "bind_ch":
                target_ch = parts[3] if len(parts) > 3 else str(getattr(interaction.channel, "id", ""))
                sess["warning_channel_id"] = target_ch
                sess["log_channel_id"] = target_ch
                ch_id = getattr(interaction.channel, "id", None)
                view = await build_wizard_step5_view(guild, ch_id)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "step6":
                view = await build_wizard_step6_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif sub_action == "complete":
                mode = sess.get("mode", AntiNukeConstants.MODE_HARD)
                if not AntiNukeConstants.is_mode_enabled(mode):
                    mode = AntiNukeConstants.MODE_HARD

                monitored = sess.get("monitored_events", AntiNukeConstants.ALL_EVENTS)
                warn_ch = sess.get("warning_channel_id") or str(getattr(interaction.channel, "id", ""))
                log_ch = sess.get("log_channel_id") or warn_ch

                updates = {
                    "setup_completed": True,
                    "enabled": True,
                    "mode": mode,
                    "monitored_events": monitored,
                    "warning_channel_id": warn_ch,
                    "log_channel_id": log_ch,
                    "thresholds": get_default_thresholds(mode),
                    "punishments": get_default_punishments(mode),
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
                        f"{EMOJIS.get('check', '✅')} Anti-Nuke security platform has been initialized and activated for **{guild.name}**.\n\n"
                        f"• **Operating Mode:** `{AntiNukeManager.get_mode_display_name(mode)}`\n"
                        f"• **Monitored Vectors:** `{len(monitored)}` events active\n"
                        f"• **Alert Channel:** <#{warn_ch}>\n"
                        f"• **Log Channel:** <#{log_ch}>\n\n"
                        f"All real-time gateway listeners are now actively monitoring and protecting this server."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Sentinel • Live Enforcement")
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
                    .add_text_display("Anti-Nuke setup wizard was cancelled. Existing configuration was preserved.")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Platform")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=cancel_box)
            return

        # 4. Whitelist Interactions (an_wl:)
        if custom_id.startswith("an_wl:"):
            from plugins.MomentumOneToolkit.commands.security.whitelist import (
                build_whitelist_dashboard_view,
                build_target_type_picker_view,
                build_target_picker_view,
                build_event_selector_view,
                build_review_and_save_view,
                set_pending_events,
                get_pending_events,
                clear_pending_events,
                format_target_mention,
            )
            from plugins.MomentumOneToolkit.commands.security.unwhitelist import (
                build_removal_target_picker_view,
                build_removal_event_selector_view,
                set_pending_removal,
                get_pending_removal,
                clear_pending_removal,
            )
            parts = custom_id.split(":")
            wl_action = parts[1] if len(parts) > 1 else ""

            # Dashboard main view
            if wl_action in ["main", "manage"]:
                view = build_whitelist_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 1: Start add flow -> Target Type Picker
            elif wl_action == "add_flow":
                view = build_target_type_picker_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 1 Callback: String select with User, Role, Channel, Category
            elif wl_action == "select_target_type":
                chosen_type = values[0] if values else AntiNukeConstants.TARGET_USER
                view = build_target_picker_view(guild, chosen_type)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 2 Callback: Native entity selector chosen (User, Role, Channel, Category)
            elif wl_action == "picked_target":
                target_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                target_id = values[0] if values else ""
                if not target_id:
                    view = build_whitelist_dashboard_view(guild)
                else:
                    # Check existing exemptions if any
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    existing = cfg.get("whitelists", {}).get(target_id, {})
                    cur_events = existing.get("events", ["*"]) if isinstance(existing, dict) else (existing if isinstance(existing, list) else ["*"])
                    set_pending_events(guild.id, target_id, cur_events)
                    view = build_event_selector_view(guild, target_id, target_type, target_id, cur_events)

                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 3 Callback: Monitored events selected from string select menu
            elif wl_action == "picked_events":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                selected_events = list(values) if values else ["*"]
                set_pending_events(guild.id, entity_id, selected_events)

                # Show review & save view with staged events
                view = build_review_and_save_view(guild, entity_id, entity_type, entity_id, selected_events)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 3 Presets (All, Channels, Roles)
            elif wl_action == "preset_events":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                preset = parts[4] if len(parts) > 4 else "all"

                if preset == "all":
                    evs = ["*"]
                elif preset == "channels":
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
                view = build_review_and_save_view(guild, entity_id, entity_type, entity_id, evs)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 4: Review button clicked
            elif wl_action == "review":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                staged = get_pending_events(guild.id, entity_id) or ["*"]
                view = build_review_and_save_view(guild, entity_id, entity_type, entity_id, staged)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 4: Edit Events button (go back to Step 3)
            elif wl_action == "edit_events":
                entity_type = parts[2] if len(parts) > 2 else AntiNukeConstants.TARGET_USER
                entity_id = parts[3] if len(parts) > 3 else ""
                staged = get_pending_events(guild.id, entity_id) or ["*"]
                view = build_event_selector_view(guild, entity_id, entity_type, entity_id, staged)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Step 4: Confirm & Save button clicked -> Write persistently to Database
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

            # Removal flow: Target Picker
            elif wl_action == "remove_flow":
                view = build_removal_target_picker_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Removal flow: Target chosen from select menu
            elif wl_action == "unwl_pick_target":
                target_id = values[0] if values else ""
                clear_pending_removal(guild.id, target_id)
                view = build_removal_event_selector_view(guild, target_id, [])
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Removal flow: Events chosen for selective removal
            elif wl_action == "unwl_pick_events":
                entity_id = parts[2] if len(parts) > 2 else ""
                selected_for_removal = list(values) if values else []
                set_pending_removal(guild.id, entity_id, selected_for_removal)
                view = build_removal_event_selector_view(guild, entity_id, selected_for_removal)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            # Removal flow: Confirm selective removal (preserves unrelated exemptions)
            elif wl_action == "unwl_confirm_selected":
                entity_id = parts[2] if len(parts) > 2 else ""
                selected_for_removal = get_pending_removal(guild.id, entity_id) or []

                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = dict(cfg.get("whitelists", {}))
                entry = whitelists.get(entity_id, {})
                t_type = entry.get("type", AntiNukeConstants.TARGET_USER) if isinstance(entry, dict) else AntiNukeConstants.TARGET_USER
                current_events = entry.get("events", []) if isinstance(entry, dict) else (entry if isinstance(entry, list) else [])

                # If removing all or "*"
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

            # Removal flow: Confirm complete removal
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

        # 5. Punishment Interactions (an_pn:)
        if custom_id.startswith("an_pn:"):
            from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_panel_view
            parts = custom_id.split(":")
            pn_action = parts[1] if len(parts) > 1 else ""

            if pn_action in ["dashboard", "overview"]:
                view = build_punishment_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "pick_event":
                chosen_event = values[0] if values else AntiNukeConstants.EVENT_CHANNEL_DELETE
                view = build_punishment_panel_view(guild, selected_event=chosen_event)
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

                view = build_punishment_panel_view(guild, selected_event=event_name)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "reset":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
                defaults = get_default_punishments(mode)
                await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": defaults})
                view = build_punishment_panel_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

        # 6. Thresholds Interactions (an_th:)
        if custom_id.startswith("an_th:"):
            from plugins.MomentumOneToolkit.commands.security.thresholds import build_thresholds_dashboard_view
            parts = custom_id.split(":")
            th_action = parts[1] if len(parts) > 1 else ""

            if th_action == "dashboard":
                view = build_thresholds_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "pick_event":
                chosen_event = values[0] if values else AntiNukeConstants.EVENT_CHANNEL_DELETE
                view = build_thresholds_dashboard_view(guild, selected_event=chosen_event)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "count":
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                count_val = int(parts[3]) if len(parts) > 3 else 1
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                thresholds = dict(cfg.get("thresholds", {}))
                cur_th = dict(thresholds.get(ev, {"count": 1, "window": 60}))
                cur_th["count"] = count_val
                thresholds[ev] = cur_th
                await AntiNukeManager.save_guild_config(str(guild.id), {"thresholds": thresholds})
                view = build_thresholds_dashboard_view(guild, selected_event=ev)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "window":
                ev = parts[2] if len(parts) > 2 else AntiNukeConstants.EVENT_CHANNEL_DELETE
                win_val = int(parts[3]) if len(parts) > 3 else 60
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                thresholds = dict(cfg.get("thresholds", {}))
                cur_th = dict(thresholds.get(ev, {"count": 1, "window": 60}))
                cur_th["window"] = win_val
                thresholds[ev] = cur_th
                await AntiNukeManager.save_guild_config(str(guild.id), {"thresholds": thresholds})
                view = build_thresholds_dashboard_view(guild, selected_event=ev)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif th_action == "reset":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                mode = cfg.get("mode", AntiNukeConstants.MODE_HARD)
                defaults = get_default_thresholds(mode)
                await AntiNukeManager.save_guild_config(str(guild.id), {"thresholds": defaults})
                view = build_thresholds_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

        # 7. Dashboard Interactions (an:)
        if custom_id.startswith("an:"):
            from plugins.MomentumOneToolkit.commands.security.antinuke import build_dashboard_view
            parts = custom_id.split(":")
            action = parts[1] if len(parts) > 1 else ""

            if action == "toggle":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                new_state = not cfg.get("enabled", False)
                await AntiNukeManager.save_guild_config(str(guild.id), {"enabled": new_state})
                new_view = build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action in ["dashboard", "view"]:
                new_view = build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "select_mode":
                target_mode = values[0] if values else AntiNukeConstants.MODE_HARD
                if AntiNukeConstants.is_mode_enabled(target_mode):
                    new_thresholds = get_default_thresholds(target_mode)
                    new_punishments = get_default_punishments(target_mode)
                    await AntiNukeManager.save_guild_config(str(guild.id), {
                        "mode": target_mode,
                        "thresholds": new_thresholds,
                        "punishments": new_punishments,
                    })
                new_view = build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "set_warning_ch":
                ch_id = values[0] if values else None
                if ch_id:
                    await AntiNukeManager.save_guild_config(str(guild.id), {"warning_channel_id": str(ch_id)})
                new_view = build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "set_log_ch":
                ch_id = values[0] if values else None
                if ch_id:
                    await AntiNukeManager.save_guild_config(str(guild.id), {"log_channel_id": str(ch_id)})
                new_view = build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "add_ticket_bot":
                bot_id = values[0] if values else None
                if bot_id:
                    cfg = AntiNukeManager.get_guild_config(str(guild.id))
                    tbs = list(cfg.get("ticket_bots", []))
                    if str(bot_id) not in tbs:
                        tbs.append(str(bot_id))
                        await AntiNukeManager.save_guild_config(str(guild.id), {"ticket_bots": tbs})
                new_view = build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "view_eo":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                eos = cfg.get("extra_owners", [])
                lines = [f"• Root Owner: <@{guild.owner_id}> (`{guild.owner_id}`)"]
                for uid in eos:
                    lines.append(f"• Extra Owner: <@{uid}> (`{uid}`)")
                back_row = ActionRowBuilder().add_button(
                    ButtonBuilder()
                    .set_custom_id(f"an:dashboard:{guild.id}")
                    .set_label("Back to Dashboard")
                    .set_style(ButtonStyle.Secondary)
                    .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                )
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('crown', '👑')} Anti-Nuke Extra Owners")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display("\n".join(lines))
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# Server Owner has absolute root revocation authority.")
                    .add_action_row(back_row)
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=box)

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
                        f"• **Dashboard (`$antinuke`):** Live monitoring posture and primary controls.\n"
                        f"• **Setup Wizard (`$setup`):** 6-step guided baseline security configuration.\n"
                        f"• **Whitelist (`$whitelist`):** Exemption workflow for users, roles, channels, and categories.\n"
                        f"• **Unwhitelist (`$unwhitelist`):** Exemption-by-exemption selective removal.\n"
                        f"• **Punishments (`$punishment`):** Configure Ban, Kick, Mute, Prune, or Strip Roles per vector.\n"
                        f"• **Thresholds (`$thresholds`):** Set event action count limits and sliding time windows."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Suite")
                    .add_action_row(back_row)
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=help_box)
            return

    except Exception as err:
        logger.error(f"[ComponentHandler] Component execution error: {err}")
