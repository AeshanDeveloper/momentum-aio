"""
Unit and integration tests for Sentinel™ Emergency Lockdown and Reversible Recovery (Agent 5 of 8).

Covers:
1. Rapid ban burst triggering immediate emergency containment without waiting for human consensus.
2. Repeated emergency signals deduplication & idempotency.
3. Partial lockdown handling: role hierarchy restrictions, missing bot permissions, and bot/recovery shielding.
4. Rate limit resilience and throttling.
5. Trusted admins with unavailable DMs falling back to secure logging channel.
6. False alarm reporting preserving all incident records and forensic evidence.
7. Post-lockdown independent admin modifications conflict detection (preserving admin intent).
8. Bot restart hydration for active/partial lockdowns.
9. Interrupted recovery procedure retrying safely.
10. Strict runtime authorization and quorum enforcement for interactive recovery buttons.
11. Security posture diagnostic auditing and setup checklist generation.
"""

import unittest
import asyncio
import time
from typing import Dict, Any, List, Optional

import discord
from discord import Permissions, PermissionOverwrite, Role, TextChannel, Member, Guild, User

from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    LockdownTargetType,
    get_default_response_policy,
)
from core.security.lockdown_journal import (
    JournalEntry,
    JournalEntryStatus,
    LockdownRecord,
    LockdownJournalManager,
)
from core.security.emergency_lockdown_manager import (
    EmergencyLockdownManager,
    DANGEROUS_PERMISSION_FLAGS,
)
from core.security.admin_notifier import (
    AdminNotifier,
    EmergencyRecoveryView,
    InteractiveActionID,
)
from core.security.protection_service import SecurityProtectionService
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
    ActionExecutionStatus,
    ReviewDecisionType,
)
from core.security.threat_assessment import AssessmentResult


class MockGuild:
    def __init__(self, guild_id: int = 12345, name: str = "Test Security Guild"):
        self.id = guild_id
        self.name = name
        self.roles: List[Role] = []
        self.channels: List[TextChannel] = []
        self.text_channels: List[TextChannel] = []
        self.me: Optional[Member] = None
        self.owner_id: int = 99999
        self.owner: Optional[Member] = None
        self.system_channel: Optional[TextChannel] = None
        self.public_updates_channel: Optional[TextChannel] = None

    def get_role(self, role_id: int) -> Optional[Role]:
        for r in self.roles:
            if r.id == role_id:
                return r
        return None

    def get_channel(self, channel_id: int) -> Optional[TextChannel]:
        for c in self.channels:
            if c.id == channel_id:
                return c
        return None

    @property
    def default_role(self) -> Role:
        for r in self.roles:
            if r.id == self.id or r.name == "@everyone":
                return r
        r = Role(id=self.id, name="@everyone", position=0, guild=self)
        self.roles.append(r)
        return r


class MockInteraction:
    def __init__(self, user: User, guild: Optional[Any] = None):
        self.user = user
        self.guild = guild
        self.response = MockInteractionResponse()
        self.followup = MockInteractionFollowup()


class MockInteractionResponse:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self._done = False

    async def send_message(self, content: str = "", embed: Any = None, ephemeral: bool = False, **kwargs):
        self._done = True
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})


class MockInteractionFollowup:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []

    async def send(self, content: str = "", embed: Any = None, ephemeral: bool = False, **kwargs):
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})


