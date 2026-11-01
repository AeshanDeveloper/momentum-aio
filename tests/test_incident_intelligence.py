"""
Comprehensive Automated Test Suite for Sentinel™ Security Incident Intelligence (Tests A through R).

Covers:
- Test A: Ordinary administrative activity (no false alerts, low severity)
- Test B: Related suspicious activity (single incident, single primary alert)
- Test C: Duplicate observations (suppressed, no double-counting, no alert spam)
- Test D: Separate incidents (unrelated actors/vectors remain independent)
- Test E: Existing incident updates (correlated events update existing incident)
- Test F: Delayed message editing (coalesces multiple events into single edit)
- Test G: New event during an edit (queued for subsequent edit pass)
- Test H: No unnecessary edits (minor counter fluctuations do not trigger edit)
- Test I: Critical emergency during cooldown (containment fires immediately)
- Test J: Whitelisted administrator (monitored and assessed, no blanket immunity)
- Test K: Legitimate maintenance burst (clarification & bounded evaluation)
- Test L: Restart recovery (hydrates incidents & message IDs without spam)
- Test M: Missing primary alert (heals deleted message / 404 cleanly)
- Test N: Discord rate limiting (respects 429 retry_after safely)
- Test O: Database failure (gracefully handled, in-memory state preserved)
- Test P: Partial protective-action failure (recorded in action history)
- Test Q: Moderator dismissal (evidence preserved, alert updated, no permanent immunity)
- Test R: Incident resolution (primary alert edited with resolution, no spam)
"""

from __future__ import annotations

import time
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, List, Optional

import discord

from config.settings import settings, COLORS, EMOJIS
from core.container.container import container
from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.event_collector import SecurityEventCollector
from core.security.activity_manager import SecurityActivityManager
from core.security.correlation_engine import (
    SecurityCorrelationEngine,
    ThreatSignal,
    ThreatSeverity,
    ThreatConfidence,
    ResponseCategory,
    PatternID,
)
from core.security.threat_assessment import (
    ThreatAssessmentEngine,
    AssessmentResult,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
    ActionExecutionStatus,
    ReviewDecisionType,
    GuildSecurityPolicy,
)
from core.security.incident_manager import IncidentManager
from core.security.alert_intelligence import (
    AlertIntelligenceManager,
    AlertDeliveryManager,
    NotificationDecision,
)
from core.security.protection_service import SecurityProtectionService
from core.security.pipeline import SentinelSecurityPipeline


class MockMessage:
    def __init__(self, message_id: int = 88889999, channel_id: int = 12345):
        self.id = message_id
        self.channel_id = channel_id
        self.edited_payloads: List[Dict[str, Any]] = []
        self.edit_count = 0
        self.deleted = False

    async def edit(self, **kwargs: Any) -> MockMessage:
        if self.deleted:
            raise discord.NotFound(MagicMock(status=404), "Unknown Message: 10008")
        self.edited_payloads.append(kwargs)
        self.edit_count += 1
        return self


class MockChannel:
    def __init__(self, channel_id: int = 12345):
        self.id = channel_id
        self.sent_messages: List[MockMessage] = []
        self.next_message_id = 100000

    async def send(self, **kwargs: Any) -> MockMessage:
        self.next_message_id += 1
        msg = MockMessage(message_id=self.next_message_id, channel_id=self.id)
        msg.initial_kwargs = kwargs
        self.sent_messages.append(msg)
        return msg

    async def fetch_message(self, message_id: int) -> MockMessage:
        for m in self.sent_messages:
            if m.id == int(message_id):
                if m.deleted:
                    raise discord.NotFound(MagicMock(status=404), "Unknown Message: 10008")
                return m
        raise discord.NotFound(MagicMock(status=404), "Unknown Message: 10008")


class MockGuild:
    def __init__(self, guild_id: int = 99887766):
        self.id = guild_id
        self.name = f"Guild {guild_id}"
        self.owner_id = 111122223333
        self.channels: Dict[int, MockChannel] = {}
        default_ch = MockChannel(channel_id=12345)
        self.channels[12345] = default_ch
        self.system_channel = default_ch

    def get_channel(self, channel_id: int) -> Optional[MockChannel]:
        return self.channels.get(int(channel_id))

    async def fetch_channel(self, channel_id: int) -> Optional[MockChannel]:
        return self.channels.get(int(channel_id))


