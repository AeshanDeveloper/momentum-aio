"""
Sentinel™ Security Incident Manager.

Agent 4 of 8 Security Core: Centralized incident lifecycle coordinator,
signal correlation & grouping, reversible snapshot management, admin voting,
and evidence preservation.

Key capabilities:
- Groups incoming ThreatSignals into cohesive, contextual Incident aggregates.
- Fast-path execution: immediately marks and logs emergency containment without
  waiting for slow human consensus or DB latency.
- Strict Reversibility: Manages PermissionSnapshots tracking exact pre-lockdown
  baselines and modified diffs to guarantee clean rollbacks.
- Strict Evidence Preservation: Never deletes incident records upon admin dismissal
  or correction; updates status, logs decision, and retains forensic proof.
- Shadow Mode Safety: Default-enabled shadow mode prevents unintended production
  disruptions while logging full simulated containment records.
- Thread & Async Safe: Per-guild locks guarantee deduplication under concurrent bursts.
- Branded Formatting: Embeds and recovery notifications utilize global configuration
  (colors, emojis, images, settings).
"""

from __future__ import annotations

import time
import uuid
import json
import asyncio
import inspect
import threading
from typing import Dict, List, Optional, Set, Any, Tuple, Union

import discord

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.logging.logger import logger
from database.database import database
from core.security.security_event import AttributionConfidence
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


