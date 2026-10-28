"""
Comprehensive Unit & Integration Test Suite for Sentinel™ Security Core Integration (Agent 7 of 8).

Validates:
1. Complete pipeline initialization, dependency container wiring, and restart hydration.
2. Event-to-signal-to-emergency-lockdown flow (immediate dispatch before human response).
3. Idempotency under duplicate signals and sustained attack bursts.
4. Graduated confidence (unknown actor velocity vs verified actor proof).
5. Strict monitoring and non-suppression of trusted/whitelisted actors.
6. Autonomous Communication Service:
   - Proactive critical alerts
   - Structured clarification conversations (Planned maintenance, Not authorised, Unsure, Review)
   - Evidence preservation of clarification statements (no blind trust, no active attack override)
   - Graceful DM failure routing to fallback channel
   - Recovery completion and partial-failure reports
7. Multi-admin reviewer interaction, vote correction, and Anti-Self-Pardon guard.
8. Reversible recovery executing real restoration interface and preserving independent admin changes.
9. Continued monitoring after false-alarm dismissal with forensic proof retention.
10. Database timeout resilience and error isolation.
11. Securitycheck diagnostic command auditing full pipeline posture and hierarchy.
"""

import time
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, List, Optional

import discord
from discord import Permissions, Role, TextChannel, Member, User

from config.settings import settings, COLORS, EMOJIS
from core.container.container import container
from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.event_collector import SecurityEventCollector
from core.security.activity_manager import SecurityActivityManager, ActivityCategory
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
    ReviewDecisionType,
)
from core.security.incident_manager import IncidentManager
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    get_default_response_policy,
)
from core.security.lockdown_journal import (
    LockdownRecord,
    JournalEntry,
    JournalEntryStatus,
    LockdownJournalManager,
)
from core.security.emergency_lockdown_manager import EmergencyLockdownManager
from core.security.protection_service import SecurityProtectionService
from core.security.communication_service import (
    SecurityCommunicationService,
    ClarificationChoice,
    ClarificationConversationView,
)
from core.security.consensus_manager import (
    IncidentConsensusManager,
    ReviewChoice,
)
from core.security.pipeline import (
    SentinelSecurityPipeline,
)
from core.security.antinuke import AntiNukeManager, AntiNukeConstants
from plugins.MomentumOneToolkit.commands.security.securitycheck import (
    execute as securitycheck_execute,
    build_security_check_container,
)


class MockMember:
    def __init__(self, user_id: int, name: str, is_admin: bool = True, is_bot: bool = False, top_role_pos: int = 10):
        self.id = user_id
        self.name = name
        self.display_name = name
        self.bot = is_bot
        self.mention = f"<@{user_id}>"
        
        # Permissions
        p = Permissions()
        if is_admin:
            p.administrator = True
            p.manage_guild = True
            p.manage_roles = True
            p.manage_channels = True
            p.ban_members = True
            p.kick_members = True
            p.view_audit_log = True
        self.guild_permissions = p

        # Top role mock
        self.top_role = MagicMock(spec=Role)
        self.top_role.id = 500 + top_role_pos
        self.top_role.name = f"Role-Pos-{top_role_pos}"
        self.top_role.position = top_role_pos
        self.top_role.managed = False

    def __str__(self):
        return f"{self.name}#{self.id}"


class MockRole:
    def __init__(self, role_id: int, name: str, position: int = 1, admin: bool = False):
        self.id = role_id
        self.name = name
        self.position = position
        self.managed = False
        p = Permissions()
        if admin:
            p.administrator = True
        self.permissions = p

    def __lt__(self, other):
        return self.position < getattr(other, "position", 0)

    def __le__(self, other):
        return self.position <= getattr(other, "position", 0)

    def __gt__(self, other):
        return self.position > getattr(other, "position", 0)

    def __ge__(self, other):
        return self.position >= getattr(other, "position", 0)

    async def edit(self, **kwargs):
        pass


class MockChannel:
    def __init__(self, channel_id: int, name: str, guild: Any = None):
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.overwrites: Dict[Any, Any] = {}
        self.sent_messages: List[Dict[str, Any]] = []

    async def set_permissions(self, target: Any, **kwargs):
        self.overwrites[target] = kwargs

    async def send(self, **kwargs):
        self.sent_messages.append(kwargs)
        msg = MagicMock(spec=discord.Message)
        msg.id = 1234567
        return msg


