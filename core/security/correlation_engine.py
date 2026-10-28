"""
Sentinel™ Security Correlation Engine.

Agent 3 of 8 Security Core: High-performance deterministic pattern-detection layer.
Consumes normalized SecurityEvent stream from Agent 1 (SecurityEventCollector) and
activity summaries / emergency signals from Agent 2 (SecurityActivityManager).

Key capabilities:
- Explicit, configurable rule-based pattern matching (zero AI/neural network dependencies).
- Real-time emergency detection: triggers immediate protective evaluation upon threshold crossing.
- Structured ThreatSignal output with rigorous distinction between observed facts and inferred intent.
- Strict non-suppression of whitelisted actors (trusted actors are monitored and flagged).
- Guild-level evaluation when actor attribution is unknown or pending.
- Robust handling of out-of-order and delayed events with chronologically sorted sliding buffers.
- Anti-alert-storm deduplication with intelligent severity escalation bypass.
- Zero database latency on hot detection paths with asynchronous persistence.
- Branded Discord formatting utilizing configurations global (emojis, colors, links).
"""

from __future__ import annotations

import time
import uuid
import bisect
import asyncio
import inspect
import collections
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Callable, Tuple

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from config.strings import get_string
from core.logging.logger import logger
from database.database import database
from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.activity_manager import (
    SecurityActivityManager,
    security_activity_manager,
    ActivityCategory,
    EmergencySignal,
    EmergencySignalType,
    ActivityWindowSummary,
)


class ThreatSeverity:
    """Canonical severity classifications for correlated threat signals."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    ALL = {LOW, MEDIUM, HIGH, CRITICAL}


class ThreatConfidence:
    """
    Graduated confidence in the correlated threat pattern.
    - UNCONFIRMED: Heuristic match or unverified single observation.
    - SUSPICIOUS: Plausible malicious pattern matching configured threshold.
    - HIGH_CONFIDENCE: Corroborated multi-event sequence or rapid burst by verified/probable actor.
    - CONFIRMED: Irrefutable sequence verified by gateway and audit log evidence.
    """
    UNCONFIRMED = "unconfirmed"
    SUSPICIOUS = "suspicious"
    HIGH_CONFIDENCE = "high_confidence"
    CONFIRMED = "confirmed"

    ALL = {UNCONFIRMED, SUSPICIOUS, HIGH_CONFIDENCE, CONFIRMED}


class ResponseCategory:
    """Recommended protective response category passed to downstream Agent 4 (Lockdown Engine)."""
    MONITOR = "monitor"
    ALERT = "alert"
    RESTRICT_ACTOR = "restrict_actor"
    ISOLATE_INTEGRATION = "isolate_integration"
    EMERGENCY_LOCKDOWN = "emergency_lockdown"

    ALL = {MONITOR, ALERT, RESTRICT_ACTOR, ISOLATE_INTEGRATION, EMERGENCY_LOCKDOWN}


class PatternID:
    """Canonical pattern identifiers for security correlation rules."""
    RAPID_BAN_BURST = "rapid_ban_burst"
    RAPID_KICK_BURST = "rapid_kick_burst"
    REPEATED_CHANNEL_DELETIONS = "repeated_channel_deletions"
    REPEATED_ROLE_DELETIONS = "repeated_role_deletions"
    PERMISSION_ESCALATION_THEN_DESTRUCTION = "permission_escalation_then_destruction"
    DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION = "dangerous_role_changes_then_destruction"
    WEBHOOK_INTEGRATION_ABUSE = "webhook_integration_abuse"
    COORDINATED_MULTI_VECTOR = "coordinated_multi_vector"
    SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION = "security_weakening_prior_to_destruction"

    ALL = {
        RAPID_BAN_BURST,
        RAPID_KICK_BURST,
        REPEATED_CHANNEL_DELETIONS,
        REPEATED_ROLE_DELETIONS,
        PERMISSION_ESCALATION_THEN_DESTRUCTION,
        DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION,
        WEBHOOK_INTEGRATION_ABUSE,
        COORDINATED_MULTI_VECTOR,
        SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION,
    }


@dataclass
class ThreatSignal:
    """
    Structured threat signal produced by the SecurityCorrelationEngine.
    Distinguishes observed facts from inferred intent. Consumed by downstream
    defensive modules (Agent 4 Lockdown Engine) and notification dispatchers.
    """
    signal_id: str = field(default_factory=lambda: f"threat_sig_{uuid.uuid4().hex[:12]}")
    pattern_id: str = ""
    pattern_name: str = ""
    guild_id: str = ""
    severity: str = ThreatSeverity.MEDIUM
    confidence: str = ThreatConfidence.SUSPICIOUS
    scope: str = "actor"  # "actor" or "guild"
    actor_id: Optional[str] = None
    actor_name: Optional[str] = None
    is_whitelisted_actor: bool = False
    attribution_confidence: str = AttributionConfidence.UNKNOWN
    recommended_response: str = ResponseCategory.ALERT
    requires_immediate_protection: bool = False
    time_window_seconds: float = 60.0

    # Structured explanations
    trigger_reasons: List[str] = field(default_factory=list)
    observed_facts: Dict[str, Any] = field(default_factory=dict)
    inferred_intent: str = ""

    # Forensics & cross references
    event_ids: List[str] = field(default_factory=list)
    target_ids: List[str] = field(default_factory=list)
    triggering_event: Optional[SecurityEvent] = None
    correlated_signals: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.guild_id = str(self.guild_id)
        if self.actor_id is not None:
            self.actor_id = str(self.actor_id)
        if self.severity not in ThreatSeverity.ALL:
            self.severity = ThreatSeverity.MEDIUM
        if self.confidence not in ThreatConfidence.ALL:
            self.confidence = ThreatConfidence.SUSPICIOUS
        if self.recommended_response not in ResponseCategory.ALL:
            self.recommended_response = ResponseCategory.ALERT

    @property
    def is_emergency(self) -> bool:
        """Determines if this signal demands immediate autonomous lockdown."""
        return self.requires_immediate_protection or (
            self.severity == ThreatSeverity.CRITICAL
            and self.recommended_response == ResponseCategory.EMERGENCY_LOCKDOWN
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the threat signal to a MongoDB-compliant dictionary."""
        return {
            "signal_id": self.signal_id,
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "guild_id": self.guild_id,
            "severity": self.severity,
            "confidence": self.confidence,
            "scope": self.scope,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "is_whitelisted_actor": self.is_whitelisted_actor,
            "attribution_confidence": self.attribution_confidence,
            "recommended_response": self.recommended_response,
            "requires_immediate_protection": self.requires_immediate_protection,
            "time_window_seconds": self.time_window_seconds,
            "trigger_reasons": self.trigger_reasons,
            "observed_facts": self.observed_facts,
            "inferred_intent": self.inferred_intent,
            "event_ids": self.event_ids,
            "target_ids": self.target_ids,
            "triggering_event_id": self.triggering_event.event_id if self.triggering_event else None,
            "correlated_signals": self.correlated_signals,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThreatSignal":
        """Reconstructs a ThreatSignal from serialized data."""
        return cls(
            signal_id=data.get("signal_id", f"threat_sig_{uuid.uuid4().hex[:12]}"),
            pattern_id=data.get("pattern_id", "unknown_pattern"),
            pattern_name=data.get("pattern_name", "Unknown Pattern"),
            guild_id=str(data.get("guild_id", "")),
            severity=data.get("severity", ThreatSeverity.MEDIUM),
            confidence=data.get("confidence", ThreatConfidence.SUSPICIOUS),
            scope=data.get("scope", "actor"),
            actor_id=str(data["actor_id"]) if data.get("actor_id") is not None else None,
            actor_name=data.get("actor_name"),
            is_whitelisted_actor=bool(data.get("is_whitelisted_actor", False)),
            attribution_confidence=data.get("attribution_confidence", AttributionConfidence.UNKNOWN),
            recommended_response=data.get("recommended_response", ResponseCategory.ALERT),
            requires_immediate_protection=bool(data.get("requires_immediate_protection", False)),
            time_window_seconds=float(data.get("time_window_seconds", 60.0)),
            trigger_reasons=list(data.get("trigger_reasons", [])),
            observed_facts=dict(data.get("observed_facts", {})),
            inferred_intent=data.get("inferred_intent", ""),
            event_ids=list(data.get("event_ids", [])),
            target_ids=list(data.get("target_ids", [])),
            triggering_event=None,
            correlated_signals=list(data.get("correlated_signals", [])),
            timestamp=float(data.get("timestamp", time.time())),
            metadata=dict(data.get("metadata", {})),
        )

    def format_alert_embed_data(self) -> Dict[str, Any]:
        """
        Formats threat signal details into Discord embed / message data
        using configurations global (emojis, colors, URLs).
        """
        # Determine theme color based on severity
        if self.severity == ThreatSeverity.CRITICAL:
            color = get_color("error", "#B21F1F")
            severity_emoji = get_emoji("error", "🚨")
        elif self.severity == ThreatSeverity.HIGH:
            color = get_color("warning", "#F59E0B")
            severity_emoji = get_emoji("warn", "⚠️")
        else:
            color = get_color("info", "#0844C5")
            severity_emoji = get_emoji("info", "ℹ️")

        sentinel_emoji = get_emoji("sentinel", "🛡️")

        actor_str = f"`{self.actor_name or 'Unknown'}` ({self.actor_id or 'Guild-wide'})"
        if self.is_whitelisted_actor:
            actor_str += " **[Whitelisted/Admin Actor]**"

        fields = [
            {"name": f"{severity_emoji} Severity & Confidence", "value": f"**{self.severity.upper()}** ({self.confidence.replace('_', ' ').title()})", "inline": True},
            {"name": "Recommended Action", "value": f"`{self.recommended_response.upper()}`", "inline": True},
            {"name": "Actor Attribution", "value": f"{actor_str}\nConfidence: `{self.attribution_confidence.upper()}`", "inline": False},
            {"name": "Observed Facts", "value": f"• Events: `{len(self.event_ids)}` across `{self.time_window_seconds}s`\n• Targets: `{len(self.target_ids)}` unique entities", "inline": False},
            {"name": "Inferred Intent (Hypothesis)", "value": f"*{self.inferred_intent}*", "inline": False},
        ]

        if self.trigger_reasons:
            reasons_text = "\n".join(f"• {r}" for r in self.trigger_reasons[:4])
            fields.append({"name": "Detection Reasons", "value": reasons_text, "inline": False})

        return {
            "title": f"{sentinel_emoji} Security Threat Detected: {self.pattern_name}",
            "color": int(color.lstrip("#"), 16) if color.startswith("#") else 0xB21F1F,
            "fields": fields,
            "footer": {
                "text": f"Sentinel™ Security Core • Signal ID: {self.signal_id}",
                "icon_url": IMAGES.get("sentinel_avatar", ""),
            },
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.timestamp)),
        }


