import time
import asyncio
import re
import collections
from typing import Dict, Any, List, Optional, Set, Tuple
try:
    import aiohttp
except ImportError:
    aiohttp = None
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.logging.logger import logger
from database.database import database
from apps.bot.discord.permissions.resolver import is_bot_owner
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle,
    SeparatorSpacingSize,
)


class AntiNukeConstants:
    # Operating Modes
    MODE_HARD = "hard"
    MODE_ULTIMATE = "ultimate"
    MODE_HYBRID = "hybrid"
    VALID_MODES = [MODE_HARD, MODE_ULTIMATE, MODE_HYBRID]

    # Punishments
    PUNISH_BAN = "ban"
    PUNISH_KICK = "kick"
    PUNISH_TIMEOUT = "timeout"
    PUNISH_PRUNE = "prune"
    PUNISH_STRIP_ROLES = "strip_roles"
    PUNISH_QUARANTINE = "quarantine"
    VALID_PUNISHMENTS = [
        PUNISH_BAN,
        PUNISH_KICK,
        PUNISH_TIMEOUT,
        PUNISH_PRUNE,
        PUNISH_STRIP_ROLES,
        PUNISH_QUARANTINE,
    ]

    # Target Types for Whitelist
    TARGET_USER = "user"
    TARGET_ROLE = "role"
    TARGET_CHANNEL = "channel"
    TARGET_CATEGORY = "category"
    VALID_TARGET_TYPES = [TARGET_USER, TARGET_ROLE, TARGET_CHANNEL, TARGET_CATEGORY]

    # Canonical 23 Discord Event Keys
    EVENT_GUILD_UPDATE = "guildUpdate"
    EVENT_CHANNEL_CREATE = "channelCreate"
    EVENT_CHANNEL_UPDATE = "channelUpdate"
    EVENT_CHANNEL_DELETE = "channelDelete"
    EVENT_ROLE_CREATE = "roleCreate"
    EVENT_ROLE_UPDATE = "roleUpdate"
    EVENT_ROLE_DELETE = "roleDelete"
    EVENT_MEMBER_UPDATE = "guildMemberUpdate"
    EVENT_MEMBER_REMOVE = "guildMemberRemove"
    EVENT_BAN_ADD = "guildBanAdd"
    EVENT_BAN = EVENT_BAN_ADD
    EVENT_BAN_REMOVE = "guildBanRemove"
    EVENT_EMOJIS_UPDATE = "guildEmojisUpdate"
    EVENT_STICKERS_UPDATE = "guildStickersUpdate"
    EVENT_WEBHOOKS_UPDATE = "webhooksUpdate"
    EVENT_INVITE_CREATE = "inviteCreate"
    EVENT_INVITE_DELETE = "inviteDelete"
    EVENT_INTEGRATIONS_UPDATE = "guildIntegrationsUpdate"
    EVENT_AUTOMOD_CREATE = "autoModerationRuleCreate"
    EVENT_AUTOMOD_UPDATE = "autoModerationRuleUpdate"
    EVENT_AUTOMOD_DELETE = "autoModerationRuleDelete"
    EVENT_AUDIT_LOG_CREATE = "guildAuditLogEntryCreate"
    EVENT_SCHEDULED_EVENT_DELETE = "guildScheduledEventDelete"
    EVENT_THREAD_DELETE = "threadDelete"
    EVENT_BOT_ADD = "bot_add"

    ALL_EVENTS = [
        EVENT_GUILD_UPDATE,
        EVENT_CHANNEL_CREATE,
        EVENT_CHANNEL_UPDATE,
        EVENT_CHANNEL_DELETE,
        EVENT_ROLE_CREATE,
        EVENT_ROLE_UPDATE,
        EVENT_ROLE_DELETE,
        EVENT_MEMBER_UPDATE,
        EVENT_MEMBER_REMOVE,
        EVENT_BAN_ADD,
        EVENT_BAN_REMOVE,
        EVENT_EMOJIS_UPDATE,
        EVENT_STICKERS_UPDATE,
        EVENT_WEBHOOKS_UPDATE,
        EVENT_INVITE_CREATE,
        EVENT_INVITE_DELETE,
        EVENT_INTEGRATIONS_UPDATE,
        EVENT_AUTOMOD_CREATE,
        EVENT_AUTOMOD_UPDATE,
        EVENT_AUTOMOD_DELETE,
        EVENT_AUDIT_LOG_CREATE,
        EVENT_SCHEDULED_EVENT_DELETE,
        EVENT_THREAD_DELETE,
        EVENT_BOT_ADD,
    ]

    # Category and Severity Metadata
    EVENT_METADATA: Dict[str, Dict[str, str]] = {
        EVENT_GUILD_UPDATE: {"category": "server", "severity": "high"},
        EVENT_CHANNEL_CREATE: {"category": "channel", "severity": "high"},
        EVENT_CHANNEL_UPDATE: {"category": "channel", "severity": "high"},
        EVENT_CHANNEL_DELETE: {"category": "channel", "severity": "critical"},
        EVENT_ROLE_CREATE: {"category": "role", "severity": "high"},
        EVENT_ROLE_UPDATE: {"category": "role", "severity": "critical"},
        EVENT_ROLE_DELETE: {"category": "role", "severity": "critical"},
        EVENT_MEMBER_UPDATE: {"category": "member", "severity": "high"},
        EVENT_MEMBER_REMOVE: {"category": "member", "severity": "critical"},
        EVENT_BAN_ADD: {"category": "moderation", "severity": "critical"},
        EVENT_BAN_REMOVE: {"category": "moderation", "severity": "high"},
        EVENT_EMOJIS_UPDATE: {"category": "assets", "severity": "high"},
        EVENT_STICKERS_UPDATE: {"category": "assets", "severity": "high"},
        EVENT_WEBHOOKS_UPDATE: {"category": "webhook", "severity": "critical"},
        EVENT_INVITE_CREATE: {"category": "invite", "severity": "medium"},
        EVENT_INVITE_DELETE: {"category": "invite", "severity": "medium"},
        EVENT_INTEGRATIONS_UPDATE: {"category": "integration", "severity": "high"},
        EVENT_AUTOMOD_CREATE: {"category": "automod", "severity": "high"},
        EVENT_AUTOMOD_UPDATE: {"category": "automod", "severity": "critical"},
        EVENT_AUTOMOD_DELETE: {"category": "automod", "severity": "critical"},
        EVENT_AUDIT_LOG_CREATE: {"category": "audit", "severity": "critical"},
        EVENT_SCHEDULED_EVENT_DELETE: {"category": "event", "severity": "medium"},
        EVENT_THREAD_DELETE: {"category": "thread", "severity": "high"},
        EVENT_BOT_ADD: {"category": "member", "severity": "critical"},
    }

    # Alias / Token normalization dictionary
    EVENT_ALIASES: Dict[str, str] = {
        "guildupdate": EVENT_GUILD_UPDATE,
        "guild_update": EVENT_GUILD_UPDATE,
        "server": EVENT_GUILD_UPDATE,
        "server_update": EVENT_GUILD_UPDATE,
        "channelcreate": EVENT_CHANNEL_CREATE,
        "channel_create": EVENT_CHANNEL_CREATE,
        "channelupdate": EVENT_CHANNEL_UPDATE,
        "channel_update": EVENT_CHANNEL_UPDATE,
        "channeldelete": EVENT_CHANNEL_DELETE,
        "channel_delete": EVENT_CHANNEL_DELETE,
        "channel": EVENT_CHANNEL_DELETE,
        "channels": EVENT_CHANNEL_DELETE,
        "rolecreate": EVENT_ROLE_CREATE,
        "role_create": EVENT_ROLE_CREATE,
        "roleupdate": EVENT_ROLE_UPDATE,
        "role_update": EVENT_ROLE_UPDATE,
        "roledelete": EVENT_ROLE_DELETE,
        "role_delete": EVENT_ROLE_DELETE,
        "role": EVENT_ROLE_DELETE,
        "roles": EVENT_ROLE_DELETE,
        "guildmemberupdate": EVENT_MEMBER_UPDATE,
        "member_update": EVENT_MEMBER_UPDATE,
        "timeout": EVENT_MEMBER_UPDATE,
        "timeouts": EVENT_MEMBER_UPDATE,
        "mute": EVENT_MEMBER_UPDATE,
        "guildmemberremove": EVENT_MEMBER_REMOVE,
        "member_remove": EVENT_MEMBER_REMOVE,
        "kick": EVENT_MEMBER_REMOVE,
        "kicks": EVENT_MEMBER_REMOVE,
        "guildbanadd": EVENT_BAN_ADD,
        "ban_add": EVENT_BAN_ADD,
        "ban": EVENT_BAN_ADD,
        "bans": EVENT_BAN_ADD,
        "guildbanremove": EVENT_BAN_REMOVE,
        "ban_remove": EVENT_BAN_REMOVE,
        "unban": EVENT_BAN_REMOVE,
        "guildemojisupdate": EVENT_EMOJIS_UPDATE,
        "emojis": EVENT_EMOJIS_UPDATE,
        "emoji": EVENT_EMOJIS_UPDATE,
        "guildstickersupdate": EVENT_STICKERS_UPDATE,
        "stickers": EVENT_STICKERS_UPDATE,
        "sticker": EVENT_STICKERS_UPDATE,
        "webhooksupdate": EVENT_WEBHOOKS_UPDATE,
        "webhook": EVENT_WEBHOOKS_UPDATE,
        "webhooks": EVENT_WEBHOOKS_UPDATE,
        "webhook_create": EVENT_WEBHOOKS_UPDATE,
        "webhook_delete": EVENT_WEBHOOKS_UPDATE,
        "webhook_update": EVENT_WEBHOOKS_UPDATE,
        "invitecreate": EVENT_INVITE_CREATE,
        "invite_create": EVENT_INVITE_CREATE,
        "invite": EVENT_INVITE_CREATE,
        "invites": EVENT_INVITE_CREATE,
        "invitedelete": EVENT_INVITE_DELETE,
        "invite_delete": EVENT_INVITE_DELETE,
        "guildintegrationsupdate": EVENT_INTEGRATIONS_UPDATE,
        "integrations": EVENT_INTEGRATIONS_UPDATE,
        "automoderationrulecreate": EVENT_AUTOMOD_CREATE,
        "automod_create": EVENT_AUTOMOD_CREATE,
        "automoderationruleupdate": EVENT_AUTOMOD_UPDATE,
        "automod_update": EVENT_AUTOMOD_UPDATE,
        "automoderationruledelete": EVENT_AUTOMOD_DELETE,
        "automod_delete": EVENT_AUTOMOD_DELETE,
        "guildauditlogentrycreate": EVENT_AUDIT_LOG_CREATE,
        "audit_log": EVENT_AUDIT_LOG_CREATE,
        "audit": EVENT_AUDIT_LOG_CREATE,
        "guildscheduledeventdelete": EVENT_SCHEDULED_EVENT_DELETE,
        "event_delete": EVENT_SCHEDULED_EVENT_DELETE,
        "threaddelete": EVENT_THREAD_DELETE,
        "thread_delete": EVENT_THREAD_DELETE,
        "threads": EVENT_THREAD_DELETE,
        "bot_add": EVENT_BOT_ADD,
        "botadd": EVENT_BOT_ADD,
        "bot": EVENT_BOT_ADD,
        "bots": EVENT_BOT_ADD,
    }

    # Dangerous Discord Native Permissions to Audit & Guard
    DANGEROUS_PERMISSIONS = {
        "administrator": "Administrator",
        "manage_guild": "Manage Server",
        "manage_roles": "Manage Roles",
        "manage_channels": "Manage Channels",
        "ban_members": "Ban Members",
        "kick_members": "Kick Members",
        "manage_webhooks": "Manage Webhooks",
    }

    # Ticket Channel Detection Patterns
    TICKET_PATTERNS = [
        re.compile(r"^ticket-", re.IGNORECASE),
        re.compile(r"^tickets-", re.IGNORECASE),
        re.compile(r"^close-", re.IGNORECASE),
        re.compile(r"^closed-", re.IGNORECASE),
        re.compile(r"^transcript-", re.IGNORECASE),
        re.compile(r"^ticket_", re.IGNORECASE),
        re.compile(r"-ticket$", re.IGNORECASE),
    ]

    @classmethod
    def get_enabled_modes(cls) -> List[str]:
        raw = getattr(settings, "ANTINUKE_MODES_ENABLED", ["hard"]) or ["hard"]
        enabled = [m.lower().strip() for m in raw if m.lower().strip() in cls.VALID_MODES]
        return enabled if enabled else [cls.MODE_HARD]

    @classmethod
    def is_mode_enabled(cls, mode: str) -> bool:
        if not mode:
            return False
        return mode.lower().strip() in cls.get_enabled_modes()

    @classmethod
    def normalize_event(cls, name_or_alias: str) -> Optional[str]:
        """Normalizes any event alias or legacy name to its canonical key."""
        if not name_or_alias:
            return None
        cleaned = name_or_alias.strip().lower()
        if cleaned in cls.EVENT_ALIASES:
            return cls.EVENT_ALIASES[cleaned]
        for ev in cls.ALL_EVENTS:
            if ev.lower() == cleaned:
                return ev
        return None

    @classmethod
    def get_event_display_name(cls, event_key: str) -> str:
        """Retrieves localized, friendly event name from Strings.json. Never shows raw keys."""
        canonical = cls.normalize_event(event_key) or event_key
        name_from_strings = get_string(f"security.antinuke.events.{canonical}.name")
        if name_from_strings:
            return name_from_strings

        return re.sub(r"([A-Z])", r" \1", canonical).replace("_", " ").title().strip()

    @classmethod
    def get_event_description(cls, event_key: str) -> str:
        """Retrieves localized event explanation from Strings.json."""
        canonical = cls.normalize_event(event_key) or event_key
        return get_string(f"security.antinuke.events.{canonical}.desc", "Monitored destructive server event.")


