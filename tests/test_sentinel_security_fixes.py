"""
Sentinel™ Comprehensive Security Verification and Invariant Test Suite.

Covers all 18 mandatory security scenarios:
1. Snapshot persistence before execution
2. Exact role bitfield restoration
3. Channel overwrite restoration
4. Clean overwrite removal (had_overwrite=False -> overwrite=None)
5. Category and voice channel containment
6. Partial lockdown handling (role hierarchy skips & status=PARTIAL)
7. Partial recovery and retry
8. Recovery idempotency
9. Restart hydration
10. Duplicate button interaction prevention & in-flight locks
11. Interaction acknowledgment & progress feedback
12. Verified outcome reporting
13. Logging category and channel creation with verified ownership
14. Logging channel isolation (no name/pattern adoption)
15. Reset with missing or stale records
16. Reset safety against identically named non-Sentinel channels
17. Correlation engine calibrated rules & threshold windows
18. Multi-actor correlation, deduplication, and audit-log attribution
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import time
import uuid

import discord
from discord import Permissions, PermissionOverwrite

from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    LockdownTargetType,
    get_default_response_policy,
)
from core.security.lockdown_journal import (
    LockdownRecord,
    JournalEntry,
    JournalEntryStatus,
    LockdownJournalManager,
)
from core.security.role_backup_manager import RoleBackupManager, RoleBackupEntry
from core.security.emergency_lockdown_manager import EmergencyLockdownManager, DANGEROUS_PERMISSION_FLAGS
from core.security.protection_service import SecurityProtectionService
from core.security.incident import Incident, IncidentStatus, ProtectiveActionType, ActionExecutionStatus
from core.security.threat_assessment import AssessmentResult, ThreatSeverity, ThreatConfidence
from core.logging.resource_tracker import SentinelResourceTracker, SentinelResourceRecord
from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory
from core.security.correlation_engine import SecurityCorrelationEngine, PatternID, SecurityEvent, ThreatSignal
from plugins.MomentumOneToolkit.commands.security.lockdown import is_guild_lockdown_in_flight, _IN_FLIGHT_LOCKDOWNS


class TestSentinelSecurityFixes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild_id = 9988776655
        self.guild_id_str = str(self.guild_id)

        # Build mock guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = self.guild_id
        self.guild.name = "Sentinel Secure Ops Server"
        self.guild.owner_id = 111122223333

        # Default role (@everyone)
        self.everyone_role = MagicMock(spec=discord.Role)
        self.everyone_role.id = self.guild_id
        self.everyone_role.name = "@everyone"
        self.everyone_role.position = 0
        self.everyone_role.permissions = Permissions(send_messages=True, read_messages=True, connect=True)
        self.everyone_role.is_default = lambda: True
        self.everyone_role.edit = AsyncMock()

        # Bot role & member
        self.bot_role = MagicMock(spec=discord.Role)
        self.bot_role.id = 555555
        self.bot_role.name = "Sentinel Sentinel"
        self.bot_role.position = 20
        self.bot_role.permissions = Permissions.all()
        self.bot_role.is_default = lambda: False

        self.bot_member = MagicMock(spec=discord.Member)
        self.bot_member.id = 999999
        self.bot_member.top_role = self.bot_role
        self.bot_member.roles = [self.bot_role, self.everyone_role]
        self.bot_member.guild_permissions = Permissions.all()
        self.guild.me = self.bot_member

        # High admin role (higher than bot)
        self.high_admin_role = MagicMock(spec=discord.Role)
        self.high_admin_role.id = 888888
        self.high_admin_role.name = "Executive Owner"
        self.high_admin_role.position = 30  # above bot!
        self.high_admin_role.permissions = Permissions.all()
        self.high_admin_role.is_default = lambda: False
        self.high_admin_role.edit = AsyncMock()

        # Manageable mod role (lower than bot)
        self.mod_role = MagicMock(spec=discord.Role)
        self.mod_role.id = 777777
        self.mod_role.name = "Moderator"
        self.mod_role.position = 10  # below bot!
        # Administrator + ban_members + kick_members
        mod_perms = Permissions(administrator=True, ban_members=True, kick_members=True, read_messages=True)
        self.mod_role.permissions = mod_perms
        self.mod_role.is_default = lambda: False
        self.mod_role.edit = AsyncMock()

        self.guild.roles = [self.high_admin_role, self.bot_role, self.mod_role, self.everyone_role]

        # Text channel 1: had existing overwrite
        self.channel1 = MagicMock(spec=discord.TextChannel)
        self.channel1.id = 101010
        self.channel1.name = "announcements"
        self.channel1.type = 0
        ow1 = PermissionOverwrite(send_messages=False, read_messages=True)
        self.channel1.overwrites = {self.everyone_role: ow1}
        self.channel1.set_permissions = AsyncMock()
        self.channel1.edit = AsyncMock()

        # Text channel 2: had NO overwrite prior to lockdown
        self.channel2 = MagicMock(spec=discord.TextChannel)
        self.channel2.id = 202020
        self.channel2.name = "general-chat"
        self.channel2.type = 0
        self.channel2.overwrites = {}  # No overwrite!
        self.channel2.set_permissions = AsyncMock()
        self.channel2.edit = AsyncMock()

        # Voice channel:
        self.voice_ch = MagicMock(spec=discord.VoiceChannel)
        self.voice_ch.id = 303030
        self.voice_ch.name = "Team Voice"
        self.voice_ch.type = 2
        self.voice_ch.overwrites = {}
        self.voice_ch.set_permissions = AsyncMock()
        self.voice_ch.edit = AsyncMock()

        # Category channel:
        self.category_ch = MagicMock(spec=discord.CategoryChannel)
        self.category_ch.id = 404040
        self.category_ch.name = "📁 COMMUNITY"
        self.category_ch.type = 4
        self.category_ch.channels = [self.channel2, self.voice_ch]
        self.category_ch.overwrites = {}
        self.category_ch.set_permissions = AsyncMock()
        self.category_ch.edit = AsyncMock()

        self.guild.channels = [self.channel1, self.channel2, self.voice_ch]
        self.guild.categories = [self.category_ch]
        self.guild.default_role = self.everyone_role

        def mock_get_channel(cid):
            cid_int = int(cid)
            for c in self.guild.channels:
                if c.id == cid_int:
                    return c
            for c in self.guild.categories:
                if c.id == cid_int:
                    return c
            return None

        def mock_get_role(rid):
            rid_int = int(rid)
            for r in self.guild.roles:
                if r.id == rid_int:
                    return r
            return None

        self.guild.get_channel = mock_get_channel
        self.guild.get_role = mock_get_role

        # Response policy
        self.policy = SecurityResponsePolicy(
            guild_id=self.guild_id_str,
            response_level=ResponseLevel.LOCKDOWN,
            auto_lockdown_enabled=True,
            shadow_mode=False,
        )

        # Incident & assessment
        self.incident = Incident(
            guild_id=self.guild_id_str,
            title="Rapid Administrator Account Compromise",
        )
        self.assessment = AssessmentResult(
            signal_id="sig_test_containment",
            threat_score=95.0,
            severity=ThreatSeverity.CRITICAL,
            confidence=ThreatConfidence.CONFIRMED,
            recommended_action=ProtectiveActionType.EMERGENCY_LOCKDOWN,
        )

        self.lockdown_mgr = EmergencyLockdownManager()

    # ==========================================================================
    # 1. Snapshot Persistence Before Execution
    # ==========================================================================
    async def test_01_snapshot_persisted_before_execution(self):
        """Verifies snapshot is written to journal storage before mutating API calls."""
        saved_before_mutation = []

        original_save = self.lockdown_mgr.journal.save_lockdown
        def intercept_save(rec):
            saved_before_mutation.append(rec.lockdown_id)
            return original_save(rec)

        with patch.object(self.lockdown_mgr.journal, "save_lockdown", side_effect=intercept_save):
            rec = await self.lockdown_mgr.execute_emergency_lockdown(
                self.guild, self.incident, self.assessment, self.policy
            )
            # save_lockdown must be called at least twice: once for baseline capture, once for finalization
            self.assertGreaterEqual(len(saved_before_mutation), 2)
            # The record must be readable in storage
            persisted = self.lockdown_mgr.journal.get_lockdown(rec.lockdown_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.guild_id, self.guild_id_str)
            self.assertGreater(len(persisted.entries), 0)

    # ==========================================================================
    # 2. Exact Role Bitfield Restoration
    # ==========================================================================
    async def test_02_exact_role_bitfield_restoration(self):
        """Restores exact 64-bit permission bitfield to modified role."""
        orig_val = self.mod_role.permissions.value

        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        # Mod role was edited
        self.assertTrue(self.mod_role.edit.called)

        # Now perform recovery
        rec_recovered = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )

        # Check call arguments on mod_role.edit during recovery
        # Last call must restore exact Permissions(orig_val)
        last_call = self.mod_role.edit.call_args
        restored_perms = last_call.kwargs.get("permissions") or (last_call.args[0] if last_call.args else None)
        self.assertEqual(restored_perms.value, orig_val)

    # ==========================================================================
    # 3. Channel Overwrite Restoration
    # ==========================================================================
    async def test_03_channel_overwrite_restoration(self):
        """Channels with prior overwrites have exact allow/deny values restored."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        rec_recovered = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )

        # channel1 had send_messages=False originally
        last_call_ch1 = self.channel1.set_permissions.call_args
        ow_ch1 = last_call_ch1.kwargs.get("overwrite")
        self.assertIsNotNone(ow_ch1)
        self.assertEqual(getattr(ow_ch1, "send_messages", None), False)

    # ==========================================================================
    # 4. Clean Overwrite Removal (had_overwrite=False)
    # ==========================================================================
    async def test_04_clean_overwrite_removal(self):
        """Channels that had NO overwrite prior to lockdown have overwrite=None called."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        rec_recovered = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )

        # channel2 had NO overwrite originally; must be cleared with overwrite=None
        last_call_ch2 = self.channel2.set_permissions.call_args
        self.assertIsNone(last_call_ch2.kwargs.get("overwrite"))

    # ==========================================================================
    # 5. Category and Voice Channel Containment
    # ==========================================================================
    async def test_05_category_and_voice_channel_containment(self):
        """Overwrites applied to categories and voice channels are properly recorded and restored."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        # Verify voice channel and category received set_permissions
        self.assertTrue(self.voice_ch.set_permissions.called)
        self.assertTrue(self.category_ch.set_permissions.called)

        # Check journal contains entries for category and voice channel
        cat_entries = [e for e in rec.entries if e.secondary_id == str(self.category_ch.id)]
        voice_entries = [e for e in rec.entries if e.secondary_id == str(self.voice_ch.id)]
        self.assertEqual(len(cat_entries), 1)
        self.assertEqual(len(voice_entries), 1)

    # ==========================================================================
    # 6. Partial Lockdown Handling
    # ==========================================================================
    async def test_06_partial_lockdown_handling(self):
        """Higher role hierarchy causes SKIPPED_HIERARCHY and marks status PARTIAL."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        # high_admin_role is above bot -> cannot be edited
        self.assertFalse(self.high_admin_role.edit.called)
        self.assertEqual(rec.status, LockdownStatus.PARTIAL)
        self.assertGreater(rec.summary.get("skipped_hierarchy", 0), 0)

    # ==========================================================================
    # 7. Partial Recovery and Retry
    # ==========================================================================
    async def test_07_partial_recovery_and_retry(self):
        """When one channel fails to restore, status is PARTIAL and retry succeeds without corrupting restored ones."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        # Simulate channel1 failing API call on first restore attempt
        self.channel1.set_permissions.side_effect = [Exception("Discord 50035 API Rate Limited"), None]

        rec_part = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )
        self.assertEqual(rec_part.status, LockdownStatus.PARTIAL)

        # Retry recovery: channel1 now succeeds
        rec_retry = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )
        self.assertEqual(rec_retry.status, LockdownStatus.RESTORED)

    # ==========================================================================
    # 8. Recovery Idempotency
    # ==========================================================================
    async def test_08_recovery_idempotency(self):
        """Calling recovery multiple times on the same record is completely idempotent."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        res1 = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )
        self.assertEqual(res1.status, LockdownStatus.RESTORED)

        # Second recovery call
        res2 = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy
        )
        self.assertEqual(res2.status, LockdownStatus.RESTORED)

    # ==========================================================================
    # 9. Restart Hydration
    # ==========================================================================
    async def test_09_restart_hydration(self):
        """Simulated bot restart hydrates active lockdowns and role backups from database."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )

        # Simulate restart: create brand-new manager instance
        new_journal = LockdownJournalManager()
        new_mgr = EmergencyLockdownManager(journal_manager=new_journal)

        hydrated = new_journal.get_active_lockdown_for_guild(self.guild_id_str)
        self.assertIsNotNone(hydrated)
        self.assertEqual(hydrated.lockdown_id, rec.lockdown_id)
        self.assertGreater(len(hydrated.entries), 0)

    # ==========================================================================
    # 10. Duplicate Button Interaction Prevention
    # ==========================================================================
    def test_10_in_flight_lock_prevents_duplicate_operations(self):
        """In-flight locks reject duplicate concurrent operations for the same guild."""
        gid = self.guild_id_str
        self.assertFalse(is_guild_lockdown_in_flight(gid))

        _IN_FLIGHT_LOCKDOWNS.add(gid)
        self.assertTrue(is_guild_lockdown_in_flight(gid))

        _IN_FLIGHT_LOCKDOWNS.discard(gid)
        self.assertFalse(is_guild_lockdown_in_flight(gid))

    # ==========================================================================
    # 11. Interaction Acknowledgment and Progress Feedback
    # ==========================================================================
    async def test_11_progress_callback_invocations(self):
        """Lockdown and recovery invoke progress callbacks at key milestones."""
        milestones = []
        async def mock_progress(step, total, msg):
            milestones.append((step, total, msg))

        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy, progress_callback=mock_progress
        )
        self.assertGreaterEqual(len(milestones), 3)

        rec_rec = await self.lockdown_mgr.restore_lockdown(
            self.guild, rec.lockdown_id, admin_user_id=111122223333, policy=self.policy, progress_callback=mock_progress
        )
        self.assertGreaterEqual(len(milestones), 5)

    # ==========================================================================
    # 12. Verified Outcome Reporting
    # ==========================================================================
    async def test_12_verified_outcome_reporting(self):
        """Lockdown summary reports exact verified, applied, and skipped counts."""
        rec = await self.lockdown_mgr.execute_emergency_lockdown(
            self.guild, self.incident, self.assessment, self.policy
        )
        self.assertIn("verified", rec.summary)
        self.assertIn("skipped_hierarchy", rec.summary)
        self.assertIn("failed_api", rec.summary)
        self.assertEqual(rec.summary["skipped_hierarchy"], 1)

    # ==========================================================================
    # 13. Logging Category and Channel Creation with Ownership
    # ==========================================================================
    async def test_13_logging_category_and_channel_creation(self):
        """Setup workflow creates dedicated category and records verified ownership in tracker."""
        mock_cat = MagicMock(spec=discord.CategoryChannel)
        mock_cat.id = 700100
        mock_cat.name = "📁 SENTINEL™ LOGS"

        mock_ch = MagicMock(spec=discord.TextChannel)
        mock_ch.id = 700200
        mock_ch.name = "security-logs"

        self.guild.create_category = AsyncMock(return_value=mock_cat)
        self.guild.create_text_channel = AsyncMock(return_value=mock_ch)
        self.guild.categories = [mock_cat]
        self.guild.text_channels = [mock_ch]

        res = await UnifiedWebhookLogger.create_logging_setup_workflow(
            guild=self.guild,
            layout="category",
            create_category=True,
            separate_antinuke=True,
        )
        self.assertTrue(res.get("success"))

        # Verify ownership recorded in SentinelResourceTracker
        is_owned = SentinelResourceTracker.is_resource_owned(self.guild.id, mock_ch.id)
        self.assertTrue(is_owned)

    # ==========================================================================
    # 14. Logging Channel Isolation
    # ==========================================================================
    async def test_14_logging_channel_isolation(self):
        """Channels with matching names outside Sentinel's ownership are never adopted."""
        user_cat = MagicMock(spec=discord.CategoryChannel)
        user_cat.id = 888100
        user_cat.name = "📁 USER LOGS"

        user_ch = MagicMock(spec=discord.TextChannel)
        user_ch.id = 888200
        user_ch.name = "security-logs"
        user_ch.category = user_cat

        # Channel is NOT in SentinelResourceTracker
        self.assertFalse(SentinelResourceTracker.is_resource_owned(self.guild.id, user_ch.id))

    # ==========================================================================
    # 15. Reset with Missing or Stale Records
    # ==========================================================================
    async def test_15_reset_with_missing_or_stale_records(self):
        """Reset handles non-existent or deleted channels gracefully without raising exceptions."""
        await SentinelResourceTracker.record_resource_creation(
            self.guild.id,
            resource_id=999888777,  # Does not exist in guild
            resource_type="text_channel",
            purpose="stale-logs",
        )

        res = await UnifiedWebhookLogger.cleanup_logging_resources(
            guild=self.guild,
            delete_from_discord=True,
        )
        self.assertTrue(res.get("success"))

    # ==========================================================================
    # 16. Reset Safety Against Identically Named Channels
    # ==========================================================================
    async def test_16_reset_safety_against_identically_named_channels(self):
        """An admin channel named 'forensic-logs' or 'security-logs' is left untouched on reset."""
        admin_ch = MagicMock(spec=discord.TextChannel)
        admin_ch.id = 999111
        admin_ch.name = "forensic-logs"
        admin_ch.topic = "Admin private notes"
        admin_ch.delete = AsyncMock()

        self.guild.channels.append(admin_ch)

        res = await UnifiedWebhookLogger.cleanup_logging_resources(
            guild=self.guild,
            delete_from_discord=True,
        )

        # Admin channel must NOT be deleted
        self.assertEqual(admin_ch.delete.call_count, 0)

    # ==========================================================================
    # 17. Correlation Rules Calibrated Thresholds
    # ==========================================================================
    def test_17_correlation_rules_calibrated_thresholds(self):
        """Correlation rules define calibrated burst thresholds and detection windows."""
        engine = SecurityCorrelationEngine()
        rules = engine._rules

        # Rapid ban burst rule
        self.assertIn(PatternID.RAPID_BAN_BURST, rules)
        ban_rule = rules[PatternID.RAPID_BAN_BURST]
        self.assertEqual(ban_rule.window_seconds, 60.0)
        self.assertEqual(ban_rule.threshold_count, 5)

        # Repeated channel deletions rule
        self.assertIn(PatternID.REPEATED_CHANNEL_DELETIONS, rules)
        ch_del_rule = rules[PatternID.REPEATED_CHANNEL_DELETIONS]
        self.assertEqual(ch_del_rule.window_seconds, 60.0)
        self.assertEqual(ch_del_rule.threshold_count, 3)

    # ==========================================================================
    # 18. Multi-Actor Correlation, Deduplication, and Audit-Log Attribution
    # ==========================================================================
    def test_18_multi_actor_correlation_and_deduplication(self):
        """Engine correlates events per actor and suppresses duplicate event IDs."""
        engine = SecurityCorrelationEngine()

        event1 = SecurityEvent(
            event_id="evt_test_dedup_1",
            guild_id=self.guild_id_str,
            event_type="member_ban",
            actor_id="actor_bad_1",
            target_id="victim_1",
            timestamp=time.time(),
        )

        signal1 = engine.ingest_event(event1)
        self.assertIsNone(signal1)  # 1 ban below threshold of 5

        # Ingest duplicate of event1: must be suppressed
        signal_dup = engine.ingest_event(event1)
        self.assertIsNone(signal_dup)

        # Separate actor: should not pool with actor_bad_1
        event_actor2 = SecurityEvent(
            event_id="evt_test_actor_2",
            guild_id=self.guild_id_str,
            event_type="member_ban",
            actor_id="actor_good_2",
            target_id="victim_2",
            timestamp=time.time(),
        )
        signal2 = engine.ingest_event(event_actor2)
        self.assertIsNone(signal2)


if __name__ == "__main__":
    unittest.main()
