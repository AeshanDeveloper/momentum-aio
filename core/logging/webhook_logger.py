import time
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Union
try:
    import aiohttp
except ImportError:
    aiohttp = None
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.logging.logger import logger
from database.database import database


class LogCategory:
    SECURITY = "security"          # Anti-nuke incidents, attacks, threshold breaches
    MODERATION = "moderation"      # Bans, unbans, kicks, timeouts, role changes
    CHANNELS = "channels"          # Channel created, deleted, updated
    ROLES = "roles"                # Role created, deleted, updated, perms
    MEMBERS = "members"            # Member joins, leaves, profile updates
    SERVER = "server"              # Server changes, invites, emojis, webhooks
    CONFIG = "config"              # Bot settings, permissions, antinuke adjustments

    ALL_CATEGORIES = [SECURITY, MODERATION, CHANNELS, ROLES, MEMBERS, SERVER, CONFIG]

    CATEGORY_METADATA = {
        SECURITY: {"name": "Security & Anti-Nuke", "emoji": EMOJIS.get("shield", "🛡️"), "color": "#EF4444"},
        MODERATION: {"name": "Moderation Actions", "emoji": EMOJIS.get("danger", "⚡"), "color": "#F97316"},
        CHANNELS: {"name": "Channel Operations", "emoji": EMOJIS.get("channel", "📁"), "color": "#3B82F6"},
        ROLES: {"name": "Role & Permission Changes", "emoji": EMOJIS.get("role", "🛡️"), "color": "#8B5CF6"},
        MEMBERS: {"name": "Member Events", "emoji": EMOJIS.get("members", "👥"), "color": "#10B981"},
        SERVER: {"name": "Server & Integrations", "emoji": EMOJIS.get("gear", "⚙️"), "color": "#6366F1"},
        CONFIG: {"name": "System Configuration", "emoji": EMOJIS.get("wrench", "🔧"), "color": "#06B6D4"},
    }


class LogSeverity:
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    SEVERITY_COLORS = {
        INFO: "#3B82F6",
        LOW: "#10B981",
        MEDIUM: "#F59E0B",
        HIGH: "#F97316",
        CRITICAL: "#EF4444",
    }


