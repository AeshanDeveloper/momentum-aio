"""
Sentinel™ Security Incident Consensus & Review Manager.

Agent 6 of 8 Security Core: Multi-admin review workflows, quorum consensus,
vote correction with immutable audit trails, subject-voting prevention,
active threat verification, and seamless integration with Agent 5 emergency recovery.

Key capabilities:
- Multi-Admin Consensus: Requires distinct eligible reviewers for material decisions (e.g., 3 votes to dismiss, 2 to confirm).
- Runtime Eligibility Verification: Revalidates reviewer's admin authority on every vote; revoked admins are rejected.
- Conflict of Interest Protection: The subject of an incident (accused actor) is strictly prohibited from voting on their own incident.
- Vote Correction Workflow: Reviewers can correct their choice; recalculates quorums dynamically, records audit diffs, and prevents unauthorized edits.
- Evidence & Monitoring Preservation: Dismissals suppress noise for that incident, but NEVER delete evidence, whitelist actors, or stop telemetry.
- Recovery Integration: Integrates directly with Agent 5's EmergencyLockdownManager; checks for ongoing active attacks before lifting containment.
"""

from __future__ import annotations

import time
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set, Tuple, Union

import discord
from discord import Permissions, ui, ButtonStyle

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    SeparatorSpacingSize,
    ButtonStyle as SdkButtonStyle,
)
from core.logging.logger import logger
from database.database import database
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    get_default_response_policy,
)
from core.security.lockdown_journal import (
    LockdownRecord,
    lockdown_journal_manager,
    LockdownJournalManager,
)
from core.security.emergency_lockdown_manager import (
    EmergencyLockdownManager,
    emergency_lockdown_manager,
)
from core.security.protection_service import (
    SecurityProtectionService,
    security_protection_service,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    AdminVote,
    ReviewDecisionType,
    ProtectiveActionType,
)
from core.security.incident_manager import (
    IncidentManager,
    incident_manager,
)
from core.security.antinuke import AntiNukeManager


class ReviewChoice:
    """Canonical voting choices for security incident review."""
    CONFIRM = "confirm"
    DISMISS = "dismiss"
    REQUEST_INFO = "request_info"
    KEEP_LOCKDOWN = "keep_lockdown"
    AUTHORIZE_RECOVERY = "authorize_recovery"

    ALL = {CONFIRM, DISMISS, REQUEST_INFO, KEEP_LOCKDOWN, AUTHORIZE_RECOVERY}


