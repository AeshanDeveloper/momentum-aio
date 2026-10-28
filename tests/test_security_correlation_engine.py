"""
Unit tests for Sentinel™ SecurityCorrelationEngine (Agent 3 of 8).

Verifies:
- Explicit deterministic rule-based pattern matching (zero AI dependencies).
- Immediate emergency detection for rapid bursts (bans, kicks, channel/role deletions).
- Multi-step sequences (permission escalation -> destruction, dangerous role -> destruction, security weakening -> destruction).
- Webhook abuse and coordinated multi-vector detection.
- Non-suppression of whitelisted actors (trusted actors are monitored and flagged).
- Guild-level evaluation when actor attribution is unknown.
- Clear distinction between observed facts and inferred intent.
- Out-of-order and delayed event handling with chronological sequence insertion.
- Anti-alert storm deduplication and escalation handling.
- Downstream subscriber pub-sub dispatch and activity manager signal consumption.
- Discord embed formatting with configurations global (emojis, colors).
"""

import time
import unittest
import asyncio

from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
)
from core.security.activity_manager import (
    SecurityActivityManager,
    EmergencySignal,
    EmergencySignalType,
)
from core.security.correlation_engine import (
    SecurityCorrelationEngine,
    ThreatSignal,
    ThreatSeverity,
    ThreatConfidence,
    ResponseCategory,
    PatternID,
    CorrelationRuleConfig,
)


