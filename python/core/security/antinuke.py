import time
import asyncio
import re
import collections
from typing import Dict, Any, List, Optional, Set, Tuple
import aiohttp
import discord

from config.settings import settings, COLORS, EMOJIS
from config.strings import get_string
from core.logging.logger import logger
from database.database import database
from apps.bot.discord.permissions.resolver import is_bot_owner
from sdk.discord.builders import ContainerBuilder, ActionRowBuilder, ButtonBuilder, SeparatorSpacingSize


class AntiNukeConstants:
    # Operating Modes
    MODE_HARD = "hard"
    MODE_ULTIMATE = "ultimate"
    MODE_HYBRID = "hybrid"
    VALID_MODES = [MODE_HARD, MODE_ULTIMATE, MODE_HYBRID]

    # Punishments
    PUNISH_BAN = "ban"
    PUNISH_KICK = "kick"
    PUNISH_QUARANTINE = "quarantine"
    PUNISH_TIMEOUT = "timeout"
    VALID_PUNISHMENTS = [PUNISH_BAN, PUNISH_KICK, PUNISH_QUARANTINE, PUNISH_TIMEOUT]

    # Events Monitored
    EVENT_BAN = "ban"
    EVENT_KICK = "kick"
    EVENT_TIMEOUT = "timeout"
    EVENT_BOT_ADD = "bot_add"
    EVENT_ROLE_CREATE = "role_create"
    EVENT_ROLE_DELETE = "role_delete"
    EVENT_ROLE_UPDATE = "role_update"
    EVENT_CHANNEL_CREATE = "channel_create"
    EVENT_CHANNEL_DELETE = "channel_delete"
    EVENT_CHANNEL_UPDATE = "channel_update"
    EVENT_WEBHOOK_CREATE = "webhook_create"
    EVENT_WEBHOOK_DELETE = "webhook_delete"
    EVENT_WEBHOOK_UPDATE = "webhook_update"
    EVENT_MEMBER_UPDATE = "member_update"

    ALL_EVENTS = [
        EVENT_BAN,
        EVENT_KICK,
        EVENT_TIMEOUT,
        EVENT_BOT_ADD,
        EVENT_ROLE_CREATE,
        EVENT_ROLE_DELETE,
        EVENT_ROLE_UPDATE,
        EVENT_CHANNEL_CREATE,
        EVENT_CHANNEL_DELETE,
        EVENT_CHANNEL_UPDATE,
        EVENT_WEBHOOK_CREATE,
        EVENT_WEBHOOK_DELETE,
        EVENT_WEBHOOK_UPDATE,
        EVENT_MEMBER_UPDATE,
    ]

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


def get_default_thresholds(mode: str) -> Dict[str, Dict[str, int]]:
    """Returns default threshold limits and sliding windows based on operating mode."""
    if mode == AntiNukeConstants.MODE_HARD:
        # Hard mode: 1 action in 60 seconds triggers zero-tolerance punishment
        return {event: {"count": 1, "window": 60} for event in AntiNukeConstants.ALL_EVENTS}

    elif mode == AntiNukeConstants.MODE_ULTIMATE:
        # Ultimate Defence Wall: Configurable sliding burst thresholds
        return {
            AntiNukeConstants.EVENT_BOT_ADD: {"count": 1, "window": 30},
            AntiNukeConstants.EVENT_BAN: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_KICK: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_TIMEOUT: {"count": 4, "window": 10},
            AntiNukeConstants.EVENT_ROLE_CREATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_ROLE_DELETE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_ROLE_UPDATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_CHANNEL_CREATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_CHANNEL_DELETE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_WEBHOOK_CREATE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_WEBHOOK_DELETE: {"count": 2, "window": 10},
            AntiNukeConstants.EVENT_WEBHOOK_UPDATE: {"count": 3, "window": 10},
            AntiNukeConstants.EVENT_MEMBER_UPDATE: {"count": 3, "window": 10},
        }

    else:
        # Hybrid mode: Instant zero-tolerance on bot additions & dangerous permissions, sliding burst on channels & roles
        return {
            AntiNukeConstants.EVENT_BOT_ADD: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_BAN: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_KICK: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_TIMEOUT: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_ROLE_CREATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_ROLE_DELETE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_ROLE_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_CHANNEL_CREATE: {"count": 3, "window": 15},
            AntiNukeConstants.EVENT_CHANNEL_DELETE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_WEBHOOK_CREATE: {"count": 1, "window": 60},
            AntiNukeConstants.EVENT_WEBHOOK_DELETE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_WEBHOOK_UPDATE: {"count": 2, "window": 15},
            AntiNukeConstants.EVENT_MEMBER_UPDATE: {"count": 2, "window": 15},
        }