class IncidentConsensusManager:
    """
    Manages multi-admin review workflows, quorum calculations, and vote corrections.
    """
    _instance: Optional["IncidentConsensusManager"] = None

    @classmethod
    def get_instance(cls) -> "IncidentConsensusManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        inc_manager: Optional[IncidentManager] = None,
        lockdown_mgr: Optional[EmergencyLockdownManager] = None,
        prot_service: Optional[SecurityProtectionService] = None,
        journal_mgr: Optional[LockdownJournalManager] = None,
    ):
        self.incident_manager: IncidentManager = inc_manager or incident_manager
        self.lockdown_manager: EmergencyLockdownManager = lockdown_mgr or emergency_lockdown_manager
        self.protection_service: SecurityProtectionService = prot_service or security_protection_service
        self.journal: LockdownJournalManager = journal_mgr or lockdown_journal_manager
        
        self._incident_async_locks: Dict[str, asyncio.Lock] = {}
        self._sync_lock = threading.RLock()

    def _get_incident_lock(self, incident_id: str) -> asyncio.Lock:
        """Retrieves or creates an asyncio.Lock for a specific incident."""
        with self._sync_lock:
            if incident_id not in self._incident_async_locks:
                self._incident_async_locks[incident_id] = asyncio.Lock()
            return self._incident_async_locks[incident_id]

    # Eligibility & Authority Verification
    def verify_reviewer_eligibility(
        self,
        guild: Any,
        user_id: Union[str, int],
        policy: SecurityResponsePolicy,
        incident: Optional[Incident] = None,
    ) -> Tuple[bool, str]:
        """
        Validates if a reviewer is currently eligible to vote on a security incident.
        Enforces policy:
        1. Must be designated recovery owner, trusted recovery admin, server owner, or Extra Owner.
        2. Must have active administrative privileges in the guild (not revoked).
        3. Conflict of interest safeguard: The subject of the incident CANNOT vote on their own review!
        """
        uid_str = str(user_id)

        # 1. Subject of incident check (Anti-Self-Pardon Guard)
        if incident and policy.prevent_subject_voting:
            subject_ids = self._get_incident_subject_ids(incident)
            if uid_str in subject_ids:
                logger.warning(
                    f"[Consensus] User {uid_str} is the subject of incident {incident.incident_id} and was blocked from voting."
                )
                return False, "Conflict of interest: You are the subject of this security incident and cannot participate in its consensus review."

        # 2. Check policy role and ownership
        is_owner = policy.is_recovery_owner(uid_str) or (guild and getattr(guild, "owner_id", None) and str(guild.owner_id) == uid_str)
        is_trusted = policy.is_trusted_recovery_actor(uid_str)
        is_extra = guild and AntiNukeManager.is_owner_or_extra_owner(guild, uid_str)

        # 3. Check for revoked permissions if guild member is accessible
        if guild and hasattr(guild, "get_member"):
            member = guild.get_member(int(uid_str))
            if member:
                perms = getattr(member, "guild_permissions", Permissions())
                has_admin = getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False)
                # If neither owner nor explicit trusted admin nor holds admin perms, revoked!
                if not is_owner and not is_trusted and not is_extra and not has_admin:
                    return False, "Unauthorized: Your administrative permissions have been revoked."
            elif not is_owner and not is_trusted and not is_extra:
                return False, "Unauthorized: You are not a recognized member of this server."

        if is_owner or is_trusted or is_extra:
            return True, "Eligible"

        return False, "Unauthorized: You are not a designated recovery administrator for this server."

    def _get_incident_subject_ids(self, incident: Incident) -> Set[str]:
        """Extracts all suspect / subject actor IDs associated with an incident."""
        subjects: Set[str] = set()
        for a in incident.relevant_actors:
            aid = str(a.get("actor_id", ""))
            if aid and not aid.startswith("system:"):
                subjects.add(aid)
        if incident.metadata.get("subject_id"):
            subjects.add(str(incident.metadata["subject_id"]))
        if incident.metadata.get("actor_id"):
            subjects.add(str(incident.metadata["actor_id"]))
        return subjects

    # Consensus Voting & Decision Submission
    async def submit_vote(
        self,
        guild: Any,
        incident_id: str,
        reviewer_id: Union[str, int],
        reviewer_name: Optional[str] = None,
        choice: str = ReviewChoice.CONFIRM,
        reason: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Atomically submits or updates an administrator's vote on an incident.
        Enforces quorum calculations, checks for continuing threats, and dispatches actions.
        """
        if choice not in ReviewChoice.ALL:
            return {
                "success": False,
                "error": f"Invalid vote choice '{choice}'. Must be one of: {', '.join(ReviewChoice.ALL)}",
            }

        incident = self.incident_manager.get_incident(incident_id)
        if not incident:
            return {"success": False, "error": f"Incident {incident_id} not found."}

        gid = str(guild.id if guild else incident.guild_id)
        policy = self.protection_service.get_policy(gid)

        # Lock this incident for atomic transaction
        lock = self._get_incident_lock(incident_id)
        async with lock:
            # 1. Eligibility Check
            eligible, el_reason = self.verify_reviewer_eligibility(guild, reviewer_id, policy, incident)
            if not eligible:
                return {"success": False, "error": el_reason, "eligible": False}

            uid_str = str(reviewer_id)
            existing_vote = incident.votes.get(uid_str)

            # 2. Idempotency & Vote Correction Handling
            action_type = "voted"
            previous_choice = None

            if existing_vote:
                if existing_vote.choice == choice and not (choice == ReviewChoice.AUTHORIZE_RECOVERY and force):
                    # Duplicate vote with same choice -> acknowledge idempotently without double-counting
                    tallies = self._calculate_tallies(incident)
                    return {
                        "success": True,
                        "action": "duplicate",
                        "choice": choice,
                        "tallies": tallies,
                        "message": f"Vote already recorded for '{choice}'. Duplicate interaction ignored.",
                        "incident_status": incident.status,
                    }
                else:
                    # Vote correction
                    if not policy.allow_vote_correction:
                        return {"success": False, "error": "Vote corrections are disabled by server policy."}

                    previous_choice = existing_vote.choice
                    existing_vote.correct(new_choice=choice, reason=reason)
                    action_type = "corrected"
                    incident.add_decision(
                        actor_id=uid_str,
                        actor_name=reviewer_name or existing_vote.admin_name,
                        decision_type=ReviewDecisionType.VOTE_CORRECTION,
                        reason=reason or f"Reviewer changed vote from {previous_choice} to {choice}",
                        metadata={"old_choice": previous_choice, "new_choice": choice},
                    )
            else:
                # Fresh vote
                vote = AdminVote(
                    admin_id=uid_str,
                    admin_name=reviewer_name,
                    choice=choice,
                    approved=(choice != ReviewChoice.DISMISS),
                    reason=reason,
                )
                incident.votes[uid_str] = vote
                incident.add_decision(
                    actor_id=uid_str,
                    actor_name=reviewer_name,
                    decision_type=ReviewDecisionType.VOTE_APPROVE if choice != ReviewChoice.DISMISS else ReviewDecisionType.VOTE_REJECT,
                    reason=reason or f"Vote cast: {choice}",
                    metadata={"choice": choice},
                )

            # 3. Recalculate Quorum Tallies
            tallies = self._calculate_tallies(incident)
            is_owner = policy.is_recovery_owner(uid_str) or (guild and getattr(guild, "owner_id", None) and str(guild.owner_id) == uid_str)

            quorum_met = False
            transition_details = ""

            # 4. Process Decision Transitions
            if choice == ReviewChoice.CONFIRM:
                # Quorum check for threat confirmation
                needed = policy.confirmation_quorum
                if is_owner or tallies[ReviewChoice.CONFIRM] >= needed:
                    quorum_met = True
                    incident.status = IncidentStatus.CONFIRMED
                    incident.add_decision(
                        actor_id="system:sentinel:consensus",
                        decision_type=ReviewDecisionType.CONFIRM,
                        reason=f"Threat confirmed by consensus ({tallies[ReviewChoice.CONFIRM]}/{needed} votes or owner approval).",
                    )
                    transition_details = "Incident status updated to CONFIRMED."

            elif choice == ReviewChoice.DISMISS:
                # Quorum check for false alarm dismissal (e.g. 3 distinct admins)
                needed = policy.dismissal_quorum
                if is_owner or tallies[ReviewChoice.DISMISS] >= needed:
                    quorum_met = True
                    # Execute dismissal safeguards:
                    # 1. Update status to DISMISSED
                    incident.status = IncidentStatus.DISMISSED
                    incident.add_decision(
                        actor_id="system:sentinel:consensus",
                        decision_type=ReviewDecisionType.DISMISS,
                        reason=f"Incident marked as False Alarm by consensus ({tallies[ReviewChoice.DISMISS]}/{needed} votes or owner approval).",
                    )
                    transition_details = (
                        f"Incident dismissed by consensus ({tallies[ReviewChoice.DISMISS]}/{needed} votes). "
                        f"Forensic evidence and audit logs remain permanently preserved."
                    )
                    
                    # 2. Lift active lockdown if containment was active for this incident
                    active_lck = self.journal.get_active_lockdown_for_guild(gid)
                    if active_lck and active_lck.incident_id == incident.incident_id:
                        try:
                            rec = await self.lockdown_manager.restore_lockdown(
                                guild=guild,
                                lockdown_id=active_lck.lockdown_id,
                                admin_user_id=uid_str,
                                policy=policy,
                            )
                            transition_details += f" Server containment lifted ({rec.summary.get('restored', 0)} resources restored)."
                        except Exception as lck_err:
                            logger.error(f"[Consensus] Auto-restore on dismissal failed: {lck_err}")
                            transition_details += f" Warning: Containment rollback error: {lck_err}"

            elif choice == ReviewChoice.REQUEST_INFO:
                incident.status = IncidentStatus.UNDER_REVIEW
                incident.add_decision(
                    actor_id=uid_str,
                    actor_name=reviewer_name,
                    decision_type=ReviewDecisionType.REQUEST_INFO,
                    reason=reason or "Reviewer requested more information or forensic clarification.",
                )
                transition_details = "Information request logged. Incident placed UNDER_REVIEW."

            elif choice == ReviewChoice.KEEP_LOCKDOWN:
                incident.status = IncidentStatus.UNDER_REVIEW
                incident.add_decision(
                    actor_id=uid_str,
                    actor_name=reviewer_name,
                    decision_type=ReviewDecisionType.LOCKDOWN,
                    reason=reason or "Reviewer voted to keep emergency containment active.",
                )
                transition_details = "Containment confirmed active by reviewer."

            elif choice == ReviewChoice.AUTHORIZE_RECOVERY:
                needed = policy.recovery_quorum
                if is_owner or tallies[ReviewChoice.AUTHORIZE_RECOVERY] >= needed:
                    quorum_met = True
                    
                    # Verify if an ongoing attack is still active on this guild
                    has_active_threat, threat_reason = self.check_active_attack_in_progress(gid, incident_id)
                    if has_active_threat and not force:
                        transition_details = (
                            f"⚠️ **Warning:** Active destructive activity is still detected ({threat_reason}). "
                            f"Recovery authorization logged ({tallies[ReviewChoice.AUTHORIZE_RECOVERY]}/{needed}), "
                            f"but automated rollback was paused for safety. Use force recovery if intended."
                        )
                    else:
                        active_lck = self.journal.get_active_lockdown_for_guild(gid)
                        if active_lck:
                            try:
                                rec = await self.lockdown_manager.restore_lockdown(
                                    guild=guild,
                                    lockdown_id=active_lck.lockdown_id,
                                    admin_user_id=uid_str,
                                    policy=policy,
                                    force=force,
                                )
                                incident.add_decision(
                                    actor_id=uid_str,
                                    actor_name=reviewer_name,
                                    decision_type=ReviewDecisionType.RESTORE,
                                    reason=f"Recovery executed by consensus ({tallies[ReviewChoice.AUTHORIZE_RECOVERY]}/{needed}). Status: {rec.status}.",
                                )
                                transition_details = (
                                    f"Server permissions successfully restored ({rec.summary.get('restored', 0)} entries). "
                                    f"Status: {rec.status}."
                                )
                            except Exception as rec_err:
                                transition_details = f"Recovery attempt failed: {rec_err}"
                        else:
                            transition_details = "Recovery authorization recorded, but no active lockdown session was found."

            # If a vote correction caused a previously met quorum to drop (e.g. dismissals dropped from 3 to 2),
            # adjust incident status back to UNDER_REVIEW
            if previous_choice == ReviewChoice.DISMISS and choice != ReviewChoice.DISMISS:
                needed = policy.dismissal_quorum
                if not is_owner and tallies[ReviewChoice.DISMISS] < needed and incident.status == IncidentStatus.DISMISSED:
                    incident.status = IncidentStatus.UNDER_REVIEW
                    incident.add_decision(
                        actor_id="system:sentinel:consensus",
                        decision_type="quorum_revoked",
                        reason=f"Dismissal quorum dropped below {needed} following vote correction. Incident reopened.",
                    )
                    transition_details += f" (Dismissal quorum dropped; incident reopened for review)."

            # Persist updated incident
            self.incident_manager._schedule_persist_incident(incident)

            logger.info(
                f"[Consensus] Processed vote by {uid_str} ({action_type}: {choice}) on incident {incident_id}. "
                f"Tallies: {tallies}. Quorum Met: {quorum_met}."
            )

            return {
                "success": True,
                "action": action_type,
                "choice": choice,
                "previous_choice": previous_choice,
                "tallies": tallies,
                "quorums": {
                    "confirm": policy.confirmation_quorum,
                    "dismiss": policy.dismissal_quorum,
                    "recovery": policy.recovery_quorum,
                },
                "quorum_met": quorum_met,
                "incident_status": incident.status,
                "details": transition_details,
            }

    def _calculate_tallies(self, incident: Incident) -> Dict[str, int]:
        """Calculates current count of unique reviewers for each choice."""
        tallies = {c: 0 for c in ReviewChoice.ALL}
        for vote in incident.votes.values():
            if vote.choice in tallies:
                tallies[vote.choice] += 1
        return tallies

    def check_active_attack_in_progress(self, guild_id: str, current_incident_id: str) -> Tuple[bool, str]:
        """
        Validates if ongoing destructive attack activity is currently occurring on the server.
        Checks active incidents and recent correlation signals.
        """
        active_incs = self.incident_manager.get_active_incidents(guild_id)
        other_active = [i for i in active_incs if i.incident_id != current_incident_id and i.is_emergency]
        if other_active:
            return True, f"{len(other_active)} additional emergency incident(s) active on server"
        
        # Check current incident latest activity window (within last 30s)
        inc = self.incident_manager.get_incident(current_incident_id)
        if inc and (time.time() - inc.latest_seen_at) < 30.0 and inc.is_emergency:
            return True, f"New signals intercepted within the last {int(time.time() - inc.latest_seen_at)} seconds"

        return False, "No active destructive activity detected"

    # Inspection & Audit APIs
    def get_consensus_summary(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Provides full consensus breakdown, active votes, quorum progress, and audit trail."""
        incident = self.incident_manager.get_incident(incident_id)
        if not incident:
            return None

        policy = self.protection_service.get_policy(incident.guild_id)
        tallies = self._calculate_tallies(incident)

        votes_list = []
        for v in incident.votes.values():
            votes_list.append({
                "admin_id": v.admin_id,
                "admin_name": v.admin_name,
                "choice": v.choice,
                "previous_choice": v.previous_choice,
                "voted_at": v.voted_at,
                "corrected_at": v.corrected_at,
                "correction_count": len(v.correction_history),
                "reason": v.reason,
            })

        return {
            "incident_id": incident.incident_id,
            "guild_id": incident.guild_id,
            "status": incident.status,
            "severity": incident.severity,
            "confidence": incident.confidence,
            "total_votes": len(incident.votes),
            "tallies": tallies,
            "quorums": {
                "confirm": policy.confirmation_quorum,
                "dismiss": policy.dismissal_quorum,
                "recovery": policy.recovery_quorum,
            },
            "quorum_progress": {
                "confirm": f"{tallies[ReviewChoice.CONFIRM]}/{policy.confirmation_quorum}",
                "dismiss": f"{tallies[ReviewChoice.DISMISS]}/{policy.dismissal_quorum}",
                "recovery": f"{tallies[ReviewChoice.AUTHORIZE_RECOVERY]}/{policy.recovery_quorum}",
            },
            "votes": votes_list,
            "decision_history": [d.to_dict() for d in incident.decision_history[-10:]],
            "evidence_count": len(incident.evidence_references),
        }


# Global singleton instance
incident_consensus_manager = IncidentConsensusManager.get_instance()


class IncidentReviewView(ui.View):
    """
    Interactive review view with buttons allowing authorized administrators
    to cast consensus votes: Confirm, Dismiss, Request Info, Keep Lockdown, Authorize Recovery.
    """
    def __init__(
        self,
        incident: Incident,
        policy: Optional[SecurityResponsePolicy] = None,
        consensus_mgr: Optional[IncidentConsensusManager] = None,
        timeout: Optional[float] = 86400.0,
    ):
        super().__init__(timeout=timeout)
        self.incident = incident
        self.policy = policy or get_default_response_policy(incident.guild_id)
        self.consensus_mgr = consensus_mgr or incident_consensus_manager

        # Incident Assessment Decisions
        self.btn_confirm = ui.Button(
            style=ButtonStyle.danger,
            label="Confirm Threat",
            custom_id=f"sentinel:review:confirm:{incident.incident_id}",
            emoji=get_emoji("shield", "🛡️"),
        )
        self.btn_confirm.callback = self._handle_confirm
        self.add_item(self.btn_confirm)

        self.btn_dismiss = ui.Button(
            style=ButtonStyle.secondary,
            label="Dismiss (False Alarm)",
            custom_id=f"sentinel:review:dismiss:{incident.incident_id}",
            emoji=get_emoji("check", "✅"),
        )
        self.btn_dismiss.callback = self._handle_dismiss
        self.add_item(self.btn_dismiss)

        self.btn_request_info = ui.Button(
            style=ButtonStyle.secondary,
            label="Request Info",
            custom_id=f"sentinel:review:request_info:{incident.incident_id}",
            emoji=get_emoji("info", "ℹ️"),
        )
        self.btn_request_info.callback = self._handle_request_info
        self.add_item(self.btn_request_info)

        # Protective Containment Controls
        self.btn_keep_lockdown = ui.Button(
            style=ButtonStyle.danger,
            label="Keep Lockdown",
            custom_id=f"sentinel:review:keep_lockdown:{incident.incident_id}",
            emoji=get_emoji("lock", "🔒"),
        )
        self.btn_keep_lockdown.callback = self._handle_keep_lockdown
        self.add_item(self.btn_keep_lockdown)

        self.btn_authorize_recovery = ui.Button(
            style=ButtonStyle.success,
            label="Authorize Recovery",
            custom_id=f"sentinel:review:authorize_recovery:{incident.incident_id}",
            emoji=get_emoji("unlock", "🔓"),
        )
        self.btn_authorize_recovery.callback = self._handle_authorize_recovery
        self.add_item(self.btn_authorize_recovery)

    async def _handle_vote_interaction(self, interaction: Any, choice: str) -> None:
        user = getattr(interaction, "user", None)
        if not user:
            return
        guild = getattr(interaction, "guild", None)
        res = await self.consensus_mgr.submit_vote(
            guild=guild,
            incident_id=self.incident.incident_id,
            reviewer_id=user.id,
            reviewer_name=str(user),
            choice=choice,
        )
        if not res.get("success"):
            err = res.get("error", "Vote could not be processed.")
            if hasattr(interaction, "response") and not interaction.response.is_done():
                await interaction.response.send_message(content=f"❌ {err}", ephemeral=True)
            elif hasattr(interaction, "followup"):
                await interaction.followup.send(content=f"❌ {err}", ephemeral=True)
            return

        tallies = res.get("tallies", {})
        action_word = "corrected to" if res.get("action") == "corrected" else "recorded for"
        if res.get("action") == "duplicate":
            msg = f"ℹ️ Your vote is already recorded as `{choice}`.\n"
        else:
            msg = f"✅ Vote successfully {action_word} `{choice}`.\n"

        msg += (
            f"• **Current Progress:** Confirm ({tallies.get(ReviewChoice.CONFIRM, 0)}/{self.policy.confirmation_quorum}) | "
            f"Dismiss ({tallies.get(ReviewChoice.DISMISS, 0)}/{self.policy.dismissal_quorum}) | "
            f"Recovery ({tallies.get(ReviewChoice.AUTHORIZE_RECOVERY, 0)}/{self.policy.recovery_quorum})\n"
        )
        if res.get("details"):
            msg += f"• **Result:** {res.get('details')}\n"

        if hasattr(interaction, "response") and not interaction.response.is_done():
            await interaction.response.send_message(content=msg, ephemeral=True)
        elif hasattr(interaction, "followup"):
            await interaction.followup.send(content=msg, ephemeral=True)

    async def _handle_confirm(self, interaction: Any):
        await self._handle_vote_interaction(interaction, ReviewChoice.CONFIRM)

    async def _handle_dismiss(self, interaction: Any):
        await self._handle_vote_interaction(interaction, ReviewChoice.DISMISS)

    async def _handle_request_info(self, interaction: Any):
        await self._handle_vote_interaction(interaction, ReviewChoice.REQUEST_INFO)

    async def _handle_keep_lockdown(self, interaction: Any):
        await self._handle_vote_interaction(interaction, ReviewChoice.KEEP_LOCKDOWN)

    async def _handle_authorize_recovery(self, interaction: Any):
        await self._handle_vote_interaction(interaction, ReviewChoice.AUTHORIZE_RECOVERY)


def build_incident_review_container(
    incident: Incident,
    policy: SecurityResponsePolicy,
    summary: Optional[Dict[str, Any]] = None,
) -> ContainerBuilder:
    """
    Renders an audit and consensus review panel for a security incident.
    """
    if summary is None:
        summary = incident_consensus_manager.get_consensus_summary(incident.incident_id) or {}

    tallies = summary.get("tallies", {})
    quorums = summary.get("quorums", {
        "confirm": policy.confirmation_quorum,
        "dismiss": policy.dismissal_quorum,
        "recovery": policy.recovery_quorum,
    })

    # Status coloring
    if incident.status == IncidentStatus.CONFIRMED:
        color = COLORS.get("danger", "#ED4245")
        status_icon = "🚨"
    elif incident.status == IncidentStatus.DISMISSED:
        color = COLORS.get("success", "#3FD438")
        status_icon = "✅"
    elif incident.status == IncidentStatus.CONTAINED:
        color = COLORS.get("success", "#3FD438")
        status_icon = "🛡️"
    else:
        color = COLORS.get("warning", "#F59E0B")
        status_icon = "⚖️"

    # Compile actors
    actors_str = ", ".join(f"<@{a.get('actor_id')}>" for a in incident.relevant_actors[:3]) or "Unknown / System"

    # Compile reviewers and votes list
    votes = summary.get("votes", [])
    if votes:
        vote_lines = []
        for v in votes:
            corr_str = f" *(changed from {v['previous_choice']})*" if v.get("previous_choice") else ""
            vote_lines.append(f"• <@{v['admin_id']}>: `{v['choice'].upper()}`{corr_str}")
        votes_display = "\n".join(vote_lines)
    else:
        votes_display = "*No votes recorded yet. Authorized admins may cast their vote below.*"

    body_text = (
        f"**Threat Pattern:** `{incident.trigger_rule_id or 'Burst Activity'}`\n"
        f"**Severity:** `{incident.severity.upper()}` | **Confidence:** `{incident.confidence.upper()}`\n"
        f"**Accused Actor(s):** {actors_str}\n"
        f"**Monitored Events:** `{incident.event_count}` correlated\n"
        f"**Forensic Proof:** `{len(incident.evidence_references)}` evidence reference(s) preserved\n\n"
        f"### 📊 Consensus Quorum Progress\n"
        f"• **Threat Confirmation:** `{tallies.get(ReviewChoice.CONFIRM, 0)}/{quorums.get('confirm', 2)}` votes required\n"
        f"• **False Alarm Dismissal:** `{tallies.get(ReviewChoice.DISMISS, 0)}/{quorums.get('dismiss', 3)}` distinct reviewer votes required\n"
        f"• **Emergency Recovery:** `{tallies.get(ReviewChoice.AUTHORIZE_RECOVERY, 0)}/{quorums.get('recovery', 2)}` approvals required\n\n"
        f"### 🗳️ Reviewer Votes & Corrections\n"
        f"{votes_display}\n\n"
        f"-# *Note: Dismissing an incident suppresses active alerts for this incident but NEVER deletes forensic proof or grants global bypass to suspected actors.*"
    )

    box = (
        ContainerBuilder()
        .set_accent_color(color)
        .add_text_display(f"### {status_icon} Incident Consensus Review: `{incident.incident_id}`")
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(body_text)
        .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
        .add_text_display(f"-# {settings.BOT_NAME} Security Governance • Multi-Admin Consensus")
    )
    return box
