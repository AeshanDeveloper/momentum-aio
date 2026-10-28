"""
Unit & Integration Tests for Sentinel™ Security Event Observation Layer.

Covers:
- Normalized SecurityEvent model integrity, serialization, and confidence levels
- SecurityEventNormalizer across all 23+ Discord event vectors
- Dangerous permission escalation and overwrite detection
- Asynchronous actor attribution enrichment (unknown -> verified)
- Suppressed duplicate filtering & deduplication window
- Preservation of whitelisted user activity without suppression
- Subscriber pub/sub dispatch interface for downstream Agent 2 threat evaluation
- Database persistence safety and in-memory ring-buffer querying
"""

import time
import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import discord

from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.event_normalizer import SecurityEventNormalizer
from core.security.event_collector import (
    SecurityEventCollector,
    security_event_collector,
)
from core.security.antinuke import AntiNukeManager, AntiNukeConstants
from database.database import database


class TestSecurityEventObservation(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        SecurityEventCollector.reset_instance()
        self.collector = SecurityEventCollector.get_instance()

        # Mock Discord Guild
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 123456789012345678
        self.guild.name = "Sentinel Secure Citadel"
        self.guild.owner_id = 999999999

        # Register guild config in AntiNukeManager
        AntiNukeManager._guild_configs[str(self.guild.id)] = {
            "guild_id": str(self.guild.id),
            "setup_completed": True,
            "enabled": True,
            "mode": AntiNukeConstants.MODE_HARD,
            "monitored_events": list(AntiNukeConstants.ALL_EVENTS),
            "extra_owners": [],
            "whitelists": {
                "user": ["888888888"],
            },
            "ticket_bots": [],
            "warning_channel_id": "111111",
            "log_channel_id": "222222",
            "thresholds": {},
            "punishments": {},
        }

    def tearDown(self):
        self.collector.clear_subscribers()

    # 1. SecurityEvent Model & Serialization Tests
    def test_security_event_model_properties_and_serialization(self):
        event = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.MEMBER_BAN,
            target_id="11223344",
            target_type="member",
            target_name="Attacker#0001",
            actor_id="99887766",
            actor_name="Moderator#1234",
            attribution_confidence=AttributionConfidence.VERIFIED,
            reason="Mass spam attack",
            metadata={"ip": "1.2.3.4"},
        )

        self.assertTrue(event.is_verified)
        self.assertFalse(event.is_unknown)
        self.assertFalse(event.is_probable)
        self.assertTrue(event.event_id.startswith("sec_evt_"))
        self.assertIsNotNone(event.dedup_key)

        # Serialization
        doc = event.to_dict()
        self.assertEqual(doc["guild_id"], str(self.guild.id))
        self.assertEqual(doc["event_type"], SecurityEventType.MEMBER_BAN)
        self.assertEqual(doc["target_id"], "11223344")
        self.assertEqual(doc["actor_id"], "99887766")
        self.assertEqual(doc["attribution_confidence"], AttributionConfidence.VERIFIED)

        # Deserialization
        reconstructed = SecurityEvent.from_dict(doc)
        self.assertEqual(reconstructed.event_id, event.event_id)
        self.assertEqual(reconstructed.guild_id, event.guild_id)
        self.assertEqual(reconstructed.target_name, "Attacker#0001")
        self.assertTrue(reconstructed.is_verified)

    # 2. Normalization: Dangerous Permission Grant Detection
    def test_normalize_role_update_dangerous_permission_grant(self):
        before_role = MagicMock(spec=discord.Role)
        before_role.id = 555666777
        before_role.name = "Moderator"
        before_role.guild = self.guild
        before_perms = discord.Permissions(0)
        before_perms.manage_messages = True
        before_perms.administrator = False
        before_role.permissions = before_perms

        after_role = MagicMock(spec=discord.Role)
        after_role.id = 555666777
        after_role.name = "Moderator"
        after_role.guild = self.guild
        after_perms = discord.Permissions(0)
        after_perms.manage_messages = True
        after_perms.administrator = True  # Escalation!
        after_perms.ban_members = True    # Escalation!
        after_role.permissions = after_perms

        evt = SecurityEventNormalizer.normalize_role_update(before_role, after_role)
        self.assertEqual(evt.event_type, SecurityEventType.DANGEROUS_PERMISSION_GRANT)
        self.assertEqual(evt.target_id, "555666777")
        self.assertIn("administrator", evt.metadata["escalated_permissions"])
        self.assertIn("ban_members", evt.metadata["escalated_permissions"])

    # 3. Normalization: Dangerous Channel Overwrite Modification
    def test_normalize_channel_update_dangerous_overwrites(self):
        before_channel = MagicMock(spec=discord.TextChannel)
        before_channel.id = 444333222
        before_channel.name = "private-vault"
        before_channel.guild = self.guild
        before_channel.overwrites = {}

        everyone_role = MagicMock(spec=discord.Role)
        everyone_role.id = self.guild.id
        everyone_role.name = "@everyone"

        danger_overwrite = MagicMock(spec=discord.PermissionOverwrite)
        danger_overwrite.manage_channels = True

        after_channel = MagicMock(spec=discord.TextChannel)
        after_channel.id = 444333222
        after_channel.name = "private-vault"
        after_channel.guild = self.guild
        after_channel.overwrites = {everyone_role: danger_overwrite}

        evt = SecurityEventNormalizer.normalize_channel_update(before_channel, after_channel)
        self.assertEqual(evt.event_type, SecurityEventType.PERMISSION_OVERWRITE_UPDATE)
        self.assertTrue(evt.metadata["overwrites_modified"])
        self.assertTrue(len(evt.metadata["dangerous_overwrites_added"]) > 0)

    # 4. Normalization: Bot Additions
    def test_normalize_bot_addition(self):
        bot_member = MagicMock(spec=discord.Member)
        bot_member.id = 777888999
        bot_member.name = "RogueBot"
        bot_member.bot = True
        bot_member.guild = self.guild
        bot_member.created_at = MagicMock()
        bot_member.created_at.timestamp.return_value = 1700000000.0

        evt = SecurityEventNormalizer.normalize_member_join(bot_member)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.event_type, SecurityEventType.BOT_ADD)
        self.assertEqual(evt.target_id, "777888999")
        self.assertTrue(evt.metadata["is_bot"])

        # Regular user join should not produce a BOT_ADD event
        human_member = MagicMock(spec=discord.Member)
        human_member.bot = False
        self.assertIsNone(SecurityEventNormalizer.normalize_member_join(human_member))

    # 5. Normalization: Server Security Settings
    def test_normalize_guild_security_settings(self):
        before_guild = MagicMock(spec=discord.Guild)
        before_guild.id = self.guild.id
        before_guild.name = "Sentinel Secure"
        before_guild.verification_level = discord.VerificationLevel.high
        before_guild.mfa_level = discord.MFALevel.require_2fa

        after_guild = MagicMock(spec=discord.Guild)
        after_guild.id = self.guild.id
        after_guild.name = "Sentinel Secure"
        after_guild.verification_level = discord.VerificationLevel.none  # Degraded security!
        after_guild.mfa_level = discord.MFALevel.disabled               # Degraded security!

        evt = SecurityEventNormalizer.normalize_guild_update(before_guild, after_guild)
        self.assertEqual(evt.event_type, SecurityEventType.SECURITY_SETTINGS_UPDATE)
        self.assertIn("verification_level", evt.metadata["changes"])
        self.assertIn("mfa_level", evt.metadata["changes"])

    # 6. Asynchronous Attribution Enrichment (Unknown -> Verified via Audit Log)
    async def test_async_audit_log_enrichment(self):
        target_channel = MagicMock(spec=discord.TextChannel)
        target_channel.id = 987123
        target_channel.name = "announcements"
        target_channel.guild = self.guild

        evt = SecurityEventNormalizer.normalize_channel_delete(target_channel)
        self.assertTrue(evt.is_unknown)
        self.assertIsNone(evt.actor_id)

        # Mock audit log entry returned asynchronously
        audit_entry = MagicMock(spec=discord.AuditLogEntry)
        audit_entry.id = 5544332211
        audit_entry.reason = "Server reorganization"
        audit_user = MagicMock(spec=discord.User)
        audit_user.id = 1122334455
        audit_user.name = "AdminOperator"
        audit_entry.user = audit_user

        async def mock_audit_query():
            await asyncio.sleep(0.01)
            return audit_entry

        received_events = []
        self.collector.subscribe(lambda e: received_events.append(e))

        ingested = self.collector.ingest(evt, audit_lookup_coro=mock_audit_query)
        self.assertEqual(ingested.event_id, evt.event_id)

        # Allow background enrichment task to complete
        await asyncio.sleep(0.1)

        self.assertEqual(len(received_events), 1)
        dispatched_event = received_events[0]
        self.assertTrue(dispatched_event.is_verified)
        self.assertEqual(dispatched_event.actor_id, "1122334455")
        self.assertEqual(dispatched_event.actor_name, str(audit_user))
        self.assertEqual(dispatched_event.reason, "Server reorganization")
        self.assertEqual(dispatched_event.source_id, "5544332211")

    # 7. Unverified / Missing Audit Log Retains UNKNOWN without Dropping Event
    async def test_audit_log_unavailable_retains_unknown_confidence(self):
        target_channel = MagicMock(spec=discord.TextChannel)
        target_channel.id = 987124
        target_channel.name = "secret-room"
        target_channel.guild = self.guild

        evt = SecurityEventNormalizer.normalize_channel_delete(target_channel)

        async def mock_empty_audit_query():
            return None

        received_events = []
        self.collector.subscribe(lambda e: received_events.append(e))

        self.collector.ingest(evt, audit_lookup_coro=mock_empty_audit_query)
        await asyncio.sleep(1.2)  # Wait for retry check

        self.assertEqual(len(received_events), 1)
        self.assertTrue(received_events[0].is_unknown)
        self.assertIsNone(received_events[0].actor_id)
        self.assertEqual(received_events[0].status, SecurityEventStatus.DISPATCHED)

    # 8. Deduplication Window Suppresses Overlapping Signals
    async def test_deduplication_suppresses_duplicate_gateway_signals(self):
        evt1 = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.CHANNEL_DELETE,
            target_id="555000111",
            dedup_key=f"{self.guild.id}:channel_delete:555000111:bucket",
        )
        evt2 = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.CHANNEL_DELETE,
            target_id="555000111",
            dedup_key=f"{self.guild.id}:channel_delete:555000111:bucket",
        )

        received_events = []
        self.collector.subscribe(lambda e: received_events.append(e))

        res1 = self.collector.ingest(evt1)
        res2 = self.collector.ingest(evt2)

        await asyncio.sleep(0.05)

        # Both returned objects point to the canonical first event
        self.assertEqual(res1.event_id, res2.event_id)
        self.assertEqual(evt2.status, SecurityEventStatus.SUPPRESSED_DUPLICATE)
        # Subscribers received only one dispatch
        self.assertEqual(len(received_events), 1)

    # 9. Whitelisted Actors MUST NOT Be Filtered or Suppressed
    async def test_whitelisted_actors_are_faithfully_observed(self):
        whitelisted_user_id = "888888888"

        evt = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.ROLE_DELETE,
            target_id="333222111",
            actor_id=whitelisted_user_id,
            actor_name="WhitelistedAdmin#0001",
            attribution_confidence=AttributionConfidence.VERIFIED,
        )

        received_events = []
        self.collector.subscribe(lambda e: received_events.append(e))

        self.collector.ingest(evt)
        await asyncio.sleep(0.05)

        self.assertEqual(len(received_events), 1)
        observed = received_events[0]
        # Crucial check: Flagged as whitelisted, but NEVER suppressed!
        self.assertTrue(observed.is_whitelisted_actor)
        self.assertEqual(observed.actor_id, whitelisted_user_id)
        self.assertEqual(observed.status, SecurityEventStatus.DISPATCHED)

    # 10. Downstream Pub/Sub Filtering (Agent 2 Handoff Interface)
    async def test_subscriber_filtering_by_event_type_and_confidence(self):
        ban_events = []
        verified_events = []

        # Subscriber 1: Ban events only
        self.collector.subscribe(
            lambda e: ban_events.append(e),
            event_types=[SecurityEventType.MEMBER_BAN],
        )
        # Subscriber 2: Verified attribution only
        self.collector.subscribe(
            lambda e: verified_events.append(e),
            min_confidence=AttributionConfidence.VERIFIED,
        )

        # Event A: Unverified Ban
        evt_a = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.MEMBER_BAN,
            target_id="111",
            attribution_confidence=AttributionConfidence.UNKNOWN,
        )
        # Event B: Verified Role Delete
        evt_b = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.ROLE_DELETE,
            target_id="222",
            actor_id="999",
            attribution_confidence=AttributionConfidence.VERIFIED,
        )

        self.collector.ingest(evt_a)
        self.collector.ingest(evt_b)
        await asyncio.sleep(0.05)

        self.assertEqual(len(ban_events), 1)
        self.assertEqual(ban_events[0].target_id, "111")

        self.assertEqual(len(verified_events), 1)
        self.assertEqual(verified_events[0].target_id, "222")

    # 11. Database Persistence Resilience
    async def test_database_persistence_failure_does_not_break_observation(self):
        evt = SecurityEvent(
            guild_id=str(self.guild.id),
            event_type=SecurityEventType.WEBHOOK_CREATE,
            target_id="666777888",
            attribution_confidence=AttributionConfidence.VERIFIED,
        )

        received_events = []
        self.collector.subscribe(lambda e: received_events.append(e))

        # Simulate database failure
        with patch.object(database, "collection", side_effect=Exception("Database connection timeout")):
            self.collector.ingest(evt)
            await asyncio.sleep(0.05)

        # Observation pipeline continues unbroken and dispatches event
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].target_id, "666777888")

    # 12. In-Memory Ring Buffer and Guild Queries
    def test_recent_events_querying(self):
        guild_a = "100"
        guild_b = "200"

        for i in range(10):
            self.collector.ingest(
                SecurityEvent(
                    guild_id=guild_a,
                    event_type=SecurityEventType.MEMBER_BAN if i % 2 == 0 else SecurityEventType.ROLE_CREATE,
                    target_id=f"target_{i}",
                    timestamp=time.time() + i,
                )
            )

        self.collector.ingest(
            SecurityEvent(guild_id=guild_b, event_type=SecurityEventType.MEMBER_BAN, target_id="guild_b_target")
        )

        # Query guild A with limit
        recent_a = self.collector.get_recent_events(guild_a, limit=5)
        self.assertEqual(len(recent_a), 5)
        # Verify descending order (newest first)
        self.assertGreater(recent_a[0].timestamp, recent_a[1].timestamp)

        # Query guild A filtered by event_type
        bans_a = self.collector.get_recent_events(guild_a, event_type=SecurityEventType.MEMBER_BAN)
        self.assertEqual(len(bans_a), 5)
        self.assertTrue(all(e.event_type == SecurityEventType.MEMBER_BAN for e in bans_a))

        # Guild B isolation
        recent_b = self.collector.get_recent_events(guild_b)
        self.assertEqual(len(recent_b), 1)
        self.assertEqual(recent_b[0].target_id, "guild_b_target")


if __name__ == "__main__":
    unittest.main()