def get_default_punishments(mode: str) -> Dict[str, str]:
    """Returns default punishment actions based on operating mode."""
    if mode == AntiNukeConstants.MODE_HARD:
        return {event: AntiNukeConstants.PUNISH_BAN for event in AntiNukeConstants.ALL_EVENTS}
    elif mode == AntiNukeConstants.MODE_ULTIMATE:
        return {
            AntiNukeConstants.EVENT_BOT_ADD: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_BAN: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_KICK: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_TIMEOUT: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_ROLE_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_ROLE_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_ROLE_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_WEBHOOK_CREATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_WEBHOOK_DELETE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_WEBHOOK_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_MEMBER_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
        }
    else:
        # Hybrid
        return {
            AntiNukeConstants.EVENT_BOT_ADD: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_BAN: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_KICK: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_TIMEOUT: AntiNukeConstants.PUNISH_TIMEOUT,
            AntiNukeConstants.EVENT_ROLE_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_ROLE_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_ROLE_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_CREATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_CHANNEL_DELETE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_CHANNEL_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_WEBHOOK_CREATE: AntiNukeConstants.PUNISH_BAN,
            AntiNukeConstants.EVENT_WEBHOOK_DELETE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_WEBHOOK_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
            AntiNukeConstants.EVENT_MEMBER_UPDATE: AntiNukeConstants.PUNISH_QUARANTINE,
        }


