import time
from typing import Any
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

        # Anti-Nuke Authority Check for all anti-nuke interactions
        if custom_id.startswith(("an:", "an_wiz:", "an_wl:", "an_pn:")):
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
                new_mode = parts[2] if len(parts) > 2 else "ultimate"
                if new_mode in AntiNukeConstants.VALID_MODES:
                    sess["mode"] = new_mode
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
                # Verify that wizard steps reached final completion
                mode = sess.get("mode", AntiNukeConstants.MODE_ULTIMATE)
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

                # Clean up session
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
                build_whitelist_type_picker_view,
                build_entity_event_manager_view,
            )
            parts = custom_id.split(":")
            wl_action = parts[1] if len(parts) > 1 else ""

            if wl_action in ["manage", "main"]:
                view = await build_whitelist_type_picker_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "prompt":
                t_type = parts[2] if len(parts) > 2 else "user"
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} Authorize {t_type.title()}")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"To whitelist a **{t_type.title()}**, use the command syntax:\n\n"
                        f"• **Syntax:** `$whitelist <@{t_type}> [events]`\n"
                        f"• **Example:** `$whitelist @Staff channel,role`\n"
                        f"• **Universal Exemption:** `$whitelist @Staff *`\n\n"
                        f"-# Mention the target entity or provide its snowflake ID."
                    )
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Whitelist System")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=box)

            elif wl_action == "view_all":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = cfg.get("whitelists", {})
                lines = [f"• **[{v.get('type', 'user').upper()}]** `<@{k}>` — `{', '.join(v.get('events', ['*']))}`" for k, v in whitelists.items()] if whitelists else ["No whitelisted entities configured."]
                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} All Configured Whitelists ({len(whitelists)})")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display("\n".join(lines))
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=box)

            elif wl_action == "set_events":
                entity_id = parts[2]
                preset = parts[3]
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = dict(cfg.get("whitelists", {}))

                if preset == "all":
                    events = ["*"]
                elif preset == "channels":
                    events = [
                        AntiNukeConstants.EVENT_CHANNEL_CREATE,
                        AntiNukeConstants.EVENT_CHANNEL_DELETE,
                        AntiNukeConstants.EVENT_CHANNEL_UPDATE,
                        AntiNukeConstants.EVENT_THREAD_DELETE,
                    ]
                else:
                    events = [
                        AntiNukeConstants.EVENT_ROLE_CREATE,
                        AntiNukeConstants.EVENT_ROLE_DELETE,
                        AntiNukeConstants.EVENT_ROLE_UPDATE,
                    ]

                whitelists[entity_id] = {
                    "id": entity_id,
                    "type": "user",
                    "events": events,
                }
                await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})

                view = await build_entity_event_manager_view(guild, entity_id, "user", f"<@{entity_id}>")
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif wl_action == "delete":
                entity_id = parts[2]
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                whitelists = dict(cfg.get("whitelists", {}))
                if entity_id in whitelists:
                    del whitelists[entity_id]
                    await AntiNukeManager.save_guild_config(str(guild.id), {"whitelists": whitelists})

                box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("success", "#3FD438"))
                    .add_text_display(f"### {EMOJIS.get('check', '✅')} Whitelist Exemption Removed")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"Exemption for entity `<@{entity_id}>` was revoked.")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=box)
            return

        # 5. Punishment Interactions (an_pn:)
        if custom_id.startswith("an_pn:"):
            from plugins.MomentumOneToolkit.commands.security.punishment import build_punishment_overview_view
            parts = custom_id.split(":")
            pn_action = parts[1] if len(parts) > 1 else ""

            if pn_action == "dashboard":
                view = await build_punishment_overview_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "set_all":
                action_to_set = parts[2] if len(parts) > 2 else "ban"
                new_punishments = {ev: action_to_set for ev in AntiNukeConstants.ALL_EVENTS}
                await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": new_punishments})
                view = await build_punishment_overview_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)

            elif pn_action == "reset":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                mode = cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE)
                new_punishments = get_default_punishments(mode)
                await AntiNukeManager.save_guild_config(str(guild.id), {"punishments": new_punishments})
                view = await build_punishment_overview_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=view)
            return

        # 6. Dashboard Interactions (an:)
        if custom_id.startswith("an:"):
            from plugins.MomentumOneToolkit.commands.security.antinuke import build_dashboard_view
            parts = custom_id.split(":")
            action = parts[1] if len(parts) > 1 else ""

            if action == "toggle":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                new_state = not cfg.get("enabled", False)
                await AntiNukeManager.save_guild_config(str(guild.id), {"enabled": new_state})
                new_view = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action in ["dashboard", "view"]:
                new_view = await build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "view_tb":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                tbs = cfg.get("ticket_bots", [])
                lines = [f"• Approved Ticket Bot: <@{bid}> (`{bid}`)" for bid in tbs] if tbs else ["No ticket bots configured."]
                back_row = ActionRowBuilder().add_button(
                    ButtonBuilder()
                    .set_custom_id(f"an:dashboard:{guild.id}")
                    .set_label("Back to Dashboard")
                    .set_style(ButtonStyle.Secondary)
                    .set_emoji(EMOJIS.get("arrow_left", "⬅️"))
                )
                sub_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Approved Ticket Bots")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display("\n".join(lines))
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(f"-# {settings.BOT_NAME} Security Authority")
                    .add_action_row(back_row)
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=sub_box)

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
                    .add_text_display(f"### {EMOJIS.get('help', '❓')} Anti-Nuke Command Directory")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display(
                        f"• `$antinuke`: Open the main security control center dashboard.\n"
                        f"• `$setup`: Launch the guided 6-step interactive security setup wizard.\n"
                        f"• `$whitelist`: Authorize users, roles, channels, or categories.\n"
                        f"• `$unwhitelist`: Revoke whitelist exemptions.\n"
                        f"• `$punishment`: Inspect and configure disciplinary responses per event.\n"
                        f"• `$antinuke ticketbot`: Authorize ticket bot channel management.\n"
                        f"• `$antinuke extraowner`: Manage secondary server root authorities."
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
