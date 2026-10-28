from __future__ import annotations

import os
from typing import Any, Optional, Set
import discord

from config.settings import settings, IMAGES, SENTINEL_AVATAR, get_color, get_emoji, get_image, EMOJIS
from core.logging.logger import logger
from sdk.discord.builders import (
    ContainerBuilder,
    SectionBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
)

name = "on_guild_join"
description = "Official guild join welcome and onboarding handler ~ By MomentumOne"
category = "general"

# In-memory deduplication set to avoid re-announcing on gateway reconnects
_processed_guilds: Set[int] = set()


def handle_guild_remove(guild: Any) -> None:
    """Resets deduplication state when Sentinel departs a guild, ensuring future legitimate joins are welcomed."""
    gid = getattr(guild, "id", None) if not isinstance(guild, int) else guild
    if gid is not None:
        _processed_guilds.discard(int(gid))
        logger.debug(f"[GuildJoin] Cleared join deduplication for departed guild {gid}")


def _get_invite_url(client_id: Optional[str | int]) -> str:
    cid = client_id or settings.CLIENT_ID or "1563628961379123302"
    return f"https://discord.com/oauth2/authorize?client_id={cid}&permissions=8&scope=bot%20applications.commands"


def _get_support_url() -> str:
    return settings.SUPPORT_SERVER_URL or os.getenv("SUPPORT_SERVER_URL", "https://discord.gg/momentumone")


def _get_bot_icon(guild: discord.Guild) -> str:
    if settings.BOT_ICON_URL:
        return settings.BOT_ICON_URL
    thumb = IMAGES.get("thumbnail") or IMAGES.get("avatar")
    if thumb:
        return str(thumb)
    if hasattr(guild, "me") and guild.me and hasattr(guild.me, "display_avatar") and guild.me.display_avatar:
        return str(guild.me.display_avatar.url)
    return str(SENTINEL_AVATAR)


def _get_banner_url() -> str:
    if settings.BANNER_URL:
        return settings.BANNER_URL
    banner = IMAGES.get("banner") or IMAGES.get("sentinel_banner")
    if banner:
        return str(banner)
    return ""


def can_bot_send(channel: Any, bot_member: Any) -> bool:
    """Verifies that channel is text-capable and bot has permissions to view and send."""
    if not channel:
        return False
    ch_type = getattr(channel, "type", None)
    # Check text/news channel types
    allowed_types = (
        discord.ChannelType.text,
        discord.ChannelType.news,
        0,  # text
        5,  # news
        None,
    )
    if ch_type not in allowed_types:
        return False
    if not hasattr(channel, "send") or not callable(channel.send):
        return False

    if hasattr(channel, "permissions_for") and bot_member:
        perms = channel.permissions_for(bot_member)
        view_perm = getattr(perms, "view_channel", getattr(perms, "read_messages", False))
        send_perm = getattr(perms, "send_messages", False)
        if not (view_perm and send_perm):
            return False
    elif hasattr(bot_member, "guild_permissions"):
        if not (bot_member.guild_permissions.send_messages and bot_member.guild_permissions.view_channel):
            return False

    return True


def can_everyone_send(channel: Any, guild: discord.Guild) -> bool:
    """Checks whether the @everyone role has effective permission to send messages in the channel."""
    default_role = getattr(guild, "default_role", None)
    if not default_role and hasattr(guild, "roles"):
        for r in guild.roles:
            if getattr(r, "name", "") == "@everyone" or getattr(r, "id", None) == guild.id:
                default_role = r
                break

    if hasattr(channel, "permissions_for") and default_role:
        perms = channel.permissions_for(default_role)
        view_perm = getattr(perms, "view_channel", getattr(perms, "read_messages", False))
        send_perm = getattr(perms, "send_messages", False)
        return bool(view_perm and send_perm)

    overwrites = getattr(channel, "overwrites", {}) or getattr(channel, "_overwrites", {})
    if default_role and default_role in overwrites:
        ow = overwrites[default_role]
        if getattr(ow, "send_messages", None) is False or getattr(ow, "view_channel", None) is False:
            return False
        if getattr(ow, "send_messages", None) is True:
            return True

    return True


