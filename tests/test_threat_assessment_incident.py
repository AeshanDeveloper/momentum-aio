"""
Unit tests for Sentinel Security Core - Agent 4 of 8.
Testing ThreatAssessmentEngine, IncidentManager, PermissionSnapshot, and Incident lifecycle.
"""

import time
import unittest
import asyncio
from unittest.mock import MagicMock, patch

from config.settings import settings, COLORS, EMOJIS, IMAGES
from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.correlation_engine import (
    ThreatSignal,
    ThreatSeverity,
    ThreatConfidence,
    ResponseCategory,
    PatternID,
    security_correlation_engine,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
    ActionExecutionStatus,
    ReviewDecisionType,
    PermissionSnapshot,
    ProtectiveActionExecution,
    DecisionRecord,
    AdminVote,
    GuildSecurityPolicy,
    EvidenceReference,
)
from core.security.threat_assessment import (
    ThreatAssessmentEngine,
    threat_assessment_engine,
    AssessmentResult,
)
from core.security.incident_manager import (
    IncidentManager,
    incident_manager,
)


class TestIncidentModels(unittest.TestCase):
    """Tests for Incident, PermissionSnapshot, and EvidenceReference models."""

    def test_permission_snapshot_checksum_and_diff(self):
        snapshot = PermissionSnapshot(
            guild_id="123456789",
            incident_id="inc_test_001",
            channel_overwrites={"1001": {"@everyone": {"send_messages": True}}},
            role_permissions={"2001": 8},
        )
        self.assertTrue(len(snapshot.checksum) == 64)  # Valid SHA-256

        # Record exact mutation made by Sentinel
        snapshot.record_diff(
            resource_type="channel_overwrite",
            resource_id="1001",
            original_state={"send_messages": True},
            altered_state={"send_messages": False},
        )
        self.assertIn("channel_overwrite", snapshot.modified_diffs)
        self.assertIn("1001", snapshot.modified_diffs["channel_overwrite"])

        # Serialization round-trip
        data = snapshot.to_dict()
        reconstructed = PermissionSnapshot.from_dict(data)
        self.assertEqual(snapshot.snapshot_id, reconstructed.snapshot_id)
        self.assertEqual(snapshot.checksum, reconstructed.checksum)
        self.assertEqual(snapshot.modified_diffs, reconstructed.modified_diffs)

    def test_incident_signal_merging_and_evidence(self):
        now = time.time()
        incident = Incident(
            guild_id="123456789",
            title="Initial Incident",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.LOW,
            confidence=ThreatConfidence.SUSPICIOUS,
            first_seen_at=now,
            latest_seen_at=now,
        )

        signal1 = ThreatSignal(
            signal_id="sig_001",
            guild_id="123456789",
            pattern_id=PatternID.RAPID_BAN_BURST,
            pattern_name="Rapid Ban Burst",
            severity=ThreatSeverity.HIGH,
            confidence=ThreatConfidence.HIGH_CONFIDENCE,
            actor_id="9991",
            actor_name="RogueAdmin",
            target_ids=["target_1", "target_2"],
            event_ids=["evt_001", "evt_002"],
            trigger_reasons=["5 bans in 4 seconds"],
            observed_facts={"ban_count": 5},
            timestamp=now + 5.0,
        )

        incident.add_signal(signal1)

        # Verify upgraded severity and confidence
        self.assertEqual(incident.severity, ThreatSeverity.HIGH)
        self.assertEqual(incident.confidence, ThreatConfidence.HIGH_CONFIDENCE)
        self.assertIn("sig_001", incident.signal_ids)
        self.assertIn(PatternID.RAPID_BAN_BURST, incident.matched_patterns)
        self.assertEqual(incident.latest_seen_at, now + 5.0)
        self.assertEqual(len(incident.relevant_actors), 1)
        self.assertEqual(incident.relevant_actors[0]["actor_id"], "9991")
        self.assertEqual(len(incident.relevant_targets), 2)
        self.assertEqual(len(incident.evidence_references), 2)

        # Serialization round-trip
        inc_dict = incident.to_dict()
        reconstructed = Incident.from_dict(inc_dict)
        self.assertEqual(incident.incident_id, reconstructed.incident_id)
        self.assertEqual(incident.severity, reconstructed.severity)
        self.assertEqual(len(reconstructed.evidence_references), 2)

    def test_incident_decision_and_voting(self):
        incident = Incident(
            guild_id="123456789",
            status=IncidentStatus.ACTIVE,
        )

        # Record admin vote
        vote = incident.record_vote(admin_id="admin_1", approved=True, reason="Attack confirmed", admin_name="SecLead")
        self.assertTrue(vote.approved)
        self.assertIn("admin_1", incident.votes)
        self.assertEqual(len(incident.decision_history), 1)

        # Transition status safely
        incident.transition_status(IncidentStatus.CONFIRMED, actor_id="admin_1", reason="Consensus reached")
        self.assertEqual(incident.status, IncidentStatus.CONFIRMED)
        self.assertEqual(len(incident.decision_history), 2)

    def test_guild_security_policy_defaults(self):
        policy = GuildSecurityPolicy(guild_id="123")
        # Default must be SHADOW MODE!
        self.assertTrue(policy.shadow_mode)
        self.assertFalse(policy.auto_lockdown_enabled)
        self.assertEqual(policy.emergency_threshold_score, 75.0)

        data = policy.to_dict()
        reconstructed = GuildSecurityPolicy.from_dict(data)
        self.assertTrue(reconstructed.shadow_mode)
        self.assertFalse(reconstructed.auto_lockdown_enabled)