class AntiNukeManager:
    """
    Centralized Anti-Nuke Security Manager.
    Handles per-guild security configurations, threshold evaluation, whitelists,
    extra owners, ticket-bot exemptions, enforcement, and forensic alerting.
    """
    _guild_configs: Dict[str, Dict[str, Any]] = {}
    _event_windows: Dict[Tuple[str, str, str], collections.deque] = {}  # (guild_id, executor_id, event) -> deque of timestamps
    _processed_audit_entries: collections.deque = collections.deque(maxlen=10000)
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
    def get_mode_display_name(cls, mode: str) -> str:
        """Retrieves localized display name for the operating mode from Strings.json."""
        default_names = {
            AntiNukeConstants.MODE_HARD: "Hard Zero-Tolerance",
            AntiNukeConstants.MODE_ULTIMATE: "Ultimate Defence Wall",
            AntiNukeConstants.MODE_HYBRID: "Hybrid Dynamic Defense",
        }
        return get_string(f"security.antinuke.mode_names.{mode}", default_names.get(mode, mode.title()))

    @classmethod
    def get_guild_config(cls, guild_id: str) -> Dict[str, Any]:
        """Returns the guild's Anti-Nuke configuration, initialized with defaults if not present."""
        gid = str(guild_id)
        if gid in cls._guild_configs:
            return cls._guild_configs[gid]

        default_mode = AntiNukeConstants.MODE_ULTIMATE
        default_config = {
            "guild_id": gid,
            "enabled": False,
            "mode": default_mode,
            "extra_owners": [],
            "whitelists": {},  # entity_id (str) -> list of allowed event strings (e.g. ["*"] or ["channel_create"])
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
    def is_whitelisted(cls, guild_id: str, user_id: int | str, event_type: str) -> bool:
        """Checks if a user or bot is whitelisted for a specific event."""
        cfg = cls.get_guild_config(str(guild_id))
        whitelists = cfg.get("whitelists", {})
        uid_str = str(user_id)
        if uid_str not in whitelists:
            return False

        allowed = whitelists[uid_str]
        if not isinstance(allowed, list):
            return False

        return ("*" in allowed or "all" in allowed or event_type in allowed)

    @classmethod
    def is_ticket_bot_exempt(
        cls,
        guild: discord.Guild,
        user_id: int | str,
        event_type: str,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> bool:
        """
        Validates whether an approved ticket bot is exempt from false positives.
        Allows ticket bots to create, delete, or edit channels matching ticket patterns.
        Retains strict security protection against unrelated destructive actions
        (such as bans, kicks, role deletions, and webhooks).
        """
        cfg = cls.get_guild_config(str(guild.id))
        uid_str = str(user_id)

        # Check if the bot is in the approved ticket bot registry
        if uid_str not in [str(x) for x in cfg.get("ticket_bots", [])]:
            return False

        # Only channel events can be exempt for ticket bots
        if event_type not in [
            AntiNukeConstants.EVENT_CHANNEL_CREATE,
            AntiNukeConstants.EVENT_CHANNEL_DELETE,
            AntiNukeConstants.EVENT_CHANNEL_UPDATE,
        ]:
            return False

        # If a channel object is available, verify it follows ticket naming or category
        if channel:
            ch_name = getattr(channel, "name", "").lower()
            ch_topic = getattr(channel, "topic", "") or ""
            category_name = getattr(channel.category, "name", "").lower() if getattr(channel, "category", None) else ""

            # Check name regex patterns
            for pat in AntiNukeConstants.TICKET_PATTERNS:
                if pat.search(ch_name):
                    return True

            # Check ticket category or topic markers
            if "ticket" in category_name or "tickets" in category_name or "ticket" in ch_topic.lower():
                return True

            # If no channel metadata matched ticket pattern, deny exemption to prevent rogue destruction
            return False

        # Channel creation/deletion without channel instance available (rare)
        return True

    @classmethod
    def check_hierarchy_and_permissions(
        cls,
        guild: discord.Guild,
        target: Optional[discord.Member] = None,
        required_perm_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Audits Discord role hierarchy and bot permissions.
        NEVER claims protection against roles or permissions the bot cannot control.
        """
        me = getattr(guild, "me", None)
        if not me:
            return {"can_act": False, "reason": "Bot member is not present in guild."}

        # Check bot native permissions
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

        # Check role hierarchy if target member is provided
        if target:
            if target.id == guild.owner_id:
                return {"can_act": False, "reason": "Target is the Server Owner; Discord prevents all bot actions."}
            if target.id == me.id:
                return {"can_act": False, "reason": "Target is the bot itself."}
            if target.top_role >= me.top_role:
                return {
                    "can_act": False,
                    "reason": f"Target's highest role ({target.top_role.name}) is higher than or equal to MomentumOne's role ({me.top_role.name})."
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
        """
        Core anti-nuke evaluation pipeline:
        1. Validates if Anti-Nuke is active.
        2. Deduplicates repeated audit-log polling events.
        3. Checks exemptions (Owner, Extra Owner, Bot, Whitelist, Ticket Bot).
        4. Evaluates sliding window thresholds.
        5. Executes punishment if threshold exceeded.
        6. Dispatches forensic security warning to webhook / alert channel.
        """
        if not guild or not executor:
            return {"action_taken": None, "reason": "Invalid guild or executor"}

        cfg = cls.get_guild_config(str(guild.id))
        if not cfg.get("enabled", False):
            return {"action_taken": None, "reason": "Anti-Nuke is disabled for this server"}

        # Check duplicate audit-log entry
        if audit_entry_id:
            if audit_entry_id in cls._processed_audit_entries:
                return {"action_taken": None, "reason": "Duplicate audit entry already processed"}
            cls._processed_audit_entries.append(audit_entry_id)

        executor_id = str(executor.id)
        me = getattr(guild, "me", None)
        if me and executor_id == str(me.id):
            return {"action_taken": None, "reason": "Executor is the bot itself"}

        # Exemption 1: Server Owner or Extra Owners
        if cls.is_owner_or_extra_owner(guild, executor_id):
            return {"action_taken": None, "reason": "Executor is Server Owner or Extra Owner"}

        # Exemption 2: Whitelist
        if cls.is_whitelisted(str(guild.id), executor_id, event_type):
            return {"action_taken": None, "reason": f"Executor is whitelisted for {event_type}"}

        # Exemption 3: Ticket Bot Exemption
        if getattr(executor, "bot", False) and cls.is_ticket_bot_exempt(guild, executor_id, event_type, channel):
            return {"action_taken": None, "reason": f"Ticket bot {executor_id} exempt for ticket channel operation"}

        # Evaluate sliding window
        now = time.time()
        mode = cfg.get("mode", AntiNukeConstants.MODE_ULTIMATE)
        thresholds = cfg.get("thresholds", {}).get(event_type) or get_default_thresholds(mode).get(event_type, {"count": 1, "window": 60})
        limit_count = thresholds.get("count", 1)
        window_seconds = thresholds.get("window", 60)

        key = (str(guild.id), executor_id, event_type)
        if key not in cls._event_windows:
            cls._event_windows[key] = collections.deque()

        dq = cls._event_windows[key]
        dq.append(now)

        # Evict timestamps outside sliding window
        while dq and dq[0] < now - window_seconds:
            dq.popleft()

        current_count = len(dq)
        if current_count < limit_count:
            # Under threshold limit: log warning state if nearing limit
            return {
                "action_taken": None,
                "current_count": current_count,
                "limit_count": limit_count,
                "reason": "Within safe threshold"
            }

        # Threshold reached or exceeded! Determine punishment
        punishments = cfg.get("punishments", {})
        default_punish = get_default_punishments(mode).get(event_type, AntiNukeConstants.PUNISH_BAN)
        punishment = punishments.get(event_type, default_punish)

        action_result = await cls._execute_punishment(guild, executor, punishment, event_type, details)

        # Log security incident to database
        incident_doc = {
            "guild_id": str(guild.id),
            "guild_name": guild.name,
            "executor_id": executor_id,
            "executor_name": str(executor),
            "is_bot": bool(getattr(executor, "bot", False)),
            "event_type": event_type,
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

        # Send security warning and forensic recommendation
        asyncio.create_task(cls._send_security_alert(guild, executor, event_type, current_count, limit_count, window_seconds, punishment, action_result, details or {}))

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

        reason = f"MomentumOne Anti-Nuke: Threshold exceeded for {event_type}."

        try:
            if punishment == AntiNukeConstants.PUNISH_BAN:
                await guild.ban(executor, reason=reason, delete_message_days=1)
                return {"success": True, "punishment": "ban"}

            elif punishment == AntiNukeConstants.PUNISH_KICK:
                if target_member:
                    await target_member.kick(reason=reason)
                    return {"success": True, "punishment": "kick"}
                else:
                    return {"success": False, "error": "Member not in guild to kick"}

            elif punishment == AntiNukeConstants.PUNISH_TIMEOUT:
                if target_member and hasattr(target_member, "timeout"):
                    timeout_until = discord.utils.utcnow() + datetime_timedelta(days=28)
                    await target_member.timeout(timeout_until, reason=reason)
                    return {"success": True, "punishment": "timeout"}
                else:
                    return {"success": False, "error": "Member cannot be timed out"}

            elif punishment == AntiNukeConstants.PUNISH_QUARANTINE:
                # Quarantine: Strip all manageable dangerous roles from attacker
                if target_member:
                    me = guild.me
                    roles_to_remove = [r for r in target_member.roles if r < me.top_role and not r.is_default()]
                    if roles_to_remove:
                        await target_member.remove_roles(*roles_to_remove, reason=reason)
                    # If a specific quarantine role is configured, apply it
                    cfg = cls.get_guild_config(str(guild.id))
                    q_role_id = cfg.get("quarantine_role_id")
                    if q_role_id:
                        q_role = guild.get_role(int(q_role_id))
                        if q_role and q_role < me.top_role:
                            await target_member.add_roles(q_role, reason="Quarantined by Anti-Nuke")
                    return {"success": True, "punishment": "quarantine", "stripped_roles": [r.name for r in roles_to_remove]}
                else:
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
        """
        Sends formatted forensic security warning to configured warning channel.
        Prefers Discord Webhook delivery with bot-message fallback.
        Includes separate user vs bot logging and actionable staff recommendations.
        """
        cfg = cls.get_guild_config(str(guild.id))
        warning_channel_id = cfg.get("warning_channel_id") or cfg.get("log_channel_id")
        webhook_url = cfg.get("webhook_url")

        is_bot = bool(getattr(executor, "bot", False))
        executor_type = "Automated Bot Account" if is_bot else "User Account"
        alert_title = get_string(
            "security.antinuke.alert_title_bot" if is_bot else "security.antinuke.alert_title_user",
            f"Forensic Alert: Unauthorized {'Bot' if is_bot else 'User'} Operation Blocked"
        )

        rec_key = f"security.antinuke.rec_{event_type}"
        default_recs = {
            AntiNukeConstants.EVENT_BAN: "Audit recent ban entries in Server Settings -> Audit Log to identify affected members.",
            AntiNukeConstants.EVENT_KICK: "Verify if executor account was compromised and revoke dangerous moderator roles.",
            AntiNukeConstants.EVENT_BOT_ADD: "The unauthorized bot was removed. Audit who invited the bot and revoke Manage Server permissions.",
            AntiNukeConstants.EVENT_ROLE_DELETE: "Role deletion detected. Re-create the role and check role hierarchy.",
            AntiNukeConstants.EVENT_ROLE_UPDATE: "Dangerous permissions were added. Revert role permissions and demote compromised accounts.",
            AntiNukeConstants.EVENT_CHANNEL_DELETE: "Channel deletion burst blocked. Review backups and rotate moderator credentials.",
            AntiNukeConstants.EVENT_CHANNEL_CREATE: "Spam channel creation detected. Clean up rogue channels.",
            AntiNukeConstants.EVENT_WEBHOOK_CREATE: "Rogue webhook creation intercepted. Review channel Integrations to delete rogue webhooks.",
        }
        recommendation = get_string(rec_key, default_recs.get(event_type, "Review recent server audit logs and secure staff accounts."))

        alert_body = get_string(
            "security.antinuke.alert_body",
            (
                f"• **Guild:** `{guild.name}` (`{guild.id}`)\n"
                f"• **Attacker:** `{executor}` (`{executor.id}`)\n"
                f"• **Category:** `{executor_type}`\n"
                f"• **Action Detected:** `{event_type}`\n"
                f"• **Rate:** `{count}` action(s) within `{window}s` (Threshold: {threshold})\n"
                f"• **Punishment Taken:** **`{punishment.upper()}`**\n"
                f"• **Logged At:** <t:{int(time.time())}:F>"
            ),
            guild_name=guild.name,
            guild_id=guild.id,
            executor_name=str(executor),
            executor_id=executor.id,
            executor_type=executor_type,
            event_type=event_type,
            count=count,
            window=window,
            threshold=threshold,
            punishment=punishment.upper(),
            timestamp=int(time.time()),
        )

        # Build Components V2 UI Container
        container = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("error", "#B21F1F"))
            .add_text_display(f"### {EMOJIS.get('danger', '⚠️')} {alert_title}")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(alert_body)
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(f"**Recommended Staff Action:**\n{recommendation}")
            .set_footer(f"MomentumOne Security Platform • Incident Guard")
            .build()
        )

        # Attempt 1: Webhook logging
        if webhook_url:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "username": "MomentumOne Security Sentinel",
                        "avatar_url": str(guild.me.display_avatar.url) if (guild.me and hasattr(guild.me, "display_avatar")) else None,
                        "embeds": [
                            {
                                "title": alert_title,
                                "description": f"{alert_body}\n\n**Recommended Staff Action:**\n{recommendation}",
                                "color": int(COLORS.get("error", "#B21F1F").replace("#", ""), 16),
                                "footer": {"text": "MomentumOne Security Platform • Webhook Log"},
                                "timestamp": discord.utils.utcnow().isoformat(),
                            }
                        ]
                    }
                    async with session.post(webhook_url, json=payload, timeout=5) as resp:
                        if resp.status in (200, 204):
                            return
                        else:
                            logger.warning(f"[AntiNuke] Webhook delivery failed with status {resp.status}. Falling back to bot channel message.")
            except Exception as w_err:
                logger.warning(f"[AntiNuke] Webhook logging error: {w_err}. Falling back to channel send.")

        # Attempt 2: Fallback to warning channel message
        if warning_channel_id:
            ch = guild.get_channel(int(warning_channel_id))
            if ch and hasattr(ch, "send"):
                try:
                    await ch.send(view=container)
                except Exception as ch_err:
                    logger.error(f"[AntiNuke] Failed to send alert message to channel {warning_channel_id}: {ch_err}")


def datetime_timedelta(**kwargs):
    """Helper for timedelta without importing datetime globally if not needed."""
    import datetime
    return datetime.timedelta(**kwargs)
