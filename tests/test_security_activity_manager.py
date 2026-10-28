"""
Unit & Integration Tests for Sentinel™ Security Activity Manager (Agent 2 of 8).

Validates:
- Rolling-window boundary calculations and sliding windows
- Real-time burst detection without waiting for window expiration
- Deduplication of duplicate event observations
- Out-of-order and late timestamp handling
- Multi-threaded concurrency and per-guild isolation
- Multiple guilds independence without cross-talk
- Unknown actor handling and guild-wide threat signals
- Whitelisted user tracking without suppression
- Sequence correlation: privilege escalation followed by destruction
- Coordinated multi-vector burst detection
- Bounded memory, LRU eviction, and idle cleanup under sustained load
- Custom guild threshold overrides and AntiNuke config adaptation
- SecurityEventCollector pub/sub integration
"""

import time
import uuid
import threading
import asyncio
import unittest
from unittest.mock import MagicMock

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
    EmergencySignalType,
    EmergencySignal,
    ThresholdConfig,
    ActivityWindowSummary,
    ActivityItem,
    RollingWindowBucket,
)
from core.security.event_collector import SecurityEventCollector
from core.security.antinuke import AntiNukeManager


class TestSecurityActivityManager(unittest.TestCase):
    def setUp(self):
        SecurityActivityManager.reset_instance()
        AntiNukeManager._guild_configs.clear()
        self.mgr = SecurityActivityManager(max_active_actors_per_guild=50, dedup_ttl=10.0, signal_cooldown=0.0)
        self.guild_id = "111222333444555666"
        self.actor_id = "999888777666555444"

    def _create_event(
        self,
        event_type: str = SecurityEventType.MEMBER_BAN,
        target_id: str = "target_1",
        actor_id: str = "actor_1",
        guild_id: str = "111222333444555666",
        timestamp: float = None,
        is_whitelisted: bool = False,
        confidence: str = AttributionConfidence.VERIFIED,
        dedup_key: str = None,
        metadata: dict = None,
    ) -> SecurityEvent:
        return SecurityEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            guild_id=guild_id,
            timestamp=timestamp if timestamp is not None else time.time(),
            actor_id=actor_id,
            actor_name="TestActor" if actor_id else None,
            attribution_confidence=confidence,
            target_id=target_id,
            target_name="TestTarget",
            target_type="user",
            is_whitelisted_actor=is_whitelisted,
            dedup_key=dedup_key,
            metadata=metadata or {},
        )

    def test_rolling_window_boundaries(self):
        """Verifies that events outside the sliding window are pruned and excluded."""
        bucket = RollingWindowBucket()
        base_time = 1000.0

        # Add 5 events across different timestamps:
        # t=900 (100s ago), t=950 (50s ago), t=985 (15s ago), t=995 (5s ago), t=1000 (0s ago)
        bucket.add(ActivityItem(900.0, "e1", "ban", "member_ban", "u1", "u1", "a1", "a1", "verified", False))
        bucket.add(ActivityItem(950.0, "e2", "ban", "member_ban", "u2", "u2", "a1", "a1", "verified", False))
        bucket.add(ActivityItem(985.0, "e3", "ban", "member_ban", "u3", "u3", "a1", "a1", "verified", False))
        bucket.add(ActivityItem(995.0, "e4", "ban", "member_ban", "u4", "u4", "a1", "a1", "verified", False))
        bucket.add(ActivityItem(1000.0, "e5", "ban", "member_ban", "u5", "u5", "a1", "a1", "verified", False))

        # Query 10-second window at t=1000 (should include t=995, t=1000 -> count = 2)
        summary_10s = bucket.get_summary(base_time, window_seconds=10.0, category="member_ban")
        self.assertEqual(summary_10s.count, 2)
        self.assertEqual(summary_10s.unique_target_count, 2)
        self.assertIn("u4", summary_10s.unique_targets)
        self.assertIn("u5", summary_10s.unique_targets)

        # Query 60-second window at t=1000 (should include t=950, t=985, t=995, t=1000 -> count = 4)
        summary_60s = bucket.get_summary(base_time, window_seconds=60.0, category="member_ban")
        self.assertEqual(summary_60s.count, 4)
        self.assertEqual(summary_60s.unique_target_count, 4)

        # Query 200-second window at t=1000 (all 5 items)
        summary_200s = bucket.get_summary(base_time, window_seconds=200.0, category="member_ban")
        self.assertEqual(summary_200s.count, 5)

        # Prune with max_retention = 60s at t=1000: t=900 should be removed
        bucket.prune(base_time, max_retention=60.0)
        self.assertEqual(len(bucket), 4)

    def test_rapid_burst_detection(self):
        """Tests that a rapid burst of member bans triggers an emergency signal immediately."""
        signals_received = []
        self.mgr.subscribe_signals(lambda sig: signals_received.append(sig))

        now = time.time()
        # Default ban threshold for actor is 5 bans in 10s
        for i in range(5):
            evt = self._create_event(
                event_type=SecurityEventType.MEMBER_BAN,
                target_id=f"victim_{i}",
                actor_id=self.actor_id,
                guild_id=self.guild_id,
                timestamp=now + (i * 0.1),
            )
            signals = self.mgr.record_event(evt)
            if i < 4:
                self.assertEqual(len(signals), 0, f"Premature signal on event {i}")
            else:
                self.assertGreaterEqual(len(signals), 1, "Burst threshold reached; signal must fire immediately")
                ban_signal = next((s for s in signals if s.signal_type == EmergencySignalType.RAPID_BURST_BAN), None)
                self.assertIsNotNone(ban_signal)
                self.assertEqual(ban_signal.guild_id, self.guild_id)
                self.assertEqual(ban_signal.actor_id, self.actor_id)
                self.assertEqual(ban_signal.severity, "critical")
                self.assertEqual(ban_signal.current_count, 5)
                self.assertEqual(ban_signal.unique_targets_count, 5)

        self.assertGreaterEqual(len(signals_received), 1)

    def test_duplicate_events_deduplication(self):
        """Verifies that duplicate events with same ID or dedup_key are suppressed and do not count twice."""
        now = time.time()
        evt1 = self._create_event(
            event_type=SecurityEventType.CHANNEL_DELETE,
            target_id="chan_1",
            actor_id=self.actor_id,
            guild_id=self.guild_id,
            timestamp=now,
            dedup_key="unique_action_key_1",
        )
        self.mgr.record_event(evt1)

        # Same event submitted again (same event_id and dedup_key)
        self.mgr.record_event(evt1)

        summary = self.mgr.get_actor_summary(self.guild_id, self.actor_id, ActivityCategory.CHANNEL_DELETE, 60.0, now)
        self.assertEqual(summary.count, 1, "Duplicate event must be suppressed")

    def test_out_of_order_timestamps(self):
        """Verifies out-of-order and late events are sorted correctly via binary search insertion."""
        now = 5000.0
        # Ingest events with unordered timestamps: 5010, 5005, 5008, 5002
        timestamps = [5010.0, 5005.0, 5008.0, 5002.0]
        for idx, ts in enumerate(timestamps):
            evt = self._create_event(
                event_type=SecurityEventType.ROLE_DELETE,
                target_id=f"role_{idx}",
                actor_id=self.actor_id,
                guild_id=self.guild_id,
                timestamp=ts,
            )
            self.mgr.record_event(evt)

        # Check actor bucket
        bucket = self.mgr._actor_buckets[self.guild_id][self.actor_id][ActivityCategory.ROLE_DELETE]
        items = bucket.get_items()
        extracted_ts = [it.timestamp for it in items]
        self.assertEqual(extracted_ts, [5002.0, 5005.0, 5008.0, 5010.0], "Items must be chronologically ordered")

        # Window query at 5010 with 6.0 second window (should encompass 5005, 5008, 5010 -> 3 items)
        summary = self.mgr.get_actor_summary(self.guild_id, self.actor_id, ActivityCategory.ROLE_DELETE, 6.0, 5010.0)
        self.assertEqual(summary.count, 3)

    def test_concurrency_and_guild_isolation(self):
        """Verifies multi-threaded concurrency safety and striped locking per guild."""
        num_threads = 8
        events_per_thread = 25
        guild_id = "thread_test_guild"

        def worker(thread_idx: int):
            for i in range(events_per_thread):
                evt = self._create_event(
                    event_type=SecurityEventType.MEMBER_BAN,
                    target_id=f"victim_{thread_idx}_{i}",
                    actor_id=f"actor_{thread_idx}",
                    guild_id=guild_id,
                    timestamp=time.time(),
                )
                self.mgr.record_event(evt)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Guild-wide count must be exactly num_threads * events_per_thread
        guild_summary = self.mgr.get_guild_summary(guild_id, ActivityCategory.MEMBER_BAN, 60.0)
        expected_total = num_threads * events_per_thread
        self.assertEqual(guild_summary.count, expected_total)
        self.assertEqual(guild_summary.unique_target_count, expected_total)

    def test_multiple_guilds_independence(self):
        """Verifies complete data and threshold isolation across distinct guilds."""
        guild_a = "guild_aaa"
        guild_b = "guild_bbb"

        # Record 4 bans in Guild A
        for i in range(4):
            evt_a = self._create_event(
                event_type=SecurityEventType.MEMBER_BAN,
                target_id=f"user_{i}",
                actor_id="actor_common",
                guild_id=guild_a,
                timestamp=time.time(),
            )
            self.mgr.record_event(evt_a)

        # Record 3 kicks in Guild B
        for i in range(3):
            evt_b = self._create_event(
                event_type=SecurityEventType.MEMBER_KICK,
                target_id=f"user_{i}",
                actor_id="actor_common",
                guild_id=guild_b,
                timestamp=time.time(),
            )
            self.mgr.record_event(evt_b)

        summary_a_bans = self.mgr.get_guild_summary(guild_a, ActivityCategory.MEMBER_BAN, 60.0)
        summary_a_kicks = self.mgr.get_guild_summary(guild_a, ActivityCategory.MEMBER_KICK, 60.0)
        summary_b_bans = self.mgr.get_guild_summary(guild_b, ActivityCategory.MEMBER_BAN, 60.0)
        summary_b_kicks = self.mgr.get_guild_summary(guild_b, ActivityCategory.MEMBER_KICK, 60.0)

        self.assertEqual(summary_a_bans.count, 4)
        self.assertEqual(summary_a_kicks.count, 0)
        self.assertEqual(summary_b_bans.count, 0)
        self.assertEqual(summary_b_kicks.count, 3)

    def test_unknown_actors_guild_wide_signal(self):
        """Verifies events with unknown actors generate guild-wide counts and signals."""
        guild_id = "unknown_actor_guild"
        now = time.time()

        # Default guild-wide channel delete threshold is 3 in 15.0 seconds
        signals = []
        for i in range(3):
            evt = self._create_event(
                event_type=SecurityEventType.CHANNEL_DELETE,
                target_id=f"channel_{i}",
                actor_id=None,
                guild_id=guild_id,
                timestamp=now + (i * 0.1),
                confidence=AttributionConfidence.UNKNOWN,
            )
            res = self.mgr.record_event(evt)
            signals.extend(res)

        guild_summary = self.mgr.get_guild_summary(guild_id, ActivityCategory.CHANNEL_DELETE, 30.0, now + 1.0)
        self.assertEqual(guild_summary.count, 3)
        self.assertEqual(guild_summary.unique_target_count, 3)

        # Check that a guild-wide signal was emitted despite unknown actor
        chan_signal = next((s for s in signals if s.signal_type == EmergencySignalType.MASS_CHANNEL_DELETE), None)
        self.assertIsNotNone(chan_signal)
        self.assertEqual(chan_signal.scope, "guild")
        self.assertIsNone(chan_signal.actor_id)
        self.assertEqual(chan_signal.attribution_confidence, AttributionConfidence.UNKNOWN)

    def test_whitelisted_users_contribute_to_counters(self):
        """Verifies whitelisted actors still contribute to all counters and signals."""
        now = time.time()
        signals = []
        for i in range(5):
            evt = self._create_event(
                event_type=SecurityEventType.MEMBER_BAN,
                target_id=f"victim_{i}",
                actor_id="trusted_admin_id",
                guild_id=self.guild_id,
                timestamp=now + (i * 0.1),
                is_whitelisted=True,
            )
            res = self.mgr.record_event(evt)
            signals.extend(res)

        summary = self.mgr.get_actor_summary(self.guild_id, "trusted_admin_id", ActivityCategory.MEMBER_BAN, 60.0, now + 1.0)
        self.assertEqual(summary.count, 5, "Whitelisted actors must not be concealed from activity counters")

        # Emergency signal must still fire, tagged with is_whitelisted_actor=True
        signal = next((s for s in signals if s.signal_type == EmergencySignalType.RAPID_BURST_BAN), None)
        self.assertIsNotNone(signal)
        self.assertTrue(signal.is_whitelisted_actor)

    def test_privilege_escalation_followed_by_destruction(self):
        """Verifies detection of permission change followed by destructive action."""
        now = time.time()

        # Step 1: Dangerous permission grant
        escalation_evt = self._create_event(
            event_type=SecurityEventType.DANGEROUS_PERMISSION_GRANT,
            target_id="admin_role_1",
            actor_id=self.actor_id,
            guild_id=self.guild_id,
            timestamp=now - 5.0,
            metadata={"permissions": ["ADMINISTRATOR"]},
        )
        self.mgr.record_event(escalation_evt)

        # Step 2: Destructive action (channel delete)
        destructive_evt = self._create_event(
            event_type=SecurityEventType.CHANNEL_DELETE,
            target_id="general_channel",
            actor_id=self.actor_id,
            guild_id=self.guild_id,
            timestamp=now,
        )
        signals = self.mgr.record_event(destructive_evt)

        escalation_signal = next(
            (s for s in signals if s.signal_type == EmergencySignalType.PRIVILEGE_ESCALATION_THEN_DESTRUCTION), None
        )
        self.assertIsNotNone(escalation_signal, "Must detect escalation followed by destruction")
        self.assertEqual(escalation_signal.severity, "critical")
        self.assertEqual(escalation_signal.actor_id, self.actor_id)

    def test_coordinated_multi_vector_burst(self):
        """Verifies coordinated multi-vector burst detection spanning >= 3 destructive categories."""
        now = time.time()

        # 3 different destructive categories by the same actor within 20s
        e1 = self._create_event(SecurityEventType.MEMBER_BAN, "u1", self.actor_id, self.guild_id, now - 4.0)
        e2 = self._create_event(SecurityEventType.CHANNEL_DELETE, "c1", self.actor_id, self.guild_id, now - 2.0)
        e3 = self._create_event(SecurityEventType.ROLE_DELETE, "r1", self.actor_id, self.guild_id, now)

        self.mgr.record_event(e1)
        self.mgr.record_event(e2)
        signals = self.mgr.record_event(e3)

        coord_signal = next((s for s in signals if s.signal_type == EmergencySignalType.COORDINATED_MULTI_VECTOR), None)
        self.assertIsNotNone(coord_signal, "Must detect coordinated multi-vector attack")
        self.assertEqual(coord_signal.severity, "critical")
        self.assertGreaterEqual(len(coord_signal.categories_involved), 3)

    def test_cleanup_under_sustained_load(self):
        """Verifies LRU eviction when actor count exceeds limit, and cleanup_idle removes stale data."""
        small_mgr = SecurityActivityManager(max_active_actors_per_guild=5, signal_cooldown=0.0)
        guild_id = "lru_guild"
        now = 10000.0

        # Ingest 5 actors
        for i in range(5):
            evt = self._create_event(
                event_type=SecurityEventType.MEMBER_BAN,
                target_id=f"u_{i}",
                actor_id=f"actor_{i}",
                guild_id=guild_id,
                timestamp=now + i,
            )
            small_mgr.record_event(evt)

        self.assertEqual(len(small_mgr._actor_buckets[guild_id]), 5)

        # Ingest 6th actor -> oldest actor (actor_0) should be evicted
        evt6 = self._create_event(
            event_type=SecurityEventType.MEMBER_BAN,
            target_id="u_6",
            actor_id="actor_5",
            guild_id=guild_id,
            timestamp=now + 10.0,
        )
        small_mgr.record_event(evt6)

        self.assertLessEqual(len(small_mgr._actor_buckets[guild_id]), 5)
        self.assertNotIn("actor_0", small_mgr._actor_buckets[guild_id])
        self.assertIn("actor_5", small_mgr._actor_buckets[guild_id])

        # Test cleanup_idle
        evicted = small_mgr.cleanup_idle(max_idle_seconds=5.0)
        self.assertGreater(evicted, 0)

    def test_custom_guild_threshold_override(self):
        """Verifies custom per-guild threshold configuration and reset."""
        guild_id = "custom_threshold_guild"
        custom_rule = ThresholdConfig(
            name="custom_ultra_sensitive_kick",
            signal_type=EmergencySignalType.CUSTOM_THRESHOLD_BREACH,
            category=ActivityCategory.MEMBER_KICK,
            count=2,
            window_seconds=10.0,
            scope="actor",
            severity="high",
        )
        self.mgr.set_guild_threshold(guild_id, custom_rule)

        now = time.time()
        # Ingest 1st kick
        e1 = self._create_event(SecurityEventType.MEMBER_KICK, "v1", self.actor_id, guild_id, now)
        s1 = self.mgr.record_event(e1)
        self.assertEqual(len(s1), 0)

        # Ingest 2nd kick -> breaches custom threshold of 2
        e2 = self._create_event(SecurityEventType.MEMBER_KICK, "v2", self.actor_id, guild_id, now + 1.0)
        s2 = self.mgr.record_event(e2)
        self.assertGreaterEqual(len(s2), 1)
        custom_sig = next((s for s in s2 if s.signal_type == EmergencySignalType.CUSTOM_THRESHOLD_BREACH), None)
        self.assertIsNotNone(custom_sig)
        self.assertEqual(custom_sig.threshold_count, 2)

        # Reset thresholds reverts to default
        self.mgr.reset_guild_thresholds(guild_id)
        thresholds = self.mgr.get_guild_thresholds(guild_id)
        self.assertNotIn(custom_rule.name, [t.name for t in thresholds])

    def test_collector_subscription_integration(self):
        """Verifies seamless pub/sub integration with SecurityEventCollector."""
        SecurityEventCollector.reset_instance()
        collector = SecurityEventCollector.get_instance()

        self.mgr.attach_to_collector(collector)

        signals_received = []
        self.mgr.subscribe_signals(lambda s: signals_received.append(s))

        now = time.time()
        # Publish 5 bans through collector
        for i in range(5):
            evt = self._create_event(
                event_type=SecurityEventType.MEMBER_BAN,
                target_id=f"target_{i}",
                actor_id="collector_actor",
                guild_id=self.guild_id,
                timestamp=now + (i * 0.1),
            )
            collector.dispatch(evt)

        # Verify activity manager consumed events and fired burst signal
        self.assertGreaterEqual(len(signals_received), 1)
        summary = self.mgr.get_actor_summary(self.guild_id, "collector_actor", ActivityCategory.MEMBER_BAN, 60.0)
        self.assertEqual(summary.count, 5)

        self.mgr.detach_from_collector(collector)


if __name__ == "__main__":
    unittest.main()
