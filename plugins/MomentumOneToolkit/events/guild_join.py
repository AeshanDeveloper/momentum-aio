from typing import Any, Optional, Set
import discord

from sdk.discord.builders import (
    ContainerBuilder,
    SectionBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
)
from sdk.event import Event
from core.logging.logger import logger
from core.logging.sentinel_event_logger import SentinelEventLogger

name = "on_guild_join"
description = "Official Sentinel™ Guild Join Announcement Handler"

_processed_guilds: Set[int] = set()


def can_bot_send(channel: Any, me: Any) -> bool:
    if not channel or not isinstance(channel, (discord.TextChannel, getattr(discord, "VoiceChannel", type(None)))):
        return False
    if not me:
        return True
    
    # Check channel overwrites first
    overwrites = getattr(channel, "overwrites", {})
    if me in overwrites:
        ow = overwrites[me]
        if getattr(ow, "send_messages", None) is False or getattr(ow, "view_channel", None) is False:
            return False
        if getattr(ow, "send_messages", None) is True:
            return True

    # Check member permissions
    perms = channel.permissions_for(me) if hasattr(channel, "permissions_for") else getattr(me, "guild_permissions", None)
    if perms:
        if getattr(perms, "administrator", False):
            return True
        return getattr(perms, "send_messages", False) and getattr(perms, "view_channel", False)
    return True


def can_everyone_send(channel: Any, guild: discord.Guild) -> bool:
    if not channel or not guild:
        return False
    everyone_role = getattr(guild, "default_role", None)
    if everyone_role and hasattr(channel, "overwrites"):
        ow = channel.overwrites.get(everyone_role)
        if ow and getattr(ow, "send_messages", None) is False:
            return False
    return True


def select_announcement_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """
    Selects announcement channel according to priority:
      1. system_channel (when bot has permissions)
      2. channel where @everyone can send (preferring #general)
      3. fallback to first text channel bot can send to
    """
    if not guild:
        return None

    me = getattr(guild, "me", None)

    # Priority 1: system_channel
    sys_ch = getattr(guild, "system_channel", None)
    if sys_ch and can_bot_send(sys_ch, me):
        return sys_ch

    text_channels = getattr(guild, "text_channels", []) or [c for c in getattr(guild, "channels", []) if isinstance(c, discord.TextChannel)]

    # Priority 2: channels where @everyone can send
    everyone_accessible = [ch for ch in text_channels if can_bot_send(ch, me) and can_everyone_send(ch, guild)]
    if everyone_accessible:
        for ch in everyone_accessible:
            if "general" in ch.name.lower() or "chat" in ch.name.lower() or "main" in ch.name.lower():
                return ch
        return everyone_accessible[0]

    # Priority 3: fallback to first text channel bot can send to
    for ch in text_channels:
        if can_bot_send(ch, me):
            return ch

    return None


async def find_inviter(guild: discord.Guild, bot_member: Any) -> Optional[Any]:
    """Finds user who invited the bot via audit logs."""
    if not guild:
        return None
    try:
        # Check mock _audit_logs or async audit_logs
        if hasattr(guild, "_audit_logs") and guild._audit_logs:
            for entry in guild._audit_logs:
                if entry.action == discord.AuditLogAction.bot_add:
                    return entry.user
        if hasattr(guild, "audit_logs"):
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                if not bot_member or getattr(entry, "target", None) == bot_member:
                    return entry.user
    except Exception:
        pass
    return None


def build_welcome_container(guild: discord.Guild) -> Any:
    builder = ContainerBuilder()
    builder.set_accent_color(0x0844C5)

    sec = SectionBuilder()
    sec.add_text_display(f"-# Sentinel™\n### Security Initialized in {guild.name}\nSentinel autonomous server protection is online.")
    sec.set_thumbnail_accessory("https://cdn.discordapp.com/avatars/1563628961379123302/d4a0d1341e7059c11b863f2a3a74dd75.png?size=512")
    builder.add_section(sec)

    row = ActionRowBuilder()
    row.add_button(ButtonBuilder().set_label("Invite Sentinel").set_url("https://discord.com/invite"))
    row.add_button(ButtonBuilder().set_label("Support Server").set_url("https://discord.gg/momentumone"))
    builder.add_action_row(row)

    builder.add_media_gallery("https://example.com/banner.png")
    builder.add_text_display("-# A MomentumOne product")

    return builder.build()


def build_inviter_dm_container(guild: discord.Guild, inviter: Any) -> Any:
    builder = ContainerBuilder()
    builder.set_accent_color(0x0844C5)
    sec = SectionBuilder()
    sec.add_text_display(f"### Thank you for adding Sentinel™ to {guild.name}\nYour server is now fortified with zero-tolerance anti-nuke defense.")
    sec.set_thumbnail_accessory("https://cdn.discordapp.com/avatars/1563628961379123302/d4a0d1341e7059c11b863f2a3a74dd75.png?size=512")
    builder.add_section(sec)
    return builder.build()


def handle_guild_remove(guild: discord.Guild) -> None:
    gid = getattr(guild, "id", None)
    if gid:
        _processed_guilds.discard(gid)


async def execute(ctx_or_guild: Any, guild: Optional[discord.Guild] = None) -> None:
    actual_guild = guild if guild is not None else (ctx_or_guild if isinstance(ctx_or_guild, discord.Guild) else getattr(ctx_or_guild, "guild", None))
    if not actual_guild:
        return

    gid = actual_guild.id
    if gid in _processed_guilds:
        return
    _processed_guilds.add(gid)

    # 1. Discover inviter & send DM
    me = getattr(actual_guild, "me", None)
    inviter = await find_inviter(actual_guild, me)
    if inviter and hasattr(inviter, "send"):
        try:
            dm_box = build_inviter_dm_container(actual_guild, inviter)
            await inviter.send(view=dm_box)
        except Exception:
            pass

    # 2. Server Announcement Channel
    channel = select_announcement_channel(actual_guild)
    if channel and hasattr(channel, "send"):
        try:
            welcome_box = build_welcome_container(actual_guild)
            await channel.send(view=welcome_box)
        except Exception as err:
            logger.error(f"[GuildJoin] Could not send welcome container in #{getattr(channel, 'name', '')}: {err}")


class event(Event):
    def __init__(self, bot: Any = None, **kwargs):
        super().__init__(name=name, execute=execute, description=description)
        self.bot = bot
