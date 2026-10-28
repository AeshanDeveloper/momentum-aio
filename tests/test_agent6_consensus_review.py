"""
Unit and integration tests for Sentinel™ Multi-Admin Consensus Review, Vote Correction,
and Conflict of Interest Protections (Agent 6 of 8).

Covers:
1. Three-person consensus dismissal requiring 3 distinct eligible reviewers.
2. Duplicate interaction prevention (idempotency, no double-counting).
3. Vote correction workflow: recalculation of quorums, status reversal, and immutable audit history.
4. Runtime eligibility verification: rejecting revoked administrators.
5. Concurrent voting transactional safety (asyncio.gather without race conditions).
6. Anti-Self-Pardon Guard: strictly blocking the accused incident subject from voting.
7. Evidence preservation and no global whitelisting upon false-alarm dismissal.
8. Recovery authorization pausing when continuing threats or active attacks are detected.
9. Owner unilateral authorization vs non-owner consensus.
10. UI view callbacks and component dispatch integration.
"""

import unittest
import asyncio
import time
from typing import Dict, Any, List, Optional, Set

import discord
from discord import Permissions, Role, TextChannel, Member, User

from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    get_default_response_policy,
)
from core.security.lockdown_journal import (
    JournalEntry,
    JournalEntryStatus,
    LockdownRecord,
    LockdownJournalManager,
)
from core.security.emergency_lockdown_manager import EmergencyLockdownManager
from core.security.protection_service import SecurityProtectionService
from core.security.incident import (
    Incident,
    IncidentStatus,
    ReviewDecisionType,
    AdminVote,
    ProtectiveActionType,
)
from core.security.incident_manager import IncidentManager
from core.security.consensus_manager import (
    IncidentConsensusManager,
    ReviewChoice,
    IncidentReviewView,
    build_incident_review_container,
)


class MockMember:
    def __init__(self, user_id: int, name: str, is_admin: bool = True):
        self.id = user_id
        self.name = name
        self.display_name = name
        p = Permissions()
        if is_admin:
            p.administrator = True
            p.manage_guild = True
        self.guild_permissions = p

    def __str__(self):
        return f"{self.name}#{self.id}"


class MockGuild:
    def __init__(self, guild_id: int = 55001, name: str = "Consensus Test Guild", owner_id: int = 90001):
        self.id = guild_id
        self.name = name
        self.owner_id = owner_id
        self.roles: List[Role] = []
        self.channels: List[TextChannel] = []
        self.members: Dict[int, MockMember] = {}

    def get_member(self, user_id: int) -> Optional[MockMember]:
        return self.members.get(user_id)

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


class MockInteraction:
    def __init__(self, user_id: int, user_name: str, guild: Optional[MockGuild] = None):
        self.user = MockMember(user_id=user_id, name=user_name, is_admin=True)
        self.guild = guild
        self.response = MockInteractionResponse()
        self.followup = MockInteractionFollowup()


class MockInteractionResponse:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        self._done = False

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content: str = "", embed: Any = None, ephemeral: bool = False, **kwargs):
        self._done = True
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})


class MockInteractionFollowup:
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []

    async def send(self, content: str = "", embed: Any = None, ephemeral: bool = False, **kwargs):
        self.messages.append({"content": content, "embed": embed, "ephemeral": ephemeral})