class TestThreatAssessmentEngine(unittest.TestCase):
    """Tests for ThreatAssessmentEngine risk scoring and emergency evaluation."""

    def setUp(self):
        self.engine = ThreatAssessmentEngine()
        self.now = time.time()

    def test_graduated_confidence_scoring(self):
        # Confirmed high severity
        sig_confirmed = ThreatSignal(
            guild_id="123",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.CONFIRMED,
            attribution_confidence=AttributionConfidence.VERIFIED,
            requires_immediate_protection=True,
            timestamp=self.now,
        )
        res_confirmed = self.engine.assess_signal(sig_confirmed)
        self.assertGreaterEqual(res_confirmed.threat_score, 90.0)
        self.assertTrue(res_confirmed.is_emergency)
        self.assertTrue(res_confirmed.should_trigger_immediate_response)

        # Unconfirmed low severity
        sig_unconfirmed = ThreatSignal(
            guild_id="123",
            pattern_id="single_channel_update",
            severity=ThreatSeverity.LOW,
            confidence=ThreatConfidence.UNCONFIRMED,
            attribution_confidence=AttributionConfidence.UNKNOWN,
            requires_immediate_protection=False,
            timestamp=self.now,
        )
        res_unconfirmed = self.engine.assess_signal(sig_unconfirmed)
        self.assertLess(res_unconfirmed.threat_score, 40.0)
        self.assertFalse(res_unconfirmed.is_emergency)
        self.assertFalse(res_unconfirmed.should_trigger_immediate_response)

    def test_unknown_actor_does_not_block_dangerous_attack(self):
        # Even if actor attribution is UNKNOWN, a critical destructive attack must trigger protection
        sig_unknown_actor = ThreatSignal(
            guild_id="123",
            pattern_id=PatternID.REPEATED_CHANNEL_DELETIONS,
            pattern_name="Repeated Channel Deletions",
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.HIGH_CONFIDENCE,
            attribution_confidence=AttributionConfidence.UNKNOWN,
            scope="guild",
            requires_immediate_protection=True,
            timestamp=self.now,
        )
        result = self.engine.assess_signal(sig_unknown_actor)
        self.assertTrue(result.is_emergency)
        self.assertTrue(result.should_trigger_immediate_response)
        self.assertEqual(result.recommended_action, ProtectiveActionType.EMERGENCY_LOCKDOWN)

    def test_whitelisted_actor_never_ignored(self):
        # Trusted actor performing mass bans must NOT be suppressed
        sig_whitelisted = ThreatSignal(
            guild_id="123",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.HIGH_CONFIDENCE,
            actor_id="trusted_admin_42",
            is_whitelisted_actor=True,
            attribution_confidence=AttributionConfidence.VERIFIED,
            requires_immediate_protection=True,
            timestamp=self.now,
        )
        result = self.engine.assess_signal(sig_whitelisted)
        self.assertTrue(result.is_whitelisted_actor)
        self.assertTrue(result.is_emergency)
        self.assertTrue(any("Whitelisted/trusted actor" in r for r in result.reasons))

    def test_shadow_mode_default_and_enforcement_toggle(self):
        sig = ThreatSignal(
            guild_id="123",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.CRITICAL,
            requires_immediate_protection=True,
            timestamp=self.now,
        )

        # 1. Default policy (shadow_mode=True)
        res_default = self.engine.assess_signal(sig)
        self.assertTrue(res_default.is_shadow_mode)

        # 2. Explicit enforcement policy
        live_policy = GuildSecurityPolicy(
            guild_id="123",
            shadow_mode=False,
            auto_lockdown_enabled=True,
        )
        self.engine.set_guild_policy("123", live_policy)
        res_live = self.engine.assess_signal(sig)
        self.assertFalse(res_live.is_shadow_mode)

    def test_recovery_plan_preserves_sentinel_and_admins(self):
        policy = GuildSecurityPolicy(
            guild_id="123",
            recovery_admin_ids=["admin_99", "admin_100"],
            recovery_channel_id="chan_emergency",
        )
        self.engine.set_guild_policy("123", policy)

        sig = ThreatSignal(
            guild_id="123",
            pattern_id=PatternID.COORDINATED_MULTI_VECTOR,
            severity=ThreatSeverity.CRITICAL,
            requires_immediate_protection=True,
            timestamp=self.now,
        )
        result = self.engine.assess_signal(sig)
        plan = result.recovery_plan
        self.assertIn("admin_99", plan["shielded_admin_ids"])
        self.assertIn("admin_100", plan["shielded_admin_ids"])
        self.assertTrue(plan["recovery_code"].startswith("SENTINEL-REC-"))
        self.assertIn("unlock", plan["instructions"])


