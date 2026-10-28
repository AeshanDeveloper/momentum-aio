"""
Sentinel™ Security Response Policy.

Agent 5 of 8 Security Core: Configurable per-guild emergency containment,
threshold management, authorization levels, trusted recovery roles, and shadow mode safety.

Key capabilities:
- Response levels: OBSERVE, INVESTIGATE, ALERT, LOCKDOWN.
- Strict shadow mode default (shadow_mode=True, auto_lockdown_enabled=False).
- Calibrated thresholds for rapid bursts (e.g. 100 bans in 60s, kicks, channel/role deletions).
- Recovery path preservation: Owner ID, trusted recovery admin IDs, and minimum quorum.
- Channel and role target filtering (shielding bot, recovery roles, exempt channels).
- Rate limiting to prevent thrashing under distributed multi-agent attacks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Union

from config.settings import settings
from core.security.correlation_engine import PatternID


class ResponseLevel:
    """Configurable containment response level."""
    OBSERVE = "observe"          # Log and monitor only; no alerts or modifications
    INVESTIGATE = "investigate"  # Correlate patterns and score threats; no mutations
    ALERT = "alert"              # Dispatch alerts/DMs to recovery admins; no mutations
    LOCKDOWN = "lockdown"        # Execute fast emergency containment if threshold exceeded

    ALL = {OBSERVE, INVESTIGATE, ALERT, LOCKDOWN}


class LockdownTargetType:
    """Scope of targets affected by emergency containment."""
    ROLES = "roles"
    CHANNELS = "channels"
    ALL = "all"


class LockdownStatus:
    """Execution status of an emergency lockdown."""
    REQUESTED = "requested"
    ATTEMPTED = "attempted"
    ACTIVE = "active"
    PARTIAL = "partial"                  # Applied with limitations (e.g. role hierarchy or missing bot perms)
    RESTORED = "restored"
    OVERRIDDEN_BY_ADMIN = "overridden_by_admin"
    FAILED = "failed"

    ALL = {REQUESTED, ATTEMPTED, ACTIVE, PARTIAL, RESTORED, OVERRIDDEN_BY_ADMIN, FAILED}


# Standard dangerous permission names in Discord
DEFAULT_DANGEROUS_PERMISSIONS: List[str] = [
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "ban_members",
    "kick_members",
    "manage_webhooks",
    "mention_everyone",
]

# Standard channel permissions denied during channel lockdown
DEFAULT_CHANNEL_DENY_PERMISSIONS: List[str] = [
    "send_messages",
    "send_messages_in_threads",
    "create_public_threads",
    "create_private_threads",
    "connect",
    "speak",
]


@dataclass
class SecurityResponsePolicy:
    """
    Per-guild security response and emergency lockdown configuration.
    CRITICAL: Always defaults to shadow mode (shadow_mode=True, auto_lockdown_enabled=False)
    to protect servers during setup and staging.
    """
    guild_id: str = ""
    response_level: str = ResponseLevel.LOCKDOWN
    shadow_mode: bool = True                     # DEFAULT TO SHADOW MODE
    auto_lockdown_enabled: bool = False          # MUST BE EXPLICITLY ENABLED
    
    # Rapid burst thresholds
    rapid_ban_threshold_count: int = 100         # e.g. 100 bans in 60s
    rapid_ban_threshold_window_seconds: float = 60.0
    rapid_kick_threshold_count: int = 50
    rapid_kick_threshold_window_seconds: float = 60.0
    rapid_channel_delete_threshold_count: int = 3
    rapid_channel_delete_threshold_window_seconds: float = 60.0
    rapid_role_delete_threshold_count: int = 3
    rapid_role_delete_threshold_window_seconds: float = 60.0
    
    # Minimum threat score to trigger emergency containment
    emergency_score_threshold: float = 75.0
    
    # Recovery and authorization hierarchy
    recovery_owner_id: Optional[str] = None      # Primary recovery authority (server owner)
    trusted_recovery_admin_ids: List[str] = field(default_factory=list)  # Designated recovery staff
    recovery_quorum: int = 2                     # Required approvals if non-owner initiates recovery
    fallback_channel_id: Optional[str] = None   # Secure fallback channel if recovery admin DMs are closed
    
    # Scoping & Preservation
    target_role_ids: List[str] = field(default_factory=list)              # Specific roles to strip (empty = default dangerous roles)
    preserved_recovery_role_ids: List[str] = field(default_factory=list)  # NEVER strip permissions from these roles
    exempt_channel_ids: List[str] = field(default_factory=list)           # NEVER lock down these channels (e.g. staff/incident channel)
    
    # Rate limiting & Permissions
    lockdown_rate_limit_per_minute: int = 3
    dangerous_permissions: List[str] = field(default_factory=lambda: list(DEFAULT_DANGEROUS_PERMISSIONS))
    channel_deny_permissions: List[str] = field(default_factory=lambda: list(DEFAULT_CHANNEL_DENY_PERMISSIONS))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_trusted_recovery_actor(self, user_id: Union[int, str]) -> bool:
        """Verifies if a user ID belongs to the recovery owner or trusted recovery admin team."""
        uid_str = str(user_id)
        if self.recovery_owner_id and str(self.recovery_owner_id) == uid_str:
            return True
        return uid_str in [str(tid) for tid in self.trusted_recovery_admin_ids]

    def is_recovery_owner(self, user_id: Union[int, str]) -> bool:
        """Verifies if a user ID is the designated recovery owner."""
        return bool(self.recovery_owner_id and str(self.recovery_owner_id) == str(user_id))

    def should_trigger_emergency_lockdown(
        self,
        pattern_id: str,
        threat_score: float,
        count: Optional[int] = None,
        window_seconds: Optional[float] = None,
    ) -> bool:
        """
        Determines if an incoming event burst or threat score crosses policy emergency criteria.
        Returns False if response level is lower than LOCKDOWN.
        """
        if self.response_level != ResponseLevel.LOCKDOWN:
            return False

        if threat_score >= self.emergency_score_threshold:
            return True

        if count is not None and window_seconds is not None:
            if pattern_id == PatternID.RAPID_BAN_BURST:
                if count >= self.rapid_ban_threshold_count and window_seconds <= self.rapid_ban_threshold_window_seconds:
                    return True
            elif pattern_id == PatternID.RAPID_KICK_BURST:
                if count >= self.rapid_kick_threshold_count and window_seconds <= self.rapid_kick_threshold_window_seconds:
                    return True
            elif pattern_id == PatternID.REPEATED_CHANNEL_DELETIONS:
                if count >= self.rapid_channel_delete_threshold_count and window_seconds <= self.rapid_channel_delete_threshold_window_seconds:
                    return True
            elif pattern_id == PatternID.REPEATED_ROLE_DELETIONS:
                if count >= self.rapid_role_delete_threshold_count and window_seconds <= self.rapid_role_delete_threshold_window_seconds:
                    return True

        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": str(self.guild_id),
            "response_level": self.response_level,
            "shadow_mode": self.shadow_mode,
            "auto_lockdown_enabled": self.auto_lockdown_enabled,
            "rapid_ban_threshold_count": self.rapid_ban_threshold_count,
            "rapid_ban_threshold_window_seconds": self.rapid_ban_threshold_window_seconds,
            "rapid_kick_threshold_count": self.rapid_kick_threshold_count,
            "rapid_kick_threshold_window_seconds": self.rapid_kick_threshold_window_seconds,
            "rapid_channel_delete_threshold_count": self.rapid_channel_delete_threshold_count,
            "rapid_channel_delete_threshold_window_seconds": self.rapid_channel_delete_threshold_window_seconds,
            "rapid_role_delete_threshold_count": self.rapid_role_delete_threshold_count,
            "rapid_role_delete_threshold_window_seconds": self.rapid_role_delete_threshold_window_seconds,
            "emergency_score_threshold": self.emergency_score_threshold,
            "recovery_owner_id": str(self.recovery_owner_id) if self.recovery_owner_id else None,
            "trusted_recovery_admin_ids": [str(x) for x in self.trusted_recovery_admin_ids],
            "recovery_quorum": self.recovery_quorum,
            "fallback_channel_id": str(self.fallback_channel_id) if self.fallback_channel_id else None,
            "target_role_ids": [str(x) for x in self.target_role_ids],
            "preserved_recovery_role_ids": [str(x) for x in self.preserved_recovery_role_ids],
            "exempt_channel_ids": [str(x) for x in self.exempt_channel_ids],
            "lockdown_rate_limit_per_minute": self.lockdown_rate_limit_per_minute,
            "dangerous_permissions": list(self.dangerous_permissions),
            "channel_deny_permissions": list(self.channel_deny_permissions),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityResponsePolicy":
        return cls(
            guild_id=str(data.get("guild_id", "")),
            response_level=data.get("response_level", ResponseLevel.LOCKDOWN),
            shadow_mode=bool(data.get("shadow_mode", True)),
            auto_lockdown_enabled=bool(data.get("auto_lockdown_enabled", False)),
            rapid_ban_threshold_count=int(data.get("rapid_ban_threshold_count", 100)),
            rapid_ban_threshold_window_seconds=float(data.get("rapid_ban_threshold_window_seconds", 60.0)),
            rapid_kick_threshold_count=int(data.get("rapid_kick_threshold_count", 50)),
            rapid_kick_threshold_window_seconds=float(data.get("rapid_kick_threshold_window_seconds", 60.0)),
            rapid_channel_delete_threshold_count=int(data.get("rapid_channel_delete_threshold_count", 3)),
            rapid_channel_delete_threshold_window_seconds=float(data.get("rapid_channel_delete_threshold_window_seconds", 60.0)),
            rapid_role_delete_threshold_count=int(data.get("rapid_role_delete_threshold_count", 3)),
            rapid_role_delete_threshold_window_seconds=float(data.get("rapid_role_delete_threshold_window_seconds", 60.0)),
            emergency_score_threshold=float(data.get("emergency_score_threshold", 75.0)),
            recovery_owner_id=data.get("recovery_owner_id"),
            trusted_recovery_admin_ids=[str(x) for x in data.get("trusted_recovery_admin_ids", [])],
            recovery_quorum=int(data.get("recovery_quorum", 2)),
            fallback_channel_id=data.get("fallback_channel_id"),
            target_role_ids=[str(x) for x in data.get("target_role_ids", [])],
            preserved_recovery_role_ids=[str(x) for x in data.get("preserved_recovery_role_ids", [])],
            exempt_channel_ids=[str(x) for x in data.get("exempt_channel_ids", [])],
            lockdown_rate_limit_per_minute=int(data.get("lockdown_rate_limit_per_minute", 3)),
            dangerous_permissions=data.get("dangerous_permissions", list(DEFAULT_DANGEROUS_PERMISSIONS)),
            channel_deny_permissions=data.get("channel_deny_permissions", list(DEFAULT_CHANNEL_DENY_PERMISSIONS)),
            metadata=data.get("metadata", {}),
        )


def get_default_response_policy(guild_id: Union[str, int]) -> SecurityResponsePolicy:
    """Creates a production-grade default security response policy for a guild."""
    return SecurityResponsePolicy(
        guild_id=str(guild_id),
        response_level=ResponseLevel.LOCKDOWN,
        shadow_mode=True,               # Default: shadow mode
        auto_lockdown_enabled=False,   # Explicit opt-in required for live Discord mutations
        rapid_ban_threshold_count=100,  # 100 bans in 60s
        rapid_ban_threshold_window_seconds=60.0,
        rapid_kick_threshold_count=50,
        rapid_kick_threshold_window_seconds=60.0,
        rapid_channel_delete_threshold_count=3,
        rapid_channel_delete_threshold_window_seconds=60.0,
        rapid_role_delete_threshold_count=3,
        rapid_role_delete_threshold_window_seconds=60.0,
        emergency_score_threshold=75.0,
        recovery_quorum=2,
    )
