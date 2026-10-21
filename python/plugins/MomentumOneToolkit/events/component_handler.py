import time
import discord
from typing import Any
from core.logging.logger import logger
from plugins.MomentumOneToolkit.tickets.manager import TicketManager
from sdk.discord import send_ui

name = "interactionComponent"
description = "Button and select menu component dispatcher"

async def execute(ctx: Any, interaction: discord.Interaction):
    try:
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if custom_id.startswith("ticket_close_"):
            channel_id = custom_id[len("ticket_close_"):]
            await interaction.response.defer()
            res = await TicketManager.close_ticket(
                guild=interaction.guild,
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

        # Anti-Nuke Interactive Buttons
        if custom_id.startswith("an:"):
            from core.security.antinuke import AntiNukeManager, AntiNukeConstants, get_default_thresholds, get_default_punishments
            from plugins.MomentumOneToolkit.commands.moderation.antinuke import _build_dashboard_view, _build_setup_wizard_view
            guild = interaction.guild
            if not guild:
                return

            # Validate root authority
            if not AntiNukeManager.is_owner_or_extra_owner(guild, interaction.user.id):
                await send_ui(interaction, "security.antinuke.extra_owner_only", ephemeral=True, style="error")
                return

            parts = custom_id.split(":")
            action = parts[1] if len(parts) > 1 else ""

            if action == "toggle":
                cfg = AntiNukeManager.get_guild_config(str(guild.id))
                new_state = not cfg.get("enabled", False)
                await AntiNukeManager.save_guild_config(str(guild.id), {"enabled": new_state})
                new_view = await _build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "wizard":
                new_view = await _build_setup_wizard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "dashboard":
                new_view = await _build_dashboard_view(guild)
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=new_view)

            elif action == "set_mode" and len(parts) >= 3:
                new_mode = parts[2]
                if new_mode in AntiNukeConstants.VALID_MODES:
                    new_thresholds = get_default_thresholds(new_mode)
                    new_punishments = get_default_punishments(new_mode)
                    await AntiNukeManager.save_guild_config(str(guild.id), {
                        "mode": new_mode,
                        "thresholds": new_thresholds,
                        "punishments": new_punishments,
                    })
                    new_view = await _build_setup_wizard_view(guild)
                    if hasattr(interaction, "response") and not interaction.response.is_done():
                        await interaction.response.edit_message(view=new_view)

            elif action in ["view_wl", "view_eo", "view_tb"]:
                from sdk.discord.builders import ContainerBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, SeparatorSpacingSize
                from config.settings import COLORS, EMOJIS
                from config.strings import get_string
                cfg = AntiNukeManager.get_guild_config(str(guild.id))

                if action == "view_wl":
                    wls = cfg.get("whitelists", {})
                    lines = [f"• `<@{k}>`: `{', '.join(v)}`" for k, v in wls.items()] if wls else ["No whitelisted entities configured."]
                    title = "Configured Whitelists"
                elif action == "view_eo":
                    eos = cfg.get("extra_owners", [])
                    lines = [f"• Root Owner: <@{guild.owner_id}>"] + [f"• Extra Owner: <@{uid}>" for uid in eos]
                    title = "Configured Extra Owners"
                else:
                    tbs = cfg.get("ticket_bots", [])
                    lines = [f"• Approved Ticket Bot: <@{bid}>" for bid in tbs] if tbs else ["No ticket bots configured."]
                    title = "Approved Ticket Bots"

                back_row = ActionRowBuilder().add_button(
                    ButtonBuilder()
                    .set_custom_id(f"an:dashboard:{guild.id}")
                    .set_label("Back to Dashboard")
                    .set_style(ButtonStyle.Secondary)
                    .set_emoji(EMOJIS.get("back", "⬅️"))
                )

                sub_box = (
                    ContainerBuilder()
                    .set_accent_color(COLORS.get("info", "#0844C5"))
                    .add_text_display(f"### {EMOJIS.get('shield', '🛡️')} {title}")
                    .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                    .add_text_display("\n".join(lines))
                    .add_action_row(back_row)
                    .build()
                )
                if hasattr(interaction, "response") and not interaction.response.is_done():
                    await interaction.response.edit_message(view=sub_box)
            return

    except Exception as err:
        logger.error(f"[ComponentHandler] Component execution error: {err}")