class TestSecurityCorrelationEngine(unittest.TestCase):
    def setUp(self):
        # Reset singletons for pure isolation
        SecurityCorrelationEngine.reset_instance()
        SecurityActivityManager.reset_instance()
        self.engine = SecurityCorrelationEngine.get_instance()
        self.guild_id = "guild_12345"
        self.actor_id = "actor_9999"
        self.now = 1700000000.0

    def tearDown(self):
        self.engine.clear_guild(self.guild_id)
        self.engine.clear_subscribers()

    def test_default_rule_configurations(self):
        """Verifies that all 9 canonical patterns are configured with defaults."""
        for pattern_id in PatternID.ALL:
            cfg = self.engine.get_rule_config(self.guild_id, pattern_id)
            self.assertIsNotNone(cfg, f"Rule config for {pattern_id} should not be None")
            self.assertTrue(cfg.enabled)
            self.assertGreater(cfg.window_seconds, 0)

    def test_guild_rule_overrides(self):
        """Tests per-guild threshold customization and reset back to defaults."""
        custom_cfg = CorrelationRuleConfig(
            pattern_id=PatternID.RAPID_BAN_BURST,
            pattern_name="Custom Ban Burst",
            description="Tuned sensitivity for guild 12345",
            actor_count_threshold=2,
            guild_count_threshold=4,
            window_seconds=5.0,
            severity=ThreatSeverity.CRITICAL,
            recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
            requires_immediate_protection=True,
        )
        self.engine.set_guild_rule_config(self.guild_id, PatternID.RAPID_BAN_BURST, custom_cfg)
        retrieved = self.engine.get_rule_config(self.guild_id, PatternID.RAPID_BAN_BURST)
        self.assertEqual(retrieved.actor_count_threshold, 2)
        self.assertEqual(retrieved.pattern_name, "Custom Ban Burst")

        # Other guild should still have standard default
        other_cfg = self.engine.get_rule_config("guild_other", PatternID.RAPID_BAN_BURST)
        self.assertEqual(other_cfg.actor_count_threshold, 5)

        # Reset overrides
        self.engine.reset_guild_rules(self.guild_id)
        reset_cfg = self.engine.get_rule_config(self.guild_id, PatternID.RAPID_BAN_BURST)
        self.assertEqual(reset_cfg.actor_count_threshold, 5)

    def test_rapid_ban_burst_actor_level(self):
        """Verifies rapid burst of 5 bans by a single actor triggers immediate emergency lockdown."""
        signals = []
        for i in range(5):
            ev = SecurityEvent(
                guild_id=self.guild_id,
                event_type=SecurityEventType.MEMBER_BAN,
                actor_id=self.actor_id,
                actor_name="RogueAdmin",
                target_id=f"target_{i}",
                target_name=f"Victim{i}",
                attribution_confidence=AttributionConfidence.VERIFIED,
                timestamp=self.now + i * 0.5,
            )
            sig_list = self.engine.ingest_event_sync(ev, current_time=self.now + i * 0.5)
            signals.extend(sig_list)

        # The 5th event breaches actor threshold
        self.assertGreaterEqual(len(signals), 1)
        ban_sig = next(s for s in signals if s.pattern_id == PatternID.RAPID_BAN_BURST)

        self.assertEqual(ban_sig.severity, ThreatSeverity.CRITICAL)
        self.assertEqual(ban_sig.scope, "actor")
        self.assertEqual(ban_sig.actor_id, self.actor_id)
        self.assertEqual(ban_sig.recommended_response, ResponseCategory.EMERGENCY_LOCKDOWN)
        self.assertTrue(ban_sig.requires_immediate_protection)
        self.assertEqual(ban_sig.confidence, ThreatConfidence.HIGH_CONFIDENCE)

        # Verify clear distinction between observed facts and inferred intent
        self.assertEqual(ban_sig.observed_facts["ban_count"], 5)
        self.assertEqual(ban_sig.observed_facts["unique_targets_count"], 5)
        self.assertIn("mass ban raid in progress", ban_sig.inferred_intent.lower())

    def test_rapid_ban_burst_unknown_actor_guild_level(self):
        """
        Verifies that unknown actor attribution does not prevent immediate guild-wide
        emergency evaluation when a rapid destructive burst occurs.
        """
        signals = []
        for i in range(10):
            ev = SecurityEvent(
                guild_id=self.guild_id,
                event_type=SecurityEventType.MEMBER_BAN,
                actor_id=None,
                actor_name=None,
                target_id=f"target_unknown_{i}",
                attribution_confidence=AttributionConfidence.UNKNOWN,
                timestamp=self.now + i * 0.8,
            )
            sig_list = self.engine.ingest_event_sync(ev, current_time=self.now + i * 0.8)
            signals.extend(sig_list)

        self.assertGreaterEqual(len(signals), 1)
        sig = next(s for s in signals if s.pattern_id == PatternID.RAPID_BAN_BURST)
        self.assertEqual(sig.scope, "guild")
        self.assertIsNone(sig.actor_id)
        self.assertEqual(sig.attribution_confidence, AttributionConfidence.UNKNOWN)
        self.assertEqual(sig.recommended_response, ResponseCategory.EMERGENCY_LOCKDOWN)
        self.assertTrue(sig.requires_immediate_protection)

    def test_whitelisted_actor_is_not_suppressed(self):
        """
        Critical Rule: Whitelisted users and trusted admins must still be monitored
        and pattern-detected without event suppression.
        """
        signals = []
        for i in range(5):
            ev = SecurityEvent(
                guild_id=self.guild_id,
                event_type=SecurityEventType.MEMBER_BAN,
                actor_id=self.actor_id,
                actor_name="WhitelistedOwner",
                target_id=f"member_{i}",
                is_whitelisted_actor=True,
                attribution_confidence=AttributionConfidence.VERIFIED,
                timestamp=self.now + i * 0.5,
            )
            sig_list = self.engine.ingest_event_sync(ev, current_time=self.now + i * 0.5)
            signals.extend(sig_list)

        self.assertGreaterEqual(len(signals), 1)
        sig = signals[-1]
        self.assertTrue(sig.is_whitelisted_actor)
        self.assertEqual(sig.actor_id, self.actor_id)
        self.assertIn("whitelisted", sig.inferred_intent.lower())
        self.assertTrue(sig.requires_immediate_protection)

    def test_channel_deletion_burst(self):
        """Verifies that 2 channel deletions within 15s triggers repeated channel deletions pattern."""
        ch1 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_101",
            target_name="general-chat",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now,
        )
        ch2 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_102",
            target_name="announcements",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now + 2.0,
        )

        sig1 = self.engine.ingest_event_sync(ch1, current_time=self.now)
        self.assertEqual(len(sig1), 0)

        sig2 = self.engine.ingest_event_sync(ch2, current_time=self.now + 2.0)
        self.assertEqual(len(sig2), 1)
        self.assertEqual(sig2[0].pattern_id, PatternID.REPEATED_CHANNEL_DELETIONS)
        self.assertEqual(sig2[0].severity, ThreatSeverity.CRITICAL)
        self.assertTrue(sig2[0].requires_immediate_protection)
        self.assertEqual(sig2[0].observed_facts["channel_deletion_count"], 2)

    def test_role_deletion_burst(self):
        """Verifies repeated role deletions pattern."""
        r1 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.ROLE_DELETE,
            actor_id=self.actor_id,
            target_id="role_1",
            target_name="Moderator",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now,
        )
        r2 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.ROLE_DELETE,
            actor_id=self.actor_id,
            target_id="role_2",
            target_name="VIP",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now + 1.0,
        )

        self.engine.ingest_event_sync(r1, current_time=self.now)
        signals = self.engine.ingest_event_sync(r2, current_time=self.now + 1.0)
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].pattern_id, PatternID.REPEATED_ROLE_DELETIONS)
        self.assertEqual(signals[0].severity, ThreatSeverity.CRITICAL)

    def test_permission_escalation_then_destruction(self):
        """
        Verifies permission escalation (dangerous permission grant) followed by
        destructive action (channel deletion) within lookback window.
        """
        escalation_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.DANGEROUS_PERMISSION_GRANT,
            actor_id=self.actor_id,
            target_id="role_admin",
            target_name="AdminRole",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now,
        )
        destructive_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_secret",
            target_name="admin-logs",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now + 15.0,
        )

        self.engine.ingest_event_sync(escalation_ev, current_time=self.now)
        signals = self.engine.ingest_event_sync(destructive_ev, current_time=self.now + 15.0)

        match = [s for s in signals if s.pattern_id == PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION]
        self.assertEqual(len(match), 1)
        sig = match[0]
        self.assertEqual(sig.severity, ThreatSeverity.CRITICAL)
        self.assertEqual(sig.confidence, ThreatConfidence.CONFIRMED)
        self.assertTrue(sig.requires_immediate_protection)
        self.assertEqual(sig.observed_facts["destructive_event_type"], SecurityEventType.CHANNEL_DELETE)
        self.assertAlmostEqual(sig.observed_facts["delta_seconds"], 15.0, places=1)

    def test_dangerous_role_changes_then_destruction(self):
        """Verifies role assignment targeting actor followed by destructive ban."""
        role_assign_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.MEMBER_ROLE_UPDATE,
            actor_id="admin_giver",
            target_id=self.actor_id,  # Role assigned to self.actor_id
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now,
        )
        ban_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id=self.actor_id,
            target_id="target_victim",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now + 25.0,
        )

        self.engine.ingest_event_sync(role_assign_ev, current_time=self.now)
        signals = self.engine.ingest_event_sync(ban_ev, current_time=self.now + 25.0)

        match = [s for s in signals if s.pattern_id == PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION]
        self.assertEqual(len(match), 1)
        sig = match[0]
        self.assertEqual(sig.severity, ThreatSeverity.CRITICAL)
        self.assertEqual(sig.actor_id, self.actor_id)

    def test_webhook_integration_abuse(self):
        """Verifies webhook creation paired with destructive channel deletion."""
        wh_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.WEBHOOK_CREATE,
            actor_id=self.actor_id,
            target_id="webhook_99",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now,
        )
        del_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_303",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now + 5.0,
        )

        self.engine.ingest_event_sync(wh_ev, current_time=self.now)
        signals = self.engine.ingest_event_sync(del_ev, current_time=self.now + 5.0)

        match = [s for s in signals if s.pattern_id == PatternID.WEBHOOK_INTEGRATION_ABUSE]
        self.assertEqual(len(match), 1)
        sig = match[0]
        self.assertEqual(sig.recommended_response, ResponseCategory.ISOLATE_INTEGRATION)
        self.assertTrue(sig.observed_facts["is_destructive_pairing"])

    def test_coordinated_multi_vector_destruction(self):
        """Verifies coordinated multi-vector attack spanning 3 distinct destructive categories."""
        ev1 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id=self.actor_id,
            target_id="victim_1",
            timestamp=self.now,
        )
        ev2 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_1",
            timestamp=self.now + 2.0,
        )
        ev3 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.ROLE_DELETE,
            actor_id=self.actor_id,
            target_id="role_1",
            timestamp=self.now + 4.0,
        )

        self.engine.ingest_event_sync(ev1, current_time=self.now)
        self.engine.ingest_event_sync(ev2, current_time=self.now + 2.0)
        signals = self.engine.ingest_event_sync(ev3, current_time=self.now + 4.0)

        match = [s for s in signals if s.pattern_id == PatternID.COORDINATED_MULTI_VECTOR]
        self.assertEqual(len(match), 1)
        sig = match[0]
        self.assertEqual(sig.severity, ThreatSeverity.CRITICAL)
        self.assertEqual(sig.observed_facts["distinct_vectors_count"], 3)
        self.assertTrue(sig.requires_immediate_protection)

    def test_security_weakening_prior_to_destruction(self):
        """Verifies security settings update followed by destructive activity."""
        weaken_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.SECURITY_SETTINGS_UPDATE,
            actor_id=self.actor_id,
            timestamp=self.now,
        )
        ban_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id=self.actor_id,
            target_id="victim_22",
            timestamp=self.now + 30.0,
        )

        self.engine.ingest_event_sync(weaken_ev, current_time=self.now)
        signals = self.engine.ingest_event_sync(ban_ev, current_time=self.now + 30.0)

        match = [s for s in signals if s.pattern_id == PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION]
        self.assertEqual(len(match), 1)
        sig = match[0]
        self.assertEqual(sig.severity, ThreatSeverity.CRITICAL)
        self.assertAlmostEqual(sig.observed_facts["delta_seconds"], 30.0, places=1)

    def test_out_of_order_and_delayed_events(self):
        """
        Verifies that events arriving out of chronological order are correctly
        inserted and evaluated within the sliding time window.
        """
        # Event at t=10 arrives first
        ev1 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_late_2",
            timestamp=self.now + 10.0,
        )
        self.engine.ingest_event_sync(ev1, current_time=self.now + 10.0)

        # Delayed Event at t=2 arrives later (out of order)
        ev0 = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_early_1",
            timestamp=self.now + 2.0,
        )
        signals = self.engine.ingest_event_sync(ev0, current_time=self.now + 10.0)

        # Both channels are within the 15s window, triggering the pattern
        match = [s for s in signals if s.pattern_id == PatternID.REPEATED_CHANNEL_DELETIONS]
        self.assertEqual(len(match), 1)

    def test_duplicate_event_suppression(self):
        """Verifies that duplicate observations of the exact same event are suppressed."""
        ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.CHANNEL_DELETE,
            actor_id=self.actor_id,
            target_id="chan_dup",
            timestamp=self.now,
        )
        self.engine.ingest_event_sync(ev, current_time=self.now)
        # Ingest exact same event again
        signals = self.engine.ingest_event_sync(ev, current_time=self.now + 0.1)
        self.assertEqual(len(signals), 0)

    def test_anti_alert_storm_and_escalation(self):
        """Verifies cooldown suppression and escalation bypass when severity increases significantly."""
        # Burst of 5 bans triggers initial signal
        for i in range(5):
            ev = SecurityEvent(
                guild_id=self.guild_id,
                event_type=SecurityEventType.MEMBER_BAN,
                actor_id=self.actor_id,
                target_id=f"target_storm_{i}",
                timestamp=self.now + i * 0.1,
            )
            self.engine.ingest_event_sync(ev, current_time=self.now + i * 0.1)

        # 6th ban within 10s cooldown should be suppressed (no significant escalation)
        ev_suppressed = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id=self.actor_id,
            target_id="target_storm_6",
            timestamp=self.now + 1.0,
        )
        sig_suppressed = self.engine.ingest_event_sync(ev_suppressed, current_time=self.now + 1.0)
        ban_sig_suppressed = [s for s in sig_suppressed if s.pattern_id == PatternID.RAPID_BAN_BURST]
        self.assertEqual(len(ban_sig_suppressed), 0)

        # Massive escalation to 12 bans (>= 1.5x) bypasses cooldown
        for i in range(7, 13):
            ev_escalated = SecurityEvent(
                guild_id=self.guild_id,
                event_type=SecurityEventType.MEMBER_BAN,
                actor_id=self.actor_id,
                target_id=f"target_storm_{i}",
                timestamp=self.now + 2.0 + (i * 0.05),
            )
            signals = self.engine.ingest_event_sync(ev_escalated, current_time=self.now + 2.0 + (i * 0.05))

        match = [s for s in signals if s.pattern_id == PatternID.RAPID_BAN_BURST]
        self.assertGreaterEqual(len(match), 1)

    def test_subscriber_dispatch(self):
        """Verifies downstream components receive dispatched ThreatSignal instances."""
        received_signals = []

        def subscriber(signal: ThreatSignal):
            received_signals.append(signal)

        self.engine.subscribe_signals(subscriber)

        # Trigger channel deletion pattern
        ev1 = SecurityEvent(guild_id=self.guild_id, event_type=SecurityEventType.CHANNEL_DELETE, actor_id=self.actor_id, target_id="c1", timestamp=self.now)
        ev2 = SecurityEvent(guild_id=self.guild_id, event_type=SecurityEventType.CHANNEL_DELETE, actor_id=self.actor_id, target_id="c2", timestamp=self.now + 1.0)

        # Use async process_event to test full pipeline dispatch
        asyncio.run(self.engine.process_event(ev1))
        asyncio.run(self.engine.process_event(ev2))

        self.assertGreaterEqual(len(received_signals), 1)
        self.assertEqual(received_signals[0].pattern_id, PatternID.REPEATED_CHANNEL_DELETIONS)

    def test_process_activity_manager_emergency_signal(self):
        """Verifies ingestion and enrichment of EmergencySignal from Agent 2 ActivityManager."""
        trigger_ev = SecurityEvent(
            guild_id=self.guild_id,
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id=self.actor_id,
            actor_name="RaidBot",
            attribution_confidence=AttributionConfidence.VERIFIED,
            timestamp=self.now,
        )
        em_sig = EmergencySignal(
            signal_id="em_sig_123",
            signal_type=EmergencySignalType.RAPID_BURST_BAN,
            guild_id=self.guild_id,
            severity="critical",
            scope="actor",
            actor_id=self.actor_id,
            actor_name="RaidBot",
            is_whitelisted_actor=False,
            attribution_confidence=AttributionConfidence.VERIFIED,
            current_count=10,
            threshold_count=5,
            window_seconds=10.0,
            unique_targets_count=10,
            unique_targets=[f"u{i}" for i in range(10)],
            event_types_involved=[SecurityEventType.MEMBER_BAN],
            categories_involved=["member_ban"],
            triggering_event=trigger_ev,
            timestamp=self.now,
        )

        threat_sig = self.engine.process_activity_signal(em_sig)
        self.assertIsNotNone(threat_sig)
        self.assertEqual(threat_sig.pattern_id, EmergencySignalType.RAPID_BURST_BAN)
        self.assertEqual(threat_sig.severity, ThreatSeverity.CRITICAL)
        self.assertTrue(threat_sig.requires_immediate_protection)
        self.assertIn("em_sig_123", threat_sig.correlated_signals)
        self.assertEqual(threat_sig.observed_facts["current_count"], 10)

    def test_format_alert_embed_data(self):
        """Verifies Discord embed formatting with Sentinel emojis and colors."""
        sig = ThreatSignal(
            pattern_id=PatternID.RAPID_BAN_BURST,
            pattern_name="Rapid Burst Member Bans",
            guild_id=self.guild_id,
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.CONFIRMED,
            scope="actor",
            actor_id=self.actor_id,
            actor_name="RogueModerator",
            is_whitelisted_actor=True,
            attribution_confidence=AttributionConfidence.VERIFIED,
            recommended_response=ResponseCategory.EMERGENCY_LOCKDOWN,
            requires_immediate_protection=True,
            time_window_seconds=10.0,
            trigger_reasons=["Observed 10 bans in 10s"],
            observed_facts={"ban_count": 10},
            inferred_intent="Hypothesis: Rogue admin credential compromise executing automated raid.",
            event_ids=["ev_1", "ev_2"],
            target_ids=["u_1", "u_2"],
            timestamp=self.now,
        )

        embed_data = sig.format_alert_embed_data()
        self.assertIn("Security Threat Detected", embed_data["title"])
        self.assertIn("CRITICAL", str(embed_data["fields"]))
        self.assertIn("Whitelisted/Admin Actor", str(embed_data["fields"]))
        self.assertIn("EMERGENCY_LOCKDOWN", str(embed_data["fields"]))
        self.assertGreater(embed_data["color"], 0)


if __name__ == "__main__":
    unittest.main()