class UnifiedWebhookLogger:
    """
    Centralized, Webhook-Only Logging Service for MomentumOne.
    Dispatches all bot-generated logs through authenticated Discord webhooks.
    Strictly forbids silent fallback to ordinary bot messages.
    """
    _configs_cache: Dict[str, Dict[str, Any]] = {}
    _webhook_cache: Dict[Tuple[str, str], str] = {}  # (guild_id, channel_id) -> webhook_url
    _initialized: bool = False

    @classmethod
    async def initialize(cls) -> None:
        """Hydrates logging configurations from database."""
        try:
            col = database.collection("guild_logging_configs")
            cursor = col.find({})
            records = await cursor.to_list(2000) if hasattr(cursor, "to_list") else await cursor
            for r in (records or []):
                gid = str(r.get("guild_id", ""))
                if gid:
                    cls._configs_cache[gid] = r
            cls._initialized = True
            logger.info(f"[UnifiedWebhookLogger] Hydrated logging configurations for {len(cls._configs_cache)} guild(s).")
        except Exception as err:
            cls._initialized = True
            logger.warning(f"[UnifiedWebhookLogger] Failed to hydrate logging configs: {err}")

    @classmethod
    def get_guild_logging_config(cls, guild_id: str | int) -> Dict[str, Any]:
        """Returns the guild's logging configuration, initializing with defaults if missing."""
        gid = str(guild_id)
        if gid in cls._configs_cache:
            return cls._configs_cache[gid]

        default_config = {
            "guild_id": gid,
            "enabled": False,
            "layout": "compact",  # "compact" | "dual" | "category" | "advanced"
            "category_id": None,
            "separate_antinuke": True,
            "destinations": {},  # category -> {"channel_id": str, "webhook_id": str, "webhook_url": str}
            "disabled_categories": [],
            "delivery_failures": [],  # list of recent failure records
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        cls._configs_cache[gid] = default_config
        return default_config

    @classmethod
    async def save_guild_logging_config(cls, guild_id: str | int, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Persists logging configuration updates to database and in-memory cache."""
        gid = str(guild_id)
        cfg = cls.get_guild_logging_config(gid)
        cfg.update(updates)
        cfg["updated_at"] = time.time()
        cls._configs_cache[gid] = cfg

        try:
            col = database.collection("guild_logging_configs")
            await col.update_one({"guild_id": gid}, {"$set": cfg}, upsert=True)
        except Exception as err:
            logger.error(f"[UnifiedWebhookLogger] Failed to persist config for guild {gid}: {err}")

        return cfg

    @classmethod
    def get_bot_avatar_url(cls, guild: Optional[discord.Guild]) -> Optional[str]:
        """Resolves the bot's configured icon from its actual identity rather than a hardcoded URL."""
        if guild and getattr(guild, "me", None):
            me = guild.me
            if hasattr(me, "display_avatar") and me.display_avatar:
                return str(me.display_avatar.url)
        bot_user = getattr(guild, "_state", None)
        if bot_user and hasattr(bot_user, "user") and bot_user.user:
            return str(bot_user.user.display_avatar.url)
        return getattr(settings, "BOT_ICON_URL", None)

    @classmethod
    def build_log_embed(
        cls,
        guild: discord.Guild,
        category: str,
        title: str,
        description: str,
        actor: Optional[Union[discord.Member, discord.User, str]] = None,
        target: Optional[Union[discord.Member, discord.User, discord.abc.GuildChannel, discord.Role, str]] = None,
        reason: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        severity: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Creates a standardized, branded log embed dict adhering to MomentumOne design constitution.
        """
        cat_meta = LogCategory.CATEGORY_METADATA.get(category, {"name": category.title(), "emoji": "📝", "color": "#0844C5"})

        if severity:
            sev_color = LogSeverity.SEVERITY_COLORS.get(severity.lower(), cat_meta.get("color", "#0844C5"))
        else:
            sev_color = cat_meta.get("color", "#0844C5")

        color_int = int(sev_color.replace("#", ""), 16)

        # Actor attribution
        if actor:
            if isinstance(actor, (discord.Member, discord.User)):
                actor_str = f"{actor.mention} (`{actor}` • ID: `{actor.id}`)"
            else:
                actor_str = str(actor)
        else:
            actor_str = "*Unknown / Unverified (Audit log entry not found)*"

        # Target formatting
        target_str = None
        if target:
            if isinstance(target, (discord.Member, discord.User)):
                target_str = f"{target.mention} (`{target}` • ID: `{target.id}`)"
            elif isinstance(target, discord.Role):
                target_str = f"{target.mention} (`@{target.name}` • ID: `{target.id}`)"
            elif isinstance(target, discord.abc.GuildChannel):
                target_str = f"{target.mention} (`#{target.name}` • ID: `{target.id}`)"
            else:
                target_str = str(target)

        embed_fields = []

        # Actor and Target in top section
        embed_fields.append({"name": "Responsible Actor", "value": actor_str, "inline": False})
        if target_str:
            embed_fields.append({"name": "Target Affected", "value": target_str, "inline": False})

        if reason:
            embed_fields.append({"name": "Reason / Context", "value": f"*{reason}*", "inline": False})

        if severity:
            sev_badge = f"`{severity.upper()}`"
            embed_fields.append({"name": "Security Severity", "value": sev_badge, "inline": True})

        # Additional custom fields
        if fields:
            for f in fields:
                embed_fields.append({
                    "name": str(f.get("name", "Detail")),
                    "value": str(f.get("value", "N/A")),
                    "inline": bool(f.get("inline", False)),
                })

        ts_val = timestamp or time.time()
        iso_timestamp = discord.utils.utcnow().isoformat()

        embed = {
            "title": f"{cat_meta.get('emoji', '📝')} {title}",
            "description": description,
            "color": color_int,
            "fields": embed_fields,
            "footer": {
                "text": f"{settings.BOT_NAME} Unified Logger • {cat_meta.get('name', 'Audit Trail')}",
            },
            "timestamp": iso_timestamp,
        }

        avatar_url = cls.get_bot_avatar_url(guild)
        if avatar_url:
            embed["thumbnail"] = {"url": avatar_url}

        return embed

    @classmethod
    async def get_or_create_channel_webhook(cls, channel: discord.TextChannel) -> Optional[str]:
        """Retrieves or creates a dedicated webhook for a channel, returning the webhook URL."""
        if not channel or not channel.guild:
            return None

        gid = str(channel.guild.id)
        cid = str(channel.id)

        # Check in-memory cache
        if (gid, cid) in cls._webhook_cache:
            return cls._webhook_cache[(gid, cid)]

        # Check existing webhooks on channel
        me = channel.guild.me
        if not me or not channel.permissions_for(me).manage_webhooks:
            logger.warning(f"[UnifiedWebhookLogger] Missing manage_webhooks permission in channel {channel.name} ({channel.id})")
            return None

        try:
            webhooks = await channel.webhooks()
            target_wh = next((w for w in webhooks if w.user and w.user.id == me.id and w.url), None)
            if not target_wh and webhooks:
                # Use existing webhook if accessible
                target_wh = next((w for w in webhooks if w.url), None)

            if not target_wh:
                target_wh = await channel.create_webhook(
                    name=f"{settings.BOT_NAME} Logger",
                    reason="MomentumOne Unified Webhook Logging Channel Setup",
                )

            if target_wh and target_wh.url:
                cls._webhook_cache[(gid, cid)] = target_wh.url
                return target_wh.url
        except Exception as err:
            logger.error(f"[UnifiedWebhookLogger] Failed to get or create webhook in channel {channel.id}: {err}")

        return None

    @classmethod
    async def resolve_webhook_for_category(cls, guild: discord.Guild, category: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Resolves the webhook URL and channel ID configured for a specific log category.
        Returns: (webhook_url, channel_id)
        """
        cfg = cls.get_guild_logging_config(str(guild.id))
        if not cfg.get("enabled", False):
            return None, None

        if category in cfg.get("disabled_categories", []):
            return None, None

        destinations = cfg.get("destinations", {})

        # 1. Check exact category mapping
        dest = destinations.get(category)

        # 2. If security category and separate_antinuke is False, route to general/moderation
        if not dest and category == LogCategory.SECURITY and not cfg.get("separate_antinuke", True):
            dest = destinations.get(LogCategory.MODERATION) or destinations.get("general")

        # 3. Fallback to compact "general" destination
        if not dest:
            dest = destinations.get("general")

        if not dest or not isinstance(dest, dict):
            return None, None

        ch_id = dest.get("channel_id")
        wh_url = dest.get("webhook_url")

        if wh_url:
            return wh_url, ch_id

        # Try to resolve via channel_id
        if ch_id:
            ch = guild.get_channel(int(ch_id))
            if isinstance(ch, discord.TextChannel):
                wh_url = await cls.get_or_create_channel_webhook(ch)
                if wh_url:
                    dest["webhook_url"] = wh_url
                    await cls.save_guild_logging_config(str(guild.id), {"destinations": destinations})
                    return wh_url, ch_id

        return None, ch_id

    @classmethod
    async def dispatch_log(
        cls,
        guild: discord.Guild,
        category: str,
        title: str,
        description: str,
        actor: Optional[Union[discord.Member, discord.User, str]] = None,
        target: Optional[Union[discord.Member, discord.User, discord.abc.GuildChannel, discord.Role, str]] = None,
        reason: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        severity: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> bool:
        """
        Delivers a log message through Discord Webhook.
        NEVER falls back to sending an ordinary bot message!
        If delivery fails, records the failure and returns False.
        """
        if not guild:
            return False

        webhook_url, ch_id = await cls.resolve_webhook_for_category(guild, category)

        if not webhook_url:
            cls._record_delivery_failure(
                guild.id, category, ch_id, "Missing or unconfigured webhook destination. Webhook delivery required."
            )
            return False

        embed = cls.build_log_embed(
            guild=guild,
            category=category,
            title=title,
            description=description,
            actor=actor,
            target=target,
            reason=reason,
            fields=fields,
            severity=severity,
            timestamp=timestamp,
        )

        payload = {
            "username": f"{settings.BOT_NAME} Security & Event Logger",
            "avatar_url": cls.get_bot_avatar_url(guild),
            "embeds": [embed],
        }

        try:
            if aiohttp is None:
                raise RuntimeError("aiohttp library is required for webhook logging.")

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=payload, timeout=5.0) as resp:
                    if resp.status in (200, 204):
                        return True
                    else:
                        resp_text = await resp.text()
                        err_msg = f"HTTP {resp.status}: {resp_text[:100]}"
                        cls._record_delivery_failure(guild.id, category, ch_id, err_msg)
                        logger.warning(f"[UnifiedWebhookLogger] Webhook delivery failed on guild {guild.id}: {err_msg}")
                        # Invalidate cached webhook on 404 / 401
                        if resp.status in (401, 404):
                            cls._webhook_cache.pop((str(guild.id), str(ch_id)), None)
                        return False
        except Exception as err:
            cls._record_delivery_failure(guild.id, category, ch_id, str(err))
            logger.error(f"[UnifiedWebhookLogger] Webhook exception on guild {guild.id}: {err}")
            return False

    @classmethod
    def _record_delivery_failure(cls, guild_id: int | str, category: str, channel_id: Optional[str], error: str) -> None:
        """Records webhook delivery failure for administrative review and warnings."""
        gid = str(guild_id)
        cfg = cls.get_guild_logging_config(gid)
        failures = list(cfg.get("delivery_failures", []))
        record = {
            "timestamp": time.time(),
            "category": category,
            "channel_id": str(channel_id) if channel_id else "unknown",
            "error": str(error),
        }
        failures.append(record)
        # Keep only the latest 20 failure logs
        if len(failures) > 20:
            failures = failures[-20:]
        cfg["delivery_failures"] = failures

    @classmethod
    async def create_logging_channel_with_webhook(
        cls,
        guild: discord.Guild,
        channel_name: str,
        category: Optional[discord.CategoryChannel] = None,
        topic: str = "",
    ) -> Tuple[Optional[discord.TextChannel], Optional[discord.Webhook], Optional[str]]:
        """
        Creates a dedicated logging channel with proper security overwrites
        (@everyone cannot read/send, staff/bot can manage/read) and creates a webhook.
        """
        me = guild.me
        if not me or not me.guild_permissions.manage_channels:
            return None, None, "Bot is missing `Manage Channels` permission."
        if not me.guild_permissions.manage_webhooks:
            return None, None, "Bot is missing `Manage Webhooks` permission."

        # Security overwrites: regular members cannot view or post
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_webhooks=True),
        }

        try:
            ch = await guild.create_text_channel(
                name=channel_name,
                category=category,
                topic=topic or f"{settings.BOT_NAME} Unified Audit & Event Logging",
                overwrites=overwrites,
                reason="MomentumOne Unified Webhook Logging System Setup",
            )
            wh = await ch.create_webhook(
                name=f"{settings.BOT_NAME} Logger",
                reason="MomentumOne Unified Logging Webhook",
            )
            cls._webhook_cache[(str(guild.id), str(ch.id))] = wh.url
            return ch, wh, None
        except Exception as err:
            logger.error(f"[UnifiedWebhookLogger] Failed to create logging channel/webhook: {err}")
            return None, None, str(err)

    @classmethod
    async def repair_webhook(cls, guild: discord.Guild, channel_id: int | str) -> Tuple[bool, str]:
        """Repairs or recreates an invalid or deleted webhook for a channel."""
        ch = guild.get_channel(int(channel_id))
        if not ch or not isinstance(ch, discord.TextChannel):
            return False, "Channel not found or is not a text channel."

        me = guild.me
        if not me.guild_permissions.manage_webhooks:
            return False, "Bot is missing `Manage Webhooks` permission."

        try:
            # Clear cache
            cls._webhook_cache.pop((str(guild.id), str(channel_id)), None)

            # Create fresh webhook
            wh = await ch.create_webhook(
                name=f"{settings.BOT_NAME} Logger (Repaired)",
                reason="MomentumOne Unified Webhook Repair Action",
            )
            cls._webhook_cache[(str(guild.id), str(channel_id))] = wh.url

            # Update in guild config destinations
            cfg = cls.get_guild_logging_config(str(guild.id))
            destinations = dict(cfg.get("destinations", {}))
            repaired_count = 0
            for cat, d in destinations.items():
                if isinstance(d, dict) and d.get("channel_id") == str(channel_id):
                    d["webhook_url"] = wh.url
                    d["webhook_id"] = str(wh.id)
                    repaired_count += 1

            # Clear failure logs for this channel
            failures = [f for f in cfg.get("delivery_failures", []) if f.get("channel_id") != str(channel_id)]
            await cls.save_guild_logging_config(str(guild.id), {"destinations": destinations, "delivery_failures": failures})

            return True, f"Webhook repaired! Linked to {repaired_count} log category destination(s)."
        except Exception as err:
            logger.error(f"[UnifiedWebhookLogger] Repair webhook error: {err}")
            return False, str(err)

    @classmethod
    async def test_webhook(cls, guild: discord.Guild, channel_id: int | str) -> Tuple[bool, str]:
        """Dispatches an explicit test embed to verify webhook connectivity."""
        ch = guild.get_channel(int(channel_id))
        if not ch or not isinstance(ch, discord.TextChannel):
            return False, "Target channel not found."

        wh_url = await cls.get_or_create_channel_webhook(ch)
        if not wh_url:
            return False, "Failed to resolve or create webhook in target channel."

        embed = cls.build_log_embed(
            guild=guild,
            category=LogCategory.CONFIG,
            title="Webhook Delivery Test",
            description="This is an automated verification test confirming that Discord webhook log delivery is fully functional.",
            actor=guild.me,
            fields=[
                {"name": "Channel", "value": f"<#{channel_id}> (`{channel_id}`)", "inline": True},
                {"name": "Status", "value": f"{EMOJIS.get('check', '✅')} Active & Connected", "inline": True},
            ],
            severity=LogSeverity.INFO,
        )

        payload = {
            "username": f"{settings.BOT_NAME} Diagnostic Tester",
            "avatar_url": cls.get_bot_avatar_url(guild),
            "embeds": [embed],
        }

        try:
            if aiohttp is None:
                return False, "aiohttp library missing."
            async with aiohttp.ClientSession() as session:
                async with session.post(wh_url, json=payload, timeout=5.0) as resp:
                    if resp.status in (200, 204):
                        return True, "Test webhook payload delivered successfully!"
                    else:
                        resp_text = await resp.text()
                        return False, f"Discord Webhook API returned HTTP {resp.status}: {resp_text[:120]}"
        except Exception as err:
            return False, f"Network or execution error: {err}"
