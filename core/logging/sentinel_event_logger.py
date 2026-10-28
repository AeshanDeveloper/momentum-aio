import time
import asyncio
from typing import Optional, Dict, Any, List, Union, Tuple
import discord

from config.settings import settings, COLORS, EMOJIS
from core.logging.logger import logger
from core.logging.webhook_logger import (
    UnifiedWebhookLogger,
    LogCategory,
    LogSeverity,
    redact_webhook_credentials,
)
from core.security.antinuke import AntiNukeConstants, AntiNukeManager
from database.database import database
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize,
    ButtonStyle,
)

class SentinelEventLogger:
    """
    Unified Event Processing, Forensic Audit Logging, Ghost Ping Detection,
    and Server Announcement Engine for Sentinel™.
    Encapsulates all domain logic so event listeners remain lean dispatchers.
    """

    # In-memory LRU cache for recent messages to detect ghost pings
    # message_id -> {"content": str, "author": discord.User/Member, "mentions": list, "channel_id": int, "guild_id": int, "timestamp": float}
    _GHOST_PING_CACHE: Dict[int, Dict[str, Any]] = {}
    _ANNOUNCED_GUILDS: set = set()
    _CACHE_MAX_AGE: float = 600.0  # 10 minutes

    # --------------------------------------------------------------------------
    # Ghost Ping & Message Caching
    # --------------------------------------------------------------------------
    @classmethod
    def _prune_cache(cls) -> None:
        now = time.time()
        expired = [mid for mid, data in cls._GHOST_PING_CACHE.items() if now - data.get("timestamp", 0) > cls._CACHE_MAX_AGE]
        for mid in expired:
            cls._GHOST_PING_CACHE.pop(mid, None)

    @classmethod
    async def handle_message_create(cls, message: discord.Message) -> None:
        """Caches messages with mentions to monitor for subsequent ghost pings."""
        if not message.guild or not message.author or message.author.bot:
            return

        cls._prune_cache()

        has_user_mentions = bool(getattr(message, "mentions", []))
        has_role_mentions = bool(getattr(message, "role_mentions", []))

        if has_user_mentions or has_role_mentions:
            cls._GHOST_PING_CACHE[message.id] = {
                "content": message.content or "",
                "author": message.author,
                "author_id": message.author.id,
                "mentions": list(getattr(message, "mentions", [])),
                "role_mentions": list(getattr(message, "role_mentions", [])),
                "channel_id": message.channel.id,
                "guild_id": message.guild.id,
                "timestamp": time.time(),
            }

    @classmethod
    async def handle_message_delete(cls, message: Union[discord.Message, Any]) -> None:
        """
        Dispatches message deletion logs and alerts if a ghost ping is detected.
        """
        guild = getattr(message, "guild", None)
        if not guild:
            return

        msg_id = getattr(message, "id", None)
        cached = cls._GHOST_PING_CACHE.pop(msg_id, None) if msg_id else None

        channel = getattr(message, "channel", None)
        author = getattr(message, "author", None)
        content = getattr(message, "content", "") or ""

        if cached:
            author = author or cached.get("author")
            content = content or cached.get("content", "")
            mentions = cached.get("mentions", [])
            roles = cached.get("role_mentions", [])
            elapsed = round(time.time() - cached.get("timestamp", time.time()), 1)

            # High Severity: Ghost Ping Detected!
            mention_strings = [u.mention for u in mentions] + [r.mention for r in roles]
            victims_str = ", ".join(mention_strings) if mention_strings else "*None*"

            fields = [
                {"name": "Sender", "value": f"{author.mention} (`{author}` • ID: `{author.id}`)" if author else "*Unknown*", "inline": True},
                {"name": "Channel", "value": f"<#{channel.id}>" if channel else "*Unknown*", "inline": True},
                {"name": "Time to Delete", "value": f"`{elapsed}s` after posting", "inline": True},
                {"name": "Pinged Targets", "value": victims_str, "inline": False},
                {"name": "Deleted Content", "value": f"```{content[:1000] or '[Empty Content]'}```", "inline": False},
            ]

            await UnifiedWebhookLogger.dispatch_log(
                guild=guild,
                category=LogCategory.SECURITY,
                title="Ghost Ping Detected",
                description=f"A message containing mentions was deleted by or on behalf of **{author}**.",
                actor=author,
                target=author,
                reason="Ghost Ping Deletion",
                fields=fields,
                severity=LogSeverity.HIGH,
            )
            return

        # Normal Message Deletion
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.message_delete, target_id=author.id if author else None
        )

        fields = [
            {"name": "Author", "value": f"{author.mention} (`{author}` • ID: `{author.id}`)" if author else "*Unknown*", "inline": True},
            {"name": "Channel", "value": f"<#{channel.id}>" if channel else "*Unknown*", "inline": True},
        ]
        if content:
            fields.append({"name": "Content", "value": f"```{content[:1000]}```", "inline": False})

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Message Deleted",
            description=f"A message from **{author or 'an unknown user'}** was deleted in <#{getattr(channel, 'id', '')}>.",
            actor=actor or author,
            target=author,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )

    @classmethod
    async def handle_message_edit(cls, before: discord.Message, after: discord.Message) -> None:
        """Dispatches message modification logs if content was changed."""
        guild = getattr(after, "guild", None)
        if not guild or not after.author or after.author.bot:
            return

        if (before.content or "") == (after.content or ""):
            return

        fields = [
            {"name": "Author", "value": f"{after.author.mention} (`{after.author}` • ID: `{after.author.id}`)", "inline": True},
            {"name": "Channel", "value": f"<#{after.channel.id}>", "inline": True},
            {"name": "Before", "value": f"```{before.content[:500] or '[Empty]'}```", "inline": False},
            {"name": "After", "value": f"```{after.content[:500] or '[Empty]'}```", "inline": False},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Message Edited",
            description=f"A message was edited in <#{after.channel.id}> by **{after.author}**.",
            actor=after.author,
            target=after.author,
            fields=fields,
            severity=LogSeverity.INFO,
        )

    @classmethod
    async def handle_bulk_message_delete(cls, messages: List[discord.Message], channel: discord.abc.GuildChannel) -> None:
        """Dispatches bulk message purge audit log."""
        guild = getattr(channel, "guild", None)
        if not guild:
            return

        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.message_bulk_delete, target_id=channel.id
        )

        fields = [
            {"name": "Channel", "value": f"<#{channel.id}> (`#{channel.name}`)", "inline": True},
            {"name": "Messages Purged", "value": f"`{len(messages)}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Bulk Messages Purged",
            description=f"`{len(messages)}` messages were bulk deleted in <#{channel.id}>.",
            actor=actor,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )

    # --------------------------------------------------------------------------
    # Member Events
    # --------------------------------------------------------------------------
    @classmethod
    async def handle_member_join(cls, member: discord.Member) -> None:
        """Dispatches member join log or bot addition security log."""
        guild = member.guild
        if not guild:
            return

        if member.bot:
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, discord.AuditLogAction.bot_add, target_id=member.id
            )
            fields = [
                {"name": "Bot Added", "value": f"{member.mention} (`{member}` • ID: `{member.id}`)", "inline": True},
                {"name": "Invited By", "value": f"{actor.mention} (`{actor}`)" if actor else "*Unknown / Direct*", "inline": True},
            ]
            await UnifiedWebhookLogger.dispatch_log(
                guild=guild,
                category=LogCategory.SECURITY,
                title="Bot Account Added",
                description=f"A new bot **{member}** was added to the server.",
                actor=actor,
                target=member,
                reason=reason,
                fields=fields,
                severity=LogSeverity.MEDIUM,
            )
            return

        fields = [
            {"name": "Member", "value": f"{member.mention} (`{member}` • ID: `{member.id}`)", "inline": True},
            {"name": "Total Members", "value": f"`{getattr(guild, 'member_count', len(getattr(guild, 'members', [])))}`", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MEMBERS,
            title="Member Joined",
            description=f"**{member}** joined the server.",
            target=member,
            fields=fields,
            severity=LogSeverity.INFO,
        )

    @classmethod
    async def handle_member_remove(cls, member: Union[discord.Member, discord.User]) -> None:
        """Dispatches member kick or departure log."""
        guild = getattr(member, "guild", None)
        if not guild:
            return

        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.member_kick, target_id=member.id
        )

        is_kick = bool(actor is not None)
        title = "Member Kicked" if is_kick else "Member Left"
        severity = LogSeverity.MEDIUM if is_kick else LogSeverity.INFO

        fields = [
            {"name": "Member", "value": f"{member.mention} (`{member}` • ID: `{member.id}`)", "inline": True},
        ]
        if is_kick:
            fields.append({"name": "Kicked By", "value": f"{actor.mention} (`{actor}`)", "inline": True})
            if reason:
                fields.append({"name": "Reason", "value": f"`{reason}`", "inline": False})

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION if is_kick else LogCategory.MEMBERS,
            title=title,
            description=f"**{member}** was kicked from the server." if is_kick else f"**{member}** left the server.",
            actor=actor,
            target=member,
            reason=reason,
            fields=fields,
            severity=severity,
        )

    @classmethod
    async def handle_member_ban(cls, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
        """Dispatches member ban log."""
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.member_ban_add, target_id=user.id
        )

        fields = [
            {"name": "Banned User", "value": f"{user.mention} (`{user}` • ID: `{user.id}`)", "inline": True},
            {"name": "Moderator", "value": f"{actor.mention} (`{actor}`)" if actor else "*Unknown*", "inline": True},
        ]
        if reason:
            fields.append({"name": "Reason", "value": f"`{reason}`", "inline": False})

        await UnifiedWebhookLogger.dispatch_log(
            guild,
            LogCategory.MODERATION,
            title="Member Banned",
            description=f"**{user}** was banned from the server.",
            actor=actor,
            target=user,
            reason=reason,
            fields=fields,
            severity=LogSeverity.HIGH,
        )

    @classmethod
    async def handle_member_unban(cls, guild: discord.Guild, user: Union[discord.User, discord.Member]) -> None:
        """Dispatches member unban log."""
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.member_ban_remove, target_id=user.id
        )

        fields = [
            {"name": "Unbanned User", "value": f"{user.mention} (`{user}` • ID: `{user.id}`)", "inline": True},
            {"name": "Moderator", "value": f"{actor.mention} (`{actor}`)" if actor else "*Unknown*", "inline": True},
        ]

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.MODERATION,
            title="Member Unbanned",
            description=f"**{user}** was unbanned from the server.",
            actor=actor,
            target=user,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )

    @classmethod
    async def handle_member_update(cls, before: discord.Member, after: discord.Member) -> None:
        """Dispatches timeout or role assignment updates."""
        guild = after.guild
        if not guild:
            return

        # 1. Timeout Check
        b_timeout = getattr(before, "timed_out_until", None)
        a_timeout = getattr(after, "timed_out_until", None)
        if b_timeout != a_timeout:
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, discord.AuditLogAction.member_update, target_id=after.id
            )
            is_timeout = bool(a_timeout is not None)
            fields = [
                {"name": "Member", "value": f"{after.mention} (`{after}` • ID: `{after.id}`)", "inline": True},
            ]
            if is_timeout:
                fields.append({"name": "Until", "value": f"<t:{int(a_timeout.timestamp())}:F>", "inline": True})
            if reason:
                fields.append({"name": "Reason", "value": f"`{reason}`", "inline": False})

            await UnifiedWebhookLogger.dispatch_log(
                guild=guild,
                category=LogCategory.MODERATION,
                title="Member Timed Out" if is_timeout else "Member Timeout Removed",
                description=f"**{after}** was placed in timeout." if is_timeout else f"**{after}** timeout was removed.",
                actor=actor,
                target=after,
                reason=reason,
                fields=fields,
                severity=LogSeverity.MEDIUM,
            )
            return

        # 2. Roles Update Check
        b_roles = set(before.roles)
        a_roles = set(after.roles)
        if b_roles != a_roles:
            added = a_roles - b_roles
            removed = b_roles - a_roles
            actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
                guild, discord.AuditLogAction.member_role_update, target_id=after.id
            )

            fields = [
                {"name": "Member", "value": f"{after.mention} (`{after}` • ID: `{after.id}`)", "inline": True},
            ]
            if added:
                fields.append({"name": "Roles Added", "value": ", ".join(r.mention for r in added), "inline": False})
            if removed:
                fields.append({"name": "Roles Removed", "value": ", ".join(r.mention for r in removed), "inline": False})

            await UnifiedWebhookLogger.dispatch_log(
                guild=guild,
                category=LogCategory.ROLES,
                title="Member Roles Updated",
                description=f"Roles for **{after}** were modified.",
                actor=actor,
                target=after,
                reason=reason,
                fields=fields,
                severity=LogSeverity.LOW,
            )

    # --------------------------------------------------------------------------
    # Channel Events
    # --------------------------------------------------------------------------
    @classmethod
    async def handle_channel_create(cls, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        if not guild:
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_create, target_id=channel.id
        )
        fields = [
            {"name": "Channel", "value": f"`#{channel.name}` (<#{channel.id}>)", "inline": True},
            {"name": "Category", "value": getattr(channel.category, "name", "None"), "inline": True},
        ]
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.CHANNELS,
            title="Channel Created",
            description=f"Channel **#{channel.name}** was created.",
            actor=actor,
            target=channel,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )

    @classmethod
    async def handle_channel_delete(cls, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        if not guild:
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_delete, target_id=channel.id
        )
        fields = [
            {"name": "Channel Name", "value": f"`#{channel.name}` (ID: `{channel.id}`)", "inline": True},
        ]
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.CHANNELS,
            title="Channel Deleted",
            description=f"Channel **#{channel.name}** was deleted.",
            actor=actor,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )

    @classmethod
    async def handle_channel_update(cls, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> None:
        guild = getattr(after, "guild", None)
        if not guild or before.name == after.name and getattr(before, "overwrites", None) == getattr(after, "overwrites", None):
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.channel_update, target_id=after.id
        )
        fields = [
            {"name": "Channel", "value": f"<#{after.id}> (`#{after.name}`)", "inline": True},
        ]
        if before.name != after.name:
            fields.append({"name": "Name Changed", "value": f"`#{before.name}` ➔ `#{after.name}`", "inline": False})

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.CHANNELS,
            title="Channel Updated",
            description=f"Channel **#{after.name}** was modified.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=LogSeverity.LOW,
        )

    # --------------------------------------------------------------------------
    # Role Events
    # --------------------------------------------------------------------------
    @classmethod
    async def handle_role_create(cls, role: discord.Role) -> None:
        guild = role.guild
        if not guild:
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.role_create, target_id=role.id
        )
        fields = [
            {"name": "Role", "value": f"{role.mention} (`{role.name}` • ID: `{role.id}`)", "inline": True},
        ]
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Created",
            description=f"Role **{role.name}** was created.",
            actor=actor,
            target=role,
            reason=reason,
            fields=fields,
            severity=LogSeverity.INFO,
        )

    @classmethod
    async def handle_role_delete(cls, role: discord.Role) -> None:
        guild = role.guild
        if not guild:
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.role_delete, target_id=role.id
        )
        fields = [
            {"name": "Role Name", "value": f"`{role.name}` (ID: `{role.id}`)", "inline": True},
        ]
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Deleted",
            description=f"Role **{role.name}** was deleted.",
            actor=actor,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )

    @classmethod
    async def handle_role_update(cls, before: discord.Role, after: discord.Role) -> None:
        guild = after.guild
        if not guild or before.name == after.name and before.permissions.value == after.permissions.value:
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.role_update, target_id=after.id
        )
        fields = [
            {"name": "Role", "value": f"{after.mention} (`{after.name}` • ID: `{after.id}`)", "inline": True},
        ]
        if before.name != after.name:
            fields.append({"name": "Name Changed", "value": f"`{before.name}` ➔ `{after.name}`", "inline": False})
        if before.permissions.value != after.permissions.value:
            fields.append({"name": "Permissions", "value": f"Updated permissions bits (`{after.permissions.value}`)", "inline": False})

        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.ROLES,
            title="Role Updated",
            description=f"Role **{after.name}** was modified.",
            actor=actor,
            target=after,
            reason=reason,
            fields=fields,
            severity=LogSeverity.MEDIUM,
        )

    # --------------------------------------------------------------------------
    # Server & Webhook Events
    # --------------------------------------------------------------------------
    @classmethod
    async def handle_guild_update(cls, before: discord.Guild, after: discord.Guild) -> None:
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            after, discord.AuditLogAction.guild_update
        )
        fields = []
        if before.name != after.name:
            fields.append({"name": "Server Name", "value": f"`{before.name}` ➔ `{after.name}`", "inline": False})

        await UnifiedWebhookLogger.dispatch_log(
            guild=after,
            category=LogCategory.SERVER,
            title="Server Updated",
            description=f"Server settings for **{after.name}** were updated.",
            actor=actor,
            reason=reason,
            fields=fields or None,
            severity=LogSeverity.MEDIUM,
        )

    @classmethod
    async def handle_webhooks_update(cls, channel: discord.abc.GuildChannel) -> None:
        guild = getattr(channel, "guild", None)
        if not guild:
            return
        actor, reason = await UnifiedWebhookLogger.fetch_audit_attribution(
            guild, discord.AuditLogAction.webhook_create, target_id=channel.id
        )
        fields = [
            {"name": "Channel", "value": f"<#{channel.id}> (`#{channel.name}`)", "inline": True},
        ]
        await UnifiedWebhookLogger.dispatch_log(
            guild=guild,
            category=LogCategory.SERVER,
            title="Webhooks Modified",
            description=f"Webhooks were updated in <#{channel.id}>.",
            actor=actor,
            reason=reason,
            fields=fields,
            severity=LogSeverity.HIGH,
        )

    # --------------------------------------------------------------------------
    # Server Join Announcement
    # --------------------------------------------------------------------------
    @classmethod
    async def handle_guild_join(cls, guild: discord.Guild) -> bool:
        """
        Sends Sentinel's introductory container when Sentinel joins a new server.
        Follows strict channel selection hierarchy:
          1. Community announcement channel (public_updates_channel or news)
          2. Moderation or logging channel
          3. First suitable public text channel
          4. Any eligible text-based channel
        Guards against duplicate announcements on bot restarts.
        """
        if not guild:
            return False

        gid = str(guild.id)

        # 1. Deduplication guard against repeated bot restarts
        if gid in cls._ANNOUNCED_GUILDS:
            return False

        try:
            col = database.collection("sentinel_join_announcements")
            existing = await col.find_one({"guild_id": gid})
            if existing:
                cls._ANNOUNCED_GUILDS.add(gid)
                return False
        except Exception:
            pass

        # 2. Select Destination Channel with strict priority
        me = getattr(guild, "me", None)
        selected_channel: Optional[discord.TextChannel] = None

        def can_send(ch: Any) -> bool:
            if not ch or not isinstance(ch, (discord.TextChannel, getattr(discord, "VoiceChannel", type(None)))):
                return False
            if me and hasattr(guild, "me"):
                perms = ch.permissions_for(me) if hasattr(ch, "permissions_for") else getattr(me, "guild_permissions", None)
                if perms:
                    return getattr(perms, "send_messages", False) and getattr(perms, "view_channel", False)
            return True

        # Priority 1: Community announcement / Updates channel
        pub_updates = getattr(guild, "public_updates_channel", None)
        if can_send(pub_updates):
            selected_channel = pub_updates
        else:
            for ch in getattr(guild, "channels", []):
                if getattr(ch, "type", None) in (discord.ChannelType.news, getattr(discord.ChannelType, "announcement", -1)):
                    if can_send(ch):
                        selected_channel = ch
                        break

        # Priority 2: Moderation or configured security logging channel
        if not selected_channel:
            an_cfg = AntiNukeManager.get_guild_config(gid)
            log_ch_id = an_cfg.get("warning_channel_id") or an_cfg.get("log_channel_id")
            if log_ch_id:
                ch = guild.get_channel(int(log_ch_id))
                if can_send(ch):
                    selected_channel = ch

        # Priority 3: First suitable public text channel
        if not selected_channel:
            for ch in getattr(guild, "text_channels", getattr(guild, "channels", [])):
                if isinstance(ch, discord.TextChannel) and can_send(ch):
                    # Prefer general or first channel
                    if "general" in ch.name.lower() or "chat" in ch.name.lower() or "main" in ch.name.lower():
                        selected_channel = ch
                        break
                    if not selected_channel:
                        selected_channel = ch

        # Priority 4: Any other eligible channel
        if not selected_channel:
            for ch in getattr(guild, "channels", []):
                if can_send(ch):
                    selected_channel = ch
                    break

        if not selected_channel:
            logger.warning(f"[SentinelJoin] No accessible text channel found to announce in guild {guild.name} ({guild.id})")
            return False

        # 3. Build Canonical Sentinel™ Introductory Container
        desc = (
            f"**Sentinel™ Autonomous Server Defense has been initialized.**\n\n"
            f"Sentinel provides enterprise-grade protection for **{guild.name}**, safeguarding against:\n"
            f"• Mass channel & role destructions (Anti-Nuke)\n"
            f"• Unauthorized administrator privilege escalations\n"
            f"• Malicious webhook creation & token hijacking\n"
            f"• Ghost pings & covert message removals\n"
            f"• Rogue bot incursions & automated raid vectors\n\n"
            f"**Security Status:** `Setup Required`\n"
            f"Server security policies, thresholds, and logging webhooks are currently unconfigured. "
            f"Run the interactive setup wizard to establish baseline defense."
        )

        cta_row = (
            ActionRowBuilder()
            .add_button(
                ButtonBuilder()
                .set_custom_id(f"an_wiz:step1:{guild.id}")
                .set_label("Begin Security Setup")
                .set_style(ButtonStyle.Primary)
                .set_emoji(EMOJIS.get("shield", "🛡️"))
            )
            .add_button(
                ButtonBuilder()
                .set_custom_id(f"log_wiz:start:{guild.id}")
                .set_label("Configure Webhook Logs")
                .set_style(ButtonStyle.Secondary)
                .set_emoji(EMOJIS.get("wrench", "🔧"))
            )
        )

        announcement_box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("default", "#0844C5"))
            .add_text_display(f"### <:sentinel:1563641257073442926> Welcome to Sentinel™ Server Protection")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(desc)
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_action_row(cta_row)
            .set_footer(f"Sentinel™ Defense • Prefix: {settings.BOT_PREFIX or '$'} • Use $setup to begin")
            .build()
        )

        try:
            await selected_channel.send(view=announcement_box)
            cls._ANNOUNCED_GUILDS.add(gid)
            try:
                col = database.collection("sentinel_join_announcements")
                await col.insert_one({"guild_id": gid, "guild_name": guild.name, "announced_at": time.time()})
            except Exception:
                pass
            logger.info(f"[SentinelJoin] Successfully announced in #{selected_channel.name} of guild {guild.name}")
            return True
        except Exception as err:
            logger.error(f"[SentinelJoin] Failed to deliver announcement in #{selected_channel.name}: {err}")
            return False