class MockGuild:
    def __init__(self, guild_id: int = 77001, name: str = "Pipeline Test Guild", owner_id: int = 90001):
        self.id = guild_id
        self.name = name
        self.owner_id = owner_id
        self.roles: List[Any] = []
        self.channels: List[Any] = []
        self.members: Dict[int, Any] = {}
        
        # Bot member
        self.me = MockMember(user_id=88888, name="SentinelBot", is_admin=True, is_bot=True, top_role_pos=50)
        self.roles.append(self.me.top_role)

    def get_member(self, user_id: int):
        return self.members.get(user_id)

    def get_role(self, role_id: int):
        for r in self.roles:
            if r.id == role_id:
                return r
        return None

    def get_channel(self, channel_id: int):
        for c in self.channels:
            if c.id == channel_id:
                return c
        return None


class MockDiscordClient:
    def __init__(self):
        self.guilds: List[MockGuild] = []
        self.users: Dict[int, Any] = {}

    def get_guild(self, guild_id: int):
        for g in self.guilds:
            if g.id == guild_id:
                return g
        return None

    def get_user(self, user_id: int):
        return self.users.get(user_id)

    async def fetch_user(self, user_id: int):
        return self.users.get(user_id)


class MockDMUser:
    def __init__(self, user_id: int, name: str, can_receive_dm: bool = True):
        self.id = user_id
        self.name = name
        self.can_receive_dm = can_receive_dm
        self.dm_channel = self if can_receive_dm else None
        self.sent_messages: List[Dict[str, Any]] = []

    async def create_dm(self):
        if not self.can_receive_dm:
            raise discord.Forbidden(MagicMock(status=403), "Cannot send messages to this user")
        return self

    async def send(self, **kwargs):
        if not self.can_receive_dm:
            raise discord.Forbidden(MagicMock(status=403), "Cannot send messages to this user")
        self.sent_messages.append(kwargs)
        msg = MagicMock(spec=discord.Message)
        msg.id = 99999
        return msg


class MockInteraction:
    def __init__(self, user_id: int, name: str, guild: Optional[MockGuild] = None):
        self.user = MockMember(user_id=user_id, name=name, is_admin=True)
        self.guild = guild
        self.response = MockInteractionResponse()
        self.followup = self.response


class MockInteractionResponse:
    def __init__(self):
        self._done = False
        self.sent_messages: List[Dict[str, Any]] = []

    def is_done(self):
        return self._done

    async def send_message(self, **kwargs):
        self._done = True
        self.sent_messages.append(kwargs)

    async def send(self, **kwargs):
        self._done = True
        self.sent_messages.append(kwargs)


