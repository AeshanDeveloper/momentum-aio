"""
Sentinel™ Security Event Normalizer.

Transforms heterogeneous Discord gateway objects, model updates, and audit log entries
into normalized SecurityEvent instances with complete metadata, dangerous permission
detection, and minimal memory footprint.
"""

import time
from typing import Any, Dict, List, Optional
import discord

from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.antinuke import AntiNukeConstants


class SecurityEventNormalizer:
    """
    Stateless normalization utility.
    Extracts delta details, dangerous permissions, and structural changes without
    throwing exceptions or blocking execution.
    """

    @staticmethod
    def _safe_id(obj: Any) -> Optional[str]:
        if obj is None:
            return None
        return str(getattr(obj, "id", obj))

    @staticmethod
    def _safe_name(obj: Any) -> Optional[str]:
        if obj is None:
            return None
        return str(getattr(obj, "name", str(obj)))

    @classmethod
    def detect_dangerous_permissions(cls, before_perms: discord.Permissions, after_perms: discord.Permissions) -> List[str]:
        """Detects if any dangerous permissions were granted from before to after."""
        escalated = []
        for perm_attr in AntiNukeConstants.DANGEROUS_PERMISSIONS.keys():
            was_set = getattr(before_perms, perm_attr, False)
            is_set = getattr(after_perms, perm_attr, False)
            if not was_set and is_set:
                escalated.append(perm_attr)
        return escalated

    @classmethod
    def normalize_guild_update(cls, before: discord.Guild, after: discord.Guild) -> SecurityEvent:
        guild_id = cls._safe_id(after) or "0"
        changes: Dict[str, Any] = {}

        if before.name != after.name:
            changes["name"] = {"before": before.name, "after": after.name}
        if getattr(before, "owner_id", None) != getattr(after, "owner_id", None):
            changes["owner_id"] = {"before": before.owner_id, "after": after.owner_id}
        if getattr(before, "verification_level", None) != getattr(after, "verification_level", None):
            changes["verification_level"] = {
                "before": str(before.verification_level),
                "after": str(after.verification_level),
            }
        if getattr(before, "mfa_level", None) != getattr(after, "mfa_level", None):
            changes["mfa_level"] = {"before": str(before.mfa_level), "after": str(after.mfa_level)}
        if getattr(before, "vanity_url_code", None) != getattr(after, "vanity_url_code", None):
            changes["vanity_url_code"] = {"before": before.vanity_url_code, "after": after.vanity_url_code}

        is_security_setting = any(k in changes for k in ("verification_level", "mfa_level", "owner_id"))
        event_type = SecurityEventType.SECURITY_SETTINGS_UPDATE if is_security_setting else SecurityEventType.GUILD_UPDATE

        return SecurityEvent(
            guild_id=guild_id,
            event_type=event_type,
            target_id=guild_id,
            target_type="guild",
            target_name=after.name,
            metadata={"changes": changes, "server_name": after.name},
        )

    @classmethod
    def normalize_channel_create(cls, channel: discord.abc.GuildChannel) -> SecurityEvent:
        guild = getattr(channel, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        category = getattr(channel, "category", None)
        category_id = cls._safe_id(category)

        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.CHANNEL_CREATE,
            target_id=cls._safe_id(channel),
            target_type="channel",
            target_name=cls._safe_name(channel),
            metadata={
                "channel_type": str(getattr(channel, "type", "unknown")),
                "category_id": category_id,
                "position": getattr(channel, "position", None),
            },
        )

    @classmethod
    def normalize_channel_delete(cls, channel: discord.abc.GuildChannel) -> SecurityEvent:
        guild = getattr(channel, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            target_id=cls._safe_id(channel),
            target_type="channel",
            target_name=cls._safe_name(channel),
            metadata={
                "channel_type": str(getattr(channel, "type", "unknown")),
            },
        )

    @classmethod
    def normalize_channel_update(
        cls, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> SecurityEvent:
        guild = getattr(after, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        changes: Dict[str, Any] = {}

        if before.name != after.name:
            changes["name"] = {"before": before.name, "after": after.name}

        # Overwrite analysis
        overwrites_before = getattr(before, "overwrites", {}) or {}
        overwrites_after = getattr(after, "overwrites", {}) or {}
        overwrites_modified = False
        dangerous_overwrites_added = []

        if overwrites_before != overwrites_after:
            overwrites_modified = True
            for target, ow_after in overwrites_after.items():
                ow_before = overwrites_before.get(target)
                target_label = f"{getattr(target, 'name', target.id)} ({getattr(target, 'id', target)})"
                for perm_key in AntiNukeConstants.DANGEROUS_PERMISSIONS.keys():
                    after_allow = getattr(ow_after, perm_key, None) is True
                    before_allow = getattr(ow_before, perm_key, None) is True if ow_before else False
                    if after_allow and not before_allow:
                        dangerous_overwrites_added.append({"target": target_label, "permission": perm_key})

        event_type = (
            SecurityEventType.PERMISSION_OVERWRITE_UPDATE
            if (overwrites_modified and dangerous_overwrites_added)
            else SecurityEventType.CHANNEL_UPDATE
        )

        return SecurityEvent(
            guild_id=guild_id,
            event_type=event_type,
            target_id=cls._safe_id(after),
            target_type="channel",
            target_name=cls._safe_name(after),
            metadata={
                "changes": changes,
                "overwrites_modified": overwrites_modified,
                "dangerous_overwrites_added": dangerous_overwrites_added,
            },
        )

    @classmethod
    def normalize_role_create(cls, role: discord.Role) -> SecurityEvent:
        guild_id = cls._safe_id(getattr(role, "guild", None)) or "0"
        has_admin = getattr(role.permissions, "administrator", False)
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.ROLE_CREATE,
            target_id=cls._safe_id(role),
            target_type="role",
            target_name=role.name,
            metadata={
                "color": getattr(role, "color", None).value if getattr(role, "color", None) else 0,
                "hoist": getattr(role, "hoist", False),
                "position": getattr(role, "position", 0),
                "has_admin": has_admin,
            },
        )

    @classmethod
    def normalize_role_delete(cls, role: discord.Role, guild: Optional[discord.Guild] = None) -> SecurityEvent:
        resolved_guild = guild or getattr(role, "guild", None)
        guild_id = cls._safe_id(resolved_guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.ROLE_DELETE,
            target_id=cls._safe_id(role),
            target_type="role",
            target_name=cls._safe_name(role),
            metadata={
                "position": getattr(role, "position", 0),
            },
        )

    @classmethod
    def normalize_role_update(cls, before: discord.Role, after: discord.Role) -> SecurityEvent:
        guild_id = cls._safe_id(getattr(after, "guild", None)) or "0"
        escalated_perms = cls.detect_dangerous_permissions(before.permissions, after.permissions)
        event_type = (
            SecurityEventType.DANGEROUS_PERMISSION_GRANT
            if escalated_perms
            else SecurityEventType.ROLE_UPDATE
        )

        return SecurityEvent(
            guild_id=guild_id,
            event_type=event_type,
            target_id=cls._safe_id(after),
            target_type="role",
            target_name=after.name,
            metadata={
                "before_name": before.name,
                "after_name": after.name,
                "escalated_permissions": escalated_perms,
                "position": getattr(after, "position", 0),
            },
        )

    @classmethod
    def normalize_member_ban(cls, guild: discord.Guild, user: discord.User | discord.Member) -> SecurityEvent:
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.MEMBER_BAN,
            target_id=cls._safe_id(user),
            target_type="member",
            target_name=str(user),
            metadata={"is_bot": getattr(user, "bot", False)},
        )

    @classmethod
    def normalize_member_unban(cls, guild: discord.Guild, user: discord.User | discord.Member) -> SecurityEvent:
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.MEMBER_UNBAN,
            target_id=cls._safe_id(user),
            target_type="member",
            target_name=str(user),
            metadata={"is_bot": getattr(user, "bot", False)},
        )

    @classmethod
    def normalize_member_remove(cls, member: discord.Member, is_kick: bool = False, actor_id: Optional[str] = None) -> SecurityEvent:
        guild_id = cls._safe_id(getattr(member, "guild", None)) or "0"
        event_type = SecurityEventType.MEMBER_KICK if is_kick else SecurityEventType.MEMBER_REMOVE
        confidence = AttributionConfidence.VERIFIED if actor_id else AttributionConfidence.UNKNOWN

        return SecurityEvent(
            guild_id=guild_id,
            event_type=event_type,
            target_id=cls._safe_id(member),
            target_type="member",
            target_name=str(member),
            actor_id=actor_id,
            attribution_confidence=confidence,
            metadata={
                "is_bot": getattr(member, "bot", False),
                "roles_count": len(getattr(member, "roles", [])),
                "joined_at": member.joined_at.timestamp() if getattr(member, "joined_at", None) else None,
            },
        )

    @classmethod
    def normalize_member_join(cls, member: discord.Member) -> Optional[SecurityEvent]:
        """
        Observes member joins. Specifically returns a SecurityEvent for bot additions
        which require strict monitoring and authorization checks.
        """
        if not getattr(member, "bot", False):
            return None
        guild_id = cls._safe_id(getattr(member, "guild", None)) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.BOT_ADD,
            target_id=cls._safe_id(member),
            target_type="member",
            target_name=str(member),
            metadata={
                "is_bot": True,
                "created_at": member.created_at.timestamp() if getattr(member, "created_at", None) else None,
            },
        )

    @classmethod
    def normalize_member_update(cls, before: discord.Member, after: discord.Member) -> Optional[SecurityEvent]:
        guild = getattr(after, "guild", None)
        guild_id = cls._safe_id(guild) or "0"

        # 1. Timeout Check
        before_timeout = getattr(before, "timed_out_until", None)
        after_timeout = getattr(after, "timed_out_until", None)
        timeout_changed = after_timeout and after_timeout != before_timeout

        # 2. Dangerous Role Assignment Check
        before_roles = set(getattr(before, "roles", []))
        after_roles = set(getattr(after, "roles", []))
        added_roles = after_roles - before_roles
        dangerous_roles_added = []
        for r in added_roles:
            perms = getattr(r, "permissions", None)
            if perms:
                for perm_key in AntiNukeConstants.DANGEROUS_PERMISSIONS.keys():
                    if getattr(perms, perm_key, False):
                        dangerous_roles_added.append({"role_id": str(r.id), "role_name": r.name, "permission": perm_key})

        if not timeout_changed and not dangerous_roles_added:
            return None

        event_type = (
            SecurityEventType.MEMBER_ROLE_UPDATE
            if dangerous_roles_added
            else SecurityEventType.MEMBER_UPDATE
        )

        return SecurityEvent(
            guild_id=guild_id,
            event_type=event_type,
            target_id=cls._safe_id(after),
            target_type="member",
            target_name=str(after),
            metadata={
                "timeout_changed": bool(timeout_changed),
                "timed_out_until": str(after_timeout) if after_timeout else None,
                "dangerous_roles_added": dangerous_roles_added,
            },
        )

    @classmethod
    def normalize_webhooks_update(cls, channel: discord.abc.GuildChannel) -> SecurityEvent:
        guild = getattr(channel, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.WEBHOOK_UPDATE,
            target_id=cls._safe_id(channel),
            target_type="channel",
            target_name=cls._safe_name(channel),
            metadata={"channel_id": cls._safe_id(channel)},
        )

    @classmethod
    def normalize_invite_create(cls, invite: discord.Invite) -> SecurityEvent:
        guild = getattr(invite, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        inviter = getattr(invite, "inviter", None)
        actor_id = cls._safe_id(inviter)
        actor_name = str(inviter) if inviter else None
        confidence = AttributionConfidence.VERIFIED if actor_id else AttributionConfidence.UNKNOWN

        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.INVITE_CREATE,
            target_id=str(getattr(invite, "code", "unknown")),
            target_type="invite",
            target_name=f"Invite {getattr(invite, 'code', '')}",
            actor_id=actor_id,
            actor_name=actor_name,
            attribution_confidence=confidence,
            metadata={
                "code": getattr(invite, "code", ""),
                "max_uses": getattr(invite, "max_uses", 0),
                "temporary": getattr(invite, "temporary", False),
            },
        )

    @classmethod
    def normalize_invite_delete(cls, invite: discord.Invite) -> SecurityEvent:
        guild = getattr(invite, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.INVITE_DELETE,
            target_id=str(getattr(invite, "code", "unknown")),
            target_type="invite",
            target_name=f"Invite {getattr(invite, 'code', '')}",
            metadata={"code": getattr(invite, "code", "")},
        )

    @classmethod
    def normalize_guild_emojis_update(cls, guild: discord.Guild, before: Any, after: Any) -> SecurityEvent:
        guild_id = cls._safe_id(guild) or "0"
        before_count = len(before) if before is not None else 0
        after_count = len(after) if after is not None else 0
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.EMOJIS_UPDATE,
            target_id=guild_id,
            target_type="guild",
            target_name=guild.name,
            metadata={"before_count": before_count, "after_count": after_count, "delta": after_count - before_count},
        )

    @classmethod
    def normalize_guild_stickers_update(cls, guild: discord.Guild, before: Any, after: Any) -> SecurityEvent:
        guild_id = cls._safe_id(guild) or "0"
        before_count = len(before) if before is not None else 0
        after_count = len(after) if after is not None else 0
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.STICKERS_UPDATE,
            target_id=guild_id,
            target_type="guild",
            target_name=guild.name,
            metadata={"before_count": before_count, "after_count": after_count, "delta": after_count - before_count},
        )

    @classmethod
    def normalize_guild_integrations_update(cls, guild: discord.Guild) -> SecurityEvent:
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.INTEGRATIONS_UPDATE,
            target_id=guild_id,
            target_type="guild",
            target_name=guild.name,
            metadata={},
        )

    @classmethod
    def normalize_automod_rule_event(cls, rule: Any, event_type: str) -> SecurityEvent:
        guild_id = cls._safe_id(getattr(rule, "guild", None) or getattr(rule, "guild_id", None)) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=event_type,
            target_id=cls._safe_id(rule),
            target_type="automod_rule",
            target_name=cls._safe_name(rule),
            metadata={"enabled": getattr(rule, "enabled", True)},
        )

    @classmethod
    def normalize_thread_delete(cls, thread: discord.Thread) -> SecurityEvent:
        guild = getattr(thread, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.THREAD_DELETE,
            target_id=cls._safe_id(thread),
            target_type="thread",
            target_name=cls._safe_name(thread),
            metadata={"parent_id": cls._safe_id(getattr(thread, "parent", None))},
        )

    @classmethod
    def normalize_scheduled_event_delete(cls, event: Any) -> SecurityEvent:
        guild_id = cls._safe_id(getattr(event, "guild", None) or getattr(event, "guild_id", None)) or "0"
        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.SCHEDULED_EVENT_DELETE,
            target_id=cls._safe_id(event),
            target_type="scheduled_event",
            target_name=cls._safe_name(event),
            metadata={},
        )

    @classmethod
    def normalize_audit_log_entry(cls, entry: discord.AuditLogEntry) -> SecurityEvent:
        """
        Directly normalizes an audit log entry into a verified SecurityEvent.
        """
        guild = getattr(entry, "guild", None)
        guild_id = cls._safe_id(guild) or "0"
        actor = getattr(entry, "user", None)
        actor_id = cls._safe_id(actor)
        actor_name = str(actor) if actor else None
        target = getattr(entry, "target", None)
        target_id = cls._safe_id(target)
        target_name = cls._safe_name(target)
        action_name = getattr(entry.action, "name", str(entry.action))

        return SecurityEvent(
            guild_id=guild_id,
            event_type=SecurityEventType.AUDIT_LOG_ENTRY,
            target_id=target_id,
            target_type="resource",
            target_name=target_name,
            actor_id=actor_id,
            actor_name=actor_name,
            attribution_confidence=AttributionConfidence.VERIFIED if actor_id else AttributionConfidence.UNKNOWN,
            reason=getattr(entry, "reason", None),
            source_id=cls._safe_id(entry),
            metadata={"action": action_name},
            status=SecurityEventStatus.ENRICHED,
        )