def get_default_thresholds(mode: str) -> Dict[str, Dict[str, int]]:
    """Returns default threshold limits and sliding windows based on operating mode."""
    if mode == AntiNukeConstants.MODE_HARD:
        return {event: {"count": 1, "window": 60} for event in AntiNukeConstants.ALL_EVENTS}

    elif mode == AntiNukeConstants.MODE_ULTIMATE:
        return {
            AntiNukeConstants.EVENT_GUILD_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_CHANNEL_CREATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_CHANNEL_DELETE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_ROLE_CREATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_ROLE_UPDATE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_ROLE_DELETE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_MEMBER_UPDATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_MEMBER_REMOVE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_BAN_ADD: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_BAN_REMOVE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_EMOJIS_UPDATE: {"count": 4, "window": 15},
            AntiNukeConstants.EVENT_STICKERS_UPDATE: {"count": 4, "window": 15},
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_INVITE_CREATE: {"count": 4, "window": 10},
            AntiNukeConstants.EVENT_INVITE_DELETE: {"count": 4, "window": 10},
            AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_AUTOMOD_CREATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_AUTOMOD_UPDATE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_AUTOMOD_DELETE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_AUDIT_LOG_CREATE: {"count": 6, "window": 10},
            AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_THREAD_DELETE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_BOT_ADD: {"count": 1, "window": 30},
        }

    else:
        return {
            AntiNukeConstants.EVENT_GUILD_UPDATE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_CHANNEL_CREATE: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_CHANNEL_DELETE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_ROLE_CREATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_ROLE_UPDATE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_ROLE_DELETE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_MEMBER_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_MEMBER_REMOVE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_BAN_ADD: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_BAN_REMOVE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_EMOJIS_UPDATE: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_STICKERS_UPDATE: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_INVITE_CREATE: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_INVITE_DELETE: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_AUTOMOD_CREATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_AUTOMOD_UPDATE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_AUTOMOD_DELETE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_AUDIT_LOG_CREATE: {"count": 4, "window": 15},
            AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_THREAD_DELETE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_BOT_ADD: {"count": 1, "window": 60},
        }


