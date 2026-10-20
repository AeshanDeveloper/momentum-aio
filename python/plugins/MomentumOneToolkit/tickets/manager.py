import time
import discord
from typing import Dict, Any, List, Optional
from database.database import database
from core.logging.logger import logger
from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from sdk.discord.builders import ContainerBuilder, ActionRowBuilder, ButtonBuilder
from sdk.discord.response import send_response
from .types import TicketRecord, TicketGuildConfig, TicketStatus, TicketType

class TicketManager:
    CONFIG_COLLECTION = "ticket_configs"
    TICKETS_COLLECTION = "tickets"
    _config_cache: Dict[str, Dict[str, Any]] = {}
    _tickets_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    async def get_guild_config(cls, guild_id: str) -> Dict[str, Any]:
        gid = str(guild_id)
        if gid in cls._config_cache:
            return cls._config_cache[gid]

        col = database.collection(cls.CONFIG_COLLECTION)
        cfg = await col.find_one({"guild_id": gid})
        if not cfg:
            cfg = {
                "guild_id": gid,
                "staff_role_ids": [],
                "ticket_counter": 1000,
                "enabled": True,
                "category_id": None
            }
            await col.insert_one(cfg)

        cls._config_cache[gid] = cfg
        return cfg

    @classmethod
    async def update_guild_config(cls, guild_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        gid = str(guild_id)
        current = await cls.get_guild_config(gid)
        current.update(updates)
        col = database.collection(cls.CONFIG_COLLECTION)
        await col.update_one({"guild_id": gid}, {"$set": updates}, upsert=True)
        cls._config_cache[gid] = current
        return current

    @classmethod
    async def create_ticket(
        cls,
        guild: discord.Guild,
        creator: discord.Member,
        subject: str = "General Support",
        ticket_type: str = TicketType.SUPPORT
    ) -> Dict[str, Any]:
        cfg = await cls.get_guild_config(str(guild.id))
        counter = cfg.get("ticket_counter", 1000) + 1
        await cls.update_guild_config(str(guild.id), {"ticket_counter": counter})

        channel_name = f"ticket-{counter}"
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            creator: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        for role_id in cfg.get("staff_role_ids", []):
            role = guild.get_role(int(role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = None
        if cfg.get("category_id"):
            category = guild.get_channel(int(cfg["category_id"]))

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                category=category,
                topic=f"Support Ticket #{counter} | Created by {creator.name} ({creator.id})"
            )
        except Exception as err:
            logger.error(f"[TicketManager] Failed to create ticket channel: {err}")
            return {"success": False, "error": str(err)}

        now = time.time()
        record = {
            "ticket_id": counter,
            "guild_id": str(guild.id),
            "channel_id": str(channel.id),
            "creator_id": str(creator.id),
            "creator_name": creator.name,
            "ticket_type": ticket_type,
            "status": TicketStatus.OPEN,
            "subject": subject,
            "created_at": now,
            "messages": [],
        }

        cls._tickets_cache[str(channel.id)] = record
        col = database.collection(cls.TICKETS_COLLECTION)
        await col.insert_one(record)

        # Send welcome panel inside ticket channel
        welcome_view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#FF7B00"))
            .add_text_display(f"### {EMOJIS.get('ticket', '🎫')} Support Ticket #{counter}")
            .add_text_display(
                f"Welcome <@{creator.id}>! Staff has been notified and will assist you shortly.\n\n"
                f"• **Subject:** `{subject}`\n"
                f"• **Type:** `{ticket_type}`\n"
                f"• **Created:** <t:{int(now)}:R>"
            )
            .add_action_row(
                lambda row: row.add_button(
                    lambda btn: btn.set_label("Close Ticket")
                    .set_custom_id(f"ticket_close_{channel.id}")
                    .set_style("danger")
                    .set_emoji("🔒")
                )
            )
            .build()
        )

        await send_response(channel, welcome_view)
        return {"success": True, "ticket_id": counter, "channel_id": str(channel.id)}

    @classmethod
    async def close_ticket(
        cls,
        guild: discord.Guild,
        channel: discord.TextChannel,
        actor_id: str,
        reason: str = "Ticket resolved"
    ) -> Dict[str, Any]:
        cid = str(channel.id)
        col = database.collection(cls.TICKETS_COLLECTION)
        record = await col.find_one({"channel_id": cid}) or cls._tickets_cache.get(cid)

        if not record:
            return {"success": False, "error": get_string("commands.ticket.ticket_not_found", "Ticket not found.")}

        if record.get("status") == TicketStatus.CLOSED:
            return {"success": False, "error": get_string("commands.ticket.already_closed", "Ticket already closed.")}

        # Collect transcript
        transcript_lines = []
        try:
            async for msg in channel.history(limit=200, oldest_first=True):
                author = f"{msg.author.name}#{msg.author.discriminator}" if hasattr(msg.author, "discriminator") else msg.author.name
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                transcript_lines.append(f"[{ts}] {author}: {msg.clean_content}")
        except Exception:
            pass

        transcript_text = "\n".join(transcript_lines)
        now = time.time()
        updates = {
            "status": TicketStatus.CLOSED,
            "closed_at": now,
            "closed_by": str(actor_id),
            "close_reason": reason,
            "transcript": transcript_text
        }
        await col.update_one({"channel_id": cid}, {"$set": updates})
        if cid in cls._tickets_cache:
            cls._tickets_cache[cid].update(updates)

        close_view = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warn", "#F59E0B"))
            .add_text_display(f"### 🔒 Ticket #{record.get('ticket_id')} Closed")
            .add_text_display(
                f"This ticket was closed by <@{actor_id}>.\n"
                f"**Reason:** {reason}\n\n"
                f"Channel will be deleted in 10 seconds."
            )
            .build()
        )
        await send_response(channel, close_view)

        async def _delete_after():
            import asyncio
            await asyncio.sleep(10)
            try:
                await channel.delete(reason=f"Closed ticket #{record.get('ticket_id')}")
            except Exception:
                pass

        import asyncio
        asyncio.create_task(_delete_after())
        return {"success": True, "ticket_id": record.get("ticket_id")}

    @classmethod
    async def list_tickets(cls, guild_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        flt: Dict[str, Any] = {}
        if guild_id:
            flt["guild_id"] = str(guild_id)
        if status:
            flt["status"] = status
        col = database.collection(cls.TICKETS_COLLECTION)
        return await col.find(flt, sort={"created_at": -1}, limit=100)
