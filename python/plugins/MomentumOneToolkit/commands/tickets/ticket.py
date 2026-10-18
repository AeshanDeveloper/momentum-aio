from typing import List, Any
import discord
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder
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
        return

    sub = args[0].lower() if args else "create"
    author = getattr(message, "user", None) if is_slash else getattr(message, "author", None)
    member = guild.get_member(author.id) or author

    if sub == "create":
        subject = " ".join(args[1:]).strip() if len(args) > 1 else "General Inquiry"
        res = await TicketManager.create_ticket(guild, member, subject=subject)
        if res.get("success"):
            created_msg = get_string(
                "commands.ticket.created",
                "✅ Created private support ticket #{ticket_id} in <#{channel_id}>.",
                ticket_id=res["ticket_id"],
                channel_id=res["channel_id"]
            )
            if is_slash and hasattr(message, "response"):
                await message.response.send_message(created_msg, ephemeral=True)
            elif hasattr(message, "reply"):
                await message.reply(created_msg)
        else:
            err = f"❌ Failed to create ticket: {res.get('error')}"
            if is_slash and hasattr(message, "response"):
                await message.response.send_message(err, ephemeral=True)
            elif hasattr(message, "reply"):
                await message.reply(err)

    elif sub == "close":
        reason = " ".join(args[1:]).strip() if len(args) > 1 else "Resolved by user"
        res = await TicketManager.close_ticket(guild, message.channel, actor_id=str(author.id), reason=reason)
        if not res.get("success"):
            err = res.get("error", "Failed to close ticket.")
            if is_slash and hasattr(message, "response"):
                await message.response.send_message(err, ephemeral=True)
            elif hasattr(message, "reply"):
                await message.reply(err)

    elif sub == "list":
        tickets = await TicketManager.list_tickets(guild_id=str(guild.id))
        lines = []
        for t in tickets[:10]:
            lines.append(f"• **#{t.get('ticket_id')}** [{t.get('status')}]: `{t.get('subject')}` (<@{t.get('creator_id')}>)")

        list_content = "\n".join(lines) if lines else "No active tickets found."
        embed = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#FF7B00"))
            .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Support Tickets for {guild.name}")
            .add_separator()
            .add_text_display(list_content)
            .build()
        )
        if is_slash and hasattr(message, "response"):
            await message.response.send_message(embed=embed)
        elif hasattr(message, "reply"):
            await message.reply(embed=embed)
