from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
from sdk.discord.response import send_response
from plugins.MomentumOneToolkit.tickets.manager import TicketManager
from shared.types.command_record import CommandType

name = "ticket"
aliases = ["support", "tickets"]
description = "Create, resolve, or inspect private support tickets."
category = "Tickets"
usage = "ticket <create|close|list> [subject/reason]"
cooldown = 5.0
guild_only = True

async def execute(ctx: Any, command_type: str, message: Any, args: List[str]):
    is_slash = (command_type == CommandType.SLASH)
    guild = getattr(message, "guild", None)
    if not guild:
        err = get_string("permissions.guild_only", "❌ This command can only be used inside a Discord server.")
        return await send_response(message, err, ephemeral=True)

    sub = args[0].lower() if args else "create"
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    member = guild.get_member(author.id) or author

    if sub == "create":
        subject = " ".join(args[1:]).strip() if len(args) > 1 else "General Inquiry"
        res = await TicketManager.create_ticket(guild, member, subject=subject)
        if res.get("success"):
            box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("success", "#10B981"))
                .add_text_display(f"### 🎫 Support Ticket Created")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(
                    f"Your private support channel has been provisioned.\n\n"
                    f"• **Ticket ID:** `#{res['ticket_id']}`\n"
                    f"• **Channel:** <#{res['channel_id']}>\n"
                    f"• **Subject:** `{subject}`\n\n"
                    f"-# Support staff have been alerted to your inquiry."
                )
                .build()
            )
            return await send_response(message, box, ephemeral=True)
        else:
            err_box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("error", "#EF4444"))
                .add_text_display(f"### ❌ Ticket Creation Failed")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(f"Failed to create support ticket: `{res.get('error')}`")
                .build()
            )
            return await send_response(message, err_box, ephemeral=True)

    elif sub == "close":
        reason = " ".join(args[1:]).strip() if len(args) > 1 else "Resolved by user"
        res = await TicketManager.close_ticket(guild, message.channel, actor_id=str(author.id), reason=reason)
        if not res.get("success"):
            err_box = (
                ContainerBuilder()
                .set_accent_color(COLORS.get("error", "#EF4444"))
                .add_text_display(f"### ❌ Ticket Close Failed")
                .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
                .add_text_display(res.get("error", "Failed to close ticket."))
                .build()
            )
            return await send_response(message, err_box, ephemeral=True)

    elif sub == "list":
        tickets = await TicketManager.list_tickets(guild_id=str(guild.id))
        lines = []
        for t in tickets[:10]:
            lines.append(f"• **#{t.get('ticket_id')}** [{t.get('status')}]: `{t.get('subject')}` (<@{t.get('creator_id')}>)")

        list_content = "\n".join(lines) if lines else "No active tickets found for this server."
        view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#FF7B00"))
            .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Support Tickets for {guild.name}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(list_content)
            .set_footer(f"Showing up to 10 active tickets")
            .build()
        )
        return await send_response(message, view)