class TestAgent6ConsensusReview(unittest.TestCase):
    def setUp(self):
        from database.database import _save_mock_data
        _save_mock_data("security_lockdowns", [])
        _save_mock_data("security_incidents", [])

        self.journal = LockdownJournalManager()
        self.lockdown_mgr = EmergencyLockdownManager(journal_manager=self.journal)
        self.inc_manager = IncidentManager()
        self.inc_manager._incidents.clear()

        self.protection_service = SecurityProtectionService(
            lockdown_mgr=self.lockdown_mgr,
            journal_mgr=self.journal,
        )

        self.consensus_mgr = IncidentConsensusManager(
            inc_manager=self.inc_manager,
            lockdown_mgr=self.lockdown_mgr,
            prot_service=self.protection_service,
            journal_mgr=self.journal,
        )

        self.guild = MockGuild(guild_id=55001, name="Consensus Fortress", owner_id=90001)

        # Policy: 3 votes to dismiss, 2 to confirm, 2 for recovery
        self.policy = SecurityResponsePolicy(
            guild_id="55001",
            response_level=ResponseLevel.LOCKDOWN,
            dismissal_quorum=3,
            confirmation_quorum=2,
            recovery_quorum=2,
            prevent_subject_voting=True,
            allow_vote_correction=True,
            trusted_recovery_admins=["10001", "10002", "10003", "10004"],
            recovery_owner_id="90001",
        )
        self.protection_service._policies["55001"] = self.policy

        # Add guild members
        self.guild.members[90001] = MockMember(90001, "ServerOwner", is_admin=True)
        self.guild.members[10001] = MockMember(10001, "AdminAlpha", is_admin=True)
        self.guild.members[10002] = MockMember(10002, "AdminBravo", is_admin=True)
        self.guild.members[10003] = MockMember(10003, "AdminCharlie", is_admin=True)
        self.guild.members[10004] = MockMember(10004, "AdminDelta", is_admin=True)
        self.guild.members[77777] = MockMember(77777, "AttackerSuspect", is_admin=True)
        self.guild.members[88888] = MockMember(88888, "RevokedAdmin", is_admin=False)

    def _create_test_incident(self, suspect_id: str = "77777") -> Incident:
        inc = Incident(
            incident_id=f"INC-{int(time.time()*1000)}",
            guild_id="55001",
            matched_patterns=["rapid_ban_burst"],
            status=IncidentStatus.UNDER_REVIEW,
            severity="critical",
            confidence="confirmed",
            is_emergency=True,
            relevant_actors=[{"actor_id": suspect_id, "type": "user"}],
            metadata={"subject_id": suspect_id},
        )
        inc.evidence_references = [
            {"evidence_id": "ev-1", "type": "audit_log_ban", "target_id": "u1"},
            {"evidence_id": "ev-2", "type": "audit_log_ban", "target_id": "u2"},
        ]
        self.inc_manager._incidents.setdefault("55001", {})[inc.incident_id] = inc
        return inc

    def test_three_person_consensus_dismissal(self):
        """1. Three-person consensus: requires 3 distinct eligible reviewers to dismiss false alarm."""
        inc = self._create_test_incident()

        # Vote 1 (Admin Alpha)
        res1 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10001",
            reviewer_name="AdminAlpha",
            choice=ReviewChoice.DISMISS,
            reason="Verified scheduled maintenance ban script",
        ))
        self.assertTrue(res1["success"])
        self.assertEqual(res1["tallies"][ReviewChoice.DISMISS], 1)
        self.assertFalse(res1["quorum_met"])
        self.assertEqual(inc.status, IncidentStatus.UNDER_REVIEW)

        # Vote 2 (Admin Bravo)
        res2 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10002",
            reviewer_name="AdminBravo",
            choice=ReviewChoice.DISMISS,
            reason="Confirmed script logs match authorized change request",
        ))
        self.assertTrue(res2["success"])
        self.assertEqual(res2["tallies"][ReviewChoice.DISMISS], 2)
        self.assertFalse(res2["quorum_met"])
        self.assertEqual(inc.status, IncidentStatus.UNDER_REVIEW)

        # Vote 3 (Admin Charlie) -> Quorum reached (3/3)
        res3 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10003",
            reviewer_name="AdminCharlie",
            choice=ReviewChoice.DISMISS,
            reason="Third admin concurrence on false alarm",
        ))
        self.assertTrue(res3["success"])
        self.assertEqual(res3["tallies"][ReviewChoice.DISMISS], 3)
        self.assertTrue(res3["quorum_met"])
        self.assertEqual(inc.status, IncidentStatus.DISMISSED)
        self.assertIn("Incident dismissed by consensus", res3["details"])

    def test_duplicate_vote_prevention(self):
        """2. Duplicate interactions: voting with same choice does not count twice or meet quorum."""
        inc = self._create_test_incident()

        res1 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10001",
            reviewer_name="AdminAlpha",
            choice=ReviewChoice.DISMISS,
        ))
        self.assertTrue(res1["success"])
        self.assertEqual(res1["tallies"][ReviewChoice.DISMISS], 1)

        # Admin Alpha clicks dismiss again (duplicate interaction)
        res2 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10001",
            reviewer_name="AdminAlpha",
            choice=ReviewChoice.DISMISS,
        ))
        self.assertTrue(res2["success"])
        self.assertEqual(res2["action"], "duplicate")
        self.assertEqual(res2["tallies"][ReviewChoice.DISMISS], 1)
        self.assertEqual(len(inc.votes), 1)
        self.assertEqual(inc.status, IncidentStatus.UNDER_REVIEW)

    def test_vote_correction_and_quorum_reversal(self):
        """3. Vote correction: changing vote recalculates quorums, updates audit trails, and reverses status if quorum lost."""
        inc = self._create_test_incident()

        # 3 admins vote dismiss -> incident is dismissed
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10001", "Alpha", ReviewChoice.DISMISS))
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10002", "Bravo", ReviewChoice.DISMISS))
        res3 = asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10003", "Charlie", ReviewChoice.DISMISS))
        self.assertEqual(inc.status, IncidentStatus.DISMISSED)
        self.assertEqual(res3["tallies"][ReviewChoice.DISMISS], 3)

        # Charlie discovers new evidence and changes vote from DISMISS to CONFIRM
        corr_res = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10003",
            reviewer_name="Charlie",
            choice=ReviewChoice.CONFIRM,
            reason="Found unauthorized tokens; this is an actual breach!",
        ))
        self.assertTrue(corr_res["success"])
        self.assertEqual(corr_res["action"], "corrected")
        self.assertEqual(corr_res["previous_choice"], ReviewChoice.DISMISS)
        self.assertEqual(corr_res["choice"], ReviewChoice.CONFIRM)
        self.assertEqual(corr_res["tallies"][ReviewChoice.DISMISS], 2)
        self.assertEqual(corr_res["tallies"][ReviewChoice.CONFIRM], 1)

        # Dismissal quorum dropped below 3 -> Incident must safely revert back to UNDER_REVIEW
        self.assertEqual(inc.status, IncidentStatus.UNDER_REVIEW)

        # Verify audit trail on vote and decision history
        vote_rec = inc.votes["10003"]
        self.assertEqual(vote_rec.previous_choice, ReviewChoice.DISMISS)
        self.assertEqual(len(vote_rec.correction_history), 1)
        self.assertEqual(vote_rec.correction_history[0]["old_choice"], ReviewChoice.DISMISS)
        self.assertEqual(vote_rec.correction_history[0]["new_choice"], ReviewChoice.CONFIRM)

        # Check decision history includes VOTE_CORRECTION entry
        correction_decisions = [d for d in inc.decision_history if d.decision_type == ReviewDecisionType.VOTE_CORRECTION]
        self.assertTrue(len(correction_decisions) >= 1)

    def test_revoked_admin_access_rejected(self):
        """4. Runtime eligibility verification: rejects reviewers whose permissions were revoked."""
        inc = self._create_test_incident()

        # User 88888 has no admin perms and is not in trusted_recovery_admins
        res = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="88888",
            reviewer_name="RevokedAdmin",
            choice=ReviewChoice.CONFIRM,
        ))
        self.assertFalse(res["success"])
        self.assertIn("Unauthorized", res["error"])
        self.assertNotIn("88888", inc.votes)

    def test_concurrent_voting_transactional_safety(self):
        """5. Concurrent voting safety: simultaneous async votes are processed transactionally without race conditions."""
        inc = self._create_test_incident()

        async def run_concurrent_votes():
            return await asyncio.gather(
                self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10001", "Alpha", ReviewChoice.CONFIRM),
                self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10002", "Bravo", ReviewChoice.CONFIRM),
                self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10003", "Charlie", ReviewChoice.REQUEST_INFO),
                self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10004", "Delta", ReviewChoice.KEEP_LOCKDOWN),
            )

        results = asyncio.run(run_concurrent_votes())
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertTrue(r["success"])

        # Exactly 4 distinct votes recorded
        self.assertEqual(len(inc.votes), 4)
        tallies = self.consensus_mgr._calculate_tallies(inc)
        self.assertEqual(tallies[ReviewChoice.CONFIRM], 2)
        self.assertEqual(tallies[ReviewChoice.REQUEST_INFO], 1)
        self.assertEqual(tallies[ReviewChoice.KEEP_LOCKDOWN], 1)

    def test_subject_prevented_from_voting_anti_self_pardon(self):
        """6. Conflict of interest: accused actor/subject cannot vote on their own incident."""
        inc = self._create_test_incident(suspect_id="77777")

        # Suspect 77777 attempts to dismiss the incident
        res = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="77777",
            reviewer_name="AttackerSuspect",
            choice=ReviewChoice.DISMISS,
        ))
        self.assertFalse(res["success"])
        self.assertIn("Conflict of interest", res["error"])
        self.assertNotIn("77777", inc.votes)

        # Disabling prevent_subject_voting in policy would allow it, but default is True
        self.assertTrue(self.policy.prevent_subject_voting)

    def test_dismissal_preserves_evidence_and_does_not_whitelist_actor(self):
        """7. Preserves evidence: dismissing an incident never deletes evidence or grants permanent actor whitelisting."""
        inc = self._create_test_incident(suspect_id="77777")
        orig_evidence_count = len(inc.evidence_references)
        self.assertEqual(orig_evidence_count, 2)

        # 3 admins dismiss false alarm
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10001", "Alpha", ReviewChoice.DISMISS))
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10002", "Bravo", ReviewChoice.DISMISS))
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10003", "Charlie", ReviewChoice.DISMISS))

        self.assertEqual(inc.status, IncidentStatus.DISMISSED)

        # Evidence references must NOT be deleted or altered
        self.assertEqual(len(inc.evidence_references), orig_evidence_count)
        self.assertEqual(inc.evidence_references[0]["evidence_id"], "ev-1")

        # Suspect actor 77777 must NOT be added to trusted recovery actors or bypass list
        self.assertFalse(self.policy.is_trusted_recovery_actor("77777"))
        self.assertNotIn("77777", self.policy.trusted_recovery_admins)

    def test_recovery_approval_checks_continuing_threat(self):
        """8. Recovery approval checks continuing threat status and pauses rollback if attack remains active."""
        inc = self._create_test_incident()

        # Create active lockdown record for this incident
        lck = LockdownRecord(
            lockdown_id=f"LCK-{int(time.time())}",
            guild_id="55001",
            incident_id=inc.incident_id,
            status=LockdownStatus.ACTIVE,
            trigger_pattern="rapid_ban_burst",
        )
        self.journal.save_lockdown(lck)

        # Mock an ongoing active attack on this guild (simulate active recent activity)
        inc.latest_seen_at = time.time()  # activity within last 5 seconds
        inc.is_emergency = True

        # Recovery requires 2 approvals
        # Admin Alpha votes authorize recovery
        res1 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10001",
            reviewer_name="Alpha",
            choice=ReviewChoice.AUTHORIZE_RECOVERY,
        ))
        self.assertTrue(res1["success"])
        self.assertFalse(res1["quorum_met"])

        # Admin Bravo votes authorize recovery (2/2 quorum reached)
        res2 = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10002",
            reviewer_name="Bravo",
            choice=ReviewChoice.AUTHORIZE_RECOVERY,
            force=False,
        ))
        self.assertTrue(res2["success"])
        self.assertTrue(res2["quorum_met"])
        # Should warn about continuing active threat and pause rollback
        self.assertIn("Active destructive activity is still detected", res2["details"])
        self.assertEqual(lck.status, LockdownStatus.ACTIVE)

        # If forced by reviewer, recovery proceeds
        res_forced = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="10001",
            reviewer_name="Alpha",
            choice=ReviewChoice.AUTHORIZE_RECOVERY,
            force=True,
        ))
        self.assertTrue(res_forced["success"])
        # With force=True, rollback executed
        self.assertEqual(lck.status, LockdownStatus.RESTORED)

    def test_owner_unilateral_authorization(self):
        """9. Server owner has root recovery authority to unilaterally confirm, dismiss, or recover."""
        inc = self._create_test_incident()

        # Server owner (90001) votes DISMISS -> quorum immediately satisfied
        res = asyncio.run(self.consensus_mgr.submit_vote(
            guild=self.guild,
            incident_id=inc.incident_id,
            reviewer_id="90001",
            reviewer_name="ServerOwner",
            choice=ReviewChoice.DISMISS,
            reason="Owner confirmed false alarm",
        ))
        self.assertTrue(res["success"])
        self.assertTrue(res["quorum_met"])
        self.assertEqual(inc.status, IncidentStatus.DISMISSED)

    def test_ui_review_view_and_container_builder(self):
        """10. Renders interactive review view and summary container with live vote breakdown."""
        inc = self._create_test_incident()

        # Add initial votes
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10001", "Alpha", ReviewChoice.CONFIRM))
        asyncio.run(self.consensus_mgr.submit_vote(self.guild, inc.incident_id, "10002", "Bravo", ReviewChoice.REQUEST_INFO))

        summary = self.consensus_mgr.get_consensus_summary(inc.incident_id)
        self.assertIsNotNone(summary)
        self.assertEqual(summary["total_votes"], 2)
        self.assertEqual(summary["tallies"][ReviewChoice.CONFIRM], 1)
        self.assertEqual(summary["tallies"][ReviewChoice.REQUEST_INFO], 1)

        # Build UI container
        container = build_incident_review_container(inc, self.policy, summary)
        built = container.build()
        self.assertIsNotNone(built)

        # Build Interactive View
        view = IncidentReviewView(inc, policy=self.policy, consensus_mgr=self.consensus_mgr)
        self.assertEqual(len(view.children), 5)

        # Simulate button interaction
        mock_interaction = MockInteraction(user_id=10003, user_name="AdminCharlie", guild=self.guild)
        asyncio.run(view._handle_vote_interaction(mock_interaction, ReviewChoice.CONFIRM))

        self.assertEqual(len(mock_interaction.response.messages), 1)
        sent = mock_interaction.response.messages[0]
        self.assertIn("Vote successfully", sent["content"])
        self.assertIn("Confirm (2/2)", sent["content"])


if __name__ == "__main__":
    unittest.main()
