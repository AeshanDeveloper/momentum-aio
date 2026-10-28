"""
Sentinel™ Security Activity Manager.

Agent 2 of 8 Security Core: High-performance rolling activity counter and
emergency detection preparation pipeline. Consumes normalized SecurityEvent
instances from the observation layer (Agent 1).

Key capabilities:
- Dual tracking: per-actor when known, and guild-wide for all events (including unknown actors).
- Bounded in-memory sliding windows for all destructive vectors and multi-event combinations.
- Real-time threshold evaluation on every incoming event without waiting for window expiration.
- EmergencySignal generation for downstream Threat Detector (Agent 3).
- Fine-grained per-guild concurrency locking (no single global lock serializing unrelated guilds).
- Out-of-order and late timestamp handling with bounded ring buffers.
- Automatic expiration of idle actors and strict memory bounds.
- Whitelisted actors contribute to counters without suppression.
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

from core.logging.logger import logger
from database.database import database
from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
)
from core.security.antinuke import AntiNukeManager, AntiNukeConstants


class ActivityCategory:
    """Canonical categories for grouping and multi-vector correlation."""
    MEMBER_BAN = "member_ban"
    MEMBER_UNBAN = "member_unban"
    MEMBER_KICK = "member_kick"
    MEMBER_REMOVE = "member_remove"
    CHANNEL_DELETE = "channel_delete"
    ROLE_DELETE = "role_delete"
    PERMISSION_CHANGE = "permission_change"
    DANGEROUS_ROLE_ASSIGN = "dangerous_role_assign"
    WEBHOOK_INTEGRATION = "webhook_integration"
    BOT_ADD = "bot_add"
    GUILD_SETTINGS = "guild_settings"
    ALL_DESTRUCTIVE = "all_destructive"

    ALL = {
        MEMBER_BAN,
        MEMBER_UNBAN,
        MEMBER_KICK,
        MEMBER_REMOVE,
        CHANNEL_DELETE,
        ROLE_DELETE,
        PERMISSION_CHANGE,
        DANGEROUS_ROLE_ASSIGN,
        WEBHOOK_INTEGRATION,
        BOT_ADD,
        GUILD_SETTINGS,
        ALL_DESTRUCTIVE,
    }


class EmergencySignalType:
    """Canonical emergency signal types emitted to downstream Agent 3 (Threat Detector)."""
    RAPID_BURST_BAN = "rapid_burst_ban"
    RAPID_BURST_KICK = "rapid_burst_kick"
    MASS_CHANNEL_DELETE = "mass_channel_delete"
    MASS_ROLE_DELETE = "mass_role_delete"
    DANGEROUS_PERMISSION_ESCALATION = "dangerous_permission_escalation"
    PRIVILEGE_ESCALATION_THEN_DESTRUCTION = "privilege_escalation_then_destruction"
    COORDINATED_MULTI_VECTOR = "coordinated_multi_vector"
    WEBHOOK_INTEGRATION_SPIKE = "webhook_integration_spike"
    ROGUE_BOT_BURST = "rogue_bot_burst"
    CUSTOM_THRESHOLD_BREACH = "custom_threshold_breach"


@dataclass
class ActivityItem:
    """Compact record representing a single event occurrence within a rolling window."""
    timestamp: float
    event_id: str
    event_type: str
    category: str
    target_id: Optional[str]
    target_name: Optional[str]
    actor_id: Optional[str]
    actor_name: Optional[str]
    attribution_confidence: str
    is_whitelisted: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For bisect ordering by timestamp
    def __lt__(self, other: "ActivityItem") -> bool:
        return self.timestamp < other.timestamp


@dataclass
class ActivityWindowSummary:
    """Statistical summary of activity within a specific category and time window."""
    category: str
    window_seconds: float
    count: int
    unique_targets: Set[str]
    unique_target_count: int
    frequency: float  # events per second
    earliest_timestamp: Optional[float]
    latest_timestamp: Optional[float]
    span_seconds: float
    distinct_categories: Set[str]
    event_ids: List[str]


@dataclass
class EmergencySignal:
    """
    Actionable threat signal produced by the activity counter and consumed
    by the downstream threat detector (Agent 3).
    """
    signal_id: str
    signal_type: str
    guild_id: str
    severity: str  # "low", "medium", "high", "critical"
    scope: str     # "actor" or "guild"
    actor_id: Optional[str]
    actor_name: Optional[str]
    is_whitelisted_actor: bool
    attribution_confidence: str  # "verified", "probable", "unknown"
    current_count: int
    threshold_count: int
    window_seconds: float
    unique_targets_count: int
    unique_targets: List[str]
    event_types_involved: List[str]
    categories_involved: List[str]
    triggering_event: SecurityEvent
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type,
            "guild_id": self.guild_id,
            "severity": self.severity,
            "scope": self.scope,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "is_whitelisted_actor": self.is_whitelisted_actor,
            "attribution_confidence": self.attribution_confidence,
            "current_count": self.current_count,
            "threshold_count": self.threshold_count,
            "window_seconds": self.window_seconds,
            "unique_targets_count": self.unique_targets_count,
            "unique_targets": self.unique_targets,
            "event_types_involved": self.event_types_involved,
            "categories_involved": self.categories_involved,
            "triggering_event_id": self.triggering_event.event_id if self.triggering_event else None,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ThresholdConfig:
    """Configurable threshold definition."""
    name: str
    signal_type: str
    category: str
    count: int
    window_seconds: float
    min_unique_targets: int = 1
    scope: str = "both"  # "actor", "guild", "both"
    severity: str = "critical"  # "low", "medium", "high", "critical"
    is_combination: bool = False
    required_distinct_categories: Optional[int] = None


class RollingWindowBucket:
    """
    High-performance bounded sliding window container.
    Handles out-of-order timestamp insertion and automatic expiration.
    """
    def __init__(self, max_items: int = 1000, max_retention_seconds: float = 600.0):
        self._items: List[ActivityItem] = []
        self._max_items = max_items
        self._max_retention_seconds = max_retention_seconds

    def add(self, item: ActivityItem) -> None:
        """Inserts an ActivityItem in sorted timestamp order using binary search."""
        if not self._items or item.timestamp >= self._items[-1].timestamp:
            self._items.append(item)
        elif item.timestamp <= self._items[0].timestamp:
            self._items.insert(0, item)
        else:
            idx = bisect.bisect_right(self._items, item)
            self._items.insert(idx, item)

        if len(self._items) > self._max_items:
            del self._items[:len(self._items) - self._max_items]

    def prune(self, current_time: float, max_retention: Optional[float] = None) -> None:
        """Removes items older than max_retention."""
        retention = max_retention if max_retention is not None else self._max_retention_seconds
        cutoff = current_time - retention
        if not self._items or self._items[0].timestamp >= cutoff:
            return
        dummy = ActivityItem(
            timestamp=cutoff,
            event_id="",
            event_type="",
            category="",
            target_id=None,
            target_name=None,
            actor_id=None,
            actor_name=None,
            attribution_confidence="",
            is_whitelisted=False,
        )
        idx = bisect.bisect_left(self._items, dummy)
        del self._items[:idx]

    def get_items(self) -> List[ActivityItem]:
        """Returns a snapshot copy of all items currently in the bucket."""
        return list(self._items)

    def get_items_in_window(self, current_time: float, window_seconds: float) -> List[ActivityItem]:
        """Returns all items whose timestamps fall within [current_time - window_seconds, current_time + skew]."""
        cutoff = current_time - window_seconds
        # Binary search for cutoff
        dummy = ActivityItem(
            timestamp=cutoff,
            event_id="",
            event_type="",
            category="",
            target_id=None,
            target_name=None,
            actor_id=None,
            actor_name=None,
            attribution_confidence="",
            is_whitelisted=False,
        )
        idx = bisect.bisect_left(self._items, dummy)
        return self._items[idx:]

    def get_summary(
        self,
        current_time: float,
        window_seconds: float,
        category: Optional[str] = None,
        category_name: Optional[str] = None,
    ) -> ActivityWindowSummary:
        """Calculates window statistics for the given interval."""
        cat_name = category or category_name or ""
        in_window = self.get_items_in_window(current_time, window_seconds)
        count = len(in_window)
        unique_targets: Set[str] = set()
        distinct_categories: Set[str] = set()
        event_ids: List[str] = []

        earliest: Optional[float] = None
        latest: Optional[float] = None

        if in_window:
            earliest = in_window[0].timestamp
            latest = in_window[-1].timestamp
            for it in in_window:
                if it.target_id:
                    unique_targets.add(it.target_id)
                distinct_categories.add(it.category)
                event_ids.append(it.event_id)

        span = (latest - earliest) if (earliest is not None and latest is not None) else 0.0
        frequency = (count / max(1.0, window_seconds))

        return ActivityWindowSummary(
            category=cat_name,
            window_seconds=window_seconds,
            count=count,
            unique_targets=unique_targets,
            unique_target_count=len(unique_targets),
            frequency=frequency,
            earliest_timestamp=earliest,
            latest_timestamp=latest,
            span_seconds=span,
            distinct_categories=distinct_categories,
            event_ids=event_ids,
        )

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def __len__(self) -> int:
        return len(self._items)

    @property
    def latest_timestamp(self) -> Optional[float]:
        return self._items[-1].timestamp if self._items else None


class SecurityActivityManager:
    """
    Real-time rolling counter and emergency detection engine for Sentinel™.
    """

    _instance: Optional["SecurityActivityManager"] = None

    def __init__(self, max_active_actors_per_guild: int = 500, dedup_ttl: float = 30.0, signal_cooldown: float = 5.0):
        self._max_active_actors_per_guild = max_active_actors_per_guild
        self._dedup_ttl = dedup_ttl
        self._signal_cooldown = signal_cooldown

        # Striped per-guild concurrency isolation
        self._guild_locks: Dict[str, asyncio.Lock] = {}
        self._guild_thread_locks: Dict[str, threading.RLock] = collections.defaultdict(threading.RLock)

        # Guild-wide counters: guild_id -> { category -> RollingWindowBucket }
        self._guild_buckets: Dict[str, Dict[str, RollingWindowBucket]] = collections.defaultdict(dict)

        # Per-actor counters: guild_id -> { actor_id -> { category -> RollingWindowBucket } }
        self._actor_buckets: Dict[str, Dict[str, Dict[str, RollingWindowBucket]]] = collections.defaultdict(
            lambda: collections.defaultdict(dict)
        )

        # LRU timestamp tracking for actor eviction
        self._actor_last_seen: Dict[str, Dict[str, float]] = collections.defaultdict(dict)

        # Deduplication cache: dedup_token -> (timestamp, event_id)
        self._seen_events: Dict[str, Tuple[float, str]] = {}

        # Custom guild threshold configurations: guild_id -> list of ThresholdConfig
        self._guild_threshold_overrides: Dict[str, List[ThresholdConfig]] = {}

        # Signal subscribers: callbacks taking EmergencySignal
        self._signal_subscribers: List[Callable[[EmergencySignal], Any]] = []

        # Signal history ring buffer (in-memory for forensics and recovery)
        self._signal_history: collections.deque[EmergencySignal] = collections.deque(maxlen=1000)

        # Signal emission cooldowns to prevent spamming identical bursts: signal_key -> timestamp
        self._signal_cooldowns: Dict[str, float] = {}

        # Default standard thresholds
        self._default_thresholds: List[ThresholdConfig] = self._build_default_thresholds()

    def set_signal_cooldown(self, seconds: float) -> None:
        """Sets the cooldown period between duplicate emergency signal emissions."""
        self._signal_cooldown = max(0.0, float(seconds))

    def attach_to_collector(self, collector: Optional[Any] = None) -> None:
        """Subscribes this activity manager to the SecurityEventCollector singleton."""
        from core.security.event_collector import SecurityEventCollector
        c = collector or SecurityEventCollector.get_instance()
        c.subscribe(self.process_event)
        logger.info("[SecurityActivityManager] Attached to SecurityEventCollector stream.")

    def detach_from_collector(self, collector: Optional[Any] = None) -> None:
        """Unsubscribes this activity manager from the SecurityEventCollector."""
        from core.security.event_collector import SecurityEventCollector
        c = collector or SecurityEventCollector.get_instance()
        c.unsubscribe(self.process_event)

    @classmethod
    def get_instance(cls) -> "SecurityActivityManager":
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resets singleton state (for isolated unit tests)."""
        cls._instance = None

    def _get_guild_lock(self, guild_id: str) -> asyncio.Lock:
        """Provides an isolated lock per guild to avoid cross-guild contention."""
        gid = str(guild_id)
        if gid not in self._guild_locks:
            self._guild_locks[gid] = asyncio.Lock()
        return self._guild_locks[gid]

    @staticmethod
    def _categorize_event(event: SecurityEvent) -> List[str]:
        """Maps a SecurityEvent into canonical activity categories."""
        ev_type = event.event_type
        cats: List[str] = []

        if ev_type == SecurityEventType.MEMBER_BAN:
            cats.extend([ActivityCategory.MEMBER_BAN, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type == SecurityEventType.MEMBER_UNBAN:
            cats.append(ActivityCategory.MEMBER_UNBAN)
        elif ev_type in (SecurityEventType.MEMBER_KICK, SecurityEventType.MEMBER_REMOVE):
            cats.extend([ActivityCategory.MEMBER_KICK, ActivityCategory.MEMBER_REMOVE, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type in (SecurityEventType.CHANNEL_DELETE, SecurityEventType.THREAD_DELETE):
            cats.extend([ActivityCategory.CHANNEL_DELETE, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type == SecurityEventType.ROLE_DELETE:
            cats.extend([ActivityCategory.ROLE_DELETE, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type in (
            SecurityEventType.DANGEROUS_PERMISSION_GRANT,
            SecurityEventType.PERMISSION_OVERWRITE_UPDATE,
            SecurityEventType.ROLE_UPDATE,
            SecurityEventType.CHANNEL_UPDATE,
        ):
            cats.extend([ActivityCategory.PERMISSION_CHANGE, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type in (
            SecurityEventType.MEMBER_ROLE_UPDATE,
            ActivityCategory.DANGEROUS_ROLE_ASSIGN,
            "dangerous_role_assign",
        ):
            cats.extend([ActivityCategory.DANGEROUS_ROLE_ASSIGN, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type in (
            SecurityEventType.WEBHOOK_CREATE,
            SecurityEventType.WEBHOOK_UPDATE,
            SecurityEventType.WEBHOOK_DELETE,
            SecurityEventType.INTEGRATIONS_UPDATE,
        ):
            cats.extend([ActivityCategory.WEBHOOK_INTEGRATION, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type == SecurityEventType.BOT_ADD:
            cats.extend([ActivityCategory.BOT_ADD, ActivityCategory.ALL_DESTRUCTIVE])
        elif ev_type in (SecurityEventType.SECURITY_SETTINGS_UPDATE, SecurityEventType.GUILD_UPDATE):
            cats.append(ActivityCategory.GUILD_SETTINGS)

        # Allow direct category events and ensure destructive combinations include ALL_DESTRUCTIVE
        if ev_type in ActivityCategory.ALL and ev_type not in cats:
            cats.append(ev_type)
            if ev_type not in (ActivityCategory.MEMBER_UNBAN, ActivityCategory.GUILD_SETTINGS):
                if ActivityCategory.ALL_DESTRUCTIVE not in cats:
                    cats.append(ActivityCategory.ALL_DESTRUCTIVE)

        return list(dict.fromkeys(cats))

    def _build_default_thresholds(self) -> List[ThresholdConfig]:
        """Instantiates default threat and burst thresholds."""
        return [
            # 1. Rapid burst of member bans (actor-level: 5 in 10s; guild-level: 10 in 10s)
            ThresholdConfig(
                name="rapid_burst_ban_actor",
                signal_type=EmergencySignalType.RAPID_BURST_BAN,
                category=ActivityCategory.MEMBER_BAN,
                count=5,
                window_seconds=10.0,
                scope="actor",
                severity="critical",
            ),
            ThresholdConfig(
                name="rapid_burst_ban_guild",
                signal_type=EmergencySignalType.RAPID_BURST_BAN,
                category=ActivityCategory.MEMBER_BAN,
                count=10,
                window_seconds=10.0,
                scope="guild",
                severity="critical",
            ),

            # 2. Channel deletions
            ThresholdConfig(
                name="mass_channel_delete_actor",
                signal_type=EmergencySignalType.MASS_CHANNEL_DELETE,
                category=ActivityCategory.CHANNEL_DELETE,
                count=2,
                window_seconds=10.0,
                scope="actor",
                severity="critical",
            ),
            ThresholdConfig(
                name="mass_channel_delete_guild",
                signal_type=EmergencySignalType.MASS_CHANNEL_DELETE,
                category=ActivityCategory.CHANNEL_DELETE,
                count=3,
                window_seconds=15.0,
                scope="guild",
                severity="critical",
            ),

            # 3. Role deletions
            ThresholdConfig(
                name="mass_role_delete_actor",
                signal_type=EmergencySignalType.MASS_ROLE_DELETE,
                category=ActivityCategory.ROLE_DELETE,
                count=2,
                window_seconds=10.0,
                scope="actor",
                severity="critical",
            ),
            ThresholdConfig(
                name="mass_role_delete_guild",
                signal_type=EmergencySignalType.MASS_ROLE_DELETE,
                category=ActivityCategory.ROLE_DELETE,
                count=3,
                window_seconds=15.0,
                scope="guild",
                severity="critical",
            ),

            # 4. Kicks and member removals
            ThresholdConfig(
                name="rapid_burst_kick_actor",
                signal_type=EmergencySignalType.RAPID_BURST_KICK,
                category=ActivityCategory.MEMBER_KICK,
                count=5,
                window_seconds=15.0,
                scope="actor",
                severity="high",
            ),

            # 5. Dangerous permission escalation
            ThresholdConfig(
                name="dangerous_permission_escalation",
                signal_type=EmergencySignalType.DANGEROUS_PERMISSION_ESCALATION,
                category=ActivityCategory.PERMISSION_CHANGE,
                count=2,
                window_seconds=30.0,
                scope="both",
                severity="critical",
            ),

            # 6. Webhook and integrations burst
            ThresholdConfig(
                name="webhook_integration_spike",
                signal_type=EmergencySignalType.WEBHOOK_INTEGRATION_SPIKE,
                category=ActivityCategory.WEBHOOK_INTEGRATION,
                count=3,
                window_seconds=15.0,
                scope="both",
                severity="high",
            ),

            # 7. Rogue bot burst
            ThresholdConfig(
                name="rogue_bot_burst",
                signal_type=EmergencySignalType.ROGUE_BOT_BURST,
                category=ActivityCategory.BOT_ADD,
                count=1,
                window_seconds=30.0,
                scope="both",
                severity="critical",
            ),

            # 8. Coordinated multi-vector destructive activity (>= 3 distinct destructive categories)
            ThresholdConfig(
                name="coordinated_multi_vector_actor",
                signal_type=EmergencySignalType.COORDINATED_MULTI_VECTOR,
                category=ActivityCategory.ALL_DESTRUCTIVE,
                count=3,
                window_seconds=20.0,
                scope="actor",
                severity="critical",
                is_combination=True,
                required_distinct_categories=3,
            ),
            ThresholdConfig(
                name="coordinated_multi_vector_guild",
                signal_type=EmergencySignalType.COORDINATED_MULTI_VECTOR,
                category=ActivityCategory.ALL_DESTRUCTIVE,
                count=5,
                window_seconds=20.0,
                scope="guild",
                severity="critical",
                is_combination=True,
                required_distinct_categories=3,
            ),
        ]

    def subscribe_signals(self, callback: Callable[[EmergencySignal], Any]) -> Callable[[EmergencySignal], Any]:
        """Subscribes a listener (e.g. Agent 3 Threat Detector) to receive emergency signals in real time."""
        self._signal_subscribers.append(callback)
        return callback

    def unsubscribe_signals(self, callback: Callable[[EmergencySignal], Any]) -> bool:
        """Removes an emergency signal subscriber."""
        before = len(self._signal_subscribers)
        self._signal_subscribers = [s for s in self._signal_subscribers if s != callback]
        return len(self._signal_subscribers) < before

    def clear_signal_subscribers(self) -> None:
        """Removes all signal subscribers."""
        self._signal_subscribers.clear()

    def set_guild_threshold(self, guild_id: str, threshold: ThresholdConfig) -> None:
        """Configures or overrides a specific threshold for a guild."""
        gid = str(guild_id)
        if hasattr(self, "_guild_thresholds_cache"):
            self._guild_thresholds_cache.pop(gid, None)
        if gid not in self._guild_threshold_overrides:
            self._guild_threshold_overrides[gid] = [t for t in self._default_thresholds if t.name != threshold.name]
            self._guild_threshold_overrides[gid].append(threshold)
        else:
            self._guild_threshold_overrides[gid] = [t for t in self._guild_threshold_overrides[gid] if t.name != threshold.name]
            self._guild_threshold_overrides[gid].append(threshold)

    def set_guild_thresholds(self, guild_id: str, thresholds: List[ThresholdConfig]) -> None:
        """Replaces all active thresholds for a guild."""
        gid = str(guild_id)
        if hasattr(self, "_guild_thresholds_cache"):
            self._guild_thresholds_cache.pop(gid, None)
        self._guild_threshold_overrides[gid] = list(thresholds)

    def reset_guild_thresholds(self, guild_id: str) -> None:
        """Clears custom overrides, reverting guild to default thresholds."""
        gid = str(guild_id)
        self._guild_threshold_overrides.pop(gid, None)
        if hasattr(self, "_guild_thresholds_cache"):
            self._guild_thresholds_cache.pop(gid, None)

    def get_guild_thresholds(self, guild_id: str) -> List[ThresholdConfig]:
        """Returns the active threshold definitions for a guild."""
        gid = str(guild_id)
        if gid in self._guild_threshold_overrides:
            return list(self._guild_threshold_overrides[gid])

        now = time.time()
        if not hasattr(self, "_guild_thresholds_cache"):
            self._guild_thresholds_cache = {}
        cached = self._guild_thresholds_cache.get(gid)
        if cached and (now - cached[0] < 30.0):
            return list(cached[1])

        # Adapt from AntiNuke configuration if custom thresholds exist
        # Adapt from AntiNuke configuration ONLY if explicitly setup and configured
        try:
            if AntiNukeManager.is_setup_completed(gid):
                cfg = AntiNukeManager.get_guild_config(gid)
                if cfg.get("enabled"):
                    an_thresholds = cfg.get("thresholds", {})
                    if an_thresholds:
                        adapted: List[ThresholdConfig] = []
                        for th in self._default_thresholds:
                            an_key = {
                                ActivityCategory.MEMBER_BAN: AntiNukeConstants.EVENT_BAN_ADD,
                                ActivityCategory.CHANNEL_DELETE: AntiNukeConstants.EVENT_CHANNEL_DELETE,
                                ActivityCategory.ROLE_DELETE: AntiNukeConstants.EVENT_ROLE_DELETE,
                                ActivityCategory.MEMBER_KICK: AntiNukeConstants.EVENT_MEMBER_REMOVE,
                                ActivityCategory.WEBHOOK_INTEGRATION: AntiNukeConstants.EVENT_WEBHOOKS_UPDATE,
                                ActivityCategory.BOT_ADD: AntiNukeConstants.EVENT_BOT_ADD,
                            }.get(th.category)

                            if an_key and an_key in an_thresholds:
                                custom_count = an_thresholds[an_key].get("count")
                                custom_win = an_thresholds[an_key].get("window")
                                if custom_count is not None and custom_win is not None and int(custom_count) > 1:
                                    adapted.append(
                                        ThresholdConfig(
                                            name=f"{th.name}_adapted",
                                            signal_type=th.signal_type,
                                            category=th.category,
                                            count=int(custom_count),
                                            window_seconds=float(custom_win),
                                            scope=th.scope,
                                            severity=th.severity,
                                            is_combination=th.is_combination,
                                            required_distinct_categories=th.required_distinct_categories,
                                        )
                                    )
                                    continue
                            adapted.append(th)
                        self._guild_thresholds_cache[gid] = (now, adapted)
                        return adapted
        except Exception:
            pass

        self._guild_thresholds_cache[gid] = (now, list(self._default_thresholds))
        return list(self._default_thresholds)

    def _purge_dedup_cache(self, current_time: float) -> None:
        """Evicts expired deduplication keys periodically."""
        if current_time - getattr(self, "_last_dedup_purge", 0.0) < 5.0 and len(self._seen_events) < 500:
            return
        self._last_dedup_purge = current_time
        cutoff = current_time - self._dedup_ttl
        expired = [k for k, (t, _) in self._seen_events.items() if t < cutoff]
        for k in expired:
            self._seen_events.pop(k, None)

    def _get_or_create_guild_bucket(self, guild_id: str, category: str) -> RollingWindowBucket:
        buckets = self._guild_buckets[guild_id]
        if category not in buckets:
            buckets[category] = RollingWindowBucket()
        return buckets[category]

    def _get_or_create_actor_bucket(self, guild_id: str, actor_id: str, category: str) -> RollingWindowBucket:
        # LRU bound enforcement on actors
        actor_map = self._actor_buckets[guild_id]
        if actor_id not in actor_map and len(actor_map) >= self._max_active_actors_per_guild:
            # Evict oldest inactive actor
            seen_map = self._actor_last_seen[guild_id]
            if seen_map:
                oldest_actor = min(seen_map.keys(), key=lambda k: seen_map[k])
                actor_map.pop(oldest_actor, None)
                seen_map.pop(oldest_actor, None)

        actor_buckets = actor_map[actor_id]
        if category not in actor_buckets:
            actor_buckets[category] = RollingWindowBucket()
        return actor_buckets[category]

    def record_event(self, event: SecurityEvent) -> List[EmergencySignal]:
        """
        Synchronously updates rolling activity counters and evaluates thresholds.
        Thread-safe and concurrency-safe per guild.
        """
        if not event or not event.guild_id:
            return []

        guild_id = str(event.guild_id)
        with self._guild_thread_locks[guild_id]:
            now = event.timestamp if event.timestamp else time.time()

            # 1. Deduplication check
            dedup_token = f"{guild_id}:{event.event_id}:{event.dedup_key or ''}"
            self._purge_dedup_cache(now)
            if dedup_token in self._seen_events:
                logger.debug(f"[SecurityActivityManager] Suppressing duplicate event ingestion: {event.event_id}")
                return []
            self._seen_events[dedup_token] = (now, event.event_id)

            categories = self._categorize_event(event)
            if not categories:
                return []

            actor_id = str(event.actor_id) if event.actor_id else None
            is_whitelisted = bool(event.is_whitelisted_actor)

            primary_category = categories[0]

            # 2. Ingest into Rolling Counters
            # Guild-wide
            for cat in categories:
                gb = self._get_or_create_guild_bucket(guild_id, cat)
                gb.prune(now)
                gb.add(
                    ActivityItem(
                        timestamp=now,
                        event_id=event.event_id,
                        event_type=event.event_type,
                        category=primary_category,
                        target_id=event.target_id,
                        target_name=event.target_name,
                        actor_id=actor_id,
                        actor_name=event.actor_name,
                        attribution_confidence=event.attribution_confidence,
                        is_whitelisted=is_whitelisted,
                        metadata=event.metadata,
                    )
                )

            # Per-actor (if actor is known)
            if actor_id:
                self._actor_last_seen[guild_id][actor_id] = now
                for cat in categories:
                    ab = self._get_or_create_actor_bucket(guild_id, actor_id, cat)
                    ab.prune(now)
                    ab.add(
                        ActivityItem(
                            timestamp=now,
                            event_id=event.event_id,
                            event_type=event.event_type,
                            category=primary_category,
                            target_id=event.target_id,
                            target_name=event.target_name,
                            actor_id=actor_id,
                            actor_name=event.actor_name,
                            attribution_confidence=event.attribution_confidence,
                            is_whitelisted=is_whitelisted,
                            metadata=event.metadata,
                        )
                    )

            # 3. Real-Time Threshold Evaluation
            signals = self._evaluate_thresholds(
                guild_id=guild_id,
                actor_id=actor_id,
                event=event,
                categories=categories,
                current_time=now,
            )

            # 4. Dispatch generated signals
            for sig in signals:
                self._dispatch_signal(sig)

            return signals

    async def record_event_async(self, event: SecurityEvent) -> List[EmergencySignal]:
        """
        Asynchronously updates rolling activity counters and evaluates thresholds.
        Uses per-guild asyncio.Lock to avoid contention across guilds.
        """
        if not event or not event.guild_id:
            return []
        guild_id = str(event.guild_id)
        async with self._get_guild_lock(guild_id):
            return self.record_event(event)

    async def process_event_async(self, event: SecurityEvent) -> List[EmergencySignal]:
        """Async convenience observer callback."""
        return await self.record_event_async(event)

    def process_event(self, event: SecurityEvent) -> List[EmergencySignal]:
        """Convenience observer callback for direct subscription to SecurityEventCollector."""
        return self.record_event(event)

    def _evaluate_thresholds(
        self,
        guild_id: str,
        actor_id: Optional[str],
        event: SecurityEvent,
        categories: List[str],
        current_time: float,
    ) -> List[EmergencySignal]:
        """Evaluates active threshold rules across actor and guild scopes."""
        signals: List[EmergencySignal] = []
        thresholds = self.get_guild_thresholds(guild_id)

        # Check sequence trigger: Privilege Escalation followed by Destructive Action
        if any(c in (ActivityCategory.CHANNEL_DELETE, ActivityCategory.ROLE_DELETE, ActivityCategory.MEMBER_BAN, ActivityCategory.MEMBER_KICK) for c in categories):
            seq_signal = self._evaluate_privilege_escalation_sequence(guild_id, actor_id, event, current_time)
            if seq_signal:
                signals.append(seq_signal)

        # Evaluate standard threshold rules
        for rule in thresholds:
            if rule.category not in categories:
                continue

            # Evaluate Actor-Level
            if actor_id and rule.scope in ("actor", "both"):
                ab = self._actor_buckets.get(guild_id, {}).get(actor_id, {}).get(rule.category)
                if ab and len(ab) >= rule.count:
                    actor_summary = self.get_actor_summary(guild_id, actor_id, rule.category, rule.window_seconds)
                    if self._check_rule_match(rule, actor_summary):
                        sig = self._create_emergency_signal(
                            rule=rule,
                            scope="actor",
                            guild_id=guild_id,
                            actor_id=actor_id,
                            summary=actor_summary,
                            event=event,
                            current_time=current_time,
                        )
                        if sig:
                            signals.append(sig)

            # Evaluate Guild-Level
            if rule.scope in ("guild", "both"):
                gb = self._guild_buckets.get(guild_id, {}).get(rule.category)
                if gb and len(gb) >= rule.count:
                    guild_summary = self.get_guild_summary(guild_id, rule.category, rule.window_seconds)
                    if self._check_rule_match(rule, guild_summary):
                        sig = self._create_emergency_signal(
                            rule=rule,
                            scope="guild",
                            guild_id=guild_id,
                            actor_id=actor_id if (actor_id and rule.scope == "guild") else None,
                            summary=guild_summary,
                            event=event,
                            current_time=current_time,
                        )
                        if sig:
                            signals.append(sig)

        return signals

    def _check_rule_match(self, rule: ThresholdConfig, summary: ActivityWindowSummary) -> bool:
        """Determines if a window summary breaches the given threshold rule."""
        if summary.count < rule.count:
            return False

        if rule.min_unique_targets > 1 and summary.unique_target_count < rule.min_unique_targets:
            return False

        if rule.is_combination:
            req_cats = rule.required_distinct_categories or 2
            if len(summary.distinct_categories) < req_cats:
                return False

        return True

    def _evaluate_privilege_escalation_sequence(
        self,
        guild_id: str,
        actor_id: Optional[str],
        current_event: SecurityEvent,
        current_time: float,
        lookback_seconds: float = 60.0,
    ) -> Optional[EmergencySignal]:
        """
        Detects dangerous permission escalation / role assignment immediately followed
        by destructive behavior within a short lookback window.
        """
        recent_escalation = False
        escalation_events: List[str] = []

        if actor_id:
            ab = self._actor_buckets.get(guild_id, {}).get(actor_id, {})
            pb = ab.get(ActivityCategory.PERMISSION_CHANGE)
            rb = ab.get(ActivityCategory.DANGEROUS_ROLE_ASSIGN)
            if pb and len(pb) > 0:
                perm_summary = self.get_actor_summary(guild_id, actor_id, ActivityCategory.PERMISSION_CHANGE, lookback_seconds)
                if perm_summary.count > 0:
                    recent_escalation = True
                    escalation_events.extend(perm_summary.event_ids)
            if rb and len(rb) > 0:
                role_assign_summary = self.get_actor_summary(guild_id, actor_id, ActivityCategory.DANGEROUS_ROLE_ASSIGN, lookback_seconds)
                if role_assign_summary.count > 0:
                    recent_escalation = True
                    escalation_events.extend(role_assign_summary.event_ids)

        if not recent_escalation:
            gb = self._guild_buckets.get(guild_id, {}).get(ActivityCategory.PERMISSION_CHANGE)
            if gb and len(gb) > 0:
                guild_perm = self.get_guild_summary(guild_id, ActivityCategory.PERMISSION_CHANGE, lookback_seconds)
                if guild_perm.count > 0:
                    recent_escalation = True
                    escalation_events.extend(guild_perm.event_ids)

        if not recent_escalation:
            return None

        cooldown_key = f"{guild_id}:{actor_id or 'guild'}:{EmergencySignalType.PRIVILEGE_ESCALATION_THEN_DESTRUCTION}"
        last_emitted = self._signal_cooldowns.get(cooldown_key, 0.0)
        if current_time - last_emitted < self._signal_cooldown:
            return None

        self._signal_cooldowns[cooldown_key] = current_time

        sig_id = f"sig_{uuid.uuid4().hex[:12]}"
        return EmergencySignal(
            signal_id=sig_id,
            signal_type=EmergencySignalType.PRIVILEGE_ESCALATION_THEN_DESTRUCTION,
            guild_id=guild_id,
            severity="critical",
            scope="actor" if actor_id else "guild",
            actor_id=actor_id,
            actor_name=current_event.actor_name,
            is_whitelisted_actor=bool(current_event.is_whitelisted_actor),
            attribution_confidence=current_event.attribution_confidence,
            current_count=len(escalation_events) + 1,
            threshold_count=2,
            window_seconds=lookback_seconds,
            unique_targets_count=1,
            unique_targets=[current_event.target_id] if current_event.target_id else [],
            event_types_involved=[SecurityEventType.DANGEROUS_PERMISSION_GRANT, current_event.event_type],
            categories_involved=[ActivityCategory.PERMISSION_CHANGE, current_event.event_type],
            triggering_event=current_event,
            timestamp=current_time,
            metadata={
                "escalation_event_ids": escalation_events,
                "destructive_event_id": current_event.event_id,
                "destructive_action": current_event.event_type,
            },
        )

    def _create_emergency_signal(
        self,
        rule: ThresholdConfig,
        scope: str,
        guild_id: str,
        actor_id: Optional[str],
        summary: ActivityWindowSummary,
        event: SecurityEvent,
        current_time: float,
    ) -> Optional[EmergencySignal]:
        """Constructs an EmergencySignal with rate-limiting de-duplication."""
        cooldown_key = f"{guild_id}:{scope}:{actor_id or 'guild'}:{rule.signal_type}:{rule.name}"
        last_emitted = self._signal_cooldowns.get(cooldown_key, 0.0)
        if current_time - last_emitted < self._signal_cooldown:
            return None

        self._signal_cooldowns[cooldown_key] = current_time

        sig_id = f"sig_{uuid.uuid4().hex[:12]}"
        return EmergencySignal(
            signal_id=sig_id,
            signal_type=rule.signal_type,
            guild_id=guild_id,
            severity=rule.severity,
            scope=scope,
            actor_id=actor_id,
            actor_name=event.actor_name if (actor_id and event.actor_id == actor_id) else None,
            is_whitelisted_actor=bool(event.is_whitelisted_actor),
            attribution_confidence=event.attribution_confidence if (actor_id and event.actor_id == actor_id) else AttributionConfidence.UNKNOWN,
            current_count=summary.count,
            threshold_count=rule.count,
            window_seconds=rule.window_seconds,
            unique_targets_count=summary.unique_target_count,
            unique_targets=list(summary.unique_targets),
            event_types_involved=[event.event_type],
            categories_involved=list(summary.distinct_categories),
            triggering_event=event,
            timestamp=current_time,
            metadata={
                "rule_name": rule.name,
                "frequency": summary.frequency,
                "span_seconds": summary.span_seconds,
                "event_ids": summary.event_ids[:20],
            },
        )

    def _dispatch_signal(self, signal: EmergencySignal) -> None:
        """Stores signal in history and notifies subscribers asynchronously."""
        self._signal_history.append(signal)

        # Asynchronous DB persist without blocking real-time detection pipeline
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._persist_signal(signal))
        except RuntimeError:
            pass

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
                logger.error(f"[SecurityActivityManager] Error in signal subscriber: {err}")

    async def _persist_signal(self, signal: EmergencySignal) -> None:
        """Persists emergency signal to database collection 'security_signals'."""
        try:
            col = database.collection("security_signals")
            doc = signal.to_dict()
            if hasattr(col, "insert_one"):
                res = col.insert_one(doc)
                if inspect.isawaitable(res):
                    await res
        except Exception as err:
            logger.debug(f"[SecurityActivityManager] Failed to persist emergency signal {signal.signal_id}: {err}")

    # Query APIs
    def get_actor_summary(
        self, guild_id: str, actor_id: str, category: str, window_seconds: float, current_time: Optional[float] = None
    ) -> ActivityWindowSummary:
        """Calculates window summary for a specific actor and category."""
        now = current_time or time.time()
        gid = str(guild_id)
        aid = str(actor_id)
        actor_map = self._actor_buckets.get(gid, {})
        actor_buckets = actor_map.get(aid, {})
        bucket = actor_buckets.get(category)
        if not bucket:
            return ActivityWindowSummary(
                category=category,
                window_seconds=window_seconds,
                count=0,
                unique_targets=set(),
                unique_target_count=0,
                frequency=0.0,
                earliest_timestamp=None,
                latest_timestamp=None,
                span_seconds=0.0,
                distinct_categories=set(),
                event_ids=[],
            )
        return bucket.get_summary(now, window_seconds, category)

    def get_guild_summary(
        self, guild_id: str, category: str, window_seconds: float, current_time: Optional[float] = None
    ) -> ActivityWindowSummary:
        """Calculates window summary guild-wide for a category."""
        now = current_time or time.time()
        gid = str(guild_id)
        guild_buckets = self._guild_buckets.get(gid, {})
        bucket = guild_buckets.get(category)
        if not bucket:
            return ActivityWindowSummary(
                category=category,
                window_seconds=window_seconds,
                count=0,
                unique_targets=set(),
                unique_target_count=0,
                frequency=0.0,
                earliest_timestamp=None,
                latest_timestamp=None,
                span_seconds=0.0,
                distinct_categories=set(),
                event_ids=[],
            )
        return bucket.get_summary(now, window_seconds, category)

    def get_all_actor_summaries(
        self, guild_id: str, actor_id: str, window_seconds: float = 60.0, current_time: Optional[float] = None
    ) -> Dict[str, ActivityWindowSummary]:
        """Provides summaries across all monitored categories for a specific actor."""
        result: Dict[str, ActivityWindowSummary] = {}
        for cat in ActivityCategory.ALL:
            summary = self.get_actor_summary(guild_id, actor_id, cat, window_seconds, current_time)
            if summary.count > 0:
                result[cat] = summary
        return result

    def get_all_guild_summaries(
        self, guild_id: str, window_seconds: float = 60.0, current_time: Optional[float] = None
    ) -> Dict[str, ActivityWindowSummary]:
        """Provides summaries across all monitored categories guild-wide."""
        result: Dict[str, ActivityWindowSummary] = {}
        for cat in ActivityCategory.ALL:
            summary = self.get_guild_summary(guild_id, cat, window_seconds, current_time)
            if summary.count > 0:
                result[cat] = summary
        return result

    def get_recent_signals(self, guild_id: Optional[str] = None, limit: int = 50) -> List[EmergencySignal]:
        """Retrieves recent emergency signals, newest first."""
        signals = list(self._signal_history)
        if guild_id:
            signals = [s for s in signals if s.guild_id == str(guild_id)]
        signals.sort(key=lambda s: s.timestamp, reverse=True)
        return signals[:limit]

    def clear_guild(self, guild_id: str) -> None:
        """Resets all in-memory activity counters for a guild."""
        gid = str(guild_id)
        self._guild_buckets.pop(gid, None)
        self._actor_buckets.pop(gid, None)
        self._actor_last_seen.pop(gid, None)
        self._guild_threshold_overrides.pop(gid, None)

    def cleanup_idle(self, max_idle_seconds: float = 600.0) -> int:
        """
        Prunes inactive actors and empty guild buckets under sustained load.
        Returns the number of actor records evicted.
        """
        now = time.time()
        evicted = 0
        cutoff = now - max_idle_seconds

        for gid in list(self._actor_last_seen.keys()):
            seen_map = self._actor_last_seen[gid]
            for aid in list(seen_map.keys()):
                if seen_map[aid] < cutoff:
                    seen_map.pop(aid, None)
                    if aid in self._actor_buckets[gid]:
                        self._actor_buckets[gid].pop(aid, None)
                        evicted += 1

        for gid in list(self._guild_buckets.keys()):
            buckets = self._guild_buckets[gid]
            for cat in list(buckets.keys()):
                b = buckets[cat]
                b.prune(now)
                if b.is_empty():
                    buckets.pop(cat, None)

        return evicted


# Singleton instance
security_activity_manager = SecurityActivityManager.get_instance()