def get_default_punishments(mode: str) -> Dict[str, str]:
    """Returns default punishment actions based on operating mode."""
    if mode == AntiNukeConstants.MODE_HARD:
        return {event: AntiNukeConstants.PUNISH_BAN for event in AntiNukeConstants.ALL_EVENTS}
    elif mode == AntiNukeConstants.MODE_ULTIMATE:
        return {
            AntiNukeConstants.EVENT_GUILD_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_ROLE_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_ROLE_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_ROLE_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_MEMBER_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_MEMBER_REMOVE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_BAN_ADD: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_BAN_REMOVE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_EMOJIS_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_STICKERS_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_INVITE_CREATE: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_INVITE_DELETE: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_AUTOMOD_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_AUTOMOD_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_AUTOMOD_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_AUDIT_LOG_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_THREAD_DELETE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_BOT_ADD: AntiNukeConstants.PUNISH_BAN,
        }
    else:
        return {
            AntiNukeConstants.EVENT_GUILD_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_CHANNEL_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_ROLE_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_ROLE_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_ROLE_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_MEMBER_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_MEMBER_REMOVE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_BAN_ADD: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_BAN_REMOVE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_EMOJIS_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_STICKERS_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_INVITE_CREATE: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_INVITE_DELETE: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_AUTOMOD_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_AUTOMOD_UPDATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_AUTOMOD_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_AUDIT_LOG_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_THREAD_DELETE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_BOT_ADD: AntiNukeConstants.PUNISH_BAN,
        }


