import discord
from typing import Any
from core.logging.logger import logger
from plugins.MomentumOneToolkit.tickets.manager import TicketManager

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
                await interaction.followup.send(f"❌ {res.get('error')}", ephemeral=True)

    except Exception as err:
        logger.error(f"[ComponentHandler] Component execution error: {err}")