def select_announcement_channel(guild: discord.Guild) -> Optional[discord.TextChannel]:
    """
    Announcement Channel Selection Hierarchy:
      Priority 1: Community Announcement Channel / guild.system_channel
      Priority 2: Text channel where @everyone has effective permission to send (prefer #general, but don't hardcode)
      Priority 3: Any other suitable accessible text channel
    """
    bot_member = getattr(guild, "me", None)
    all_channels = getattr(guild, "text_channels", []) or [
        c for c in getattr(guild, "channels", []) if getattr(c, "type", None) in (discord.ChannelType.text, discord.ChannelType.news, 0, 5)
    ]

    # --- Priority 1: Community Announcement Channel / system_channel ---
    system_channel = getattr(guild, "system_channel", None)
    if system_channel and can_bot_send(system_channel, bot_member):
        return system_channel

    public_updates = getattr(guild, "public_updates_channel", None)
    if public_updates and can_bot_send(public_updates, bot_member):
        return public_updates

    # News / Announcement channels
    for ch in all_channels:
        if getattr(ch, "type", None) in (discord.ChannelType.news, 5):
            if can_bot_send(ch, bot_member):
                return ch

    # --- Priority 2: Text channel where @everyone has effective permission to send ---
    p2_candidates = []
    for ch in all_channels:
        if can_bot_send(ch, bot_member) and can_everyone_send(ch, guild):
            p2_candidates.append(ch)

    if p2_candidates:
        # Prefer #general or channels named with "general", but do not hardcode as requirement
        general_ch = next((c for c in p2_candidates if "general" in getattr(c, "name", "").lower()), None)
        if general_ch:
            return general_ch

        # Prefer chat/main/lounge/discussion
        chat_ch = next(
            (c for c in p2_candidates if any(k in getattr(c, "name", "").lower() for k in ("main", "chat", "lounge", "welcome"))),
            None,
        )
        if chat_ch:
            return chat_ch

        # Sort by channel position if available, else take first
        p2_candidates.sort(key=lambda c: getattr(c, "position", 0))
        return p2_candidates[0]

    # --- Priority 3: Any other suitable accessible text channel where Sentinel can send ---
    for ch in all_channels:
        if can_bot_send(ch, bot_member):
            return ch

    return None


async def find_inviter(guild: discord.Guild, bot_id: int) -> Optional[discord.User]:
    """Attempts to identify the administrator who invited Sentinel via audit logs."""
    try:
        bot_add_action = getattr(discord.AuditLogAction, "bot_add", None)
        if hasattr(guild, "audit_logs") and bot_add_action is not None:
            async for entry in guild.audit_logs(limit=5, action=bot_add_action):
                target_id = getattr(getattr(entry, "target", None), "id", None)
                is_target_bot = getattr(getattr(entry, "target", None), "bot", False)
                if (target_id == bot_id or is_target_bot) and getattr(entry, "user", None):
                    if not getattr(entry.user, "bot", False):
                        return entry.user
    except Exception as err:
        logger.debug(f"[GuildJoin] Could not inspect audit logs for inviter in {guild.id}: {err}")
    return None


def build_welcome_container(guild: discord.Guild) -> Any:
    """
    Builds the official Components V2 Container for server welcome:
      Order 1: Components V2 container (accent color: primary)
      Order 2: Main section with thumbnail accessory & text display starting strictly with -# Sentinel™
      Order 3: Exactly two action buttons outside section ("Invite Sentinel", "Support Server")
      Order 4: Banner image gallery containing Sentinel's configured banner asset
      Order 5: Product branding footer text: -# A MomentumOne product
    """
    bot_id = getattr(getattr(guild, "me", None), "id", None)
    invite_url = _get_invite_url(bot_id)
    support_url = _get_support_url()
    bot_icon_url = _get_bot_icon(guild)
    banner_url = _get_banner_url()

    builder = ContainerBuilder()
    builder.set_accent_color(get_color("primary", "#0844C5"))

    # Order 2: Main section with thumbnail accessory & text display
    welcome_copy = (
        f"-# {get_emoji('bot_icon')} @{settings.BOT_NAME}\n"
        f"Thank you for adding [{settings.BOT_NAME}]({settings.SUPPORT_SERVER_URL}) to **{guild.name}**!\n\n"
        f"{get_emoji('sub_point')} [{settings.BOT_NAME}]({settings.SUPPORT_SERVER_URL}) specializes in neglecting attacks on the server even from betrayals by whitelisted members, through safety patterns and algorithmic calculations"
        "enforcement, forensic administrative auditing, and automated threat containment.\n\n"
        f"- {get_emoji('antinuke')} **Anti-Nuke Systems:** High-frequency event monitoring guarding channels, roles, webhooks, and permissions.\n"
        f"- {get_emoji('log')} **Forensic Auditing:** Automated detection and attribution for administrative anomalies.\n"
        f"- {get_emoji('security')} **Immediate Protection:** Type `$setup` or `$antinuke setup` to initialize your server's defensive posture."
    )

    section = SectionBuilder()
    section.add_text_display(welcome_copy)
    if bot_icon_url:
        section.set_thumbnail_accessory(bot_icon_url)
    builder.add_section(section)

    # Order 3: Exactly two action buttons outside the section
    action_row = ActionRowBuilder()
    action_row.add_button(
        ButtonBuilder()
        .set_label("Invite")
        .set_style(ButtonStyle.Link)
        .set_url(invite_url)
    )
    action_row.add_button(
        ButtonBuilder()
        .set_label("Support")
        .set_style(ButtonStyle.Link)
        .set_url(support_url)
    )
    builder.add_action_row(action_row)

    # Order 4: Banner image gallery containing Sentinel's banner asset
    if banner_url:
        builder.add_media_gallery(banner_url)

    # Order 5: Product branding footer text
    builder.add_text_display("-# A MomentumOne product")

    return builder.build()


