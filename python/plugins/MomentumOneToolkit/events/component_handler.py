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

    except Exception as err:
        logger.error(f"[ComponentHandler] Component execution error: {err}")