@dataclass
class CorrelationRuleConfig:
    """Configurable parameters for pattern correlation rules."""
    pattern_id: str
    pattern_name: str
    description: str
    enabled: bool = True
    actor_count_threshold: int = 5
    guild_count_threshold: int = 10
    window_seconds: float = 60.0
    min_unique_targets: int = 1
    severity: str = ThreatSeverity.CRITICAL
    recommended_response: str = ResponseCategory.EMERGENCY_LOCKDOWN
    requires_immediate_protection: bool = True
    cooldown_seconds: float = 10.0
    custom_params: Dict[str, Any] = field(default_factory=dict)


class SecurityCorrelationEngine:
    """
    Sentinel™ Threat Correlation and Pattern Detection Engine.

    Aggregates normalized security events and rolling counters to detect
    complex attack patterns across Discord server vectors.
    """

    _instance: Optional["SecurityCorrelationEngine"] = None

    def __init__(
        self,
        activity_manager: Optional[SecurityActivityManager] = None,
        max_events_per_guild: int = 300,
        max_events_per_actor: int = 100,
        event_retention_seconds: float = 600.0,
    ):
        self._activity_manager = activity_manager or SecurityActivityManager.get_instance()
        self._max_events_per_guild = max_events_per_guild
        self._max_events_per_actor = max_events_per_actor
        self._event_retention_seconds = event_retention_seconds

        # Striped per-guild thread concurrency
        self._guild_locks: Dict[str, threading.RLock] = collections.defaultdict(threading.RLock)
        self._async_locks: Dict[str, asyncio.Lock] = {}

        # Chronologically sorted event sequence buffers
        # guild_id -> List[SecurityEvent]
        self._guild_event_sequences: Dict[str, List[SecurityEvent]] = collections.defaultdict(list)
        # guild_id -> { actor_id -> List[SecurityEvent] }
        self._actor_event_sequences: Dict[str, Dict[str, List[SecurityEvent]]] = collections.defaultdict(
            lambda: collections.defaultdict(list)
        )

        # Deduplication cache for incoming events: dedup_key -> timestamp
        self._processed_events: Dict[str, float] = {}

        # Anti-alert storm cooldown tracker: (guild_id, pattern_id, actor_id or 'guild') -> (timestamp, last_count)
        self._alert_cooldowns: Dict[Tuple[str, str, str], Tuple[float, int]] = {}

        # Default rule configurations
        self._rule_configs: Dict[str, CorrelationRuleConfig] = self._build_default_rule_configs()

        # Guild-specific rule overrides: guild_id -> { pattern_id -> CorrelationRuleConfig }
        self._guild_rule_overrides: Dict[str, Dict[str, CorrelationRuleConfig]] = collections.defaultdict(dict)

        # Downstream signal subscribers: callbacks accepting ThreatSignal
        self._signal_subscribers: List[Callable[[ThreatSignal], Any]] = []

        # Signal history buffer (in-memory forensics)
        self._signal_history: collections.deque[ThreatSignal] = collections.deque(maxlen=1000)

        # Activity manager subscription token
        self._am_subscriber_cb: Optional[Callable[[EmergencySignal], Any]] = None

    @classmethod
    def get_instance(cls) -> "SecurityCorrelationEngine":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resets singleton state (for unit testing)."""
        cls._instance = None

    def _get_async_lock(self, guild_id: str) -> asyncio.Lock:
        gid = str(guild_id)
        if gid not in self._async_locks:
            self._async_locks[gid] = asyncio.Lock()
        return self._async_locks[gid]

    def _build_default_rule_configs(self) -> Dict[str, CorrelationRuleConfig]:
        """Defines the standard set of pattern correlation rules and thresholds."""
        return {
            # 1. Rapid burst of member bans
            PatternID.RAPID_BAN_BURST: CorrelationRuleConfig(
                pattern_id=PatternID.RAPID_BAN_BURST,
                pattern_name="Rapid Burst Member Bans",
                description="Rapid burst of bans within a narrow interval indicating a mass ban raid.",
                actor_count_threshold=5,
                guild_count_threshold=10,
                window_seconds=10.0,
                min_unique_targets=3,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=10.0,
            ),

            # 2. Burst of kicks or member removals
            PatternID.RAPID_KICK_BURST: CorrelationRuleConfig(
                pattern_id=PatternID.RAPID_KICK_BURST,
                pattern_name="Rapid Burst Member Kicks",
                description="Sudden series of kicks or removals exceeding normal operational velocity.",
                actor_count_threshold=5,
                guild_count_threshold=10,
                window_seconds=15.0,
                min_unique_targets=3,
                severity=ThreatSeverity.HIGH,
                recommended_response=ResponseCategory.RESTRICT_ACTOR,
                requires_immediate_protection=False,
                cooldown_seconds=15.0,
            ),

            # 3. Repeated channel/category deletions
            PatternID.REPEATED_CHANNEL_DELETIONS: CorrelationRuleConfig(
                pattern_id=PatternID.REPEATED_CHANNEL_DELETIONS,
                pattern_name="Repeated Channel/Category Deletions",
                description="Multiple channels or categories deleted in rapid succession.",
                actor_count_threshold=2,
                guild_count_threshold=3,
                window_seconds=15.0,
                min_unique_targets=2,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=10.0,
            ),

            # 4. Repeated role deletions
            PatternID.REPEATED_ROLE_DELETIONS: CorrelationRuleConfig(
                pattern_id=PatternID.REPEATED_ROLE_DELETIONS,
                pattern_name="Repeated Role Deletions",
                description="Multiple roles deleted rapidly, compromising permission architecture.",
                actor_count_threshold=2,
                guild_count_threshold=3,
                window_seconds=15.0,
                min_unique_targets=2,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=10.0,
            ),

            # 5. Permission escalation followed by destructive actions
            PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION: CorrelationRuleConfig(
                pattern_id=PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION,
                pattern_name="Permission Escalation Then Destruction",
                description="Dangerous administrative permission grant followed by destructive activity.",
                actor_count_threshold=1,
                guild_count_threshold=1,
                window_seconds=120.0,
                min_unique_targets=1,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=15.0,
            ),

            # 6. Dangerous role changes followed by bans or channel deletions
            PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION: CorrelationRuleConfig(
                pattern_id=PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION,
                pattern_name="Dangerous Role Assignment Then Destruction",
                description="Account granted privileged role subsequently executing bans or deletions.",
                actor_count_threshold=1,
                guild_count_threshold=1,
                window_seconds=120.0,
                min_unique_targets=1,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=15.0,
            ),

            # 7. Webhook or integration changes combined with other suspicious activity
            PatternID.WEBHOOK_INTEGRATION_ABUSE: CorrelationRuleConfig(
                pattern_id=PatternID.WEBHOOK_INTEGRATION_ABUSE,
                pattern_name="Webhook / Integration Abuse Spike",
                description="Webhook creation or bot additions paired with destructive channel/member operations.",
                actor_count_threshold=2,
                guild_count_threshold=3,
                window_seconds=30.0,
                min_unique_targets=1,
                severity=ThreatSeverity.HIGH,
                recommended_response=ResponseCategory.ISOLATE_INTEGRATION,
                requires_immediate_protection=False,
                cooldown_seconds=15.0,
            ),

            # 8. Several destructive event types occurring within a short period (Coordinated Multi-Vector)
            PatternID.COORDINATED_MULTI_VECTOR: CorrelationRuleConfig(
                pattern_id=PatternID.COORDINATED_MULTI_VECTOR,
                pattern_name="Coordinated Multi-Vector Attack",
                description="Simultaneous execution across 3 or more distinct destructive event categories.",
                actor_count_threshold=3,
                guild_count_threshold=4,
                window_seconds=25.0,
                min_unique_targets=2,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=10.0,
                custom_params={"min_distinct_vectors": 3},
            ),

            # 9. Attempts to weaken security settings before destructive activity
            PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION: CorrelationRuleConfig(
                pattern_id=PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION,
                pattern_name="Security Weakening Prior to Destruction",
                description="Modification of server security parameters or AutoMod rules followed by destructive actions.",
                actor_count_threshold=1,
                guild_count_threshold=1,
                window_seconds=180.0,
                min_unique_targets=1,
                severity=ThreatSeverity.CRITICAL,
                recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
                requires_immediate_protection=True,
                cooldown_seconds=15.0,
            ),
        }

    # Configuration APIs
    def get_rule_config(self, guild_id: str, pattern_id: str) -> Optional[CorrelationRuleConfig]:
        """Returns the effective rule configuration for a guild, honoring per-guild overrides."""
        gid = str(guild_id)
        if gid in self._guild_rule_overrides and pattern_id in self._guild_rule_overrides[gid]:
            return self._guild_rule_overrides[gid][pattern_id]
        return self._rule_configs.get(pattern_id)

    def set_guild_rule_config(self, guild_id: str, pattern_id: str, config: CorrelationRuleConfig) -> None:
        """Sets a per-guild custom configuration override for a pattern."""
        self._guild_rule_overrides[str(guild_id)][pattern_id] = config

    def list_rules(self) -> List[CorrelationRuleConfig]:
        """Returns list of all active correlation rule configurations."""
        return list(self._rule_configs.values())

    def reset_guild_rules(self, guild_id: str) -> None:
        """Clears all custom rule overrides for a guild, reverting to global defaults."""
        self._guild_rule_overrides.pop(str(guild_id), None)

    # Pub-Sub Attachment
    def attach_to_collector(self, collector: Optional[Any] = None) -> None:
        """Subscribes this correlation engine to raw SecurityEventCollector stream."""
        from core.security.event_collector import SecurityEventCollector
        c = collector or SecurityEventCollector.get_instance()
        c.subscribe(self.process_event)
        logger.info("[SecurityCorrelationEngine] Attached to SecurityEventCollector stream.")

    def detach_from_collector(self, collector: Optional[Any] = None) -> None:
        """Unsubscribes from the SecurityEventCollector stream."""
        from core.security.event_collector import SecurityEventCollector
        c = collector or SecurityEventCollector.get_instance()
        c.unsubscribe(self.process_event)

    def attach_to_activity_manager(self, am: Optional[SecurityActivityManager] = None) -> None:
        """Subscribes to emergency signals emitted by the SecurityActivityManager."""
        target_am = am or self._activity_manager
        if self._am_subscriber_cb is None:
            self._am_subscriber_cb = self.process_activity_signal
            target_am.subscribe_signals(self._am_subscriber_cb)
            logger.info("[SecurityCorrelationEngine] Attached to SecurityActivityManager emergency signals.")

    def detach_from_activity_manager(self, am: Optional[SecurityActivityManager] = None) -> None:
        """Unsubscribes from the SecurityActivityManager emergency signals."""
        target_am = am or self._activity_manager
        if self._am_subscriber_cb:
            target_am.unsubscribe_signals(self._am_subscriber_cb)
            self._am_subscriber_cb = None

    def subscribe_signals(self, callback: Callable[[ThreatSignal], Any]) -> Callable[[ThreatSignal], Any]:
        """Subscribes a downstream component (e.g. Agent 4 Lockdown Engine) to ThreatSignal emissions."""
        self._signal_subscribers.append(callback)
        return callback

    def unsubscribe_signals(self, callback: Callable[[ThreatSignal], Any]) -> bool:
        """Unsubscribes a listener from ThreatSignal emissions."""
        before = len(self._signal_subscribers)
        self._signal_subscribers = [s for s in self._signal_subscribers if s != callback]
        return len(self._signal_subscribers) < before

    def clear_subscribers(self) -> None:
        """Removes all ThreatSignal subscribers."""
        self._signal_subscribers.clear()

    # Ingestion & Evaluation Pipeline
    async def process_event(self, event: SecurityEvent, current_time: Optional[float] = None) -> List[ThreatSignal]:
        """
        Asynchronous entry point for SecurityEvent ingestion.
        Delegates to synchronized thread-safe processing.
        """
        gid = event.guild_id
        async_lock = self._get_async_lock(gid)
        async with async_lock:
            signals = self.ingest_event_sync(event, current_time=current_time)

        for sig in signals:
            self._dispatch_signal(sig)

        return signals

    def ingest_event_sync(self, event: SecurityEvent, current_time: Optional[float] = None) -> List[ThreatSignal]:
        """
        Synchronous deterministic evaluation pipeline for an incoming SecurityEvent.
        Updates internal chronological sequences, detects pattern violations,
        and returns any generated ThreatSignal objects.
        """
        now = current_time if current_time is not None else (event.timestamp if event.timestamp else time.time())
        gid = event.guild_id

        # Deduplication check
        dedup_key = event.dedup_key or event.event_id
        if dedup_key in self._processed_events:
            prev_t = self._processed_events[dedup_key]
            if now - prev_t < 15.0:
                logger.debug(f"[SecurityCorrelationEngine] Suppressing duplicate event ingestion: {event.event_id}")
                return []
        self._processed_events[dedup_key] = now

        # Prune deduplication cache periodically
        self._prune_dedup_cache(now)

        thread_lock = self._guild_locks[gid]
        with thread_lock:
            # Insert event in chronological order into guild & actor sliding sequences
            self._insert_event_sorted(event, now)

            # Evaluate pattern rules
            signals: List[ThreatSignal] = []

            # 1. Burst of Bans
            sig = self._evaluate_rapid_bans(event, now)
            if sig:
                signals.append(sig)

            # 2. Burst of Kicks
            sig = self._evaluate_rapid_kicks(event, now)
            if sig:
                signals.append(sig)

            # 3. Channel Deletions
            sig = self._evaluate_channel_deletions(event, now)
            if sig:
                signals.append(sig)

            # 4. Role Deletions
            sig = self._evaluate_role_deletions(event, now)
            if sig:
                signals.append(sig)

            # 5. Permission Escalation -> Destruction
            sig = self._evaluate_permission_escalation_sequence(event, now)
            if sig:
                signals.append(sig)

            # 6. Dangerous Role Change -> Destruction
            sig = self._evaluate_dangerous_role_sequence(event, now)
            if sig:
                signals.append(sig)

            # 7. Webhook / Integration Abuse
            sig = self._evaluate_webhook_integration_abuse(event, now)
            if sig:
                signals.append(sig)

            # 8. Coordinated Multi-Vector Destruction
            sig = self._evaluate_coordinated_multi_vector(event, now)
            if sig:
                signals.append(sig)

            # 9. Security Weakening Prior to Destruction
            sig = self._evaluate_security_weakening_sequence(event, now)
            if sig:
                signals.append(sig)

            return signals

    def process_activity_signal(self, emergency_signal: EmergencySignal) -> Optional[ThreatSignal]:
        """
        Consumes an EmergencySignal from Agent 2's SecurityActivityManager and
        enriches it into a full correlated ThreatSignal with distinct facts and inferred intent.
        """
        rule_cfg = self.get_rule_config(emergency_signal.guild_id, emergency_signal.signal_type) or \
                   self.get_rule_config(emergency_signal.guild_id, PatternID.RAPID_BAN_BURST)

        # Check anti-alert storm cooldown
        actor_key = emergency_signal.actor_id or "guild"
        cooldown_key = (emergency_signal.guild_id, emergency_signal.signal_type, actor_key)
        now = time.time()
        last_info = self._alert_cooldowns.get(cooldown_key)
        if last_info:
            last_time, last_count = last_info
            cooldown_dur = rule_cfg.cooldown_seconds if rule_cfg else 10.0
            # If within cooldown and count hasn't escalated significantly, suppress
            if now - last_time < cooldown_dur and emergency_signal.current_count < int(last_count * 1.5):
                return None

        self._alert_cooldowns[cooldown_key] = (now, emergency_signal.current_count)

        # Distinguish observed facts from inferred intent
        observed_facts = {
            "source": "activity_manager_emergency_signal",
            "signal_type": emergency_signal.signal_type,
            "current_count": emergency_signal.current_count,
            "threshold_count": emergency_signal.threshold_count,
            "time_window_seconds": emergency_signal.window_seconds,
            "unique_targets_count": emergency_signal.unique_targets_count,
            "unique_targets": emergency_signal.unique_targets,
            "categories_involved": emergency_signal.categories_involved,
            "triggering_event_id": emergency_signal.triggering_event.event_id if emergency_signal.triggering_event else None,
            "attribution_confidence": emergency_signal.attribution_confidence,
            "is_whitelisted_actor": emergency_signal.is_whitelisted_actor,
        }

        # Demarcate hypothesis clearly
        inferred_intent = (
            f"Observed velocity ({emergency_signal.current_count} events / {emergency_signal.window_seconds}s) "
            f"strongly aligns with automated or malicious guild disruption in category '{emergency_signal.signal_type}'."
        )
        if emergency_signal.is_whitelisted_actor:
            inferred_intent += " Actor is configured as trusted/whitelisted; possible credential compromise or rogue admin action."

        # Map to ThreatSignal
        threat_sig = ThreatSignal(
            signal_id=f"threat_sig_{uuid.uuid4().hex[:12]}",
            pattern_id=emergency_signal.signal_type,
            pattern_name=emergency_signal.signal_type.replace("_", " ").title(),
            guild_id=emergency_signal.guild_id,
            severity=emergency_signal.severity if emergency_signal.severity in ThreatSeverity.ALL else ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.HIGH_CONFIDENCE if emergency_signal.attribution_confidence == AttributionConfidence.VERIFIED else ThreatConfidence.SUSPICIOUS,
            scope=emergency_signal.scope,
            actor_id=emergency_signal.actor_id,
            actor_name=emergency_signal.actor_name,
            is_whitelisted_actor=emergency_signal.is_whitelisted_actor,
            attribution_confidence=emergency_signal.attribution_confidence,
            recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN if emergency_signal.severity == "critical" else ResponseCategory.RESTRICT_ACTOR,
            requires_immediate_protection=(emergency_signal.severity == "critical"),
            time_window_seconds=emergency_signal.window_seconds,
            trigger_reasons=[
                f"Crossed emergency threshold {emergency_signal.current_count}/{emergency_signal.threshold_count} within {emergency_signal.window_seconds}s",
                f"Involved {emergency_signal.unique_targets_count} unique targets across {len(emergency_signal.categories_involved)} categories",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=[emergency_signal.triggering_event.event_id] if emergency_signal.triggering_event else [],
            target_ids=emergency_signal.unique_targets,
            triggering_event=emergency_signal.triggering_event,
            correlated_signals=[emergency_signal.signal_id],
            timestamp=emergency_signal.timestamp,
        )

        self._dispatch_signal(threat_sig)
        return threat_sig

    # Specific Pattern Evaluators
    def _evaluate_rapid_bans(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """Detects rapid bursts of member bans per actor or guild-wide."""
        if event.event_type != SecurityEventType.MEMBER_BAN:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.RAPID_BAN_BURST)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        # Query recent ban events within time window
        recent_bans = self._get_events_in_window(gid, aid, [SecurityEventType.MEMBER_BAN], win, now)
        ban_count = len(recent_bans)
        unique_targets = {e.target_id for e in recent_bans if e.target_id}

        # Check actor-level threshold if actor is known
        threshold = rule_cfg.actor_count_threshold if aid else rule_cfg.guild_count_threshold
        scope = "actor" if aid else "guild"

        # Also check guild-wide ban count in case actor is unknown or distributed
        guild_bans = self._get_events_in_window(gid, None, [SecurityEventType.MEMBER_BAN], win, now)
        guild_ban_count = len(guild_bans)
        guild_targets = {e.target_id for e in guild_bans if e.target_id}

        matched = False
        effective_count = ban_count
        effective_targets = unique_targets
        effective_events = recent_bans

        if aid and ban_count >= rule_cfg.actor_count_threshold and len(unique_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "actor"
            effective_count = ban_count
            effective_targets = unique_targets
            effective_events = recent_bans
        elif guild_ban_count >= rule_cfg.guild_count_threshold and len(guild_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "guild"
            effective_count = guild_ban_count
            effective_targets = guild_targets
            effective_events = guild_bans

        if not matched:
            return None

        # Anti-alert storm check
        actor_key = aid if scope == "actor" else "guild"
        if not self._check_cooldown_and_update(gid, PatternID.RAPID_BAN_BURST, actor_key, effective_count, rule_cfg.cooldown_seconds, now):
            return None

        # Build facts vs intent
        target_names = [e.target_name for e in effective_events if e.target_name][:10]
        observed_facts = {
            "ban_count": effective_count,
            "threshold_configured": threshold,
            "window_seconds": win,
            "unique_targets_count": len(effective_targets),
            "sample_target_names": target_names,
            "scope": scope,
            "actor_id": aid if scope == "actor" else None,
            "attribution_confidence": event.attribution_confidence if scope == "actor" else AttributionConfidence.UNKNOWN,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        # Determine graduated confidence
        if scope == "actor" and event.attribution_confidence == AttributionConfidence.VERIFIED:
            conf = ThreatConfidence.HIGH_CONFIDENCE if effective_count < 20 else ThreatConfidence.CONFIRMED
        elif scope == "actor" and event.attribution_confidence == AttributionConfidence.PROBABLE:
            conf = ThreatConfidence.HIGH_CONFIDENCE
        else:
            conf = ThreatConfidence.SUSPICIOUS

        inferred_intent = (
            f"High-velocity mass ban raid in progress ({effective_count} bans in {win:.1f}s). "
            f"Pattern matches rogue administrative access or compromised bot/user token wiping server members."
        )
        if event.is_whitelisted_actor and scope == "actor":
            inferred_intent += " CAUTION: Initiated by a whitelisted or admin account; investigate potential account takeover."

        return ThreatSignal(
            pattern_id=PatternID.RAPID_BAN_BURST,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope=scope,
            actor_id=aid if scope == "actor" else None,
            actor_name=event.actor_name if scope == "actor" else None,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if scope == "actor" else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Observed {effective_count} member bans within {win:.1f}s (configured limit: {threshold})",
                f"Affected {len(effective_targets)} unique user accounts",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=[e.event_id for e in effective_events],
            target_ids=list(effective_targets),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_rapid_kicks(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """Detects rapid bursts of member kicks or removals."""
        if event.event_type not in (SecurityEventType.MEMBER_KICK, SecurityEventType.MEMBER_REMOVE):
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.RAPID_KICK_BURST)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        types = [SecurityEventType.MEMBER_KICK, SecurityEventType.MEMBER_REMOVE]
        recent_kicks = self._get_events_in_window(gid, aid, types, win, now)
        kick_count = len(recent_kicks)
        unique_targets = {e.target_id for e in recent_kicks if e.target_id}

        guild_kicks = self._get_events_in_window(gid, None, types, win, now)
        guild_kick_count = len(guild_kicks)
        guild_targets = {e.target_id for e in guild_kicks if e.target_id}

        matched = False
        scope = "actor" if aid else "guild"
        effective_count = kick_count
        effective_targets = unique_targets
        effective_events = recent_kicks

        if aid and kick_count >= rule_cfg.actor_count_threshold and len(unique_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "actor"
        elif guild_kick_count >= rule_cfg.guild_count_threshold and len(guild_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "guild"
            effective_count = guild_kick_count
            effective_targets = guild_targets
            effective_events = guild_kicks

        if not matched:
            return None

        actor_key = aid if scope == "actor" else "guild"
        if not self._check_cooldown_and_update(gid, PatternID.RAPID_KICK_BURST, actor_key, effective_count, rule_cfg.cooldown_seconds, now):
            return None

        observed_facts = {
            "kick_count": effective_count,
            "threshold_configured": rule_cfg.actor_count_threshold if scope == "actor" else rule_cfg.guild_count_threshold,
            "window_seconds": win,
            "unique_targets_count": len(effective_targets),
            "scope": scope,
            "actor_id": aid if scope == "actor" else None,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.HIGH_CONFIDENCE if (scope == "actor" and event.is_verified) else ThreatConfidence.SUSPICIOUS
        inferred_intent = (
            f"Abnormal burst of member kicks ({effective_count} in {win:.1f}s) targeting members. "
            f"May represent mass purge attempt or abusive moderator script."
        )

        return ThreatSignal(
            pattern_id=PatternID.RAPID_KICK_BURST,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope=scope,
            actor_id=aid if scope == "actor" else None,
            actor_name=event.actor_name if scope == "actor" else None,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if scope == "actor" else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Observed {effective_count} member kicks within {win:.1f}s",
                f"Affected {len(effective_targets)} distinct users",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=[e.event_id for e in effective_events],
            target_ids=list(effective_targets),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_channel_deletions(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """Detects rapid channel or category deletions."""
        if event.event_type not in (SecurityEventType.CHANNEL_DELETE, SecurityEventType.THREAD_DELETE):
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.REPEATED_CHANNEL_DELETIONS)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        types = [SecurityEventType.CHANNEL_DELETE, SecurityEventType.THREAD_DELETE]
        recent_events = self._get_events_in_window(gid, aid, types, win, now)
        count = len(recent_events)
        unique_targets = {e.target_id for e in recent_events if e.target_id}

        guild_events = self._get_events_in_window(gid, None, types, win, now)
        guild_count = len(guild_events)
        guild_targets = {e.target_id for e in guild_events if e.target_id}

        matched = False
        scope = "actor" if aid else "guild"
        effective_count = count
        effective_targets = unique_targets
        effective_events = recent_events

        if aid and count >= rule_cfg.actor_count_threshold and len(unique_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "actor"
        elif guild_count >= rule_cfg.guild_count_threshold and len(guild_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "guild"
            effective_count = guild_count
            effective_targets = guild_targets
            effective_events = guild_events

        if not matched:
            return None

        actor_key = aid if scope == "actor" else "guild"
        if not self._check_cooldown_and_update(gid, PatternID.REPEATED_CHANNEL_DELETIONS, actor_key, effective_count, rule_cfg.cooldown_seconds, now):
            return None

        channel_names = [e.target_name for e in effective_events if e.target_name]
        observed_facts = {
            "channel_deletion_count": effective_count,
            "threshold_configured": rule_cfg.actor_count_threshold if scope == "actor" else rule_cfg.guild_count_threshold,
            "window_seconds": win,
            "deleted_channels": channel_names,
            "scope": scope,
            "actor_id": aid if scope == "actor" else None,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.CONFIRMED if (scope == "actor" and event.is_verified) else ThreatConfidence.HIGH_CONFIDENCE
        inferred_intent = (
            f"Rapid channel eradication attack ({effective_count} channels deleted in {win:.1f}s). "
            f"Direct threat to server structure and community history. Immediate isolation indicated."
        )

        return ThreatSignal(
            pattern_id=PatternID.REPEATED_CHANNEL_DELETIONS,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope=scope,
            actor_id=aid if scope == "actor" else None,
            actor_name=event.actor_name if scope == "actor" else None,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if scope == "actor" else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Observed {effective_count} channel deletions in {win:.1f}s",
                f"Deleted channels: {', '.join(channel_names[:5]) if channel_names else 'multiple'}",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=[e.event_id for e in effective_events],
            target_ids=list(effective_targets),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_role_deletions(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """Detects rapid role deletions."""
        if event.event_type != SecurityEventType.ROLE_DELETE:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.REPEATED_ROLE_DELETIONS)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        types = [SecurityEventType.ROLE_DELETE]
        recent_events = self._get_events_in_window(gid, aid, types, win, now)
        count = len(recent_events)
        unique_targets = {e.target_id for e in recent_events if e.target_id}

        guild_events = self._get_events_in_window(gid, None, types, win, now)
        guild_count = len(guild_events)
        guild_targets = {e.target_id for e in guild_events if e.target_id}

        matched = False
        scope = "actor" if aid else "guild"
        effective_count = count
        effective_targets = unique_targets
        effective_events = recent_events

        if aid and count >= rule_cfg.actor_count_threshold and len(unique_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "actor"
        elif guild_count >= rule_cfg.guild_count_threshold and len(guild_targets) >= rule_cfg.min_unique_targets:
            matched = True
            scope = "guild"
            effective_count = guild_count
            effective_targets = guild_targets
            effective_events = guild_events

        if not matched:
            return None

        actor_key = aid if scope == "actor" else "guild"
        if not self._check_cooldown_and_update(gid, PatternID.REPEATED_ROLE_DELETIONS, actor_key, effective_count, rule_cfg.cooldown_seconds, now):
            return None

        role_names = [e.target_name for e in effective_events if e.target_name]
        observed_facts = {
            "role_deletion_count": effective_count,
            "threshold_configured": rule_cfg.actor_count_threshold if scope == "actor" else rule_cfg.guild_count_threshold,
            "window_seconds": win,
            "deleted_roles": role_names,
            "scope": scope,
            "actor_id": aid if scope == "actor" else None,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.CONFIRMED if (scope == "actor" and event.is_verified) else ThreatConfidence.HIGH_CONFIDENCE
        inferred_intent = (
            f"Rapid role stripping attack ({effective_count} roles deleted in {win:.1f}s). "
            f"Pattern indicates deliberate neutralization of hierarchy before wider raid."
        )

        return ThreatSignal(
            pattern_id=PatternID.REPEATED_ROLE_DELETIONS,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope=scope,
            actor_id=aid if scope == "actor" else None,
            actor_name=event.actor_name if scope == "actor" else None,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if scope == "actor" else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Observed {effective_count} role deletions in {win:.1f}s",
                f"Deleted roles: {', '.join(role_names[:5]) if role_names else 'multiple'}",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=[e.event_id for e in effective_events],
            target_ids=list(effective_targets),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_permission_escalation_sequence(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """
        Detects dangerous permission escalation or permission overwrite modification
        followed by a destructive action (ban, kick, channel delete, role delete) within lookback window.
        """
        destructive_types = {
            SecurityEventType.MEMBER_BAN,
            SecurityEventType.MEMBER_KICK,
            SecurityEventType.CHANNEL_DELETE,
            SecurityEventType.ROLE_DELETE,
        }
        if event.event_type not in destructive_types:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        escalation_types = [
            SecurityEventType.DANGEROUS_PERMISSION_GRANT,
            SecurityEventType.PERMISSION_OVERWRITE_UPDATE,
            SecurityEventType.ROLE_UPDATE,
        ]

        # Check actor escalation first
        escalation_events = []
        if aid:
            escalation_events = self._get_events_in_window(gid, aid, escalation_types, win, now)

        # If not found for actor, check guild-wide recent escalation
        guild_level = False
        if not escalation_events:
            escalation_events = self._get_events_in_window(gid, None, escalation_types, win, now)
            guild_level = True

        if not escalation_events:
            return None

        actor_key = aid if (aid and not guild_level) else "guild"
        if not self._check_cooldown_and_update(gid, PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION, actor_key, len(escalation_events) + 1, rule_cfg.cooldown_seconds, now):
            return None

        earliest_escalation = escalation_events[0]
        observed_facts = {
            "escalation_event_type": earliest_escalation.event_type,
            "escalation_event_id": earliest_escalation.event_id,
            "escalation_timestamp": earliest_escalation.timestamp,
            "destructive_event_type": event.event_type,
            "destructive_event_id": event.event_id,
            "destructive_target": event.target_name or event.target_id,
            "delta_seconds": round(event.timestamp - earliest_escalation.timestamp, 2),
            "actor_id": aid,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.CONFIRMED if (aid and earliest_escalation.actor_id == aid and event.is_verified) else ThreatConfidence.HIGH_CONFIDENCE
        inferred_intent = (
            f"Privilege escalation sequence confirmed: Permission modification ({earliest_escalation.event_type}) "
            f"was immediately followed {observed_facts['delta_seconds']}s later by destructive action ({event.event_type}). "
            f"Pattern indicates intentional privilege abuse to conduct unauthorized destruction."
        )

        all_event_ids = [e.event_id for e in escalation_events] + [event.event_id]
        targets = [e.target_id for e in escalation_events if e.target_id]
        if event.target_id:
            targets.append(event.target_id)

        return ThreatSignal(
            pattern_id=PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope="actor" if aid and not guild_level else "guild",
            actor_id=aid,
            actor_name=event.actor_name,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if aid else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Permission escalation event '{earliest_escalation.event_type}' observed",
                f"Destructive event '{event.event_type}' executed within {observed_facts['delta_seconds']}s",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=all_event_ids,
            target_ids=list(dict.fromkeys(targets)),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_dangerous_role_sequence(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """
        Detects dangerous role assignment (e.g. member assigned administrative role)
        followed by destructive activity (ban, kick, channel delete) within lookback window.
        """
        destructive_types = {
            SecurityEventType.MEMBER_BAN,
            SecurityEventType.MEMBER_KICK,
            SecurityEventType.CHANNEL_DELETE,
            SecurityEventType.ROLE_DELETE,
        }
        if event.event_type not in destructive_types:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        role_assign_types = [
            SecurityEventType.MEMBER_ROLE_UPDATE,
            "dangerous_role_assign",
        ]

        # Look for role assignments targeting this actor, or role assignments performed by this actor
        recent_role_events = self._get_events_in_window(gid, None, role_assign_types, win, now)
        relevant_role_events = [
            e for e in recent_role_events
            if (aid and (e.target_id == aid or e.actor_id == aid))
        ]

        if not relevant_role_events:
            return None

        earliest_role_event = relevant_role_events[0]
        actor_key = aid or "guild"
        if not self._check_cooldown_and_update(gid, PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION, actor_key, len(relevant_role_events) + 1, rule_cfg.cooldown_seconds, now):
            return None

        delta = round(event.timestamp - earliest_role_event.timestamp, 2)
        observed_facts = {
            "role_event_id": earliest_role_event.event_id,
            "role_target_id": earliest_role_event.target_id,
            "role_actor_id": earliest_role_event.actor_id,
            "destructive_event_id": event.event_id,
            "destructive_action": event.event_type,
            "delta_seconds": delta,
            "actor_id": aid,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.HIGH_CONFIDENCE if event.is_verified else ThreatConfidence.SUSPICIOUS
        inferred_intent = (
            f"Role escalation exploit detected: Role modification ({earliest_role_event.event_type}) "
            f"linked to actor `{aid}` was followed {delta}s later by destructive action `{event.event_type}`."
        )

        all_events = [e.event_id for e in relevant_role_events] + [event.event_id]
        targets = [e.target_id for e in relevant_role_events if e.target_id]
        if event.target_id:
            targets.append(event.target_id)

        return ThreatSignal(
            pattern_id=PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope="actor" if aid else "guild",
            actor_id=aid,
            actor_name=event.actor_name,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if aid else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Role assignment modification observed within {delta}s of destructive action",
                f"Destructive action: {event.event_type} on target {event.target_name or event.target_id}",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=all_events,
            target_ids=list(dict.fromkeys(targets)),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_webhook_integration_abuse(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """Detects webhook/integration creation spikes or pairing with destructive events."""
        webhook_types = {
            SecurityEventType.WEBHOOK_CREATE,
            SecurityEventType.WEBHOOK_UPDATE,
            SecurityEventType.WEBHOOK_DELETE,
            SecurityEventType.INTEGRATIONS_UPDATE,
            SecurityEventType.BOT_ADD,
        }
        destructive_types = {
            SecurityEventType.MEMBER_BAN,
            SecurityEventType.MEMBER_KICK,
            SecurityEventType.CHANNEL_DELETE,
            SecurityEventType.ROLE_DELETE,
        }

        if event.event_type not in webhook_types and event.event_type not in destructive_types:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.WEBHOOK_INTEGRATION_ABUSE)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        recent_webhooks = self._get_events_in_window(gid, aid, list(webhook_types), win, now)
        recent_destructive = self._get_events_in_window(gid, aid, list(destructive_types), win, now)

        # Trigger if either:
        # A) 3+ webhook creations in short interval
        # B) Webhook created AND destructive action occurred in same window
        is_spike = len(recent_webhooks) >= rule_cfg.actor_count_threshold
        is_destructive_pairing = (len(recent_webhooks) >= 1 and len(recent_destructive) >= 1)

        if not (is_spike or is_destructive_pairing):
            return None

        actor_key = aid or "guild"
        total_events = len(recent_webhooks) + len(recent_destructive)
        if not self._check_cooldown_and_update(gid, PatternID.WEBHOOK_INTEGRATION_ABUSE, actor_key, total_events, rule_cfg.cooldown_seconds, now):
            return None

        observed_facts = {
            "webhook_event_count": len(recent_webhooks),
            "destructive_event_count": len(recent_destructive),
            "is_spike": is_spike,
            "is_destructive_pairing": is_destructive_pairing,
            "actor_id": aid,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.HIGH_CONFIDENCE if (is_destructive_pairing and event.is_verified) else ThreatConfidence.SUSPICIOUS
        inferred_intent = (
            f"Webhook integration abuse detected: {'High volume webhook creation' if is_spike else 'Webhook activity combined with destructive actions'} "
            f"suggests backdoor creation or spam webhook injection."
        )

        all_events = [e.event_id for e in recent_webhooks] + [e.event_id for e in recent_destructive]
        targets = [e.target_id for e in recent_webhooks + recent_destructive if e.target_id]

        return ThreatSignal(
            pattern_id=PatternID.WEBHOOK_INTEGRATION_ABUSE,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope="actor" if aid else "guild",
            actor_id=aid,
            actor_name=event.actor_name,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if aid else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=is_destructive_pairing,  # escalate to immediate if paired with destruction
            time_window_seconds=win,
            trigger_reasons=[
                f"Observed {len(recent_webhooks)} webhook/bot modifications within {win:.1f}s",
                f"Observed {len(recent_destructive)} concurrent destructive operations",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=all_events,
            target_ids=list(dict.fromkeys(targets)),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_coordinated_multi_vector(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """Detects simultaneous activity across multiple distinct destructive categories."""
        all_destructive_types = [
            SecurityEventType.MEMBER_BAN,
            SecurityEventType.MEMBER_KICK,
            SecurityEventType.MEMBER_REMOVE,
            SecurityEventType.CHANNEL_DELETE,
            SecurityEventType.ROLE_DELETE,
            SecurityEventType.DANGEROUS_PERMISSION_GRANT,
            SecurityEventType.WEBHOOK_CREATE,
        ]
        if event.event_type not in all_destructive_types:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.COORDINATED_MULTI_VECTOR)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds
        min_vectors = int(rule_cfg.custom_params.get("min_distinct_vectors", 3))

        # Check actor events if actor is known
        actor_events = self._get_events_in_window(gid, aid, all_destructive_types, win, now) if aid else []
        actor_categories = self._extract_distinct_categories(actor_events)

        guild_events = self._get_events_in_window(gid, None, all_destructive_types, win, now)
        guild_categories = self._extract_distinct_categories(guild_events)

        matched = False
        scope = "actor" if aid else "guild"
        effective_events = actor_events
        effective_categories = actor_categories

        if aid and len(actor_categories) >= min_vectors and len(actor_events) >= rule_cfg.actor_count_threshold:
            matched = True
            scope = "actor"
        elif len(guild_categories) >= min_vectors and len(guild_events) >= rule_cfg.guild_count_threshold:
            matched = True
            scope = "guild"
            effective_events = guild_events
            effective_categories = guild_categories

        if not matched:
            return None

        actor_key = aid if scope == "actor" else "guild"
        if not self._check_cooldown_and_update(gid, PatternID.COORDINATED_MULTI_VECTOR, actor_key, len(effective_events), rule_cfg.cooldown_seconds, now):
            return None

        unique_targets = {e.target_id for e in effective_events if e.target_id}
        observed_facts = {
            "total_destructive_events": len(effective_events),
            "distinct_vectors_count": len(effective_categories),
            "distinct_vectors": list(effective_categories),
            "unique_targets_count": len(unique_targets),
            "scope": scope,
            "actor_id": aid if scope == "actor" else None,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.HIGH_CONFIDENCE if (scope == "actor" and event.is_verified) else ThreatConfidence.SUSPICIOUS
        inferred_intent = (
            f"Coordinated multi-vector attack detected across {len(effective_categories)} distinct vectors "
            f"({', '.join(effective_categories)}). Indicates a scripted raid bot or determined attacker "
            f"attempting simultaneous maximum disruption across server systems."
        )

        return ThreatSignal(
            pattern_id=PatternID.COORDINATED_MULTI_VECTOR,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope=scope,
            actor_id=aid if scope == "actor" else None,
            actor_name=event.actor_name if scope == "actor" else None,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if scope == "actor" else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Multi-vector destruction active across {len(effective_categories)} vectors: {', '.join(effective_categories)}",
                f"Total {len(effective_events)} destructive actions in {win:.1f}s",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=[e.event_id for e in effective_events],
            target_ids=list(unique_targets),
            triggering_event=event,
            timestamp=now,
        )

    def _evaluate_security_weakening_sequence(self, event: SecurityEvent, now: float) -> Optional[ThreatSignal]:
        """
        Detects attempts to weaken server security (reducing verification level,
        disabling MFA requirements, deleting AutoMod rules) followed by destructive activity.
        """
        destructive_types = {
            SecurityEventType.MEMBER_BAN,
            SecurityEventType.MEMBER_KICK,
            SecurityEventType.CHANNEL_DELETE,
            SecurityEventType.ROLE_DELETE,
        }
        if event.event_type not in destructive_types:
            return None

        rule_cfg = self.get_rule_config(event.guild_id, PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION)
        if not rule_cfg or not rule_cfg.enabled:
            return None

        gid = event.guild_id
        aid = event.actor_id
        win = rule_cfg.window_seconds

        weakening_types = [
            SecurityEventType.SECURITY_SETTINGS_UPDATE,
            SecurityEventType.GUILD_UPDATE,
            SecurityEventType.AUTOMOD_RULE_DELETE,
        ]

        recent_weakening = self._get_events_in_window(gid, aid, weakening_types, win, now)
        if not recent_weakening:
            recent_weakening = self._get_events_in_window(gid, None, weakening_types, win, now)

        if not recent_weakening:
            return None

        earliest_weakening = recent_weakening[0]
        actor_key = aid or "guild"
        if not self._check_cooldown_and_update(gid, PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION, actor_key, len(recent_weakening) + 1, rule_cfg.cooldown_seconds, now):
            return None

        delta = round(event.timestamp - earliest_weakening.timestamp, 2)
        observed_facts = {
            "weakening_event_type": earliest_weakening.event_type,
            "weakening_event_id": earliest_weakening.event_id,
            "destructive_event_type": event.event_type,
            "destructive_event_id": event.event_id,
            "delta_seconds": delta,
            "actor_id": aid,
            "is_whitelisted_actor": bool(event.is_whitelisted_actor),
        }

        conf = ThreatConfidence.HIGH_CONFIDENCE if event.is_verified else ThreatConfidence.SUSPICIOUS
        inferred_intent = (
            f"Security defense disabling sequence: Server security settings or AutoMod rules "
            f"were altered/removed ({earliest_weakening.event_type}) {delta}s before destructive operations ({event.event_type}). "
            f"Pattern indicates deliberate neutralization of server safeguards before executing an attack."
        )

        all_events = [e.event_id for e in recent_weakening] + [event.event_id]
        targets = [e.target_id for e in recent_weakening if e.target_id]
        if event.target_id:
            targets.append(event.target_id)

        return ThreatSignal(
            pattern_id=PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION,
            pattern_name=rule_cfg.pattern_name,
            guild_id=gid,
            severity=rule_cfg.severity,
            confidence=conf,
            scope="actor" if aid else "guild",
            actor_id=aid,
            actor_name=event.actor_name,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if aid else AttributionConfidence.UNKNOWN,
            recommended_response=rule_cfg.recommended_response,
            requires_immediate_protection=rule_cfg.requires_immediate_protection,
            time_window_seconds=win,
            trigger_reasons=[
                f"Security configuration was modified ({earliest_weakening.event_type})",
                f"Destructive action ({event.event_type}) followed {delta}s later",
            ],
            observed_facts=observed_facts,
            inferred_intent=inferred_intent,
            event_ids=all_events,
            target_ids=list(dict.fromkeys(targets)),
            triggering_event=event,
            timestamp=now,
        )

    # Internal sequence and sliding window helpers
    def _insert_event_sorted(self, event: SecurityEvent, now: float) -> None:
        """Maintains chronologically sorted sequences per guild and per actor with bounded retention."""
        gid = event.guild_id
        aid = event.actor_id

        # Guild sequence
        guild_seq = self._guild_event_sequences[gid]
        self._insort_event(guild_seq, event)
        if len(guild_seq) > self._max_events_per_guild:
            guild_seq.pop(0)

        # Actor sequence
        if aid:
            actor_seq = self._actor_event_sequences[gid][aid]
            self._insort_event(actor_seq, event)
            if len(actor_seq) > self._max_events_per_actor:
                actor_seq.pop(0)

        # Prune older than retention window
        cutoff = now - self._event_retention_seconds
        while guild_seq and guild_seq[0].timestamp < cutoff:
            guild_seq.pop(0)

        if aid:
            while actor_seq and actor_seq[0].timestamp < cutoff:
                actor_seq.pop(0)

    @staticmethod
    def _insort_event(seq: List[SecurityEvent], event: SecurityEvent) -> None:
        """Inserts an event into a sorted sequence by timestamp using binary search."""
        if not seq or event.timestamp >= seq[-1].timestamp:
            seq.append(event)
        elif event.timestamp <= seq[0].timestamp:
            seq.insert(0, event)
        else:
            # Custom binary search insert based on event.timestamp
            timestamps = [e.timestamp for e in seq]
            idx = bisect.bisect_right(timestamps, event.timestamp)
            seq.insert(idx, event)

    def _get_events_in_window(
        self,
        guild_id: str,
        actor_id: Optional[str],
        event_types: List[str],
        window_seconds: float,
        now: float,
    ) -> List[SecurityEvent]:
        """
        Retrieves matching events occurring within the specified sliding window [now - window_seconds, now + skew].
        Handles clock skew and out-of-order timestamps gracefully.
        """
        gid = str(guild_id)
        if actor_id:
            seq = self._actor_event_sequences.get(gid, {}).get(str(actor_id), [])
        else:
            seq = self._guild_event_sequences.get(gid, [])

        if not seq:
            return []

        cutoff = now - window_seconds
        allowed_types = set(event_types)

        # Filter events in time window matching event types
        matching: List[SecurityEvent] = []
        for ev in reversed(seq):
            if ev.timestamp < cutoff:
                break
            if ev.event_type in allowed_types:
                matching.append(ev)

        matching.reverse()
        return matching

    @staticmethod
    def _extract_distinct_categories(events: List[SecurityEvent]) -> Set[str]:
        """Categorizes a collection of security events into high-level attack vectors."""
        categories: Set[str] = set()
        for ev in events:
            t = ev.event_type
            if t in (SecurityEventType.MEMBER_BAN, SecurityEventType.MEMBER_UNBAN):
                categories.add("bans")
            elif t in (SecurityEventType.MEMBER_KICK, SecurityEventType.MEMBER_REMOVE):
                categories.add("kicks")
            elif t in (SecurityEventType.CHANNEL_DELETE, SecurityEventType.THREAD_DELETE):
                categories.add("channels")
            elif t == SecurityEventType.ROLE_DELETE:
                categories.add("roles")
            elif t in (SecurityEventType.DANGEROUS_PERMISSION_GRANT, SecurityEventType.PERMISSION_OVERWRITE_UPDATE):
                categories.add("permissions")
            elif t in (SecurityEventType.WEBHOOK_CREATE, SecurityEventType.WEBHOOK_UPDATE, SecurityEventType.BOT_ADD):
                categories.add("webhooks")
            elif t in (SecurityEventType.SECURITY_SETTINGS_UPDATE, SecurityEventType.GUILD_UPDATE):
                categories.add("settings")
            else:
                categories.add(t)
        return categories

    def _check_cooldown_and_update(
        self,
        guild_id: str,
        pattern_id: str,
        actor_key: str,
        current_count: int,
        cooldown_seconds: float,
        now: float,
    ) -> bool:
        """
        Anti-alert storm mechanism:
        Suppresses identical alerts within the cooldown window UNLESS significant escalation occurs.
        """
        key = (guild_id, pattern_id, actor_key)
        last_info = self._alert_cooldowns.get(key)
        if last_info:
            last_time, last_count = last_info
            if now - last_time < cooldown_seconds:
                # Allow escalation if count has increased by >= 50%
                if current_count >= int(last_count * 1.5) and current_count >= last_count + 3:
                    self._alert_cooldowns[key] = (now, current_count)
                    return True
                return False

        self._alert_cooldowns[key] = (now, current_count)
        return True

    def _prune_dedup_cache(self, now: float) -> None:
        """Removes expired entries from the deduplication tracking cache."""
        cutoff = now - 60.0
        expired = [k for k, t in self._processed_events.items() if t < cutoff]
        for k in expired:
            self._processed_events.pop(k, None)

        # Prune alert cooldowns older than 5 minutes
        cooldown_cutoff = now - 300.0
        expired_cooldowns = [k for k, (t, _) in self._alert_cooldowns.items() if t < cooldown_cutoff]
        for k in expired_cooldowns:
            self._alert_cooldowns.pop(k, None)

    def _dispatch_signal(self, signal: ThreatSignal) -> None:
        """Notifies subscribers and logs signal to history buffer and database."""
        self._signal_history.append(signal)

        # Asynchronous DB persist without delaying pipeline
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._persist_signal(signal))
        except RuntimeError:
            pass

        # Notify downstream subscribers (e.g. Agent 4 Lockdown Engine)
        for subscriber in list(self._signal_subscribers):
            try:
                if inspect.iscoroutinefunction(subscriber):
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_running():
                            loop.create_task(subscriber(signal))
                    except RuntimeError:
                        pass
                else:
                    subscriber(signal)
            except Exception as err:
                logger.error(f"[SecurityCorrelationEngine] Error in ThreatSignal subscriber: {err}")

    async def _persist_signal(self, signal: ThreatSignal) -> None:
        """Persists ThreatSignal to database collection 'security_threat_signals'."""
        try:
            col = database.collection("security_threat_signals")
            doc = signal.to_dict()
            if hasattr(col, "insert_one"):
                res = col.insert_one(doc)
                if inspect.isawaitable(res):
                    await res
        except Exception as err:
            logger.debug(f"[SecurityCorrelationEngine] Failed to persist threat signal {signal.signal_id}: {err}")

    # Forensic & Inspection APIs
    def get_recent_signals(self, guild_id: Optional[str] = None, limit: int = 50) -> List[ThreatSignal]:
        """Retrieves recently detected ThreatSignals, newest first."""
        signals = list(self._signal_history)
        if guild_id:
            signals = [s for s in signals if s.guild_id == str(guild_id)]
        signals.sort(key=lambda s: s.timestamp, reverse=True)
        return signals[:limit]

    def clear_guild(self, guild_id: str) -> None:
        """Resets all in-memory correlation state for a guild."""
        gid = str(guild_id)
        self._guild_event_sequences.pop(gid, None)
        self._actor_event_sequences.pop(gid, None)
        self._guild_rule_overrides.pop(gid, None)
        keys_to_remove = [k for k in self._alert_cooldowns.keys() if k[0] == gid]
        for k in keys_to_remove:
            self._alert_cooldowns.pop(k, None)


# Singleton instance
security_correlation_engine = SecurityCorrelationEngine.get_instance()