class TestIncidentManager(unittest.TestCase):
    """Tests for IncidentManager lifecycle, grouping, snapshots, and evidence preservation."""

    def setUp(self):
        self.manager = IncidentManager()
        self.guild_id = "guild_test_777"
        self.manager.clear_guild(self.guild_id)
        self.now = time.time()

    def test_signal_grouping_into_single_incident(self):
        # Two related signals within 60 seconds from same actor
        sig1 = ThreatSignal(
            signal_id="sig_burst_1",
            guild_id=self.guild_id,
            pattern_id=PatternID.RAPID_BAN_BURST,
            pattern_name="Rapid Ban Burst",
            severity=ThreatSeverity.HIGH,
            confidence=ThreatConfidence.HIGH_CONFIDENCE,
            actor_id="actor_bad",
            target_ids=["target_1"],
            event_ids=["evt_1"],
            timestamp=self.now,
        )
        inc1, asmt1 = self.manager.process_signal_sync(sig1)
        self.assertIsNotNone(inc1)

        sig2 = ThreatSignal(
            signal_id="sig_burst_2",
            guild_id=self.guild_id,
            pattern_id=PatternID.REPEATED_CHANNEL_DELETIONS,
            pattern_name="Repeated Channel Deletions",
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.CONFIRMED,
            actor_id="actor_bad",
            target_ids=["target_2"],
            event_ids=["evt_2"],
            timestamp=self.now + 20.0,
        )
        inc2, asmt2 = self.manager.process_signal_sync(sig2)

        # Both signals must merge into the same incident!
        self.assertEqual(inc1.incident_id, inc2.incident_id)
        self.assertEqual(len(inc2.signal_ids), 2)
        self.assertIn(PatternID.RAPID_BAN_BURST, inc2.matched_patterns)
        self.assertIn(PatternID.REPEATED_CHANNEL_DELETIONS, inc2.matched_patterns)
        self.assertEqual(inc2.severity, ThreatSeverity.CRITICAL)

    def test_emergency_fast_path_and_snapshot_creation(self):
        sig_crit = ThreatSignal(
            signal_id="sig_emergency",
            guild_id=self.guild_id,
            pattern_id=PatternID.COORDINATED_MULTI_VECTOR,
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.CONFIRMED,
            requires_immediate_protection=True,
            actor_id="hacker_9",
            timestamp=self.now,
        )
        inc, asmt = self.manager.process_signal_sync(sig_crit)

        self.assertEqual(inc.status, IncidentStatus.CONTAINED)
        self.assertTrue(len(inc.protective_actions) >= 1)
        self.assertTrue(len(inc.snapshot_ids) >= 1)

        snapshot_id = inc.snapshot_ids[0]
        snapshot = self.manager.get_snapshot(snapshot_id)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.incident_id, inc.incident_id)

    def test_dismiss_incident_preserves_evidence(self):
        sig = ThreatSignal(
            signal_id="sig_test_dismiss",
            guild_id=self.guild_id,
            pattern_id=PatternID.RAPID_KICK_BURST,
            severity=ThreatSeverity.MEDIUM,
            event_ids=["evt_kick_1", "evt_kick_2"],
            timestamp=self.now,
        )
        inc, _ = self.manager.process_signal_sync(sig)
        incident_id = inc.incident_id

        # Admin dismisses incident
        updated = self.manager.dismiss_incident(
            incident_id=incident_id,
            admin_id="admin_mod",
            reason="Authorized raid drill",
            admin_name="LeadModerator",
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, IncidentStatus.DISMISSED)

        # CRITICAL TEST: Incident and evidence must NOT be deleted!
        retrieved = self.manager.get_incident(incident_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.status, IncidentStatus.DISMISSED)
        self.assertEqual(len(retrieved.evidence_references), 2)
        self.assertTrue(any("Authorized raid drill" in d.reason for d in retrieved.decision_history))

    def test_reversible_snapshot_diff_and_restoration(self):
        snapshot = self.manager.create_permission_snapshot(
            guild_id=self.guild_id,
            incident_id="inc_rollback_test",
            channel_overwrites={"channel_main": {"@everyone": {"send_messages": True}}},
        )
        # Record diff
        self.manager.record_snapshot_diff(
            snapshot_id=snapshot.snapshot_id,
            resource_type="channel_overwrite",
            resource_id="channel_main",
            original_state={"send_messages": True},
            altered_state={"send_messages": False},
        )
        # Verify restoration tracking
        success = self.manager.record_snapshot_restoration(snapshot.snapshot_id, restored_by="admin_recovery")
        self.assertTrue(success)

        reloaded = self.manager.get_snapshot(snapshot.snapshot_id)
        self.assertTrue(reloaded.is_restored)
        self.assertEqual(reloaded.restored_by, "admin_recovery")

    def test_embed_and_recovery_dm_formatting(self):
        sig = ThreatSignal(
            signal_id="sig_format",
            guild_id=self.guild_id,
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.CRITICAL,
            requires_immediate_protection=True,
            timestamp=self.now,
        )
        inc, asmt = self.manager.process_signal_sync(sig)

        embed = self.manager.format_incident_embed(inc, asmt)
        self.assertIsNotNone(embed)
        self.assertIn("CRITICAL", embed.description)
        self.assertIn("SHADOW MODE", embed.description)

        dm_text = self.manager.format_recovery_dm(inc)
        self.assertIn("URGENT SECURITY ALERT", dm_text)
        self.assertIn(inc.incident_id, dm_text)
        self.assertIn(inc.recovery_code, dm_text)

    def test_search_and_query_apis(self):
        sig = ThreatSignal(
            signal_id="sig_search",
            guild_id=self.guild_id,
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.HIGH,
            actor_id="actor_specific",
            timestamp=self.now,
        )
        inc, _ = self.manager.process_signal_sync(sig)

        # Search by actor
        found = self.manager.search_incidents(self.guild_id, actor_id="actor_specific")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].incident_id, inc.incident_id)

        # Search by wrong actor
        not_found = self.manager.search_incidents(self.guild_id, actor_id="nobody")
        self.assertEqual(len(not_found), 0)

        # List incidents
        all_incs = self.manager.list_incidents(self.guild_id)
        self.assertEqual(len(all_incs), 1)

    def test_concurrent_signal_processing(self):
        async def run_concurrent():
            sig1 = ThreatSignal(
                signal_id="sig_c1",
                guild_id=self.guild_id,
                pattern_id=PatternID.RAPID_BAN_BURST,
                severity=ThreatSeverity.HIGH,
                actor_id="concurrent_actor",
                timestamp=self.now,
            )
            sig2 = ThreatSignal(
                signal_id="sig_c2",
                guild_id=self.guild_id,
                pattern_id=PatternID.RAPID_BAN_BURST,
                severity=ThreatSeverity.CRITICAL,
                actor_id="concurrent_actor",
                timestamp=self.now + 1.0,
            )
            # Run concurrently
            results = await asyncio.gather(
                self.manager.handle_threat_signal(sig1),
                self.manager.handle_threat_signal(sig2),
            )
            inc_a, _ = results[0]
            inc_b, _ = results[1]
            self.assertEqual(inc_a.incident_id, inc_b.incident_id)

        asyncio.run(run_concurrent())


if __name__ == "__main__":
    unittest.main()