def build_inviter_dm_container(guild: discord.Guild, inviter: discord.User) -> Any:
    """Builds the personalized Components V2 direct message thanking the inviter."""
    bot_id = getattr(getattr(guild, "me", None), "id", None)
    invite_url = _get_invite_url(bot_id)
    support_url = _get_support_url()
    bot_icon_url = _get_bot_icon(guild)
    banner_url = _get_banner_url()

    builder = ContainerBuilder()
    builder.set_accent_color(get_color("primary", "#0844C5"))

    dm_copy = (
        f"-# {get_emoji('bot_icon')} @{settings.BOT_NAME}\n"
        f"Hello {getattr(inviter, 'name', 'Administrator')}, Sentinel is now actively connected and looking after your server!"
        f"\n\n"
        "**Recommended Next Steps:**\n"
        f"- {get_emoji('sub_point')} **Run Guided Security Audit:** Use `$setup` to verify bot role hierarchy, audit dangerous permissions and enable antinuke, it'll guide you through everything reliabily.\n"
        f"- {get_emoji('sub_point')} **Explore Command Center:** Use `$help` to view all moderation, anti-nuke, and utility controls."
    )

    section = SectionBuilder()
    section.add_text_display(dm_copy)
    if bot_icon_url:
        section.set_thumbnail_accessory(bot_icon_url)
    builder.add_section(section)

    action_row = ActionRowBuilder()
    action_row.add_button(
        ButtonBuilder()
        .set_label("Invite")
        .set_style(ButtonStyle.Link)
        .set_url(invite_url)
    )
    action_row.add_button(
        ButtonBuilder()
        .set_label("Support")
        .set_style(ButtonStyle.Link)
        .set_url(support_url)
    )
    builder.add_action_row(action_row)

    if banner_url:
        builder.add_media_gallery(banner_url)

    builder.add_text_display("-# A MomentumOne product")

    return builder.build()


async def execute(*args: Any, **kwargs: Any) -> None:
    """
    Guild Join event entry point. Dispatches welcome announcement to suitable channel
    and sends personalized thank you direct message to inviter when identified.
    """
    guild: Optional[discord.Guild] = None
    if len(args) == 1:
        guild = args[0]
    elif len(args) >= 2:
        if isinstance(args[1], discord.Guild):
            guild = args[1]
        elif isinstance(args[0], discord.Guild):
            guild = args[0]
        else:
            guild = args[1]
    if not guild:
        guild = kwargs.get("guild")

    if not guild or not hasattr(guild, "id"):
        return

    # Deduplicate processing
    if guild.id in _processed_guilds:
        logger.debug(f"[GuildJoin] Guild {guild.id} already processed. Skipping duplicate execution.")
        return

    _processed_guilds.add(guild.id)
    if len(_processed_guilds) > 10_000:
        _processed_guilds.clear()
        _processed_guilds.add(guild.id)

    logger.info(f"[GuildJoin] Joined guild: {guild.name} ({guild.id}) with {getattr(guild, 'member_count', 'unknown')} members.")

    # 1. Attempt to identify and thank inviter via Direct Message
    bot_id = getattr(getattr(guild, "me", None), "id", 0)
    try:
        inviter = await find_inviter(guild, bot_id)
        if inviter and not getattr(inviter, "bot", False):
            try:
                dm_view = build_inviter_dm_container(guild, inviter)
                await inviter.send(view=dm_view)
                logger.info(f"[GuildJoin] Sent personalized welcome DM to inviter {inviter.id} for guild {guild.id}.")
            except Exception as dm_err:
                logger.debug(f"[GuildJoin] Could not dispatch DM to inviter {inviter.id}: {dm_err}")
    except Exception as err:
        logger.debug(f"[GuildJoin] Non-fatal error during inviter resolution: {err}")

    # 2. Channel Resolution Hierarchy
    target_channel = select_announcement_channel(guild)
    if not target_channel:
        logger.warning(
            f"[GuildJoin] No suitable announcement channel found in guild '{guild.name}' ({guild.id}) "
            f"with effective permissions to send Components V2 messages."
        )
        return

    # 3. Dispatch Components V2 Announcement to Server
    try:
        welcome_view = build_welcome_container(guild)
        await target_channel.send(view=welcome_view)
        logger.info(f"[GuildJoin] Successfully published Components V2 welcome announcement in channel #{target_channel.name} ({target_channel.id}) for guild {guild.id}.")
    except Exception as send_err:
        logger.error(f"[GuildJoin] Failed to send welcome announcement to channel #{target_channel.name} in guild {guild.id}: {send_err}")