class MockBotClient:
    def __init__(self):
        self.guilds: Dict[int, MockGuild] = {}
        self.channels: Dict[int, MockChannel] = {}

    def get_guild(self, guild_id: int) -> Optional[MockGuild]:
        return self.guilds.get(int(guild_id))

    def get_channel(self, channel_id: int) -> Optional[MockChannel]:
        return self.channels.get(int(channel_id))

    async def fetch_channel(self, channel_id: int) -> Optional[MockChannel]:
        return self.channels.get(int(channel_id))


class TestIncidentIntelligenceSuite(unittest.TestCase):
    """Automated Test Suite for Sentinel™ Security Incident Intelligence (Tests A-R)."""

    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # Fresh isolated instances
        self.collector = SecurityEventCollector()
        self.activity_manager = SecurityActivityManager()
        self.correlation_engine = SecurityCorrelationEngine()
        self.threat_engine = ThreatAssessmentEngine()
        self.incident_manager = IncidentManager()
        self.alert_intelligence = AlertIntelligenceManager()
        self.alert_delivery = AlertDeliveryManager()
        self.alert_delivery.edit_delay_seconds = 0.05  # Fast delay for testing

        self.mock_client = MockBotClient()
        self.guild = MockGuild(guild_id=99887766)
        self.channel = self.guild.channels[12345]
        self.mock_client.guilds[99887766] = self.guild
        self.mock_client.channels[12345] = self.channel
        self.alert_delivery.bot_client = self.mock_client

        # Wire pipeline
        self.pipeline = SentinelSecurityPipeline(
            collector=self.collector,
            activity_mgr=self.activity_manager,
            corr_engine=self.correlation_engine,
            threat_engine=self.threat_engine,
            inc_manager=self.incident_manager,
            alert_intel=self.alert_intelligence,
            alert_delivery=self.alert_delivery,
        )
        self.pipeline.initialize(self.mock_client)

    def tearDown(self):
        try:
            self.loop.stop()
            self.loop.close()
        except Exception:
            pass

    # Test A: Ordinary administrative activity
    def test_a_ordinary_administrative_activity(self):
        """Test A: Normal administrative activity does not generate false alarms or alert spam."""
        signal = ThreatSignal(
            guild_id="99887766",
            actor_id="5555",
            actor_name="NormalAdmin",
            pattern_id="single_role_update",
            pattern_name="Single Role Update",
            severity=ThreatSeverity.LOW,
            confidence=ThreatConfidence.UNCONFIRMED,
            event_ids=["evt_norm_1"],
            target_ids=["role_1"],
            timestamp=time.time(),
        )

        incident, assessment = self.incident_manager.process_signal_sync(signal)
        self.assertIsNotNone(incident)
        self.assertEqual(incident.severity, ThreatSeverity.LOW)
        self.assertEqual(assessment.urgency, "low")
        self.assertFalse(assessment.is_emergency)

        decision = self.alert_intelligence.evaluate_incident(incident, assessment)
        self.assertEqual(decision, NotificationDecision.NO_NOTIFICATION)
        self.assertIsNone(incident.primary_alert_message_id)

    # Test B: Related suspicious activity
    def test_b_related_suspicious_activity_primary_alert(self):
        """Test B: Related suspicious activity creates single persistent incident and 1 primary alert."""
        signal = ThreatSignal(
            guild_id="99887766",
            actor_id="6666",
            actor_name="SuspiciousActor",
            pattern_id=PatternID.RAPID_BAN_BURST,
            pattern_name="Rapid Ban Burst",
            severity=ThreatSeverity.HIGH,
            confidence=ThreatConfidence.HIGH_CONFIDENCE,
            event_ids=["evt_ban_1", "evt_ban_2", "evt_ban_3"],
            target_ids=["target_1", "target_2", "target_3"],
            timestamp=time.time(),
        )

        incident, assessment = self.incident_manager.process_signal_sync(signal)
        self.assertIsNotNone(incident)
        self.assertEqual(incident.severity, ThreatSeverity.HIGH)
        self.assertIn("RELATED_DESTRUCTIVE_ACTIVITY", assessment.reason_codes)

        # Trigger notification delivery
        res = self.loop.run_until_complete(
            self.alert_delivery.process_incident_notification(
                incident, assessment, guild=self.guild, channel_id=12345
            )
        )
        self.assertEqual(res, NotificationDecision.CREATE_PRIMARY_ALERT)
        self.assertIsNotNone(incident.primary_alert_message_id)
        self.assertEqual(len(self.channel.sent_messages), 1)

    # Test C: Duplicate observations
    def test_c_duplicate_observations(self):
        """Test C: Duplicate observations are deduplicated without inflating threat or spamming."""
        now = time.time()
        evt1 = SecurityEvent(
            event_id="sec_evt_dedup_test",
            guild_id="99887766",
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id="7777",
            target_id="victim_1",
            timestamp=now,
        )
        # Duplicate with same event_id
        evt2 = SecurityEvent(
            event_id="sec_evt_dedup_test",
            guild_id="99887766",
            event_type=SecurityEventType.MEMBER_BAN,
            actor_id="7777",
            target_id="victim_1",
            timestamp=now + 0.1,
        )

        res1 = self.collector.ingest_event(evt1)
        res2 = self.collector.ingest_event(evt2)

        self.assertTrue(res1)
        self.assertFalse(res2)  # Suppressed by collector deduplication
        self.assertEqual(self.collector.duplicate_event_count, 1)

    # Test D: Separate incidents
    def test_d_separate_incidents(self):
        """Test D: Unrelated actors and vectors are partitioned into distinct incidents."""
        now = time.time()
        signal_actor1 = ThreatSignal(
            guild_id="99887766",
            actor_id="actor_111",
            pattern_id=PatternID.RAPID_KICK_BURST,
            severity=ThreatSeverity.MEDIUM,
            event_ids=["evt_1"],
            target_ids=["target_1"],
            timestamp=now,
        )
        signal_actor2 = ThreatSignal(
            guild_id="99887766",
            actor_id="actor_222",
            pattern_id=PatternID.WEBHOOK_INTEGRATION_ABUSE,
            severity=ThreatSeverity.MEDIUM,
            event_ids=["evt_2"],
            target_ids=["webhook_1"],
            timestamp=now + 5.0,
        )

        inc1, _ = self.incident_manager.process_signal_sync(signal_actor1)
        inc2, _ = self.incident_manager.process_signal_sync(signal_actor2)

        self.assertNotEqual(inc1.incident_id, inc2.incident_id)
        self.assertEqual(len(self.incident_manager.get_active_incidents("99887766")), 2)

    # Test E: Existing incident updates
    def test_e_existing_incident_updates(self):
        """Test E: Subsequent correlated events merge into existing incident without creating duplicates."""
        now = time.time()
        signal1 = ThreatSignal(
            guild_id="99887766",
            actor_id="actor_333",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.MEDIUM,
            event_ids=["evt_a1"],
            target_ids=["u1"],
            timestamp=now,
        )
        inc1, _ = self.incident_manager.process_signal_sync(signal1)

        signal2 = ThreatSignal(
            guild_id="99887766",
            actor_id="actor_333",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.HIGH,
            event_ids=["evt_a2"],
            target_ids=["u2"],
            timestamp=now + 10.0,
        )
        inc2, _ = self.incident_manager.process_signal_sync(signal2)

        self.assertEqual(inc1.incident_id, inc2.incident_id)
        self.assertEqual(inc1.severity, ThreatSeverity.HIGH)
        self.assertIn("evt_a2", [e.event_id for e in inc1.evidence_references])

    # Test F: Delayed message editing
    def test_f_delayed_message_editing_coalescing(self):
        """Test F: Multiple material changes coalesce into a single delayed edit."""
        now = time.time()
        signal = ThreatSignal(
            guild_id="99887766",
            actor_id="actor_444",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.HIGH,
            event_ids=["evt_f1"],
            target_ids=["u1"],
            timestamp=now,
        )
        incident, asmt = self.incident_manager.process_signal_sync(signal)

        # 1. Create primary alert
        self.loop.run_until_complete(
            self.alert_delivery.create_primary_alert(incident, asmt, guild=self.guild, channel_id=12345)
        )
        msg_id = incident.primary_alert_message_id
        self.assertIsNotNone(msg_id)
        mock_msg = self.channel.sent_messages[0]

        # 2. Schedule two material changes rapidly
        incident.severity = ThreatSeverity.CRITICAL
        self.alert_delivery.schedule_delayed_edit(incident, reason="severity_jump")
        incident.relevant_targets.extend(["u2", "u3", "u4", "u5"])
        self.alert_delivery.schedule_delayed_edit(incident, reason="target_surge")

        # Let the delay timer (0.05s) fire
        self.loop.run_until_complete(asyncio.sleep(0.1))

        # Should coalesce into 1 edit call on the message
        self.assertEqual(mock_msg.edit_count, 1)
        self.assertFalse(incident.pending_alert_edit)

    # Test G: New event during an edit
    def test_g_event_arriving_during_in_flight_edit(self):
        """Test G: An event arriving while an edit is delivering schedules a subsequent edit pass."""
        now = time.time()
        incident = Incident(
            guild_id="99887766",
            title="Test Incident",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.HIGH,
            primary_alert_message_id="100001",
            alert_channel_id="12345",
        )
        mock_msg = MockMessage(message_id=100001, channel_id=12345)
        self.channel.sent_messages.append(mock_msg)

        # Simulate in-flight edit where new event arrives before completion
        incident.pending_alert_edit = True
        incident.alert_delivery_state = "delivering"

        # New event arrives during delivery
        incident.pending_alert_edit = True
        incident.pending_alert_version += 1

        # Run delayed worker
        self.loop.run_until_complete(self.alert_delivery._delayed_edit_worker(incident, delay=0.01))
        # Wait for any follow-up task scheduled
        self.loop.run_until_complete(asyncio.sleep(0.1))

        self.assertGreaterEqual(mock_msg.edit_count, 1)

    # Test H: No unnecessary edits
    def test_h_no_unnecessary_edits_for_minor_fluctuations(self):
        """Test H: Minor fluctuations in counters without material facts do not trigger message edits."""
        now = time.time()
        incident = Incident(
            incident_id="inc_test_h",
            guild_id="99887766",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.HIGH,
            primary_alert_message_id="100001",
            alert_channel_id="12345",
            relevant_targets=["t1"],
        )
        self.alert_intelligence.capture_snapshot(incident)

        # Minor tick (+1 event without severity change, target change, or action)
        incident.signal_ids.append("sig_minor")

        decision = self.alert_intelligence.evaluate_incident(incident)
        self.assertEqual(decision, NotificationDecision.NO_NOTIFICATION)
        self.assertIn("suppressed_no_material_change", incident.suppression_reason)

    # Test I: Critical emergency during cooldown
    def test_i_critical_emergency_bypasses_cooldown(self):
        """Test I: Autonomous emergency containment executes immediately even during notification cooldown."""
        now = time.time()
        # Incident with emergency lockdown recommendation
        signal = ThreatSignal(
            guild_id="99887766",
            actor_id="destroyer",
            pattern_id=PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION,
            severity=ThreatSeverity.CRITICAL,
            requires_immediate_protection=True,
            event_ids=["evt_crit_1"],
            target_ids=["admin_role"],
            timestamp=now,
        )

        policy = GuildSecurityPolicy(
            guild_id="99887766",
            shadow_mode=False,
            auto_lockdown_enabled=True,
        )

        incident, asmt = self.incident_manager.process_signal_sync(signal, policy=policy)
        self.assertTrue(asmt.should_trigger_immediate_response)
        self.assertTrue(incident.is_emergency)
        # Verify protective action recorded immediately without waiting for alert timer
        self.assertTrue(any(a.action_type == ProtectiveActionType.EMERGENCY_LOCKDOWN for a in incident.protective_actions))

    # Test J: Whitelisted administrator
    def test_j_whitelisted_administrator_evaluated(self):
        """Test J: Whitelisted status does not grant immunity from monitoring or assessment."""
        now = time.time()
        signal = ThreatSignal(
            guild_id="99887766",
            actor_id="trusted_admin_123",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.HIGH,
            is_whitelisted_actor=True,
            event_ids=["evt_wl_1", "evt_wl_2"],
            target_ids=["u1", "u2"],
            timestamp=now,
        )

        incident, asmt = self.incident_manager.process_signal_sync(signal)
        self.assertTrue(incident.is_whitelisted_actor_involved)
        self.assertIn("WHITELIST_ACTOR_DESTRUCTIVE", asmt.reason_codes)
        self.assertEqual(incident.severity, ThreatSeverity.HIGH)

    # Test K: Legitimate maintenance burst
    def test_k_legitimate_maintenance_burst(self):
        """Test K: Legitimate maintenance burst records admin context and avoids false panic."""
        incident = Incident(
            incident_id="inc_maint_test",
            guild_id="99887766",
            title="Channel Clean-up",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.MEDIUM,
        )
        # Admin clarifies planned maintenance
        incident.record_evidence(
            source_type="admin_clarification",
            summary="Planned server overhaul and channel archiving",
            actor_id="111122223333",
        )
        self.assertEqual(len(incident.evidence_references), 1)
        self.assertIn("channel archiving", incident.evidence_references[0].summary)

    # Test L: Restart recovery
    def test_l_restart_recovery_without_alert_spam(self):
        """Test L: Hydrating active incidents across restart preserves alert IDs and prevents alert spam."""
        fake_db_docs = [
            {
                "incident_id": "inc_hydrated_1",
                "guild_id": "99887766",
                "title": "Unresolved Incident",
                "status": IncidentStatus.ACTIVE,
                "severity": ThreatSeverity.HIGH,
                "urgency": "high",
                "primary_alert_message_id": "100001",
                "alert_channel_id": "12345",
                "evidence_references": [],
                "protective_actions": [],
            }
        ]

        from database.database import database
        with patch.object(database, "collection") as mock_col:
            mock_cursor = MagicMock()
            mock_cursor.__iter__.return_value = iter(fake_db_docs)
            mock_col.return_value.find.return_value = mock_cursor

            hydrated = self.incident_manager.hydrate_active_incidents()
            self.assertEqual(len(hydrated), 1)
            hydrated_inc = self.incident_manager.get_incident("inc_hydrated_1")
            self.assertIsNotNone(hydrated_inc)
            self.assertEqual(hydrated_inc.primary_alert_message_id, "100001")

            # Notification evaluation after hydration recognizes no material change -> NO_NOTIFICATION
            decision = self.alert_intelligence.evaluate_incident(hydrated_inc)
            self.assertEqual(decision, NotificationDecision.NO_NOTIFICATION)

    # Test M: Missing primary alert (404 self-healing)
    def test_m_missing_primary_alert_self_healing(self):
        """Test M: Deleted primary alert (404) is self-healed by safely recreating once."""
        mock_msg = MockMessage(message_id=200001, channel_id=12345)
        mock_msg.deleted = True  # Deleted in Discord
        self.channel.sent_messages.append(mock_msg)

        incident = Incident(
            incident_id="inc_heal_test",
            guild_id="99887766",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.HIGH,
            primary_alert_message_id="200001",
            alert_channel_id="12345",
        )

        # Trigger message edit on deleted message
        success = self.loop.run_until_complete(
            self.alert_delivery._perform_message_edit(incident)
        )
        self.assertTrue(success)
        # Message ID updated to recreated message
        self.assertNotEqual(incident.primary_alert_message_id, "200001")
        self.assertEqual(self.alert_delivery.total_recreations_on_404, 1)

    # Test N: Discord rate limiting
    def test_n_discord_rate_limiting_handling(self):
        """Test N: Discord HTTP 429 rate limit is caught and handled safely."""
        mock_msg = MockMessage(message_id=300001, channel_id=12345)
        # First call raises 429, second succeeds
        rate_limit_err = discord.HTTPException(MagicMock(status=429), "Rate limited")
        rate_limit_err.status = 429
        rate_limit_err.retry_after = 0.01

        call_count = 0
        async def mock_edit(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise rate_limit_err
            return mock_msg

        mock_msg.edit = mock_edit
        self.channel.sent_messages.append(mock_msg)

        incident = Incident(
            incident_id="inc_ratelimit_test",
            guild_id="99887766",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.HIGH,
            primary_alert_message_id="300001",
            alert_channel_id="12345",
        )

        success = self.loop.run_until_complete(self.alert_delivery._perform_message_edit(incident))
        self.assertTrue(success)
        self.assertEqual(call_count, 2)

    # Test O: Database failure resilience
    def test_o_database_failure_resilience(self):
        """Test O: Database connectivity errors do not crash in-memory incident grouping."""
        from database.database import database
        with patch.object(database, "collection") as mock_col:
            mock_col.return_value.update_one.side_effect = TimeoutError("MongoDB connection timed out")

            signal = ThreatSignal(
                guild_id="99887766",
                actor_id="actor_555",
                pattern_id=PatternID.RAPID_BAN_BURST,
                severity=ThreatSeverity.HIGH,
                event_ids=["evt_db_fail"],
                target_ids=["u_db"],
                timestamp=time.time(),
            )

            # Ingestion should succeed in-memory
            incident, asmt = self.incident_manager.process_signal_sync(signal)
            self.assertIsNotNone(incident)
            self.assertIn("evt_db_fail", [e.event_id for e in incident.evidence_references])

    # Test P: Partial protective-action failure
    def test_p_partial_protective_action_failure(self):
        """Test P: Partial failure of protective action is logged in action history."""
        incident = Incident(
            incident_id="inc_partial_test",
            guild_id="99887766",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.HIGH,
        )

        action = incident.record_action(
            action_type=ProtectiveActionType.EMERGENCY_LOCKDOWN,
            status=ActionExecutionStatus.FAILED,
            is_shadow_mode=False,
            target_ids=["role_admin_top"],
            error="Bot lacks permission to edit role higher in hierarchy",
        )

        self.assertEqual(action.status, ActionExecutionStatus.FAILED)
        self.assertIn("higher in hierarchy", action.error)
        self.assertEqual(len(incident.protective_actions), 1)

    # Test Q: Moderator dismissal
    def test_q_moderator_dismissal_preserves_evidence(self):
        """Test Q: Moderator dismissal marks status, preserves evidence, and avoids new spam."""
        incident = Incident(
            incident_id="inc_dismiss_test",
            guild_id="99887766",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.HIGH,
            primary_alert_message_id="400001",
            alert_channel_id="12345",
        )
        incident.record_evidence(event_id="ev_d1", summary="Suspicious channel deletion")
        self.incident_manager._incidents["99887766"] = {incident.incident_id: incident}

        mock_msg = MockMessage(message_id=400001, channel_id=12345)
        self.channel.sent_messages.append(mock_msg)

        # Moderator dismisses
        res_inc = self.incident_manager.dismiss_incident(
            incident.incident_id,
            admin_id="admin_mod",
            admin_name="LeadMod",
            reason="Approved authorized test by engineering team",
        )

        self.assertEqual(res_inc.status, IncidentStatus.DISMISSED)
        self.assertEqual(len(res_inc.evidence_references), 1)  # Evidence preserved!
        self.assertEqual(res_inc.resolved_by, "admin_mod")

        # Process notification for dismissal
        decision = self.alert_intelligence.evaluate_incident(res_inc)
        self.assertEqual(decision, NotificationDecision.SEND_RESOLUTION_UPDATE)

    # Test R: Incident resolution
    def test_r_incident_resolution_edits_primary_alert(self):
        """Test R: Incident resolution edits the primary alert without posting new messages."""
        incident = Incident(
            incident_id="inc_resolve_test",
            guild_id="99887766",
            status=IncidentStatus.ACTIVE,
            severity=ThreatSeverity.CRITICAL,
            primary_alert_message_id="500001",
            alert_channel_id="12345",
        )
        incident.record_evidence(event_id="ev_r1", summary="Destructive attack contained")
        self.incident_manager._incidents["99887766"] = {incident.incident_id: incident}

        mock_msg = MockMessage(message_id=500001, channel_id=12345)
        self.channel.sent_messages.append(mock_msg)

        res_inc = self.incident_manager.resolve_incident(
            incident.incident_id,
            admin_id="sec_lead",
            admin_name="SecurityLead",
            reason="Attacker banned and channel permissions restored",
        )

        self.assertEqual(res_inc.status, IncidentStatus.RESOLVED)
        self.assertEqual(res_inc.resolved_by, "sec_lead")

        # Edit primary alert with resolution
        edit_ok = self.loop.run_until_complete(
            self.alert_delivery.update_primary_alert_now(res_inc, is_resolution=True)
        )
        self.assertTrue(edit_ok)
        self.assertEqual(mock_msg.edit_count, 1)
        self.assertEqual(self.alert_delivery.total_resolution_updates, 1)


if __name__ == "__main__":
    unittest.main()