class AntiNukeManager:
    """
    Centralized Anti-Nuke Security Manager.
    Handles per-guild security configurations, setup state, threshold evaluation, whitelists,
    extra owners, ticket-bot exemptions, enforcement, and forensic alerting.
    """
    _guild_configs: Dict[str, Dict[str, Any]] = {}
    _event_windows: Dict[Tuple[str, str, str], collections.deque] = {}
    _processed_audit_entries: collections.deque = collections.deque(maxlen=10000)
    _recent_infraction_dedup: Dict[str, float] = {}
    _initialized: bool = False

    @classmethod
    async def initialize(cls) -> None:
        """Hydrate in-memory anti-nuke settings from database."""
        try:
            col = database.collection("antinuke_configs")
            cursor = col.find({})
            records = await cursor.to_list(2000) if hasattr(cursor, "to_list") else await cursor
            for r in (records or []):
                gid = str(r.get("guild_id", ""))
                if gid:
                    cls._guild_configs[gid] = r
            cls._initialized = True
            logger.info(f"[AntiNukeManager] Hydrated Anti-Nuke configurations for {len(cls._guild_configs)} guild(s).")
        except Exception as err:
            cls._initialized = True
            logger.warning(f"[AntiNukeManager] Failed to hydrate antinuke configurations from database: {err}")

    @classmethod
    def is_setup_completed(cls, guild_id: str | int) -> bool:
        """Checks if anti-nuke setup has been completed for a guild."""
        cfg = cls.get_guild_config(str(guild_id))
        return bool(cfg.get("setup_completed", False))

    @classmethod
    def build_setup_required_view(cls, guild: discord.Guild) -> Any:
        """
        Builds the mandatory Components V2 Container when a command is run before setup is complete.
        Structure: Heading -> Separator -> Concise explanation -> Separator -> Configured branding.
        """
        title = get_string(
            "security.antinuke.setup_required.title",
            f"{EMOJIS.get('shield', '🛡️')} Anti-Nuke Setup Required"
        )
        desc = get_string(
            "security.antinuke.setup_required.description",
            (
                f"{EMOJIS.get('warning', '⚠️')} Anti-Nuke protection has not been initialized for this server.\n\n"
                f"To prevent misconfiguration and accidental lockouts, all anti-nuke controls, whitelists, "
                f"and real-time monitoring are locked until the interactive Setup Wizard is completed.\n\n"
                f"Use `$setup` or `$antinuke setup` to begin the guided security configuration."
            )
        )
        footer_text = f"{settings.BOT_NAME} Security Platform • Setup Enforcement"

        action_row = (
            ActionRowBuilder()
            .add_button(
                ButtonBuilder()
                .set_custom_id(f"an_wiz:step1:{guild.id}")
                .set_label("Run Setup Wizard")
                .set_style(ButtonStyle.Primary)
                .set_emoji(EMOJIS.get("wrench", "🔧"))
            )
        )

        return (
            ContainerBuilder()
            .set_accent_color(COLORS.get("warning", "#F59E0B"))
            .add_text_display(f"### {title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(desc)
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"-# {footer_text}")
            .add_action_row(action_row)
            .build()
        )

    @classmethod
    def get_mode_display_name(cls, mode: str) -> str:
        """Retrieves localized display name for the operating mode from Strings.json."""
        localized = get_string(f"security.antinuke.modes.{mode}")
        if localized:
            return localized
        if mode == AntiNukeConstants.MODE_HARD:
            return "Hard (Zero-Tolerance)"
        elif mode == AntiNukeConstants.MODE_ULTIMATE:
            return "Ultimate Defence Wall (Disabled)"
        elif mode == AntiNukeConstants.MODE_HYBRID:
            return "Hybrid Defense (Disabled)"
        return mode.title()

    @classmethod
    def get_guild_config(cls, guild_id: str) -> Dict[str, Any]:
        """Returns the guild's Anti-Nuke configuration, initialized with defaults if not present."""
        gid = str(guild_id)
        if gid in cls._guild_configs:
            cfg = cls._guild_configs[gid]
            # Ensure disabled modes fall back to an enabled mode
            if not AntiNukeConstants.is_mode_enabled(cfg.get("mode", "")):
                cfg["mode"] = AntiNukeConstants.MODE_HARD
            return cfg

        default_mode = AntiNukeConstants.MODE_HARD
        default_config = {
            "guild_id": gid,
            "setup_completed": False,
            "enabled": False,
            "mode": default_mode,
            "monitored_events": list(AntiNukeConstants.ALL_EVENTS),
            "extra_owners": [],
            "whitelists": {},  # entity_id (str) -> {"type": "user"|"role"|"channel"|"category", "name": str, "events": list[str]}
            "ticket_bots": [],  # list of bot user IDs exempt from ticket channel operations
            "warning_channel_id": None,
            "log_channel_id": None,
            "webhook_url": None,
            "thresholds": get_default_thresholds(default_mode),
            "punishments": get_default_punishments(default_mode),
            "quarantine_role_id": None,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        cls._guild_configs[gid] = default_config
        return default_config

    @classmethod
    async def save_guild_config(cls, guild_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Persists updates to a guild's Anti-Nuke configuration."""
        gid = str(guild_id)
        cfg = cls.get_guild_config(gid)
        cfg.update(updates)
        cfg["updated_at"] = time.time()
        cls._guild_configs[gid] = cfg

        try:
            col = database.collection("antinuke_configs")
            await col.update_one({"guild_id": gid}, {"$set": cfg}, upsert=True)
        except Exception as err:
            logger.error(f"[AntiNukeManager] Failed to persist config for guild {gid}: {err}")

        return cfg

    @classmethod
    def is_owner_or_extra_owner(cls, guild: discord.Guild, user_id: int | str) -> bool:
        """Validates if user is Server Owner, Bot Owner, or configured Extra Owner."""
        uid_str = str(user_id)
        if guild and guild.owner_id and str(guild.owner_id) == uid_str:
            return True
        if is_bot_owner(uid_str):
            return True
        if guild:
            cfg = cls.get_guild_config(str(guild.id))
            if uid_str in [str(x) for x in cfg.get("extra_owners", [])]:
                return True
        return False

    @classmethod
    def is_whitelisted(
        cls,
        guild_id: str,
        executor: discord.Member | discord.User,
        event_type: str,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> bool:
        """Checks if an entity is whitelisted for a specific event with target-type awareness."""
        cfg = cls.get_guild_config(str(guild_id))
        whitelists = cfg.get("whitelists", {})
        if not whitelists:
            return False

        canonical_event = AntiNukeConstants.normalize_event(event_type) or event_type

        def _event_matches(allowed_events: Any) -> bool:
            if not isinstance(allowed_events, list):
                return False
            if "*" in allowed_events or "all" in allowed_events:
                return True
            for ev in allowed_events:
                if (AntiNukeConstants.normalize_event(ev) or ev) == canonical_event:
                    return True
            return False

        executor_id = str(executor.id) if hasattr(executor, "id") else str(executor)

        # 1. User check
        if executor_id in whitelists:
            data = whitelists[executor_id]
            allowed = data.get("events", []) if isinstance(data, dict) else data
            if _event_matches(allowed):
                return True

        # 2. Role check (if executor has roles)
        if hasattr(executor, "roles"):
            for role in (getattr(executor, "roles", None) or []):
                role_id = str(role.id)
                if role_id in whitelists:
                    data = whitelists[role_id]
                    allowed = data.get("events", []) if isinstance(data, dict) else data
                    if _event_matches(allowed):
                        return True

        # 3. Channel check
        if channel:
            ch_id = str(channel.id)
            if ch_id in whitelists:
                data = whitelists[ch_id]
                allowed = data.get("events", []) if isinstance(data, dict) else data
                if _event_matches(allowed):
                    return True

            # 4. Category check
            category_id = str(channel.category.id) if getattr(channel, "category", None) else None
            if category_id and category_id in whitelists:
                data = whitelists[category_id]
                allowed = data.get("events", []) if isinstance(data, dict) else data
                if _event_matches(allowed):
                    return True

        return False

    @classmethod
    def is_ticket_bot_exempt(
        cls,
        guild: discord.Guild,
        user_id: int | str,
        event_type: str,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> bool:
        """Validates whether an approved ticket bot is exempt from false positives."""
        cfg = cls.get_guild_config(str(guild.id))
        uid_str = str(user_id)

        if uid_str not in [str(x) for x in cfg.get("ticket_bots", [])]:
            return False

        canonical_event = AntiNukeConstants.normalize_event(event_type) or event_type
        if canonical_event not in [
            AntiNukeConstants.EVENT_CHANNEL_CREATE,
            AntiNukeConstants.EVENT_CHANNEL_DELETE,
            AntiNukeConstants.EVENT_CHANNEL_UPDATE,
            AntiNukeConstants.EVENT_THREAD_DELETE,
        ]:
            return False

        if channel:
            ch_name = getattr(channel, "name", "").lower()
            ch_topic = getattr(channel, "topic", "") or ""
            category_name = getattr(channel.category, "name", "").lower() if getattr(channel, "category", None) else ""

            for pat in AntiNukeConstants.TICKET_PATTERNS:
                if pat.search(ch_name):
                    return True

            if "ticket" in category_name or "tickets" in category_name or "ticket" in ch_topic.lower():
                return True

            return False

        return True

    @classmethod
    def check_hierarchy_and_permissions(
        cls,
        guild: discord.Guild,
        target: Optional[discord.Member] = None,
        required_perm_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Audits Discord role hierarchy and bot permissions."""
        me = getattr(guild, "me", None)
        if not me:
            return {"can_act": False, "reason": "Bot member is not present in guild."}

        if not me.guild_permissions.administrator:
            needed = {
                "ban": me.guild_permissions.ban_members,
                "kick": me.guild_permissions.kick_members,
                "manage_roles": me.guild_permissions.manage_roles,
                "manage_channels": me.guild_permissions.manage_channels,
                "view_audit_log": me.guild_permissions.view_audit_log,
            }
            if required_perm_name and not needed.get(required_perm_name, False):
                return {
                    "can_act": False,
                    "reason": f"Bot is missing required Discord permission: `{required_perm_name}`."
                }

        if target:
            if target.id == guild.owner_id:
                return {"can_act": False, "reason": "Target is the Server Owner; Discord prevents all bot actions."}
            if target.id == me.id:
                return {"can_act": False, "reason": "Target is the bot itself."}
            if target.top_role >= me.top_role:
                return {
                    "can_act": False,
                    "reason": f"Target's highest role ({target.top_role.name}) is higher than or equal to {settings.BOT_NAME}'s role ({me.top_role.name})."
                }

        return {"can_act": True, "reason": "Bot has adequate hierarchy and permissions."}

    @classmethod
    async def record_and_evaluate_infraction(
        cls,
        guild: discord.Guild,
        executor: discord.Member | discord.User,
        event_type: str,
        audit_entry_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> Dict[str, Any]:
        """Core anti-nuke evaluation and rate-limiting pipeline."""
        if not guild or not executor:
            return {"action_taken": None, "reason": "Invalid guild or executor"}

        cfg = cls.get_guild_config(str(guild.id))

        if not cfg.get("enabled", False):
            return {"action_taken": None, "reason": "Anti-Nuke is disabled for this server"}

        canonical_event = AntiNukeConstants.normalize_event(event_type) or event_type

        monitored = cfg.get("monitored_events", AntiNukeConstants.ALL_EVENTS)
        if canonical_event not in monitored and "*" not in monitored:
            return {"action_taken": None, "reason": f"Event {canonical_event} is not in monitored events"}

        if audit_entry_id:
            if audit_entry_id in cls._processed_audit_entries:
                return {"action_taken": None, "reason": "Duplicate audit entry already processed"}
            cls._processed_audit_entries.append(audit_entry_id)

        executor_id = str(executor.id)
        me = getattr(guild, "me", None)
        if me and executor_id == str(me.id):
            return {"action_taken": None, "reason": "Executor is the bot itself"}

        if cls.is_owner_or_extra_owner(guild, executor_id):
            return {"action_taken": None, "reason": "Executor is Server Owner or Extra Owner"}

        if cls.is_whitelisted(str(guild.id), executor, canonical_event, channel):
            return {"action_taken": None, "reason": f"Executor or target is whitelisted for {canonical_event}"}

        if getattr(executor, "bot", False) and cls.is_ticket_bot_exempt(guild, executor_id, canonical_event, channel):
            return {"action_taken": None, "reason": f"Ticket bot {executor_id} exempt for ticket channel operation"}

        dedup_key = f"{guild.id}:{executor_id}:{canonical_event}:{audit_entry_id or time.time() // 2}"
        now = time.time()
        if dedup_key in cls._recent_infraction_dedup:
            if now - cls._recent_infraction_dedup[dedup_key] < 3.0:
                return {"action_taken": None, "reason": "Deduplicated rapid duplicate event"}
        cls._recent_infraction_dedup[dedup_key] = now

        mode = cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE)
        thresholds = cfg.get("thresholds", {}).get(canonical_event) or get_default_thresholds(mode).get(canonical_event, {"count": 1, "window": 60})
        limit_count = thresholds.get("count", 1)
        window_seconds = thresholds.get("window", 60)

        key = (str(guild.id), executor_id, canonical_event)
        if key not in cls._event_windows:
            cls._event_windows[key] = collections.deque()

        dq = cls._event_windows[key]
        dq.append(now)

        while dq and dq[0] < now - window_seconds:
            dq.popleft()

        current_count = len(dq)
        if current_count < limit_count:
            return {
                "action_taken": None,
                "current_count": current_count,
                "limit_count": limit_count,
                "reason": "Within safe threshold"
            }

        punishments = cfg.get("punishments", {})
        default_punish = get_default_punishments(mode).get(canonical_event, AntiNukeConstants.PUNISH_BAN)
        punishment = punishments.get(canonical_event, default_punish)

        action_result = await cls._execute_punishment(guild, executor, punishment, canonical_event, details)

        incident_doc = {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "executor_id": executor_id,
            "executor_name": str(executor),
            "is_bot": bool(getattr(executor, "bot", False)),
            "event_type": canonical_event,
            "count": current_count,
            "threshold": limit_count,
            "window": window_seconds,
            "punishment": punishment,
            "action_result": action_result,
            "details": details or {},
            "timestamp": now,
        }
        try:
            col = database.collection("antinuke_logs")
            await col.insert_one(incident_doc)
        except Exception as err:
            logger.error(f"[AntiNukeManager] Failed to log security incident to database: {err}")

        asyncio.create_task(
            cls._send_security_alert(
                guild, executor, canonical_event, current_count, limit_count, window_seconds, punishment, action_result, details or {}
            )
        )

        return {
            "action_taken": punishment,
            "action_result": action_result,
            "current_count": current_count,
            "limit_count": limit_count,
        }

    @classmethod
    async def _execute_punishment(
        cls,
        guild: discord.Guild,
        executor: discord.Member | discord.User,
        punishment: str,
        event_type: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Applies configured punishment adhering strictly to role hierarchy safety."""
        target_member: Optional[discord.Member] = None
        if isinstance(executor, discord.Member):
            target_member = executor
        else:
            try:
                target_member = await guild.fetch_member(executor.id)
            except Exception:
                target_member = None

        hierarchy_check = cls.check_hierarchy_and_permissions(guild, target_member)
        if not hierarchy_check.get("can_act"):
            logger.warning(f"[AntiNuke] Cannot punish {executor} ({executor.id}): {hierarchy_check.get('reason')}")
            return {"success": False, "error": hierarchy_check.get("reason")}

        friendly_event = AntiNukeConstants.get_event_display_name(event_type)
        reason = f"{settings.BOT_NAME} Anti-Nuke: Threshold exceeded for {friendly_event}."

        try:
            if punishment == AntiNukeConstants.PUNISH_BAN:
                await guild.ban(executor, reason=reason, delete_message_days=1)
                return {"success": True, "punishment": "ban"}

            elif punishment == AntiNukeConstants.PUNISH_KICK:
                if target_member:
                    await target_member.kick(reason=reason)
                    return {"success": True, "punishment": "kick"}
                return {"success": False, "error": "Member not in guild to kick"}

            elif punishment == AntiNukeConstants.PUNISH_TIMEOUT:
                if target_member and hasattr(target_member, "timeout"):
                    import datetime
                    timeout_until = discord.utils.utcnow() + datetime.timedelta(days=28)
                    await target_member.timeout(timeout_until, reason=reason)
                    return {"success": True, "punishment": "timeout"}
                return {"success": False, "error": "Member cannot be timed out"}

            elif punishment == AntiNukeConstants.PUNISH_STRIP_ROLES:
                if target_member:
                    me = guild.me
                    roles_to_remove = [r for r in target_member.roles if r < me.top_role and not r.is_default()]
                    if roles_to_remove:
                        await target_member.remove_roles(*roles_to_remove, reason=reason)
                    return {"success": True, "punishment": "strip_roles", "stripped_roles": [r.name for r in roles_to_remove]}
                return {"success": False, "error": "Member not in guild to strip roles"}

            elif punishment == AntiNukeConstants.PUNISH_PRUNE:
                if target_member:
                    await target_member.kick(reason=f"{reason} (Prune)")
                    return {"success": True, "punishment": "prune"}
                return {"success": False, "error": "Member not in guild to prune"}

            elif punishment == AntiNukeConstants.PUNISH_QUARANTINE:
                if target_member:
                    me = guild.me
                    roles_to_remove = [r for r in target_member.roles if r < me.top_role and not r.is_default()]
                    if roles_to_remove:
                        await target_member.remove_roles(*roles_to_remove, reason=reason)
                    cfg = cls.get_guild_config(str(guild.id))
                    q_role_id = cfg.get("quarantine_role_id")
                    if q_role_id:
                        q_role = guild.get_role(int(q_role_id))
                        if q_role and q_role < me.top_role:
                            await target_member.add_roles(q_role, reason="Quarantined by Anti-Nuke")
                    return {"success": True, "punishment": "quarantine", "stripped_roles": [r.name for r in roles_to_remove]}
                return {"success": False, "error": "Member not found to quarantine"}

        except Exception as err:
            logger.error(f"[AntiNuke] Execution error enforcing {punishment} on {executor.id}: {err}")
            return {"success": False, "error": str(err)}

        return {"success": False, "error": f"Unknown punishment {punishment}"}

    @classmethod
    async def _send_security_alert(
        cls,
        guild: discord.Guild,
        executor: discord.Member | discord.User,
        event_type: str,
        count: int,
        threshold: int,
        window: int,
        punishment: str,
        action_result: Dict[str, Any],
        details: Dict[str, Any],
    ) -> None:
        """Sends formatted forensic alert adhering to Components V2 container standards."""
        cfg = cls.get_guild_config(str(guild.id))
        warning_channel_id = cfg.get("warning_channel_id") or cfg.get("log_channel_id")
        webhook_url = cfg.get("webhook_url")

        is_bot = bool(getattr(executor, "bot", False))
        executor_type = "Automated Bot Account" if is_bot else "User Account"
        friendly_event = AntiNukeConstants.get_event_display_name(event_type)

        alert_title = get_string(
            "security.antinuke.alert_title_bot" if is_bot else "security.antinuke.alert_title_user",
            f"Forensic Alert: Unauthorized {'Bot' if is_bot else 'User'} Operation Blocked"
        )

        rec_key = f"security.antinuke.rec_{event_type}"
        default_recs = {
            AntiNukeConstants.EVENT_BAN_ADD: "Audit recent bans in Server Settings -> Audit Log to identify affected members.",
            AntiNukeConstants.EVENT_MEMBER_REMOVE: "Verify if executor account was compromised and revoke dangerous moderator roles.",
            AntiNukeConstants.EVENT_BOT_ADD: "The unauthorized bot was expelled immediately. Audit who invited the bot.",
            AntiNukeConstants.EVENT_ROLE_DELETE: "Role deletion detected. Re-create the role and check role hierarchy.",
            AntiNukeConstants.EVENT_ROLE_UPDATE: "Dangerous permissions were added. Revert role permissions immediately.",
            AntiNukeConstants.EVENT_CHANNEL_DELETE: "Channel deletion burst blocked. Review channel audit logs and secure credentials.",
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE: "Rogue webhook activity intercepted. Inspect channel integrations to purge rogue webhooks.",
        }
        recommendation = get_string(rec_key, default_recs.get(event_type, "Review recent server audit logs and secure staff accounts."))

        alert_body = (
            f"• **Guild:** `{guild.name}` (`{guild.id}`)\n"
            f"• **Culprit:** `{executor}` (`{executor.id}`)\n"
            f"• **Category:** `{executor_type}`\n"
            f"• **Event Triggered:** **{friendly_event}**\n"
            f"• **Burst Rate:** `{count}` action(s) in `{window}s` (Threshold: {threshold})\n"
            f"• **Disciplinary Action:** **`{punishment.upper()}`**\n"
            f"• **Logged At:** <t:{int(time.time())}:F> (<t:{int(time.time())}:R>)"
        )

        container = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('danger', '⚠️')} {alert_title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(alert_body)
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"**Recommended Staff Action:**\n{recommendation}")
            .set_footer(f"{settings.BOT_NAME} Security Sentinel • Incident Record")
            .build()
        )

        if webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "username": f"{settings.BOT_NAME} Security Sentinel",
                        "avatar_url": str(guild.me.display_avatar.url) if (guild.me and hasattr(guild.me, "display_avatar")) else None,
                        "embeds": [
                            {
                                "title": alert_title,
                                "description": f"{alert_body}\n\n**Recommended Staff Action:**\n{recommendation}",
                                "color": int(COLORS.get("error", "#B21F1F").replace("#", ""), 16),
                                "footer": {"text": f"{settings.BOT_NAME} Security Platform • Webhook Log"},
                                "timestamp": discord.utils.utcnow().isoformat(),
                            }
                        ]
                    }
                    async with session.post(webhook_url, json=payload, timeout=5) as resp:
                        if resp.status in (200, 204):
                            return
            except Exception as w_err:
                logger.warning(f"[AntiNuke] Webhook logging failed: {w_err}")

        if warning_channel_id:
            ch = guild.get_channel(int(warning_channel_id))
            if ch and hasattr(ch, "send"):
                try:
                    await ch.send(view=container)
                except Exception as ch_err:
                    logger.error(f"[AntiNuke] Failed to send alert message to channel {warning_channel_id}: {ch_err}")

    @classmethod
    def get_registered_events_diagnostics(cls) -> Dict[str, Any]:
        """Audits all 24 monitored event vectors and provides startup/runtime diagnostics."""
        from apps.bot.discord.events.registry import events_registry
        registered_events = set()
        for evt in events_registry.list_all():
            registered_events.add(evt.name)

        # Mapping of canonical event to required discord.py event handler name
        vector_mappings = {
            AntiNukeConstants.EVENT_GUILD_UPDATE: "on_guild_update",
            AntiNukeConstants.EVENT_CHANNEL_CREATE: "on_guild_channel_create",
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: "on_guild_channel_update",
            AntiNukeConstants.EVENT_CHANNEL_DELETE: "on_guild_channel_delete",
            AntiNukeConstants.EVENT_ROLE_CREATE: "on_guild_role_create",
            AntiNukeConstants.EVENT_ROLE_UPDATE: "on_guild_role_update",
            AntiNukeConstants.EVENT_ROLE_DELETE: "on_guild_role_delete",
            AntiNukeConstants.EVENT_MEMBER_UPDATE: "on_member_update",
            AntiNukeConstants.EVENT_MEMBER_REMOVE: "on_member_remove",
            AntiNukeConstants.EVENT_BAN_ADD: "on_member_ban",
            AntiNukeConstants.EVENT_BAN_REMOVE: "on_member_unban",
            AntiNukeConstants.EVENT_EMOJIS_UPDATE: "on_guild_emojis_update",
            AntiNukeConstants.EVENT_STICKERS_UPDATE: "on_guild_stickers_update",
            AntiNukeConstants.EVENT_WEBHOOKS_UPDATE: "on_webhooks_update",
            AntiNukeConstants.EVENT_INVITE_CREATE: "on_invite_create",
            AntiNukeConstants.EVENT_INVITE_DELETE: "on_invite_delete",
            AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE: "on_guild_integrations_update",
            AntiNukeConstants.EVENT_AUTOMOD_CREATE: "on_auto_moderation_rule_create",
            AntiNukeConstants.EVENT_AUTOMOD_UPDATE: "on_auto_moderation_rule_update",
            AntiNukeConstants.EVENT_AUTOMOD_DELETE: "on_auto_moderation_rule_delete",
            AntiNukeConstants.EVENT_AUDIT_LOG_CREATE: "on_audit_log_entry_create",
            AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE: "on_scheduled_event_delete",
            AntiNukeConstants.EVENT_THREAD_DELETE: "on_thread_delete",
            AntiNukeConstants.EVENT_BOT_ADD: "on_member_join",
        }

        active = []
        missing = []
        for canonical, handler_name in vector_mappings.items():
            if handler_name in registered_events:
                active.append({"canonical": canonical, "handler": handler_name, "status": "active"})
            else:
                missing.append({"canonical": canonical, "handler": handler_name, "status": "missing"})

        return {
            "total_monitored": len(vector_mappings),
            "registered_count": len(active),
            "missing_count": len(missing),
            "active_vectors": active,
            "missing_vectors": missing,
            "all_registered": len(missing) == 0,
        }

