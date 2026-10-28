"""
Sentinel™ Security Event Observation Layer: Normalized Data Models.

Provides standardized, immutable-friendly security event representations across all
Discord event vectors with graduated attribution confidence, deduplication keys,
and rich metadata capture.
"""

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List


class AttributionConfidence:
    """
    Confidence level in the identified actor for a security event.
    - VERIFIED: Corroborated with direct audit log or gateway actor proof.
    - PROBABLE: Corroborated with temporal correlation or high-heuristic evidence.
    - UNKNOWN: Actor cannot yet be confirmed (e.g. audit log pending, throttled, or missing).
    """
    VERIFIED = "verified"
    PROBABLE = "probable"
    UNKNOWN = "unknown"

    ALL = {VERIFIED, PROBABLE, UNKNOWN}


class SecurityEventType:
    """
    Canonical security event types normalized across Discord gateway and audit log vectors.
    """
    # Member moderation & access
    MEMBER_BAN = "member_ban"
    MEMBER_UNBAN = "member_unban"
    MEMBER_KICK = "member_kick"
    MEMBER_REMOVE = "member_remove"
    MEMBER_UPDATE = "member_update"
    MEMBER_ROLE_UPDATE = "member_role_update"
    BOT_ADD = "bot_add"

    # Channel & Category structures
    CHANNEL_CREATE = "channel_create"
    CHANNEL_UPDATE = "channel_update"
    CHANNEL_DELETE = "channel_delete"
    PERMISSION_OVERWRITE_UPDATE = "permission_overwrite_update"
    THREAD_DELETE = "thread_delete"

    # Role & Permission hierarchy
    ROLE_CREATE = "role_create"
    ROLE_UPDATE = "role_update"
    ROLE_DELETE = "role_delete"
    DANGEROUS_PERMISSION_GRANT = "dangerous_permission_grant"

    # Webhooks & Integrations
    WEBHOOK_CREATE = "webhook_create"
    WEBHOOK_UPDATE = "webhook_update"
    WEBHOOK_DELETE = "webhook_delete"
    INTEGRATIONS_UPDATE = "integrations_update"

    # Server settings & Assets
    GUILD_UPDATE = "guild_update"
    SECURITY_SETTINGS_UPDATE = "security_settings_update"
    EMOJIS_UPDATE = "emojis_update"
    STICKERS_UPDATE = "stickers_update"

    # Access invitations & scheduled events
    INVITE_CREATE = "invite_create"
    INVITE_DELETE = "invite_delete"
    SCHEDULED_EVENT_DELETE = "scheduled_event_delete"

    # AutoModeration rules
    AUTOMOD_RULE_CREATE = "automod_rule_create"
    AUTOMOD_RULE_UPDATE = "automod_rule_update"
    AUTOMOD_RULE_DELETE = "automod_rule_delete"

    # Audit log stream
    AUDIT_LOG_ENTRY = "audit_log_entry"


class SecurityEventStatus:
    OBSERVED = "observed"
    ENRICHING = "enriching"
    ENRICHED = "enriched"
    DISPATCHED = "dispatched"
    SUPPRESSED_DUPLICATE = "suppressed_duplicate"


