import time
import asyncio
import re
import uuid
from typing import Dict, Any, List, Optional, Tuple, Union, Callable, Awaitable
try:
    import aiohttp
except ImportError:
    aiohttp = None
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.logging.logger import logger
from database.database import database
from core.logging.resource_tracker import SentinelResourceTracker, SentinelResourceRecord

_WEBHOOK_URL_REGEX = re.compile(r"https?://(?:[a-zA-Z0-9-]+\.)?discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+", re.IGNORECASE)
_WEBHOOK_TOKEN_REGEX = re.compile(r"(/api/webhooks/\d+/)[A-Za-z0-9_-]+", re.IGNORECASE)

def redact_webhook_credentials(text: Any) -> str:
    """Removes all webhook URLs, tokens, and secrets from text, logs, and errors."""
    if text is None:
        return ""
    s = str(text)
    s = _WEBHOOK_URL_REGEX.sub("[REDACTED_WEBHOOK_URL]", s)
    s = _WEBHOOK_TOKEN_REGEX.sub(r"\1[REDACTED_TOKEN]", s)
    return s

def get_webhook_display_status(guild: Optional[discord.Guild], dest: Optional[Dict[str, Any]]) -> str:
    """
    Returns only the user-facing status string: 'Configured', 'Missing', or 'Needs Repair'.
    Never outputs URLs, tokens, or sensitive IDs.
    """
    if not dest or not isinstance(dest, dict):
        return "Missing"
    cid = dest.get("channel_id")
    wh_url = dest.get("webhook_url")
    if not cid or not wh_url:
        return "Missing"
    if guild:
        ch = guild.get_channel(int(cid))
        if not ch or not isinstance(ch, discord.TextChannel):
            return "Needs Repair"
    return "Configured"


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
    _ACTIVE_SETUP_SERVERS: set = set()
    _SETUP_LOCK: asyncio.Lock = asyncio.Lock()
    _PROCESSED_AUDIT_LOG_IDS: Dict[int, float] = {}
    _OPERATION_DELAY: float = 1.0

    @classmethod
    async def acquire_setup_lock(cls, guild_id: str | int) -> bool:
        """Acquires single-setup lock per guild to prevent duplicate concurrent workflows."""
        gid = str(guild_id)
        async with cls._SETUP_LOCK:
            if gid in cls._ACTIVE_SETUP_SERVERS:
                return False
            cls._ACTIVE_SETUP_SERVERS.add(gid)
            return True

    @classmethod
    def release_setup_lock(cls, guild_id: str | int) -> Any:
        """Releases the setup lock for a guild. Supports both sync and await syntax."""
        gid = str(guild_id)
        cls._ACTIVE_SETUP_SERVERS.discard(gid)

        class _LockReleaseAwaitable:
            def __await__(self):
                async def _noop():
                    pass
                return _noop().__await__()

        return _LockReleaseAwaitable()

    @classmethod
    def is_setup_in_progress(cls, guild_id: str | int) -> bool:
        """Checks if a setup workflow is active for the specified guild."""
        return str(guild_id) in cls._ACTIVE_SETUP_SERVERS

    @classmethod
    async def fetch_audit_attribution(
        cls,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: Optional[Union[int, str]] = None,
        max_age_seconds: float = 8.0,
    ) -> Tuple[Optional[Union[discord.Member, discord.User]], Optional[str]]:
        """
        Retrieves responsible actor and reason from Discord audit log.
        Deduplicates entries so identical audit log events are not reported multiple times.
        """
        if not guild:
            return None, None
        me = getattr(guild, "me", None)
        if not me or not getattr(me.guild_permissions, "view_audit_log", False):
            return None, None

        now = time.time()
        # Clean expired audit ids (> 60s)
        expired = [eid for eid, exp in cls._PROCESSED_AUDIT_LOG_IDS.items() if now > exp]
        for eid in expired:
            cls._PROCESSED_AUDIT_LOG_IDS.pop(eid, None)

        try:
            async for entry in guild.audit_logs(action=action, limit=5):
                entry_age = now - entry.created_at.timestamp()
                if entry_age > max_age_seconds:
                    break
                if target_id is not None:
                    target_match = False
                    if entry.target and hasattr(entry.target, "id"):
                        target_match = (str(entry.target.id) == str(target_id))
                    if not target_match:
                        continue

                # Check if already processed
                if entry.id in cls._PROCESSED_AUDIT_LOG_IDS:
                    return None, None

                cls._PROCESSED_AUDIT_LOG_IDS[entry.id] = now + 60.0
                return entry.user, entry.reason
        except Exception as err:
            logger.debug(f"[UnifiedWebhookLogger] Audit log lookup exception on guild {guild.id}: {err}")

        return None, None

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

        if isinstance(title, dict):
            p_dict = title
            embed = cls.build_log_embed(
                guild=guild,
                category=category,
                title=str(p_dict.get("title", description or "Event Log")),
                description=str(p_dict.get("description", description or "")),
                actor=actor or p_dict.get("actor"),
                target=target or p_dict.get("target"),
                reason=reason or p_dict.get("reason"),
                fields=fields or p_dict.get("fields"),
                severity=severity or p_dict.get("severity"),
                timestamp=timestamp or p_dict.get("timestamp"),
            )
        else:
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
                        err_msg = redact_webhook_credentials(f"HTTP {resp.status}: {resp_text[:100]}")
                        cls._record_delivery_failure(guild.id, category, ch_id, err_msg)
                        logger.warning(f"[UnifiedWebhookLogger] Webhook delivery failed on guild {guild.id}: {err_msg}")
                        # Invalidate cached webhook on 404 / 401
                        if resp.status in (401, 404):
                            cls._webhook_cache.pop((str(guild.id), str(ch_id)), None)
                        return False
        except Exception as err:
            err_str = redact_webhook_credentials(str(err))
            cls._record_delivery_failure(guild.id, category, ch_id, err_str)
            logger.error(f"[UnifiedWebhookLogger] Webhook exception on guild {guild.id}: {err_str}")
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
            "error": redact_webhook_credentials(error),
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
        """Dispatches an explicit test embed to verify webhook connectivity without revealing secrets."""
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
            description="Automated verification test confirming that Discord webhook log delivery is active and operational.",
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
                        sanitized = redact_webhook_credentials(resp_text[:120])
                        return False, f"Discord Webhook API returned HTTP {resp.status}: {sanitized}"
        except Exception as err:
            return False, f"Network or execution error: {redact_webhook_credentials(str(err))}"

    @classmethod
    def mask_webhook_url(cls, webhook_url: Optional[str]) -> str:
        """Deprecated: Replaced by status badge. Never prints URLs or tokens."""
        if not webhook_url or not isinstance(webhook_url, str):
            return "Missing"
        return "Configured"

    @classmethod
    async def assign_category_channel(
        cls, guild: discord.Guild, category: str, channel: discord.TextChannel
    ) -> Tuple[bool, str]:
        """Assigns a log category to a specified text channel and creates/links a webhook."""
        wh_url = await cls.get_or_create_channel_webhook(channel)
        if not wh_url:
            return False, f"Failed to acquire or create webhook in <#{channel.id}>. Verify `Manage Webhooks` permission."

        cfg = cls.get_guild_logging_config(str(guild.id))
        destinations = dict(cfg.get("destinations", {}))
        destinations[category] = {
            "channel_id": str(channel.id),
            "channel_name": channel.name,
            "webhook_url": wh_url,
        }
        await cls.save_guild_logging_config(str(guild.id), {"destinations": destinations, "enabled": True})
        return True, f"Category **{category.title()}** successfully mapped to <#{channel.id}> via webhook."

    @classmethod
    async def create_logging_setup_workflow(
        cls,
        guild: discord.Guild,
        layout: str,
        create_category: bool = True,
        category_name: Optional[str] = None,
        separate_antinuke: bool = True,
        progress_callback: Optional[Callable[[str], Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes an idempotent, rate-limit protected logging setup workflow.
        Reuses existing categories, channels, and webhooks without duplicating them.
        """
        async def report(msg: str) -> None:
            if progress_callback:
                try:
                    res = progress_callback(msg)
                    if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                        await res
                except Exception as err:
                    logger.debug(f"[UnifiedWebhookLogger] Progress callback error: {err}")

        await report("Preparing logging configuration…")

        me = getattr(guild, "me", None)
        if not me or not getattr(me.guild_permissions, "manage_channels", False):
            return {"success": False, "error": "Bot is missing `Manage Channels` permission.", "step": "permissions"}
        if not getattr(me.guild_permissions, "manage_webhooks", False):
            return {"success": False, "error": "Bot is missing `Manage Webhooks` permission.", "step": "permissions"}

        await report("Checking existing channels and categories…")
        cfg = cls.get_guild_logging_config(str(guild.id))
        existing_destinations = dict(cfg.get("destinations", {}))

        # 1. Category Resolution & Reuse
        target_cat: Optional[discord.CategoryChannel] = None
        created_category = False
        reused_category = False
        cat_label = category_name or f"{settings.BOT_NAME.upper()} LOGS"

        setup_id = f"setup_{uuid.uuid4().hex[:8]}"
        if create_category:
            # Check previously configured category ID IF and ONLY IF verified in SentinelResourceTracker
            saved_cat_id = cfg.get("category_id")
            if saved_cat_id and SentinelResourceTracker.is_resource_owned(guild.id, saved_cat_id):
                for c in (guild.categories or []):
                    if str(getattr(c, "id", "")) == str(saved_cat_id):
                        target_cat = c
                        reused_category = True
                        break
                if not target_cat:
                    ch = guild.get_channel(int(saved_cat_id))
                    if isinstance(ch, discord.CategoryChannel):
                        target_cat = ch
                        reused_category = True

            # If still not found by verified ownership ID, create a brand-new dedicated category
            # Never scan categories by name or pattern!
            if not target_cat:
                await report(f"Creating dedicated logging category `{cat_label}`…")
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                    me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_webhooks=True),
                }
                try:
                    target_cat = await guild.create_category(
                        name=cat_label,
                        overwrites=overwrites,
                        reason="Sentinel Unified Webhook Logging Category Setup",
                    )
                    created_category = True
                    await SentinelResourceTracker.record_resource_creation(
                        guild_id=guild.id,
                        resource_id=target_cat.id,
                        resource_type="category",
                        setup_id=setup_id,
                        purpose="forensic_category",
                        metadata={"name": cat_label},
                    )
                    await asyncio.sleep(cls._OPERATION_DELAY)
                except Exception as err:
                    return {
                        "success": False,
                        "error": f"Failed to create category `{cat_label}`: {redact_webhook_credentials(str(err))}",
                        "step": "category_creation",
                    }

        # 2. Build Specs based on layout
        specs = []
        if layout == "compact":
            general_cats = [
                LogCategory.MODERATION,
                LogCategory.CHANNELS,
                LogCategory.ROLES,
                LogCategory.MEMBERS,
                LogCategory.SERVER,
                LogCategory.CONFIG,
            ]
            if not separate_antinuke:
                general_cats.append(LogCategory.SECURITY)
            specs.append(("server-logs", general_cats, "Centralized Server & Audit Logs"))
            if separate_antinuke:
                specs.append(("security-logs", [LogCategory.SECURITY], "Anti-Nuke & Security Incident Logs"))

        elif layout == "dual":
            specs.append(("moderation-logs", [LogCategory.MODERATION, LogCategory.MEMBERS], "Moderation & Member Actions"))
            specs.append(("server-logs", [LogCategory.CHANNELS, LogCategory.ROLES, LogCategory.SERVER, LogCategory.CONFIG], "Server Operations & Configuration"))
            if separate_antinuke:
                specs.append(("security-logs", [LogCategory.SECURITY], "Anti-Nuke & Security Incident Logs"))

        elif layout == "category":
            specs.append(("security-logs", [LogCategory.SECURITY], "Anti-Nuke & Security Incident Alerts"))
            specs.append(("moderation-logs", [LogCategory.MODERATION], "Server Moderation Logs"))
            specs.append(("channel-logs", [LogCategory.CHANNELS], "Channel Creations, Deletions, and Overwrite Updates"))
            specs.append(("role-logs", [LogCategory.ROLES], "Role Changes, Creations, and Permission Audits"))
            specs.append(("member-logs", [LogCategory.MEMBERS], "Member Joins, Leaves, and Moderation Updates"))
            specs.append(("server-logs", [LogCategory.SERVER, LogCategory.CONFIG], "Integrations, Invites, Emojis, and Configuration"))

        else:  # advanced / default
            specs.append(("security-logs", [LogCategory.SECURITY], "Security Logs"))
            specs.append(("moderation-logs", [LogCategory.MODERATION, LogCategory.MEMBERS], "Moderation Logs"))
            specs.append(("server-logs", [LogCategory.CHANNELS, LogCategory.ROLES, LogCategory.SERVER, LogCategory.CONFIG], "Server Logs"))

        created_channels = []
        reused_channels = []
        all_channels = []
        new_destinations = {}
        errors = []

        # 3. Channel & Webhook Resolution with Verified Ownership
        for ch_name, cats, topic in specs:
            target_ch: Optional[discord.TextChannel] = None
            is_reused_ch = False

            # Check if we already have a verified Sentinel-owned channel for this purpose under target_cat
            if target_cat:
                for rec in SentinelResourceTracker.get_all_owned_resources(guild.id):
                    if (
                        rec.resource_type == "text_channel"
                        and rec.parent_id == str(target_cat.id)
                        and rec.purpose == ch_name
                    ):
                        cand = guild.get_channel(int(rec.resource_id))
                        if isinstance(cand, discord.TextChannel):
                            target_ch = cand
                            is_reused_ch = True
                            break

            # If not already verified and owned by Sentinel, create a new dedicated channel under target_cat
            # NEVER search guild text channels by name or adopt user channels!
            if not target_ch:
                await report(f"Creating channel `#{ch_name}`…")
                await asyncio.sleep(cls._OPERATION_DELAY)
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
                    me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_webhooks=True),
                }
                try:
                    target_ch = await guild.create_text_channel(
                        name=ch_name,
                        category=target_cat,
                        topic=topic or f"{settings.BOT_NAME} Unified Audit & Event Logging",
                        overwrites=overwrites,
                        reason="Sentinel Unified Webhook Logging System Setup",
                    )
                    created_channels.append(target_ch)
                    await SentinelResourceTracker.record_resource_creation(
                        guild_id=guild.id,
                        resource_id=target_ch.id,
                        resource_type="text_channel",
                        parent_id=target_cat.id if target_cat else None,
                        setup_id=setup_id,
                        purpose=ch_name,
                        metadata={"name": ch_name, "topic": topic},
                    )
                except Exception as err:
                    errors.append(f"Failed to create `#{ch_name}`: {redact_webhook_credentials(str(err))}")
                    continue
            else:
                reused_channels.append(target_ch)

            all_channels.append(target_ch)

            # Webhook Resolution & Reuse
            await report(f"Configuring webhook for `#{target_ch.name}`…")
            target_wh: Optional[discord.Webhook] = None
            try:
                wh_list = await target_ch.webhooks()
                # Find webhook recorded in SentinelResourceTracker or created by bot
                for w in wh_list:
                    if SentinelResourceTracker.is_resource_owned(guild.id, w.id) or (getattr(w, "user", None) and getattr(w.user, "id", None) == me.id):
                        target_wh = w
                        break

                if not target_wh:
                    await asyncio.sleep(0.5)
                    target_wh = await target_ch.create_webhook(
                        name=f"{settings.BOT_NAME} Logger",
                        reason=f"{settings.BOT_NAME} Unified Logging Webhook",
                    )
                    await SentinelResourceTracker.record_resource_creation(
                        guild_id=guild.id,
                        resource_id=target_wh.id,
                        resource_type="webhook",
                        parent_id=target_ch.id,
                        setup_id=setup_id,
                        purpose=f"{ch_name}_webhook",
                    )
            except Exception as err:
                errors.append(f"Webhook error in `#{target_ch.name}`: {redact_webhook_credentials(str(err))}")
                continue

            if target_wh and target_wh.url:
                cls._webhook_cache[(str(guild.id), str(target_ch.id))] = target_wh.url
                dest_data = {
                    "channel_id": str(target_ch.id),
                    "channel_name": target_ch.name,
                    "webhook_id": str(target_wh.id),
                    "webhook_url": target_wh.url,
                }
                for cat in cats:
                    new_destinations[cat] = dest_data
                if "general" not in new_destinations:
                    new_destinations["general"] = dest_data

        await report("Registering log destinations…")
        cfg_updates = {
            "enabled": True,
            "layout": layout,
            "category_id": str(target_cat.id) if target_cat else None,
            "separate_antinuke": separate_antinuke,
            "destinations": new_destinations,
        }
        await cls.save_guild_logging_config(str(guild.id), cfg_updates)

        await report("Verifying configuration…")
        success = len(all_channels) > 0 and len(new_destinations) > 0

        return {
            "status": "success" if success else "error",
            "success": success,
            "category": target_cat,
            "created_category": created_category,
            "reused_category": reused_category,
            "created_channels": created_channels,
            "reused_channels": reused_channels,
            "channels": all_channels,
            "destinations": new_destinations,
            "errors": errors,
        }

    @classmethod
    async def cleanup_logging_resources(
        cls,
        guild: discord.Guild,
        channel_ids: Optional[List[Union[int, str]]] = None,
        delete_from_discord: bool = False,
        delete_category: bool = False,
    ) -> Dict[str, Any]:
        """
        Safely removes logging resources created and managed by MomentumOne.
        Never touches user-created or third-party channels.
        Cleans up associated webhooks, DB destinations, and in-memory caches.
        """
        cfg = cls.get_guild_logging_config(str(guild.id))
        destinations = dict(cfg.get("destinations", {}))
        me = getattr(guild, "me", None)

        filter_cids = {str(cid) for cid in channel_ids} if channel_ids else None
        deleted_channels = []
        deleted_webhooks = []
        errors = []

        # 1. Load Sentinel's persisted ownership records
        owned_resources = SentinelResourceTracker.get_all_owned_resources(guild.id)
        verified_channels = [r for r in owned_resources if r.resource_type == "text_channel"]
        verified_categories = [r for r in owned_resources if r.resource_type == "category"]

        # Also identify channels configured in destinations that have Sentinel topic markers
        dest_channels_to_clean = set()
        for cat_key, d in destinations.items():
            if isinstance(d, dict) and d.get("channel_id"):
                cid_str = str(d.get("channel_id"))
                if filter_cids is None or cid_str in filter_cids:
                    dest_channels_to_clean.add(cid_str)

        all_target_cids = {str(r.resource_id) for r in verified_channels}
        if filter_cids:
            all_target_cids = all_target_cids.intersection(filter_cids)
            all_target_cids.update(dest_channels_to_clean)
        else:
            all_target_cids.update(dest_channels_to_clean)

        # 2. Process channels for deletion & webhook cleanup
        for cid in all_target_cids:
            cls._webhook_cache.pop((str(guild.id), cid), None)
            ch = guild.get_channel(int(cid))

            if isinstance(ch, discord.TextChannel):
                # Verify Sentinel ownership: check tracker OR topic signature inside Sentinel category
                is_tracker_owned = SentinelResourceTracker.is_resource_owned(guild.id, cid)
                is_signature_owned = False
                topic_val = getattr(ch, "topic", "") or ""
                if (settings.BOT_NAME.lower() in topic_val.lower() or "sentinel" in topic_val.lower()):
                    if cfg.get("category_id") and str(getattr(ch, "category_id", "")) == str(cfg.get("category_id")):
                        is_signature_owned = True
                    elif str(getattr(getattr(ch, "category", None), "id", "")) == str(cfg.get("category_id", "")):
                        is_signature_owned = True
                    elif "automated webhook channel" in topic_val.lower():
                        is_signature_owned = True

                if not is_tracker_owned and not is_signature_owned:
                    logger.warning(f"[UnifiedWebhookLogger] Preserving non-Sentinel channel {ch.id} ({ch.name})")
                    continue

                if me and getattr(me.guild_permissions, "manage_webhooks", False):
                    try:
                        whs = await ch.webhooks()
                        for wh in whs:
                            if SentinelResourceTracker.is_resource_owned(guild.id, wh.id) or (getattr(wh, "user", None) and getattr(wh.user, "id", None) == me.id):
                                await wh.delete(reason=f"{settings.BOT_NAME} Logging Resource Decommission")
                                deleted_webhooks.append(wh.name)
                                await SentinelResourceTracker.remove_resource_record(guild.id, wh.id)
                    except Exception as err:
                        errors.append(f"Webhook deletion error in <#{cid}>: {redact_webhook_credentials(str(err))}")

                if delete_from_discord and me and getattr(me.guild_permissions, "manage_channels", False):
                    try:
                        ch_name = getattr(ch, "name", f"channel-{cid}")
                        await ch.delete(reason=f"{settings.BOT_NAME} Logging Resource Decommission")
                        deleted_channels.append(ch_name)
                        await SentinelResourceTracker.remove_resource_record(guild.id, cid)
                    except Exception as err:
                        errors.append(f"Channel deletion error for <#{cid}>: {redact_webhook_credentials(str(err))}")
            else:
                await SentinelResourceTracker.remove_resource_record(guild.id, cid)

        # 3. Update destinations in config
        if filter_cids is None:
            new_destinations = {}
        else:
            new_destinations = {}
            for cat, d in destinations.items():
                if isinstance(d, dict) and str(d.get("channel_id")) in all_target_cids:
                    continue
                new_destinations[cat] = d

        # 4. Check category cleanup if requested
        deleted_cat = False
        if delete_category:
            candidate_cat_ids = {str(r.resource_id) for r in verified_categories}
            if cfg.get("category_id"):
                candidate_cat_ids.add(str(cfg.get("category_id")))

            for cat_id_str in candidate_cat_ids:
                cat = guild.get_channel(int(cat_id_str))
                if not cat:
                    for c in getattr(guild, "categories", []) or []:
                        if str(getattr(c, "id", "")) == cat_id_str:
                            cat = c
                            break

                if cat and me and getattr(me.guild_permissions, "manage_channels", False):
                    cat_channels = getattr(cat, "channels", []) or []
                    remaining_non_sentinel = [
                        c for c in cat_channels
                        if not SentinelResourceTracker.is_resource_owned(guild.id, c.id)
                        and "sentinel" not in (getattr(c, "topic", "") or "").lower()
                    ]
                    if not remaining_non_sentinel:
                        try:
                            await cat.delete(reason=f"{settings.BOT_NAME} Logging Category Decommission")
                            deleted_cat = True
                            await SentinelResourceTracker.remove_resource_record(guild.id, cat_id_str)
                        except Exception as err:
                            errors.append(f"Category deletion error: {redact_webhook_credentials(str(err))}")
                    else:
                        logger.warning(f"[UnifiedWebhookLogger] Preserving category {cat.name} ({cat.id}) as it contains non-Sentinel resources.")
                else:
                    await SentinelResourceTracker.remove_resource_record(guild.id, cat_id_str)

        # Update and persist config
        is_still_enabled = len(new_destinations) > 0 and cfg.get("enabled", False)
        if filter_cids is None:
            is_still_enabled = False
        updates = {
            "destinations": new_destinations,
            "enabled": is_still_enabled,
        }
        if deleted_cat or not new_destinations:
            updates["category_id"] = None

        await cls.save_guild_logging_config(str(guild.id), updates)

        return {
            "success": True,
            "deleted_channels": deleted_channels,
            "deleted_webhooks": deleted_webhooks,
            "deleted_category": deleted_cat,
            "remaining_destinations": len(new_destinations),
            "errors": errors,
        }


# Top-level module convenience aliases
acquire_setup_lock = UnifiedWebhookLogger.acquire_setup_lock
release_setup_lock = UnifiedWebhookLogger.release_setup_lock
is_setup_in_progress = UnifiedWebhookLogger.is_setup_in_progress