class TestEmergencyLockdown(unittest.TestCase):
    def setUp(self):
        from core.security.lockdown_journal import lockdown_journal_manager
        lockdown_journal_manager._lockdowns.clear()
        lockdown_journal_manager._guild_lockdowns.clear()

        from database.database import _save_mock_data
        _save_mock_data("security_lockdowns", [])

        self.journal = LockdownJournalManager()
        self.manager = EmergencyLockdownManager(journal_manager=self.journal)
        self.manager._lockdown_history.clear()
        self.notifier = AdminNotifier()
        self.service = SecurityProtectionService(
            lockdown_mgr=self.manager,
            notifier=self.notifier,
            journal_mgr=self.journal,
        )

        # Setup standard mock guild with hierarchy
        self.guild = MockGuild(12345, "Fortified Server")

        # Roles:
        # 0: @everyone (default)
        self.role_everyone = Role(id=12345, name="@everyone", position=0, guild=self.guild)
        self.role_everyone.permissions = Permissions(send_messages=True, read_messages=True)
        self.guild.roles.append(self.role_everyone)

        # 1: Member Role
        self.role_member = Role(id=101, name="Member", position=1, guild=self.guild)
        self.role_member.permissions = Permissions(send_messages=True)
        self.guild.roles.append(self.role_member)

        # 2: Preserved Recovery Role
        self.role_recovery = Role(id=102, name="Security Escrow", position=2, guild=self.guild)
        self.role_recovery.permissions = Permissions(administrator=True)
        self.guild.roles.append(self.role_recovery)

        # 3: Moderator Role (Compromised or targeted)
        self.role_mod = Role(id=103, name="Moderator", position=3, guild=self.guild)
        # Give moderator ban and kick permissions
        self.role_mod.permissions = Permissions(
            permissions=(1 << 2) | (1 << 1) | (1 << 4),  # ban, kick, manage_channels
            ban_members=True,
            kick_members=True,
            manage_channels=True,
        )
        self.guild.roles.append(self.role_mod)

        # 4: Sentinel Bot Role
        self.role_sentinel = Role(id=104, name="Sentinel Protection", position=4, guild=self.guild)
        self.role_sentinel.permissions = Permissions(administrator=True, manage_roles=True, manage_channels=True)
        self.guild.roles.append(self.role_sentinel)

        # 5: Senior Admin Role (Higher than bot in hierarchy)
        self.role_senior_admin = Role(id=105, name="Senior Admin", position=5, guild=self.guild)
        self.role_senior_admin.permissions = Permissions(administrator=True)
        self.guild.roles.append(self.role_senior_admin)

        # Bot Member setup
        self.bot_member = Member(id=999, name="SentinelBot", guild=self.guild)
        self.bot_member.roles = [self.role_sentinel]
        self.bot_member.top_role = self.role_sentinel
        self.bot_member.guild_permissions = Permissions(administrator=True, manage_roles=True, manage_channels=True)
        self.guild.me = self.bot_member

        # Channels:
        self.chan_general = TextChannel(id=501, name="general")
        self.chan_general.guild = self.guild
        self.guild.channels.append(self.chan_general)
        self.guild.text_channels.append(self.chan_general)

        self.chan_security = TextChannel(id=502, name="sentinel-security-audit")
        self.chan_security.guild = self.guild
        self.guild.channels.append(self.chan_security)
        self.guild.text_channels.append(self.chan_security)
        self.guild.system_channel = self.chan_security

    def test_rapid_ban_burst_triggers_immediate_lockdown(self):
        """1. Rapid ban burst threshold crossing initiates autonomous containment without waiting for human voting."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            response_level=ResponseLevel.LOCKDOWN,
            shadow_mode=False,
            auto_lockdown_enabled=True,
            rapid_ban_threshold_count=100,
            rapid_ban_threshold_window_seconds=60.0,
            preserved_recovery_role_ids=["102"],
            exempt_channel_ids=["502"],
        )

        # Verify threshold evaluation
        should_trigger = policy.should_trigger_emergency_lockdown(
            pattern_id="rapid_ban_burst",
            threat_score=85.0,
            count=120,
            window_seconds=45.0,
        )
        self.assertTrue(should_trigger)

        incident = Incident(
            guild_id="12345",
            title="Rapid Ban Attack Intercepted",
            severity="critical",
            confidence="high",
            is_emergency=True,
        )
        assessment = AssessmentResult(
            signal_id="sig_test_ban_1",
            threat_score=95.0,
            severity="critical",
            confidence="high",
            should_trigger_immediate_response=True,
            recommended_action=ProtectiveActionType.EMERGENCY_LOCKDOWN,
            is_shadow_mode=False,
        )

        # Run emergency lockdown
        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        self.assertIsNotNone(record)
        self.assertEqual(record.status, LockdownStatus.PARTIAL)  # Role 105 is higher than bot
        self.assertEqual(incident.status, IncidentStatus.CONTAINED)
        self.assertTrue(len(record.entries) > 0)

        # Moderator role (103) had ban_members and kick_members stripped
        mod_entry = next((e for e in record.entries if e.target_id == "103"), None)
        self.assertIsNotNone(mod_entry)
        self.assertIn(mod_entry.status, (JournalEntryStatus.APPLIED, JournalEntryStatus.VERIFIED))
        new_mod_perms = self.role_mod.permissions.value
        self.assertEqual(new_mod_perms & (1 << 2), 0)  # ban_members removed
        self.assertEqual(new_mod_perms & (1 << 1), 0)  # kick_members removed

        # General channel (501) had send_messages denied for @everyone
        chan_entry = next((e for e in record.entries if e.secondary_id == "501"), None)
        self.assertIsNotNone(chan_entry)
        self.assertIn(chan_entry.status, (JournalEntryStatus.APPLIED, JournalEntryStatus.VERIFIED))

        # Exempt channel (502) was not modified
        sec_entry = next((e for e in record.entries if e.secondary_id == "502"), None)
        self.assertIsNone(sec_entry)

    def test_repeated_signals_deduplication_and_idempotency(self):
        """2. Successive rapid signals for the same guild/incident return existing lockdown and do not duplicate mutations."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            response_level=ResponseLevel.LOCKDOWN,
            shadow_mode=False,
            auto_lockdown_enabled=True,
        )
        incident = Incident(guild_id="12345", title="Ban Burst", severity="critical")
        assessment = AssessmentResult(
            signal_id="sig_1",
            threat_score=90.0,
            should_trigger_immediate_response=True,
            is_shadow_mode=False,
        )

        record1 = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertIn(record1.status, (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL))

        # Second signal arrives
        record2 = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertEqual(record1.lockdown_id, record2.lockdown_id)
        self.assertTrue("duplicate_signal_suppressed" in record2.metadata)

    def test_partial_lockdown_hierarchy_and_shielding(self):
        """3. Higher roles and bot roles are skipped safely; Sentinel distinguishes PARTIAL from full lockdown."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            shadow_mode=False,
            auto_lockdown_enabled=True,
            preserved_recovery_role_ids=["102"],
        )
        incident = Incident(guild_id="12345", title="Multi Vector Attack")
        assessment = AssessmentResult(signal_id="sig_m", threat_score=80.0, should_trigger_immediate_response=True, is_shadow_mode=False)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        # Check senior admin role (105): Higher than bot (position 5 vs position 4)
        senior_entry = next((e for e in record.entries if e.target_id == "105"), None)
        self.assertIsNotNone(senior_entry)
        self.assertEqual(senior_entry.status, JournalEntryStatus.SKIPPED_HIERARCHY)
        self.assertIn("higher than or equal to", senior_entry.error)

        # Sentinel's own role (104) was NOT targeted or modified
        sentinel_entry = next((e for e in record.entries if e.target_id == "104"), None)
        self.assertIsNone(sentinel_entry)

        # Preserved recovery role (102) was explicitly shielded
        recovery_entry = next((e for e in record.entries if e.target_id == "102"), None)
        self.assertIsNotNone(recovery_entry)
        self.assertEqual(recovery_entry.status, JournalEntryStatus.SKIPPED_PRESERVED)

        # Lockdown record correctly classified as PARTIAL due to hierarchy limitation
        self.assertEqual(record.status, LockdownStatus.PARTIAL)
        self.assertTrue(record.summary["is_partial"])

    def test_rate_limit_resilience(self):
        """4. Multiple lockdowns triggered rapidly are throttled by lockdown_rate_limit_per_minute."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            lockdown_rate_limit_per_minute=2,
            shadow_mode=True,
            auto_lockdown_enabled=False,
        )

        # First 2 allowed
        self.assertTrue(self.manager._check_rate_limit("12345", 2))
        self.assertTrue(self.manager._check_rate_limit("12345", 2))
        # 3rd is throttled
        self.assertFalse(self.manager._check_rate_limit("12345", 2))

    def test_trusted_admin_dms_fallback_channel(self):
        """5. Closed recovery admin DMs trigger fallback notification to secure channel."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            recovery_owner_id="777",
            trusted_recovery_admin_ids=["888"],
            fallback_channel_id="502",
        )
        incident = Incident(guild_id="12345", title="Unauthorized Mass Deletion", recovery_code="REC-999")

        # Mock client where DM sending fails (e.g. DMs closed / 403 Forbidden)
        class MockFailingClient:
            def get_user(self, uid):
                class BrokenUser:
                    async def send(self, *args, **kwargs):
                        raise discord.Forbidden(message="Cannot send messages to this user")
                return BrokenUser()

        dispatch_result = asyncio.run(
            self.notifier.dispatch_emergency_alert(
                bot_client=MockFailingClient(),
                guild=self.guild,
                incident=incident,
                policy=policy,
            )
        )

        self.assertEqual(dispatch_result["dms_failed"], 2)
        self.assertEqual(dispatch_result["dms_sent"], 0)
        self.assertTrue(dispatch_result["fallback_channel_sent"])

    def test_false_alarm_reporting_preserves_evidence(self):
        """6. False alarm dismissal updates status and rolls back lockdown without deleting incident records."""
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=True, recovery_owner_id="777")
        incident = Incident(guild_id="12345", title="Suspicious Spike", is_emergency=True)
        incident.add_fact("10 members kicked in 2 seconds")
        incident.record_evidence(event_id="evt_123", event_type="guild_member_remove", summary="Member kick")

        view = EmergencyRecoveryView(incident=incident, policy=policy)
        admin_user = User(id=777, name="RecoveryOwner")
        interaction = MockInteraction(user=admin_user, guild=self.guild)

        asyncio.run(view.handle_false_alarm(interaction))

        self.assertEqual(incident.status, IncidentStatus.DISMISSED)
        # Verify evidence references are PERMANENTLY PRESERVED
        self.assertEqual(len(incident.evidence_references), 1)
        self.assertEqual(incident.evidence_references[0].event_id, "evt_123")
        # Decision history contains dismissal record
        dismissal = next((d for d in incident.decision_history if d.decision_type == ReviewDecisionType.DISMISS), None)
        self.assertIsNotNone(dismissal)
        self.assertEqual(dismissal.actor_id, "777")

    def test_post_lockdown_conflict_detection(self):
        """7. If an admin modifies a role post-lockdown, Sentinel preserves admin changes and marks CONFLICT_DETECTED."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            shadow_mode=False,
            auto_lockdown_enabled=True,
            recovery_owner_id="777",
        )
        incident = Incident(guild_id="12345", title="Attack", recovery_code="REC-XYZ")
        assessment = AssessmentResult(signal_id="sig_conf", threat_score=90.0, should_trigger_immediate_response=True, is_shadow_mode=False)

        # Execute lockdown
        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        mod_entry = next((e for e in record.entries if e.target_id == "103"), None)
        self.assertIsNotNone(mod_entry)
        self.assertIn(mod_entry.status, (JournalEntryStatus.APPLIED, JournalEntryStatus.VERIFIED))
        applied_val = mod_entry.applied_state["permissions_value"]

        # Simulate independent admin change post-lockdown
        # An admin manually granted an additional permission to role 103 (e.g. view_audit_log 1<<7)
        self.role_mod.permissions = Permissions(permissions=applied_val | (1 << 7))

        # Recovery is executed
        restored_record = asyncio.run(
            self.manager.restore_lockdown(
                guild=self.guild,
                lockdown_id=record.lockdown_id,
                admin_user_id="777",
                policy=policy,
                force=False,  # Respect human admin changes!
            )
        )

        # Verify entry status became CONFLICT_DETECTED and admin change was preserved
        updated_mod_entry = next((e for e in restored_record.entries if e.target_id == "103"), None)
        self.assertEqual(updated_mod_entry.status, JournalEntryStatus.CONFLICT_DETECTED)
        self.assertEqual(self.role_mod.permissions.value, applied_val | (1 << 7))

    def test_bot_restart_hydration(self):
        """8. Active and partial lockdowns are successfully hydrated from storage across restarts."""
        record = LockdownRecord(
            guild_id="88881",
            incident_id="inc_hydrate",
            status=LockdownStatus.PARTIAL,
            is_shadow_mode=False,
            trigger_pattern="Hydration Test",
            trigger_score=88.0,
        )
        self.journal.save_lockdown(record)

        hydrated = self.service.hydrate_active_lockdowns()
        self.assertTrue(any(l.lockdown_id == record.lockdown_id for l in hydrated))

    def test_interrupted_recovery_retry(self):
        """9. Interrupted recovery procedure can be retried safely without losing state."""
        retry_guild = MockGuild(88882, "Retry Guild")
        # Setup roles on retry_guild
        r_everyone = Role(id=88882, name="@everyone", position=0, guild=retry_guild)
        retry_guild.roles.append(r_everyone)
        r_mod = Role(id=103, name="Moderator", position=3, guild=retry_guild)
        r_mod.permissions = Permissions((1 << 2) | (1 << 1) | (1 << 4), ban_members=True, kick_members=True)
        retry_guild.roles.append(r_mod)
        r_bot = Role(id=104, name="Sentinel", position=4, guild=retry_guild)
        r_bot.permissions = Permissions(administrator=True, manage_roles=True)
        retry_guild.roles.append(r_bot)
        retry_bot_member = Member(id=999, name="SentinelBot", guild=retry_guild)
        retry_bot_member.roles = [r_bot]
        retry_bot_member.top_role = r_bot
        retry_bot_member.guild_permissions = Permissions(administrator=True)
        retry_guild.me = retry_bot_member

        policy = SecurityResponsePolicy(guild_id="88882", shadow_mode=False, auto_lockdown_enabled=True)
        incident = Incident(guild_id="88882", title="Incident for retry")
        assessment = AssessmentResult(signal_id="sig_retry", threat_score=85.0, should_trigger_immediate_response=True, is_shadow_mode=False)

        record = asyncio.run(self.manager.execute_emergency_lockdown(retry_guild, incident, assessment, policy))

        # Simulate failure on role 103 during first recovery attempt
        original_edit = r_mod.edit
        async def failing_edit(*args, **kwargs):
            raise discord.HTTPException(message="Discord 500 Internal Server Error")

        r_mod.edit = failing_edit

        # First restore attempt fails on role 103
        attempt1 = asyncio.run(
            self.manager.restore_lockdown(retry_guild, record.lockdown_id, admin_user_id="777", policy=policy)
        )
        mod_entry = next((e for e in attempt1.entries if e.target_id == "103"), None)
        self.assertEqual(mod_entry.status, JournalEntryStatus.FAILED_RESTORE)

        # Discord recovers, restore method restored
        r_mod.edit = original_edit

        # Second recovery retry resumes and restores successfully
        attempt2 = asyncio.run(
            self.manager.restore_lockdown(retry_guild, record.lockdown_id, admin_user_id="777", policy=policy)
        )
        updated_mod_entry = next((e for e in attempt2.entries if e.target_id == "103"), None)
        self.assertEqual(updated_mod_entry.status, JournalEntryStatus.RESTORED)

    def test_runtime_authorization_and_quorum(self):
        """10. Unauthorized users cannot trigger buttons; non-owner admins require quorum."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            recovery_owner_id="1000",
            trusted_recovery_admin_ids=["2001", "2002"],
            recovery_quorum=2,
            shadow_mode=True,
        )
        incident = Incident(guild_id="12345", title="Quorum Test")
        record = LockdownRecord(guild_id="12345", incident_id=incident.incident_id, status=LockdownStatus.ACTIVE)
        self.journal.save_lockdown(record)

        view = EmergencyRecoveryView(incident=incident, lockdown_record=record, policy=policy)

        # A) Unauthorized user attempts action
        random_user = User(id=9999, name="Attacker")
        interaction_unauth = MockInteraction(user=random_user, guild=self.guild)
        asyncio.run(view.handle_begin_recovery(interaction_unauth))
        self.assertIn("Unauthorized", interaction_unauth.response.messages[0]["content"])
        self.assertEqual(record.status, LockdownStatus.ACTIVE)

        # B) Trusted Admin 1 votes: quorum (2) not yet met
        admin1 = User(id=2001, name="TrustedAdmin1")
        interaction_admin1 = MockInteraction(user=admin1, guild=self.guild)
        asyncio.run(view.handle_begin_recovery(interaction_admin1))
        self.assertIn("1/2 required approvals", interaction_admin1.response.messages[0]["content"])
        self.assertEqual(record.status, LockdownStatus.ACTIVE)

        # C) Trusted Admin 2 votes: quorum met (2/2) -> recovery executes!
        admin2 = User(id=2002, name="TrustedAdmin2")
        interaction_admin2 = MockInteraction(user=admin2, guild=self.guild)
        asyncio.run(view.handle_begin_recovery(interaction_admin2))
        self.assertIn("Server Permissions Restored", interaction_admin2.response.messages[0]["content"])

    def test_security_posture_diagnostic_audit(self):
        """11. Security posture diagnostic checklist evaluates role hierarchy, permissions, and weaknesses."""
        policy = SecurityResponsePolicy(
            guild_id="12345",
            recovery_owner_id="1000",
            trusted_recovery_admin_ids=["2001"],
            shadow_mode=True,
        )

        audit = self.manager.audit_guild_security_posture(self.guild, policy)

        self.assertIn("findings", audit)
        self.assertIn("checklist", audit)
        self.assertEqual(audit["guild_id"], "12345")

        # Senior admin role was positioned higher than bot -> triggers WARNING
        hierarchy_check = next((f for f in audit["findings"] if f["check"] == "Role Hierarchy Containment Power"), None)
        self.assertIsNotNone(hierarchy_check)
        self.assertEqual(hierarchy_check["status"], "WARNING")
        self.assertIn("Senior Admin", hierarchy_check["detail"])

        # Bot has manage_roles and manage_channels verified -> PASS
        manage_roles_check = next((f for f in audit["findings"] if f["check"] == "Bot Permission: manage_roles"), None)
        self.assertTrue(manage_roles_check["passed"])

    def test_channel_permission_lockdown_without_name_error(self):
        """12. Channel permissions during emergency lockdown set correctly without name error."""
        guild = MockGuild(guild_id=54321, name="Channel Test Guild")
        bot_member = Member(id=999, name="SentinelBot", guild=guild)
        bot_member.guild_permissions = Permissions(administrator=True, manage_channels=True, manage_roles=True)
        guild.me = bot_member

        cat = discord.CategoryChannel(id=1, name="Text channels")
        cat.guild = guild
        tc = discord.TextChannel(id=2, name="general")
        tc.guild = guild
        vc = discord.VoiceChannel(id=3, name="Voice channels")
        vc.guild = guild
        guild.channels.extend([cat, tc, vc])

        policy = SecurityResponsePolicy(
            guild_id="54321",
            recovery_owner_id="1000",
            shadow_mode=False,
            auto_lockdown_enabled=True,
            channel_deny_permissions=["send_messages", "view_channel", "connect"],
        )

        incident = Incident(
            guild_id="54321",
            title="Channel Test Incident",
            severity="critical",
            confidence="high",
            is_emergency=True,
        )
        assessment = AssessmentResult(
            signal_id="sig_test_chan",
            threat_score=90.0,
            severity="critical",
            confidence="high",
            should_trigger_immediate_response=True,
            recommended_action=ProtectiveActionType.EMERGENCY_LOCKDOWN,
            is_shadow_mode=False,
        )

        record = asyncio.run(
            self.manager.execute_emergency_lockdown(
                guild=guild,
                incident=incident,
                assessment=assessment,
                policy=policy,
            )
        )

        self.assertIsNotNone(record)
        # Verify default role overwrite was applied on all channels without NameError
        chan_entries = [e for e in record.entries if e.target_type == "channel_overwrite"]
        self.assertGreaterEqual(len(chan_entries), 3)
        for e in chan_entries:
            self.assertEqual(e.status, JournalEntryStatus.VERIFIED)
            self.assertIsNone(e.error)

    # -------------------------------------------------------------------------
    # REQUIRED REGRESSION SUITE (TESTS A - L)
    # Emergency Lockdown Permission Preservation, Snapshots & Reversible Recovery
    # -------------------------------------------------------------------------

    def test_a_private_owner_channel_visibility_preserved_and_restored(self):
        """Test A: Private owner channel visibility preserved during lockdown and restored."""
        owner_chan = TextChannel(id=701, name="owner-private", guild=self.guild)
        owner_chan.overwrites = {
            self.role_everyone: PermissionOverwrite(view_channel=False, send_messages=False),
        }
        self.guild.channels.append(owner_chan)
        self.guild.text_channels.append(owner_chan)

        self.assertFalse(owner_chan.permissions_for(self.role_everyone).view_channel)

        incident = Incident(guild_id="12345", title="Owner Channel Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_a", threat_score=95.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertIn(record.status, (LockdownStatus.ACTIVE, LockdownStatus.VERIFIED, LockdownStatus.PARTIAL))

        # CRITICAL ASSERTION: Channel visibility for @everyone MUST REMAIN False
        self.assertFalse(owner_chan.permissions_for(self.role_everyone).view_channel)
        entry = next((e for e in record.entries if e.secondary_id == "701"), None)
        self.assertIsNotNone(entry)
        self.assertTrue(entry.original_visibility.get("is_private"))
        self.assertFalse(entry.applied_state.get("send_messages", True))

        # Recovery
        rec = asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertIn(rec.status, (LockdownStatus.RESTORED, LockdownStatus.PARTIAL))
        self.assertFalse(owner_chan.permissions_for(self.role_everyone).view_channel)

    def test_b_private_logging_channel_never_becomes_visible(self):
        """Test B: Private logging channel never becomes visible to @everyone."""
        log_chan = TextChannel(id=702, name="security-audit-logs", guild=self.guild)
        log_chan.overwrites = {
            self.role_everyone: PermissionOverwrite(view_channel=False, read_messages=False, send_messages=False),
            self.guild.me: PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True),
        }
        self.guild.channels.append(log_chan)

        self.assertFalse(log_chan.permissions_for(self.role_everyone).view_channel)

        incident = Incident(guild_id="12345", title="Audit Logging Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_b", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertFalse(log_chan.permissions_for(self.role_everyone).view_channel)

        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertFalse(log_chan.permissions_for(self.role_everyone).view_channel)

    def test_c_private_staff_channel_visibility_preserved(self):
        """Test C: Private staff channel visibility preserved throughout containment."""
        staff_chan = TextChannel(id=703, name="staff-confidential", guild=self.guild)
        staff_chan.overwrites = {
            self.role_everyone: PermissionOverwrite(view_channel=False),
            self.role_member: PermissionOverwrite(view_channel=True, send_messages=True),
        }
        self.guild.channels.append(staff_chan)

        self.assertFalse(staff_chan.permissions_for(self.role_everyone).view_channel)

        incident = Incident(guild_id="12345", title="Staff Privacy Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_c", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertFalse(staff_chan.permissions_for(self.role_everyone).view_channel)

        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertFalse(staff_chan.permissions_for(self.role_everyone).view_channel)

    def test_d_category_and_child_channel_inheritance_preserved(self):
        """Test D: Category and child channel permission inheritance preserved."""
        mgmt_category = discord.CategoryChannel(id=800, name="Management Category", guild=self.guild)
        mgmt_category.overwrites = {
            self.role_everyone: PermissionOverwrite(view_channel=False, send_messages=False),
        }
        child_chan = TextChannel(id=801, name="executive-briefs", guild=self.guild)
        child_chan.category = mgmt_category
        child_chan.overwrites = {}  # No explicit overwrite: inherits view_channel=False from category

        self.guild.channels.extend([mgmt_category, child_chan])

        # Child channel is private via category inheritance
        self.assertFalse(child_chan.permissions_for(self.role_everyone).view_channel)

        incident = Incident(guild_id="12345", title="Category Inheritance Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_d", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        # Post-lockdown: child channel MUST NOT have become visible
        self.assertFalse(child_chan.permissions_for(self.role_everyone).view_channel)
        entry = next((e for e in record.entries if e.secondary_id == "801"), None)
        self.assertIsNotNone(entry)
        self.assertFalse(entry.had_overwrite)
        self.assertEqual(entry.parent_category_id, "800")

        # Recovery restores category inheritance by removing the temporary overwrite
        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertNotIn(self.role_everyone, child_chan.overwrites)
        self.assertFalse(child_chan.permissions_for(self.role_everyone).view_channel)

    def test_e_existing_overwrite_unrelated_bits_preserved_and_restored(self):
        """Test E: Existing overwrite unrelated permission bits preserved and restored."""
        chan = TextChannel(id=704, name="announcements", guild=self.guild)
        chan.overwrites = {
            self.role_everyone: PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=False,
                attach_files=False,
                read_message_history=True,
            ),
        }
        self.guild.channels.append(chan)

        incident = Incident(guild_id="12345", title="Bitfield Preservation Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_e", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        # During lockdown, send_messages is restricted, but unrelated embed_links=False is preserved!
        ow_during = chan.overwrites[self.role_everyone]
        self.assertFalse(ow_during.send_messages)
        self.assertFalse(ow_during.embed_links)
        self.assertTrue(ow_during.read_message_history)

        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))

        # Post-recovery: send_messages is restored to True, and embed_links is still False
        ow_after = chan.overwrites[self.role_everyone]
        self.assertTrue(ow_after.send_messages)
        self.assertFalse(ow_after.embed_links)
        self.assertTrue(ow_after.read_message_history)

    def test_f_originally_absent_overwrite_removed_on_recovery(self):
        """Test F: Originally absent overwrite completely removed on recovery."""
        chan = TextChannel(id=705, name="lounge", guild=self.guild)
        chan.overwrites = {}  # Had no overwrite before lockdown
        self.guild.channels.append(chan)

        incident = Incident(guild_id="12345", title="Absent Overwrite Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_f", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertIn(self.role_everyone, chan.overwrites)

        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        # Must be removed completely
        self.assertNotIn(self.role_everyone, chan.overwrites)

    def test_g_snapshot_persistence_failure_aborts_lockdown(self):
        """Test G: MongoDB snapshot persistence failure aborts lockdown before any mutations."""
        class FailingJournal(LockdownJournalManager):
            async def save_lockdown_durable(self, record: LockdownRecord) -> bool:
                return False  # Simulate DB failure

        failing_mgr = EmergencyLockdownManager(journal_manager=FailingJournal())

        chan = TextChannel(id=706, name="critical-data", guild=self.guild)
        chan.overwrites = {
            self.role_everyone: PermissionOverwrite(send_messages=True),
        }
        self.guild.channels.append(chan)

        incident = Incident(guild_id="12345", title="DB Fail Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_g", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(failing_mgr.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        self.assertEqual(record.status, LockdownStatus.FAILED)
        # Verify no mutations occurred!
        self.assertTrue(chan.overwrites[self.role_everyone].send_messages)

    def test_h_partial_lockdown_failure_retains_snapshot_and_records_status(self):
        """Test H: Partial lockdown failure retains snapshot and records status."""
        incident = Incident(guild_id="12345", title="Partial Lockdown Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_h", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        # Senior Admin was skipped due to hierarchy, so status is PARTIAL
        self.assertEqual(record.status, LockdownStatus.PARTIAL)
        self.assertTrue(record.summary.get("is_partial"))

        # Snapshot is retained and contains SKIPPED_HIERARCHY entry
        skipped_entries = [e for e in record.entries if e.status == JournalEntryStatus.SKIPPED_HIERARCHY]
        self.assertGreater(len(skipped_entries), 0)

    def test_i_partial_recovery_failure_leaves_unrestored_recoverable(self):
        """Test I: Partial recovery failure leaves unrestored entries recoverable on subsequent attempt."""
        chan1 = TextChannel(id=707, name="chan-1", guild=self.guild)
        chan2 = TextChannel(id=708, name="chan-2", guild=self.guild)
        chan1.overwrites = {self.role_everyone: PermissionOverwrite(send_messages=True)}
        chan2.overwrites = {self.role_everyone: PermissionOverwrite(send_messages=True)}
        self.guild.channels.extend([chan1, chan2])

        incident = Incident(guild_id="12345", title="Recovery Retry Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_i", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        # Simulate error on chan2 during first recovery attempt
        original_set_perms = chan2.set_permissions
        chan2.set_permissions = lambda *args, **kwargs: (_ for _ in ()).throw(discord.HTTPException(None, "500 Internal Error"))

        rec1 = asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertEqual(rec1.status, LockdownStatus.PARTIAL)
        entry2 = next(e for e in rec1.entries if e.secondary_id == "708")
        self.assertEqual(entry2.status, JournalEntryStatus.FAILED_RESTORE)

        # Restore normal operation and retry recovery
        chan2.set_permissions = original_set_perms
        rec2 = asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertEqual(rec2.status, LockdownStatus.RESTORED)
        self.assertEqual(entry2.status, JournalEntryStatus.RESTORED)

    def test_j_unrelated_administrator_changes_preserved_on_recovery(self):
        """Test J: Unrelated administrator changes preserved on recovery."""
        chan = TextChannel(id=709, name="support", guild=self.guild)
        chan.overwrites = {self.role_everyone: PermissionOverwrite(view_channel=True, send_messages=True)}
        self.guild.channels.append(chan)

        incident = Incident(guild_id="12345", title="Admin Edit Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_j", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        self.assertFalse(chan.overwrites[self.role_everyone].send_messages)

        # Admin independently enables attach_files during lockdown
        chan.overwrites[self.role_everyone].attach_files = True

        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000", force=False))

        # Sentinel restores send_messages=True, but PRESERVES the admin's attach_files=True!
        self.assertTrue(chan.overwrites[self.role_everyone].send_messages)
        self.assertTrue(chan.overwrites[self.role_everyone].attach_files)

    def test_k_restart_recovery_uses_persisted_snapshot(self):
        """Test K: Restart recovery uses persisted MongoDB snapshot across process reboot."""
        chan = TextChannel(id=710, name="general-chat", guild=self.guild)
        chan.overwrites = {self.role_everyone: PermissionOverwrite(send_messages=True)}
        self.guild.channels.append(chan)

        incident = Incident(guild_id="12345", title="Restart Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_k", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))
        lockdown_id = record.lockdown_id

        # Simulate complete bot restart by creating a new journal and manager with cleared in-memory state
        fresh_journal = LockdownJournalManager()
        fresh_journal._lockdowns.clear()
        fresh_journal._guild_lockdowns.clear()
        fresh_manager = EmergencyLockdownManager(journal_manager=fresh_journal)

        # Verify manager hydrates from database store and successfully restores
        rec = asyncio.run(fresh_manager.restore_lockdown(self.guild, lockdown_id, admin_user_id="1000"))
        self.assertEqual(rec.status, LockdownStatus.RESTORED)
        self.assertTrue(chan.overwrites[self.role_everyone].send_messages)

    def test_l_channel_type_compatibility_handles_categories_voice_threads(self):
        """Test L: Channel type compatibility handles categories, text, voice, and threads."""
        cat = discord.CategoryChannel(id=901, name="Community", guild=self.guild)
        tc = discord.TextChannel(id=902, name="general", guild=self.guild)
        vc = discord.VoiceChannel(id=903, name="lounge-voice", guild=self.guild)
        th = discord.Thread(id=904, name="discussion-thread", guild=self.guild)

        cat.overwrites = {self.role_everyone: PermissionOverwrite(send_messages=True)}
        tc.overwrites = {self.role_everyone: PermissionOverwrite(send_messages=True)}
        vc.overwrites = {self.role_everyone: PermissionOverwrite(connect=True, speak=True)}
        th.overwrites = {self.role_everyone: PermissionOverwrite(send_messages=True)}

        self.guild.channels.extend([cat, tc, vc, th])

        incident = Incident(guild_id="12345", title="Multi Type Test", severity="critical", is_emergency=True)
        assessment = AssessmentResult(signal_id="sig_l", threat_score=90.0, severity="critical", confidence="high", should_trigger_immediate_response=True)
        policy = SecurityResponsePolicy(guild_id="12345", shadow_mode=False, auto_lockdown_enabled=True)

        record = asyncio.run(self.manager.execute_emergency_lockdown(self.guild, incident, assessment, policy))

        # Check VoiceChannel has connect and speak denied
        self.assertFalse(vc.overwrites[self.role_everyone].connect)
        self.assertFalse(vc.overwrites[self.role_everyone].speak)

        # Check TextChannel and Thread have write permissions denied
        self.assertFalse(tc.overwrites[self.role_everyone].send_messages)
        self.assertFalse(th.overwrites[self.role_everyone].send_messages)

        # Recovery
        asyncio.run(self.manager.restore_lockdown(self.guild, record.lockdown_id, admin_user_id="1000"))
        self.assertTrue(vc.overwrites[self.role_everyone].connect)
        self.assertTrue(vc.overwrites[self.role_everyone].speak)
        self.assertTrue(tc.overwrites[self.role_everyone].send_messages)


if __name__ == "__main__":
    unittest.main()