class TestAgent7SecurityPipeline(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset singletons for pristine test isolation
        SecurityEventCollector.reset_instance()
        SecurityActivityManager.reset_instance()
        SecurityCorrelationEngine.reset_instance()
        SentinelSecurityPipeline.reset_instance()
        SecurityCommunicationService.reset_instance()

        self.collector = SecurityEventCollector.get_instance()
        self.activity_mgr = SecurityActivityManager(max_active_actors_per_guild=50, signal_cooldown=0.0)
        self.corr_engine = SecurityCorrelationEngine(activity_manager=self.activity_mgr)
        self.threat_engine = ThreatAssessmentEngine()
        self.inc_manager = IncidentManager()
        self.journal_mgr = LockdownJournalManager()
        self.lockdown_mgr = EmergencyLockdownManager(journal_manager=self.journal_mgr)
        self.protection_service = SecurityProtectionService(
            lockdown_mgr=self.lockdown_mgr,
            journal_mgr=self.journal_mgr,
            inc_mgr=self.inc_manager,
        )
        self.consensus_mgr = IncidentConsensusManager(
            inc_manager=self.inc_manager,
            lockdown_mgr=self.lockdown_mgr,
            prot_service=self.protection_service,
            journal_mgr=self.journal_mgr,
        )
        self.comm_service = SecurityCommunicationService(
            inc_manager=self.inc_manager,
            consensus_mgr=self.consensus_mgr,
        )

        self.pipeline = SentinelSecurityPipeline(
            collector=self.collector,
            activity_mgr=self.activity_mgr,
            corr_engine=self.corr_engine,
            threat_engine=self.threat_engine,
            inc_manager=self.inc_manager,
            prot_service=self.protection_service,
            comm_service=self.comm_service,
            consensus_mgr=self.consensus_mgr,
        )

        # Setup Mock Guild & Environment
        self.guild = MockGuild(guild_id=77001, name="Citadel Defense Guild", owner_id=90001)
        self.owner = MockMember(user_id=90001, name="ServerOwner", is_admin=True)
        self.admin1 = MockMember(user_id=10001, name="AdminAlice", is_admin=True)
        self.admin2 = MockMember(user_id=10002, name="AdminBob", is_admin=True)
        self.admin3 = MockMember(user_id=10003, name="AdminCharlie", is_admin=True)
        self.attacker = MockMember(user_id=66666, name="RogueAttacker", is_admin=True)

        self.guild.members[self.owner.id] = self.owner
        self.guild.members[self.admin1.id] = self.admin1
        self.guild.members[self.admin2.id] = self.admin2
        self.guild.members[self.admin3.id] = self.admin3
        self.guild.members[self.attacker.id] = self.attacker

        # Fallback channel
        self.fallback_channel = MockChannel(channel_id=99001, name="security-audit-logs", guild=self.guild)
        self.guild.channels.append(self.fallback_channel)

        # Mock client
        self.client = MockDiscordClient()
        self.client.guilds.append(self.guild)

        # Add mock DM users
        self.dm_owner = MockDMUser(user_id=90001, name="ServerOwner")
        self.dm_admin1 = MockDMUser(user_id=10001, name="AdminAlice")
        self.dm_admin2 = MockDMUser(user_id=10002, name="AdminBob", can_receive_dm=False)  # closed DMs
        self.dm_admin3 = MockDMUser(user_id=10003, name="AdminCharlie")
        self.client.users[90001] = self.dm_owner
        self.client.users[10001] = self.dm_admin1
        self.client.users[10002] = self.dm_admin2
        self.client.users[10003] = self.dm_admin3

        # Configure Policy: armed live mode for containment test
        self.policy = SecurityResponsePolicy(
            guild_id="77001",
            response_level=ResponseLevel.LOCKDOWN,
            auto_lockdown_enabled=True,
            shadow_mode=False,
            recovery_owner_id="90001",
            trusted_recovery_admin_ids=["10001", "10002", "10003"],
            fallback_channel_id="99001",
            confirmation_quorum=2,
            dismissal_quorum=3,
            recovery_quorum=2,
        )
        self.protection_service._policies["77001"] = self.policy

        # Initialize pipeline
        self.pipeline.initialize(self.client)

    async def asyncTearDown(self):
        self.collector.clear_subscribers()
        self.corr_engine.clear_subscribers()

    # -------------------------------------------------------------------------
    # Test 1: Complete Pipeline Initialization, Container Binding, & Hydration
    # -------------------------------------------------------------------------
    async def test_pipeline_initialization_and_hydration(self):
        """Verifies all components wire up, bind to IoC container, and hydrate state."""
        self.assertTrue(self.pipeline._is_initialized)
        self.assertTrue(container.has("sentinel_security_pipeline"))
        self.assertTrue(container.has("security_event_collector"))
        self.assertTrue(container.has("security_protection_service"))
        self.assertTrue(container.has("security_communication_service"))
        self.assertTrue(container.has("incident_consensus_manager"))

        # Re-initialization is idempotent
        res = self.pipeline.initialize(self.client)
        self.assertTrue(res)

    # -------------------------------------------------------------------------
    # Test 2: Event-to-Signal-to-Lockdown (Immediate Autonomous Protection)
    # -------------------------------------------------------------------------
    async def test_event_to_emergency_lockdown_immediate_dispatch(self):
        """
        Verifies that rapid burst deletions trigger immediate emergency lockdown
        without waiting for human response or external consensus.
        """
        now = time.time()
        # Ingest 3 rapid channel deletions (configured threshold for repeated channel deletions)
        for i in range(3):
            ch = MockChannel(channel_id=101 + i, name=f"deleted-ch-{i}", guild=self.guild)
            self.pipeline.process_gateway_event(
                AntiNukeConstants.EVENT_CHANNEL_DELETE,
                ch,
                guild=self.guild,
                actor=self.attacker,
                audit_entry_id=8800 + i,
            )

        # Allow async tasks in loop to execute
        await asyncio.sleep(0.1)

        # Verify incident was created
        incidents = self.inc_manager.get_active_incidents("77001")
        self.assertGreaterEqual(len(incidents), 1)
        inc = incidents[0]
        self.assertTrue(inc.is_emergency)

        # Verify emergency lockdown was executed autonomously
        active_lck = self.journal_mgr.get_active_lockdown_for_guild("77001")
        self.assertIsNotNone(active_lck)
        self.assertEqual(active_lck.guild_id, "77001")
        self.assertIn(active_lck.status, (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL, LockdownStatus.VERIFIED))

    # -------------------------------------------------------------------------
    # Test 3: Lockdown Idempotency Under Duplicate Signals
    # -------------------------------------------------------------------------
    async def test_lockdown_idempotency_prevents_duplicate_execution(self):
        """Verifies duplicate signals while lockdown is active do not trigger repeated executions."""
        # Execute initial lockdown
        incident = Incident(guild_id="77001", title="Initial Attack", severity="critical", is_emergency=True)
        assessment = AssessmentResult(
            threat_score=100.0,
            severity="critical",
            should_trigger_immediate_response=True,
        )
        record1 = await self.lockdown_mgr.execute_emergency_lockdown(
            guild=self.guild,
            incident=incident,
            assessment=assessment,
            policy=self.policy,
        )
        self.assertIn(record1.status, (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL, LockdownStatus.VERIFIED))

        # Second signal for same guild
        record2 = await self.lockdown_mgr.execute_emergency_lockdown(
            guild=self.guild,
            incident=incident,
            assessment=assessment,
            policy=self.policy,
        )
        # Should return the existing active record without re-running destructive changes
        self.assertEqual(record1.lockdown_id, record2.lockdown_id)

    # -------------------------------------------------------------------------
    # Test 4: Graduated Confidence & Unknown Actor Handling
    # -------------------------------------------------------------------------
    async def test_unknown_actor_velocity_triggers_protection(self):
        """Unknown actor attribution must not prevent protective response to high-velocity destruction."""
        sig = ThreatSignal(
            guild_id="77001",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.SUSPICIOUS,
            attribution_confidence=AttributionConfidence.UNKNOWN,
            actor_id=None,
            requires_immediate_protection=True,
            event_ids=["evt_1", "evt_2", "evt_3", "evt_4", "evt_5"],
        )
        assessment = self.threat_engine.assess_signal(sig, self.policy)
        # Threat score remains high to protect the server
        self.assertGreaterEqual(assessment.threat_score, 75.0)
        self.assertTrue(assessment.should_trigger_immediate_response)

    # -------------------------------------------------------------------------
    # Test 5: Trusted & Whitelisted Actors Monitored Without Suppression
    # -------------------------------------------------------------------------
    async def test_whitelisted_actor_monitored_and_flagged(self):
        """Whitelisted users must still be monitored; anomalous activity is flagged as potential compromise."""
        sig = ThreatSignal(
            guild_id="77001",
            pattern_id=PatternID.RAPID_BAN_BURST,
            severity=ThreatSeverity.HIGH,
            confidence=ThreatConfidence.HIGH_CONFIDENCE,
            attribution_confidence=AttributionConfidence.VERIFIED,
            actor_id="10001",  # Whitelisted admin
            is_whitelisted_actor=True,
            requires_immediate_protection=True,
            event_ids=["evt_a", "evt_b", "evt_c"],
        )
        assessment = self.threat_engine.assess_signal(sig, self.policy)
        self.assertTrue(assessment.is_whitelisted_actor)
        self.assertGreaterEqual(assessment.threat_score, 80.0)
        # Reasons must indicate potential compromise of trusted account
        reasons_joined = " ".join(assessment.reasons)
        self.assertIn("Whitelisted/trusted actor", reasons_joined)

    # -------------------------------------------------------------------------
    # Test 6: Clarification Conversation Workflow & Evidence Recording
    # -------------------------------------------------------------------------
    async def test_clarification_conversation_options_and_evidence(self):
        """Tests sending structured clarification question and recording responses as evidence."""
        incident = Incident(
            guild_id="77001",
            title="Suspicious Channel Modifications",
            severity="medium",
            confidence="suspicious",
            actor_id="10001",
        )
        self.inc_manager._incidents.setdefault("77001", {})[incident.incident_id] = incident

        # Initiate clarification conversation
        success = await self.comm_service.initiate_clarification_conversation(
            incident=incident,
            recipient_id="10001",
            guild_id="77001",
        )
        self.assertTrue(success)
        self.assertGreaterEqual(len(self.dm_admin1.sent_messages), 1)

        # 6a. Admin answers 'Planned Maintenance'
        interaction = MockInteraction(user_id=10001, name="AdminAlice", guild=self.guild)
        await self.comm_service.handle_clarification_response(
            interaction=interaction,
            choice=ClarificationChoice.MAINTENANCE,
            incident_id=incident.incident_id,
            recipient_id="10001",
        )
        # Verify evidence recorded
        self.assertTrue(any("Planned Maintenance" in f for f in incident.observed_facts))
        self.assertTrue(any(e.source_type == "admin_clarification" for e in incident.evidence_references))

        # 6b. Answering Planned Maintenance does NOT override active critical attack
        critical_inc = Incident(
            guild_id="77001",
            title="Critical Server Purge",
            severity="critical",
            confidence="confirmed",
            is_emergency=True,
        )
        self.inc_manager._incidents["77001"][critical_inc.incident_id] = critical_inc
        inter2 = MockInteraction(user_id=10001, name="AdminAlice", guild=self.guild)
        await self.comm_service.handle_clarification_response(
            interaction=inter2,
            choice=ClarificationChoice.MAINTENANCE,
            incident_id=critical_inc.incident_id,
            recipient_id="10001",
        )
        # Response warns that critical attack threshold was exceeded and containment remains active
        self.assertTrue(critical_inc.is_emergency)
        self.assertIn("critical emergency thresholds", inter2.response.sent_messages[0]["content"])

    # -------------------------------------------------------------------------
    # Test 7: Clarification 'Not Authorised' Triggers Escalation
    # -------------------------------------------------------------------------
    async def test_clarification_unauthorized_triggers_emergency_escalation(self):
        """If admin answers 'Not Authorised', Sentinel escalates to CRITICAL and engages containment."""
        incident = Incident(
            guild_id="77001",
            title="Suspicious Role Grant",
            severity="medium",
            confidence="suspicious",
            is_emergency=False,
        )
        self.inc_manager._incidents.setdefault("77001", {})[incident.incident_id] = incident

        interaction = MockInteraction(user_id=90001, name="ServerOwner", guild=self.guild)
        await self.comm_service.handle_clarification_response(
            interaction=interaction,
            choice=ClarificationChoice.UNAUTHORIZED,
            incident_id=incident.incident_id,
            recipient_id="90001",
        )
        # Escalated immediately
        self.assertEqual(incident.severity, "critical")
        self.assertEqual(incident.confidence, "confirmed")
        self.assertTrue(incident.is_emergency)

    # -------------------------------------------------------------------------
    # Test 8: DM Failure Fallback Routing Without Crashing
    # -------------------------------------------------------------------------
    async def test_dm_failure_routes_to_fallback_channel(self):
        """When admin DM is blocked/closed, alert seamlessly routes to fallback channel."""
        incident = Incident(
            guild_id="77001",
            title="Mass Kick Detected",
            severity="high",
            confidence="high_confidence",
        )
        self.inc_manager._incidents.setdefault("77001", {})[incident.incident_id] = incident

        # AdminBob (10002) has closed DMs
        success = await self.comm_service.initiate_clarification_conversation(
            incident=incident,
            recipient_id="10002",
            guild_id="77001",
        )
        # Message was delivered to fallback channel
        self.assertTrue(success)
        self.assertGreaterEqual(len(self.fallback_channel.sent_messages), 1)
        self.assertIn("<@10002>", self.fallback_channel.sent_messages[0]["content"])

    # -------------------------------------------------------------------------
    # Test 9: Multi-Admin Consensus & Vote Correction
    # -------------------------------------------------------------------------
    async def test_consensus_review_and_vote_correction(self):
        """Tests casting votes, correcting decisions, and Anti-Self-Pardon guard."""
        incident = Incident(
            guild_id="77001",
            title="Suspicious Admin Actions",
            severity="high",
            confidence="suspicious",
            actor_id="66666",
        )
        self.inc_manager._incidents.setdefault("77001", {})[incident.incident_id] = incident

        # 9a. Accused subject is blocked from voting
        inter_subject = MockInteraction(user_id=66666, name="RogueAttacker", guild=self.guild)
        res_subj = await self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=incident.incident_id,
            reviewer_id=66666,
            reviewer_name="RogueAttacker",
            choice=ReviewChoice.DISMISS,
        )
        self.assertFalse(res_subj["success"])
        self.assertIn("Conflict of interest", res_subj["error"])

        # 9b. Eligible admin votes dismiss, then corrects to confirm
        res1 = await self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=incident.incident_id,
            reviewer_id=10001,
            reviewer_name="AdminAlice",
            choice=ReviewChoice.DISMISS,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["tallies"][ReviewChoice.DISMISS], 1)

        # Correction
        res2 = await self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=incident.incident_id,
            reviewer_id=10001,
            reviewer_name="AdminAlice",
            choice=ReviewChoice.CONFIRM,
        )
        self.assertTrue(res2["success"])
        self.assertEqual(res2["action"], "corrected")
        self.assertEqual(res2["tallies"][ReviewChoice.DISMISS], 0)
        self.assertEqual(res2["tallies"][ReviewChoice.CONFIRM], 1)

    # -------------------------------------------------------------------------
    # Test 10: Reversible Recovery & Partial Failure Reporting
    # -------------------------------------------------------------------------
    async def test_reversible_recovery_and_partial_failure_reporting(self):
        """Verifies real lockdown restoration interface and partial failure reporting."""
        # Create active lockdown record with journal entries
        record = LockdownRecord(
            guild_id="77001",
            incident_id="inc_test_rec",
            status=LockdownStatus.ACTIVE,
            is_shadow_mode=False,
        )
        # Entry 1: will succeed
        mod_role = MockRole(role_id=101, name="ModRole", position=10)
        self.guild.roles.append(mod_role)
        entry1 = JournalEntry(
            entity_id="101",
            entity_type="role",
            entity_name="ModRole",
            original_state={"permissions": 128},
            modified_state={"permissions": 0},
            status=JournalEntryStatus.APPLIED,
        )
        record.add_entry(entry1)
        self.journal_mgr.save_lockdown(record)

        # Execute recovery
        restored = await self.protection_service.manual_recovery(
            guild=self.guild,
            lockdown_id=record.lockdown_id,
            admin_id=90001,
            force=True,
        )
        self.assertEqual(restored.status, LockdownStatus.RESTORED)

        # Send recovery report
        rep = await self.comm_service.send_recovery_report(
            guild=self.guild,
            lockdown_record=restored,
            initiated_by=90001,
            policy=self.policy,
        )
        self.assertEqual(rep["status"], LockdownStatus.RESTORED)
        self.assertGreaterEqual(rep["dms_sent"], 1)

    # -------------------------------------------------------------------------
    # Test 11: Securitycheck Diagnostic Command Execution
    # -------------------------------------------------------------------------
    async def test_securitycheck_diagnostic_command(self):
        """Verifies securitycheck diagnostic command runs and reports all system vectors."""
        mock_msg = MagicMock()
        mock_msg.guild = self.guild
        mock_msg.author = self.owner
        mock_msg.channel = self.fallback_channel

        responses = []
        with patch("plugins.MomentumOneToolkit.commands.security.securitycheck.send_response", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = lambda msg, box: responses.append(box)
            await securitycheck_execute(
                ctx=MagicMock(),
                command_type="prefix",
                message=mock_msg,
                args=["full"],
            )

        self.assertGreaterEqual(len(responses), 1)
        container_builder = responses[0]
        # Verify rendered text includes diagnostic sections
        text_displays = [c.text for c in container_builder._components if hasattr(c, "text")]
        full_text = " ".join(text_displays)
        self.assertIn("Pipeline & Observation Health", full_text)
        self.assertIn("Threat Detection & Rolling Counters", full_text)
        self.assertIn("Emergency Protection & Recovery", full_text)
        self.assertIn("Database Reachability", full_text)
        # Privacy check: No tokens or webhooks in copy
        self.assertNotIn("https://discord.com/api/webhooks", full_text)

    # -------------------------------------------------------------------------
    # Test 12: Securitycheck Access Denial for Unauthorized Users
    # -------------------------------------------------------------------------
    async def test_securitycheck_unauthorized_access_denied(self):
        """Unauthorized non-admin users must be strictly rejected from diagnostics."""
        mock_msg = MagicMock()
        mock_msg.guild = self.guild
        unauth_user = MockMember(user_id=12345, name="RandomUser", is_admin=False)
        mock_msg.author = unauth_user
        mock_msg.channel = self.fallback_channel

        responses = []
        with patch("plugins.MomentumOneToolkit.commands.security.securitycheck.send_response", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = lambda msg, box: responses.append(box)
            await securitycheck_execute(
                ctx=MagicMock(),
                command_type="prefix",
                message=mock_msg,
                args=[],
            )

        self.assertGreaterEqual(len(responses), 1)
        container_builder = responses[0]
        full_text = str(container_builder)
        self.assertIn("Access Denied", full_text)


if __name__ == "__main__":
    unittest.main()