@dataclass
class SecurityEvent:
    """
    Normalized Security Event container passed through the observation pipeline
    to downstream threat evaluation (Agent 2) and logging components.
    """
    guild_id: str
    event_type: str
    event_id: str = field(default_factory=lambda: f"sec_evt_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)

    # Target entity
    target_id: Optional[str] = None
    target_type: Optional[str] = None  # "member", "role", "channel", "webhook", "guild", "invite", "rule"
    target_name: Optional[str] = None

    # Actor attribution
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    attribution_confidence: str = AttributionConfidence.UNKNOWN
    reason: Optional[str] = None

    # Event context & payload
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None  # Audit log entry ID, gateway event ID, or message ID
    dedup_key: Optional[str] = None

    # Pipeline lifecycle
    status: str = SecurityEventStatus.OBSERVED
    correlation_id: Optional[str] = None
    is_whitelisted_actor: Optional[bool] = None

    def __post_init__(self):
        # Guarantee string conversions
        self.guild_id = str(self.guild_id)
        if self.target_id is not None:
            self.target_id = str(self.target_id)
        if self.actor_id is not None:
            self.actor_id = str(self.actor_id)
        if self.source_id is not None:
            self.source_id = str(self.source_id)

        # Generate deduplication key if omitted
        if not self.dedup_key:
            self.dedup_key = self.generate_dedup_key()

        # Validate confidence
        if self.attribution_confidence not in AttributionConfidence.ALL:
            self.attribution_confidence = AttributionConfidence.UNKNOWN

    def generate_dedup_key(self) -> str:
        """
        Calculates a deterministic deduplication token to correlate multiple signals
        (e.g., gateway event + audit log entry) referencing the same underlying action.
        """
        # Bucket timestamp into 10-second intervals to absorb clock skew
        bucket = int(self.timestamp // 10)
        target = self.target_id or "unknown"
        source = self.source_id or ""
        return f"{self.guild_id}:{self.event_type}:{target}:{source}:{bucket}"

    @property
    def is_verified(self) -> bool:
        return self.attribution_confidence == AttributionConfidence.VERIFIED

    @property
    def is_probable(self) -> bool:
        return self.attribution_confidence == AttributionConfidence.PROBABLE

    @property
    def is_unknown(self) -> bool:
        return self.attribution_confidence == AttributionConfidence.UNKNOWN

    def enrich_actor(
        self,
        actor_id: str,
        actor_name: Optional[str] = None,
        reason: Optional[str] = None,
        confidence: str = AttributionConfidence.VERIFIED,
        is_whitelisted: Optional[bool] = None,
        source_id: Optional[str] = None,
    ) -> None:
        """
        Asynchronously updates the actor attribution of this event once verified
        from audit logs or external correlation.
        """
        self.actor_id = str(actor_id) if actor_id else None
        if actor_name:
            self.actor_name = actor_name
        if reason:
            self.reason = reason
        if confidence in AttributionConfidence.ALL:
            self.attribution_confidence = confidence
        if is_whitelisted is not None:
            self.is_whitelisted_actor = is_whitelisted
        if source_id:
            self.source_id = str(source_id)
        self.status = SecurityEventStatus.ENRICHED

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the event into a JSON / MongoDB compatible document dictionary."""
        return {
            "event_id": self.event_id,
            "guild_id": self.guild_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "target_name": self.target_name,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "attribution_confidence": self.attribution_confidence,
            "reason": self.reason,
            "metadata": self.metadata,
            "source_id": self.source_id,
            "dedup_key": self.dedup_key,
            "status": self.status,
            "correlation_id": self.correlation_id,
            "is_whitelisted_actor": self.is_whitelisted_actor,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityEvent":
        """Reconstructs a SecurityEvent from a dictionary / database record."""
        return cls(
            event_id=data.get("event_id", f"sec_evt_{uuid.uuid4().hex[:12]}"),
            guild_id=str(data.get("guild_id", "")),
            event_type=data.get("event_type", "unknown"),
            timestamp=float(data.get("timestamp", time.time())),
            target_id=str(data["target_id"]) if data.get("target_id") is not None else None,
            target_type=data.get("target_type"),
            target_name=data.get("target_name"),
            actor_id=str(data["actor_id"]) if data.get("actor_id") is not None else None,
            actor_name=data.get("actor_name"),
            attribution_confidence=data.get("attribution_confidence", AttributionConfidence.UNKNOWN),
            reason=data.get("reason"),
            metadata=dict(data.get("metadata", {})),
            source_id=str(data["source_id"]) if data.get("source_id") is not None else None,
            dedup_key=data.get("dedup_key"),
            status=data.get("status", SecurityEventStatus.OBSERVED),
            correlation_id=data.get("correlation_id"),
            is_whitelisted_actor=data.get("is_whitelisted_actor"),
        )