class IncidentManager:
    """
    Coordinator of Sentinel's Incident response pipeline.
    Maintains in-memory incident cache, provides thread-safe grouping,
    evaluates fast-path emergency protection, and persists to MongoDB.
    """

    _instance: Optional["IncidentManager"] = None

    @classmethod
    def get_instance(cls) -> "IncidentManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # In-memory incident repository: guild_id -> {incident_id: Incident}
        self._incidents: Dict[str, Dict[str, Incident]] = {}
        # Snapshot repository: snapshot_id -> PermissionSnapshot
        self._snapshots: Dict[str, PermissionSnapshot] = {}
        # Concurrency control per guild
        self._guild_async_locks: Dict[str, asyncio.Lock] = {}
        self._sync_lock = threading.RLock()
        # Incident lifecycle subscribers (e.g. Agent 5 lockdown executor, alert dispatchers)
        self._incident_subscribers: List[Any] = []
        self._is_attached_to_correlation: bool = False

    def attach_to_correlation_engine(self, engine: Optional[Any] = None) -> None:
        """Subscribes the incident manager to the security correlation engine stream."""
        target_engine = engine or security_correlation_engine
        target_engine.subscribe_signals(self.on_threat_signal)
        self._is_attached_to_correlation = True
        logger.info("[IncidentManager] Subscribed to SecurityCorrelationEngine threat stream")

    def subscribe_incidents(self, subscriber: Any) -> None:
        """Registers a listener for incident lifecycle updates."""
        if subscriber not in self._incident_subscribers:
            self._incident_subscribers.append(subscriber)

    def _get_guild_lock(self, guild_id: str) -> asyncio.Lock:
        """Retrieves or creates an asyncio.Lock for a specific guild."""
        gid = str(guild_id)
        with self._sync_lock:
            if gid not in self._guild_async_locks:
                self._guild_async_locks[gid] = asyncio.Lock()
            return self._guild_async_locks[gid]

    # Signal Ingestion & Grouping
    def on_threat_signal(self, signal: ThreatSignal) -> None:
        """
        Synchronous / task callback invoked when SecurityCorrelationEngine emits a signal.
        Schedules async handling safely if loop is running, or falls back to synchronous path.
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.handle_threat_signal(signal))
                return
        except RuntimeError:
            pass
        self.process_signal_sync(signal)

    async def handle_threat_signal(
        self,
        signal: ThreatSignal,
        policy: Optional[GuildSecurityPolicy] = None,
    ) -> Tuple[Incident, AssessmentResult]:
        """
        Asynchronously handles a ThreatSignal with concurrency safety per guild.
        Performs fast-path assessment, grouping, snapshot reservation, and persistence.
        """
        gid = str(signal.guild_id)
        lock = self._get_guild_lock(gid)
        async with lock:
            return self._process_signal_internal(signal, policy)

    def process_signal_sync(
        self,
        signal: ThreatSignal,
        policy: Optional[GuildSecurityPolicy] = None,
    ) -> Tuple[Incident, AssessmentResult]:
        """Synchronous version for non-async environments or synchronous unit tests."""
        with self._sync_lock:
            return self._process_signal_internal(signal, policy)

    def _process_signal_internal(
        self,
        signal: ThreatSignal,
        policy: Optional[GuildSecurityPolicy] = None,
    ) -> Tuple[Incident, AssessmentResult]:
        """
        Core synchronous execution path for signal assessment and incident grouping.
        """
        gid = str(signal.guild_id)
        guild_policy = policy or threat_assessment_engine.get_guild_policy(gid)

        # 1. Immediate Threat Assessment
        assessment = threat_assessment_engine.assess_signal(signal, guild_policy)

        # 2. Correlate with Active Incident in Guild
        incident = self._find_matching_active_incident(signal, guild_policy)

        if incident:
            # Merge signal into existing active incident
            incident.add_signal(signal)
            incident.add_decision(
                actor_id="system:sentinel",
                decision_type="signal_merged",
                reason=f"Correlated signal {signal.signal_id} ({signal.pattern_name or signal.pattern_id}) merged into incident",
            )
        else:
            # Create a new Incident aggregate root
            incident = Incident(
                guild_id=gid,
                title=f"Security Alert: {signal.pattern_name or signal.pattern_id}",
                status=IncidentStatus.ACTIVE,
                severity=signal.severity,
                confidence=signal.confidence,
                attribution_confidence=signal.attribution_confidence,
                is_emergency=assessment.is_emergency,
                is_shadow_mode=assessment.is_shadow_mode,
                is_whitelisted_actor_involved=signal.is_whitelisted_actor,
                first_seen_at=signal.timestamp,
                latest_seen_at=signal.timestamp,
                recovery_code=assessment.recovery_plan.get("recovery_code"),
                recovery_instructions=assessment.recovery_plan.get("instructions"),
                metadata={"initial_pattern": signal.pattern_id},
            )
            incident.add_signal(signal)
            incident.add_decision(
                actor_id="system:sentinel",
                decision_type="incident_created",
                reason=f"Incident opened due to pattern {signal.pattern_id} (Threat Score: {assessment.threat_score})",
            )
            with self._sync_lock:
                if gid not in self._incidents:
                    self._incidents[gid] = {}
                self._incidents[gid][incident.incident_id] = incident

        # 3. Emergency Protective Response Evaluation
        if assessment.should_trigger_immediate_response:
            has_action = any(
                a.action_type == assessment.recommended_action
                for a in incident.protective_actions
            )
            if not has_action:
                self._apply_emergency_response(incident, assessment, guild_policy)

        # 4. Asynchronous Write-Through Persistence
        self._schedule_persist_incident(incident)

        # 5. Notify Incident Subscribers
        self._notify_subscribers(incident, assessment)

        return incident, assessment

    def _find_matching_active_incident(
        self,
        signal: ThreatSignal,
        policy: GuildSecurityPolicy,
    ) -> Optional[Incident]:
        """
        Locates an active/under_review/contained incident for the same guild eligible for grouping.
        Matches by recent time window and either actor affinity or vector affinity.
        """
        gid = str(signal.guild_id)
        with self._sync_lock:
            guild_incs = list(self._incidents.get(gid, {}).values())

        if not guild_incs:
            return None

        window = policy.incident_grouping_window_seconds
        now = signal.timestamp

        for inc in reversed(guild_incs):
            # Merge into active, under-review, or ongoing contained incidents
            if inc.status not in (IncidentStatus.ACTIVE, IncidentStatus.UNDER_REVIEW, IncidentStatus.CONTAINED):
                continue

            # Check time correlation window
            if abs(now - inc.latest_seen_at) > window:
                continue

            # Affinity check:
            # A) Same actor
            if signal.actor_id and any(a.get("actor_id") == str(signal.actor_id) for a in inc.relevant_actors):
                return inc

            # B) Overlapping target IDs
            if signal.target_ids and any(str(t) in inc.relevant_targets for t in signal.target_ids):
                return inc

            # C) Coordinated destructive multi-vector attack on the same guild
            destructive_patterns = {
                PatternID.RAPID_BAN_BURST,
                PatternID.RAPID_KICK_BURST,
                PatternID.REPEATED_CHANNEL_DELETIONS,
                PatternID.REPEATED_ROLE_DELETIONS,
                PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION,
                PatternID.COORDINATED_MULTI_VECTOR,
            }
            if signal.pattern_id in destructive_patterns and any(p in destructive_patterns for p in inc.matched_patterns):
                return inc

        return None

    def _apply_emergency_response(
        self,
        incident: Incident,
        assessment: AssessmentResult,
        policy: GuildSecurityPolicy,
    ) -> None:
        """
        Fast-path emergency containment handler.
        Creates pre-lockdown permission snapshot and registers the protective action.
        """
        # Determine execution status based on shadow mode
        status = ActionExecutionStatus.SIMULATED_SHADOW_MODE if assessment.is_shadow_mode else ActionExecutionStatus.ATTEMPTED

        # Create or reserve baseline PermissionSnapshot for reversible rollback
        snapshot = self.create_permission_snapshot(
            guild_id=incident.guild_id,
            incident_id=incident.incident_id,
            metadata={
                "trigger_signal": assessment.signal_id,
                "threat_score": assessment.threat_score,
                "recovery_code": assessment.recovery_plan.get("recovery_code"),
            },
        )

        # Record action in incident
        action = incident.record_action(
            action_type=assessment.recommended_action,
            status=status,
            is_shadow_mode=assessment.is_shadow_mode,
            target_ids=assessment.target_ids,
            details={
                "threat_score": assessment.threat_score,
                "recommended_action": assessment.recommended_action,
                "recovery_code": assessment.recovery_plan.get("recovery_code"),
                "shielded_bot_id": assessment.recovery_plan.get("shielded_bot_id"),
                "shielded_admin_count": len(assessment.recovery_plan.get("shielded_admin_ids", [])),
            },
            snapshot_id=snapshot.snapshot_id,
        )

        decision_reason = (
            f"Autonomous containment triggered (Score: {assessment.threat_score}). "
            f"Mode: {'SHADOW (Simulated)' if assessment.is_shadow_mode else 'LIVE ENFORCEMENT'}. "
            f"Action: {assessment.recommended_action}."
        )

        incident.add_decision(
            actor_id="system:sentinel",
            decision_type=ReviewDecisionType.LOCKDOWN,
            reason=decision_reason,
            metadata={"action_id": action.action_id, "snapshot_id": snapshot.snapshot_id},
        )

        # Transition incident to CONTAINED
        incident.status = IncidentStatus.CONTAINED

    # Reversible Permission Snapshot Management
    def create_permission_snapshot(
        self,
        guild_id: str,
        incident_id: str,
        channel_overwrites: Optional[Dict[str, Any]] = None,
        role_permissions: Optional[Dict[str, int]] = None,
        guild_features: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PermissionSnapshot:
        """
        Saves original baseline server permissions before any protective mutations.
        Guarantees clean, reversible restoration.
        """
        snapshot = PermissionSnapshot(
            guild_id=str(guild_id),
            incident_id=incident_id,
            channel_overwrites=channel_overwrites or {},
            role_permissions=role_permissions or {},
            guild_features=guild_features or {},
            metadata=metadata or {},
        )
        with self._sync_lock:
            self._snapshots[snapshot.snapshot_id] = snapshot

        self._schedule_persist_snapshot(snapshot)
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> Optional[PermissionSnapshot]:
        """Retrieves a PermissionSnapshot by ID."""
        with self._sync_lock:
            return self._snapshots.get(snapshot_id)

    def record_snapshot_diff(
        self,
        snapshot_id: str,
        resource_type: str,
        resource_id: str,
        original_state: Any,
        altered_state: Any,
    ) -> bool:
        """Records an exact mutation made during containment for later reversal."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return False
        snapshot.record_diff(resource_type, resource_id, original_state, altered_state)
        self._schedule_persist_snapshot(snapshot)
        return True

    def record_snapshot_restoration(
        self,
        snapshot_id: str,
        restored_by: str,
    ) -> bool:
        """Marks a snapshot as cleanly restored and updates the parent incident."""
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return False
        snapshot.is_restored = True
        snapshot.restored_at = time.time()
        snapshot.restored_by = str(restored_by)

        # Update parent incident if found
        incident = self.get_incident(snapshot.incident_id)
        if incident:
            incident.add_decision(
                actor_id=str(restored_by),
                decision_type=ReviewDecisionType.RESTORE,
                reason=f"Permissions restored using baseline snapshot {snapshot_id}",
            )
            incident.record_action(
                action_type=ProtectiveActionType.RESTORE_PERMISSIONS,
                status=ActionExecutionStatus.EXECUTED,
                is_shadow_mode=False,
                snapshot_id=snapshot_id,
            )
            self._schedule_persist_incident(incident)

        self._schedule_persist_snapshot(snapshot)
        return True

    # Administrative Actions & Consensus
    def record_admin_vote(
        self,
        incident_id: str,
        admin_id: str,
        approved: bool,
        reason: Optional[str] = None,
        admin_name: Optional[str] = None,
    ) -> Optional[Incident]:
        """Records an admin consensus vote on incident resolution."""
        incident = self.get_incident(incident_id)
        if not incident:
            return None

        incident.record_vote(admin_id=admin_id, approved=approved, reason=reason, admin_name=admin_name)
        self._schedule_persist_incident(incident)
        return incident

    def record_admin_decision(
        self,
        incident_id: str,
        admin_id: str,
        decision_type: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Incident]:
        """Appends an administrative decision to the audit trail."""
        incident = self.get_incident(incident_id)
        if not incident:
            return None

        incident.add_decision(
            actor_id=admin_id,
            decision_type=decision_type,
            reason=reason,
            metadata=metadata,
        )
        self._schedule_persist_incident(incident)
        return incident

    def dismiss_incident(
        self,
        incident_id: str,
        admin_id: str,
        reason: str,
        admin_name: Optional[str] = None,
    ) -> Optional[Incident]:
        """
        Marks an incident as DISMISSED (e.g. false positive or authorized drill).
        CRITICAL: Never deletes the incident record or supporting evidence!
        """
        incident = self.get_incident(incident_id)
        if not incident:
            return None

        incident.transition_status(
            new_status=IncidentStatus.DISMISSED,
            actor_id=str(admin_id),
            reason=f"Dismissed by {admin_name or admin_id}: {reason}",
        )
        self._schedule_persist_incident(incident)
        return incident

    def confirm_incident(
        self,
        incident_id: str,
        admin_id: str,
        reason: str,
        admin_name: Optional[str] = None,
    ) -> Optional[Incident]:
        """Marks an incident as CONFIRMED attack."""
        incident = self.get_incident(incident_id)
        if not incident:
            return None

        incident.transition_status(
            new_status=IncidentStatus.CONFIRMED,
            actor_id=str(admin_id),
            reason=f"Confirmed by {admin_name or admin_id}: {reason}",
        )
        self._schedule_persist_incident(incident)
        return incident

    def contain_incident(
        self,
        incident_id: str,
        details: Optional[Dict[str, Any]] = None,
        actor_id: str = "system:sentinel",
    ) -> Optional[Incident]:
        """Updates incident status to CONTAINED following successful mitigation."""
        incident = self.get_incident(incident_id)
        if not incident:
            return None

        incident.transition_status(
            new_status=IncidentStatus.CONTAINED,
            actor_id=actor_id,
            reason=f"Containment verified: {details or {}}",
        )
        self._schedule_persist_incident(incident)
        return incident

    # Query & Inspection APIs
    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Looks up an incident across all guild in-memory caches."""
        with self._sync_lock:
            for guild_incs in self._incidents.values():
                if incident_id in guild_incs:
                    return guild_incs[incident_id]
        return None

    def get_active_incidents(self, guild_id: str) -> List[Incident]:
        """Retrieves all ACTIVE or UNDER_REVIEW incidents for a guild."""
        gid = str(guild_id)
        with self._sync_lock:
            guild_incs = list(self._incidents.get(gid, {}).values())
        return [
            inc for inc in guild_incs
            if inc.status in (IncidentStatus.ACTIVE, IncidentStatus.UNDER_REVIEW)
        ]

    def list_incidents(
        self,
        guild_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Incident]:
        """Lists incidents for a guild with optional status filtering and pagination."""
        gid = str(guild_id)
        with self._sync_lock:
            incs = list(self._incidents.get(gid, {}).values())

        if status:
            incs = [i for i in incs if i.status == status]

        # Sort newest first
        incs.sort(key=lambda x: x.latest_seen_at, reverse=True)
        return incs[offset : offset + limit]

    def search_incidents(
        self,
        guild_id: str,
        actor_id: Optional[str] = None,
        pattern_id: Optional[str] = None,
        min_severity: Optional[str] = None,
    ) -> List[Incident]:
        """Searches incidents matching specific forensic parameters."""
        gid = str(guild_id)
        with self._sync_lock:
            incs = list(self._incidents.get(gid, {}).values())

        results: List[Incident] = []
        severity_ranks = {
            ThreatSeverity.LOW: 1,
            ThreatSeverity.MEDIUM: 2,
            ThreatSeverity.HIGH: 3,
            ThreatSeverity.CRITICAL: 4,
        }
        min_rank = severity_ranks.get(min_severity, 1) if min_severity else 1

        for inc in incs:
            if actor_id and not any(a.get("actor_id") == str(actor_id) for a in inc.relevant_actors):
                continue
            if pattern_id and pattern_id not in inc.matched_patterns:
                continue
            if severity_ranks.get(inc.severity, 1) < min_rank:
                continue
            results.append(inc)

        results.sort(key=lambda x: x.latest_seen_at, reverse=True)
        return results

    def prune_expired_incidents(self, guild_id: str, retention_days: int = 90) -> int:
        """
        Enforces data retention policy.
        Never removes unreviewed, active, or confirmed incidents under investigation.
        """
        gid = str(guild_id)
        cutoff = time.time() - (retention_days * 86400.0)
        pruned_count = 0

        with self._sync_lock:
            if gid not in self._incidents:
                return 0
            keys_to_remove = []
            for inc_id, inc in self._incidents[gid].items():
                if inc.latest_seen_at < cutoff and inc.status in (IncidentStatus.DISMISSED, IncidentStatus.INCONCLUSIVE):
                    keys_to_remove.append(inc_id)

            for k in keys_to_remove:
                self._incidents[gid].pop(k, None)
                pruned_count += 1

        return pruned_count

    # Discord Alert & Recovery Formatting
    def format_incident_embed(
        self,
        incident: Incident,
        assessment: Optional[AssessmentResult] = None,
    ) -> discord.Embed:
        """
        Builds a high-impact branded Discord alert embed.
        Conforms to configurations global (emojis, colors, images, settings).
        """
        is_critical = incident.severity == ThreatSeverity.CRITICAL or (assessment and assessment.is_emergency)
        color_hex = get_color("danger", "#ED4245") if is_critical else get_color("warning", "#FEE75C")
        clean_color = int(color_hex.removeprefix("#"), 16) if isinstance(color_hex, str) else 0xED4245

        embed = discord.Embed(
            title=f"{get_emoji('shield', '🛡️')} {incident.title}",
            color=clean_color,
            timestamp=discord.utils.utcnow(),
        )

        status_emoji = {
            IncidentStatus.ACTIVE: get_emoji("fire", "🔥"),
            IncidentStatus.CONTAINED: get_emoji("lock", "🔒"),
            IncidentStatus.UNDER_REVIEW: get_emoji("eyes", "👀"),
            IncidentStatus.CONFIRMED: get_emoji("check", "✅"),
            IncidentStatus.DISMISSED: get_emoji("cross", "❌"),
        }.get(incident.status, "🛡️")

        embed.description = (
            f"**Incident ID:** `{incident.incident_id}`\n"
            f"**Status:** {status_emoji} `{incident.status.upper()}`\n"
            f"**Severity:** `{incident.severity.upper()}` | **Confidence:** `{incident.confidence.upper()}`\n"
            f"**Execution Mode:** `{'SHADOW MODE (Simulated)' if incident.is_shadow_mode else 'LIVE ENFORCEMENT'}`\n"
        )

        if incident.is_whitelisted_actor_involved:
            embed.description += f"\n⚠️ **Warning:** A whitelisted administrator account was identified in this activity."

        # Key Facts
        if incident.observed_facts:
            facts_lines = []
            for k, v in list(incident.observed_facts.items())[:5]:
                facts_lines.append(f"• **{k.replace('_', ' ').title()}:** `{v}`")
            if facts_lines:
                embed.add_field(name="📊 Observed Facts", value="\n".join(facts_lines), inline=False)

        # Trigger Reasons
        if incident.trigger_reasons:
            embed.add_field(
                name="🚨 Detection Signals",
                value="\n".join(f"• {r}" for r in incident.trigger_reasons[:4]),
                inline=False,
            )

        # Actions & Reversibility
        if incident.protective_actions:
            actions_text = []
            for act in incident.protective_actions[-3:]:
                act_str = f"• **{act.action_type}**: `{act.status}`"
                if act.snapshot_id:
                    act_str += f" (Snapshot: `{act.snapshot_id}`)"
                actions_text.append(act_str)
            embed.add_field(name="🛡️ Protective Actions", value="\n".join(actions_text), inline=False)

        # Recovery Path
        if incident.recovery_code:
            embed.add_field(
                name="🔑 Emergency Recovery",
                value=f"Unlock Code: `{incident.recovery_code}`\nCommand: `{settings.BOT_PREFIX}unlock {incident.recovery_code}`",
                inline=False,
            )

        avatar_url = IMAGES.get("sentinel_avatar", settings.BOT_ICON_URL or "")
        if avatar_url and hasattr(embed, "set_thumbnail"):
            embed.set_thumbnail(url=avatar_url)

        if hasattr(embed, "set_footer"):
            embed.set_footer(
                text=f"{settings.BOT_NAME} Security Core • Reversible Lockdown Framework",
                icon_url=avatar_url or None,
            )
        return embed

    def format_recovery_dm(self, incident: Incident) -> str:
        """Constructs an urgent DM notification for designated recovery admins."""
        code = incident.recovery_code or "N/A"
        return (
            f"🚨 **URGENT SECURITY ALERT: {settings.BOT_NAME}**\n\n"
            f"An emergency containment lockdown was evaluated for your server (`Guild ID: {incident.guild_id}`).\n"
            f"**Incident ID:** `{incident.incident_id}`\n"
            f"**Severity:** `{incident.severity.upper()}`\n"
            f"**Mode:** `{'SHADOW MODE (Simulated)' if incident.is_shadow_mode else 'LIVE ENFORCEMENT'}`\n\n"
            f"**Recovery Procedure:**\n"
            f"1. As a designated recovery administrator, your administrative access has been explicitly shielded.\n"
            f"2. A full permission snapshot (`{incident.snapshot_ids[-1] if incident.snapshot_ids else 'baseline'}`) has been saved.\n"
            f"3. To unlock the server and reverse all changes, run:\n"
            f"   `{settings.BOT_PREFIX}unlock {code}`\n\n"
            f"View incident details and votes in your server's security channel."
        )

    # Database Persistence
    def _schedule_persist_incident(self, incident: Incident) -> None:
        """Asynchronously writes incident to MongoDB without blocking execution."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._persist_incident_async(incident))
        except RuntimeError:
            pass

    async def _persist_incident_async(self, incident: Incident) -> None:
        """Writes incident document to 'security_incidents' collection."""
        try:
            col = database.collection("security_incidents")
            doc = incident.to_dict()
            if hasattr(col, "update_one"):
                res = col.update_one(
                    {"incident_id": incident.incident_id},
                    {"$set": doc},
                    upsert=True,
                )
                if inspect.isawaitable(res):
                    await res
        except Exception as err:
            logger.debug(f"[IncidentManager] Failed to persist incident {incident.incident_id}: {err}")

    def _schedule_persist_snapshot(self, snapshot: PermissionSnapshot) -> None:
        """Asynchronously writes snapshot to MongoDB."""
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._persist_snapshot_async(snapshot))
        except RuntimeError:
            pass

    async def _persist_snapshot_async(self, snapshot: PermissionSnapshot) -> None:
        """Writes snapshot document to 'security_permission_snapshots' collection."""
        try:
            col = database.collection("security_permission_snapshots")
            doc = snapshot.to_dict()
            if hasattr(col, "update_one"):
                res = col.update_one(
                    {"snapshot_id": snapshot.snapshot_id},
                    {"$set": doc},
                    upsert=True,
                )
                if inspect.isawaitable(res):
                    await res
        except Exception as err:
            logger.debug(f"[IncidentManager] Failed to persist snapshot {snapshot.snapshot_id}: {err}")

    def _notify_subscribers(self, incident: Incident, assessment: AssessmentResult) -> None:
        """Dispatches incident update events to registered subscribers."""
        for sub in list(self._incident_subscribers):
            try:
                if inspect.iscoroutinefunction(sub):
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_running():
                            loop.create_task(sub(incident, assessment))
                    except RuntimeError:
                        pass
                else:
                    sub(incident, assessment)
            except Exception as err:
                logger.error(f"[IncidentManager] Error in incident subscriber: {err}")

    def clear_guild(self, guild_id: str) -> None:
        """Clears all in-memory incident cache for a guild."""
        gid = str(guild_id)
        with self._sync_lock:
            self._incidents.pop(gid, None)
            self._guild_async_locks.pop(gid, None)


# Singleton instance
incident_manager = IncidentManager.get_instance()
