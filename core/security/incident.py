"""
Sentinel™ Security Incident and Evidence Reference Models.

Agent 4 of 8 Security Core: Dedicated incident grouping, evidence tracking,
reversible lockdown snapshots, and audit trail records.

Key capabilities:
- Comprehensive Incident aggregate root capturing actors, targets, matched patterns,
  graduated confidence, observed facts vs inferred intent, and decision history.
- Immutable evidence references linking back to normalized SecurityEvent identifiers.
- Reversible PermissionSnapshot recording exact pre-lockdown baseline permissions
  and modified diffs so recovery can cleanly rollback Sentinel's changes without
  stomping on subsequent admin alterations.
- Dedicated tracking of admin decisions, votes, corrections, and protective actions.
- Full serialization/deserialization for MongoDB persistence.
- Adherence to global configuration (emojis, colors, settings, branding).
"""

from __future__ import annotations

import time
import uuid
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Union

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.security.security_event import AttributionConfidence
from core.security.correlation_engine import (
    ThreatSignal,
    ThreatSeverity,
    ThreatConfidence,
    ResponseCategory,
    PatternID,
)


class IncidentStatus:
    """Canonical lifecycle states of a security incident."""
    ACTIVE = "active"
    CONTAINED = "contained"
    UNDER_REVIEW = "under_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    INCONCLUSIVE = "inconclusive"
    RESOLVED = "resolved"

    ALL = {ACTIVE, CONTAINED, UNDER_REVIEW, CONFIRMED, DISMISSED, INCONCLUSIVE, RESOLVED}


class ProtectiveActionType:
    """Canonical protective action types authorized for emergency mitigation."""
    EMERGENCY_LOCKDOWN = "emergency_lockdown"
    ISOLATE_ACTOR = "isolate_actor"
    PAUSE_INVITES = "pause_invites"
    ISOLATE_INTEGRATION = "isolate_integration"
    RESTORE_PERMISSIONS = "restore_permissions"
    ALERT_DISPATCH = "alert_dispatch"

    ALL = {
        EMERGENCY_LOCKDOWN,
        ISOLATE_ACTOR,
        PAUSE_INVITES,
        ISOLATE_INTEGRATION,
        RESTORE_PERMISSIONS,
        ALERT_DISPATCH,
    }


class ActionExecutionStatus:
    """Execution status for protective containment actions."""
    REQUESTED = "requested"
    ATTEMPTED = "attempted"
    EXECUTED = "executed"
    VERIFIED = "verified"
    FAILED = "failed"
    SIMULATED_SHADOW_MODE = "simulated_shadow_mode"

    ALL = {REQUESTED, ATTEMPTED, EXECUTED, VERIFIED, FAILED, SIMULATED_SHADOW_MODE}


class ReviewDecisionType:
    """Types of administrative decisions, reviews, and corrections."""
    CONFIRM = "confirm"
    DISMISS = "dismiss"
    LOCKDOWN = "lockdown"
    RESTORE = "restore"
    VOTE_APPROVE = "vote_approve"
    VOTE_REJECT = "vote_reject"
    COMMENT = "comment"
    REQUEST_INFO = "request_info"
    VOTE_CORRECTION = "vote_correction"
    QUORUM_REVOKED = "quorum_revoked"

    ALL = {
        CONFIRM,
        DISMISS,
        LOCKDOWN,
        RESTORE,
        VOTE_APPROVE,
        VOTE_REJECT,
        COMMENT,
        REQUEST_INFO,
        VOTE_CORRECTION,
        QUORUM_REVOKED,
    }


@dataclass
class EvidenceReference:
    """
    Cryptographically verifiable reference to normalized security evidence.
    Ensures minimum necessary evidence is stored while preserving immutable provenance.
    """
    evidence_id: str = field(default_factory=lambda: f"ev_{uuid.uuid4().hex[:12]}")
    event_id: str = ""
    event_type: str = ""
    actor_id: Optional[str] = None
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    raw_data_hash: str = ""
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def source_type(self) -> str:
        return self.metadata.get("source_type", self.event_type)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "timestamp": self.timestamp,
            "raw_data_hash": self.raw_data_hash,
            "summary": self.summary,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceReference":
        return cls(
            evidence_id=data.get("evidence_id", f"ev_{uuid.uuid4().hex[:12]}"),
            event_id=data.get("event_id", ""),
            event_type=data.get("event_type", ""),
            actor_id=data.get("actor_id"),
            target_id=data.get("target_id"),
            target_type=data.get("target_type"),
            timestamp=float(data.get("timestamp", time.time())),
            raw_data_hash=data.get("raw_data_hash", ""),
            summary=data.get("summary", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PermissionSnapshot:
    """
    Captures exact baseline server state before Sentinel applies protective changes.
    Tracks exact modified diffs so restoration is strictly reversible and never
    overwrites legitimate admin changes made afterward.
    """
    snapshot_id: str = field(default_factory=lambda: f"snap_{uuid.uuid4().hex[:12]}")
    guild_id: str = ""
    incident_id: str = ""
    created_at: float = field(default_factory=time.time)
    channel_overwrites: Dict[str, Dict[str, Dict[str, Optional[bool]]]] = field(default_factory=dict)
    role_permissions: Dict[str, int] = field(default_factory=dict)
    guild_features: Dict[str, Any] = field(default_factory=dict)
    modified_diffs: Dict[str, Any] = field(default_factory=dict)
    checksum: str = ""
    is_restored: bool = False
    restored_at: Optional[float] = None
    restored_by: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self.calculate_checksum()

    def calculate_checksum(self) -> str:
        """Computes SHA-256 fingerprint of the baseline permission snapshot."""
        serialized = json.dumps(
            {
                "guild_id": self.guild_id,
                "channel_overwrites": self.channel_overwrites,
                "role_permissions": self.role_permissions,
                "guild_features": self.guild_features,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def record_diff(self, resource_type: str, resource_id: str, original_state: Any, altered_state: Any) -> None:
        """Records an exact mutation performed by Sentinel."""
        if resource_type not in self.modified_diffs:
            self.modified_diffs[resource_type] = {}
        self.modified_diffs[resource_type][resource_id] = {
            "original": original_state,
            "altered": altered_state,
            "timestamp": time.time(),
        }

    def compute_restoration_plan(self) -> Dict[str, Any]:
        """
        Calculates exact diff changes needed to reverse Sentinel's changes.
        Only modifies resources Sentinel actually changed.
        """
        return {
            "snapshot_id": self.snapshot_id,
            "guild_id": self.guild_id,
            "incident_id": self.incident_id,
            "resources_to_restore": self.modified_diffs,
            "checksum": self.checksum,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "guild_id": self.guild_id,
            "incident_id": self.incident_id,
            "created_at": self.created_at,
            "channel_overwrites": self.channel_overwrites,
            "role_permissions": self.role_permissions,
            "guild_features": self.guild_features,
            "modified_diffs": self.modified_diffs,
            "checksum": self.checksum,
            "is_restored": self.is_restored,
            "restored_at": self.restored_at,
            "restored_by": self.restored_by,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionSnapshot":
        return cls(
            snapshot_id=data.get("snapshot_id", f"snap_{uuid.uuid4().hex[:12]}"),
            guild_id=str(data.get("guild_id", "")),
            incident_id=data.get("incident_id", ""),
            created_at=float(data.get("created_at", time.time())),
            channel_overwrites=data.get("channel_overwrites", {}),
            role_permissions=data.get("role_permissions", {}),
            guild_features=data.get("guild_features", {}),
            modified_diffs=data.get("modified_diffs", {}),
            checksum=data.get("checksum", ""),
            is_restored=bool(data.get("is_restored", False)),
            restored_at=data.get("restored_at"),
            restored_by=data.get("restored_by"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProtectiveActionExecution:
    """Record of a protective containment action taken or simulated by Sentinel."""
    action_id: str = field(default_factory=lambda: f"act_{uuid.uuid4().hex[:12]}")
    action_type: str = ProtectiveActionType.EMERGENCY_LOCKDOWN
    status: str = ActionExecutionStatus.EXECUTED
    is_shadow_mode: bool = False
    executed_at: float = field(default_factory=time.time)
    target_ids: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    snapshot_id: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "status": self.status,
            "is_shadow_mode": self.is_shadow_mode,
            "executed_at": self.executed_at,
            "target_ids": self.target_ids,
            "details": self.details,
            "snapshot_id": self.snapshot_id,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtectiveActionExecution":
        return cls(
            action_id=data.get("action_id", f"act_{uuid.uuid4().hex[:12]}"),
            action_type=data.get("action_type", ProtectiveActionType.EMERGENCY_LOCKDOWN),
            status=data.get("status", ActionExecutionStatus.EXECUTED),
            is_shadow_mode=bool(data.get("is_shadow_mode", False)),
            executed_at=float(data.get("executed_at", time.time())),
            target_ids=data.get("target_ids", []),
            details=data.get("details", {}),
            snapshot_id=data.get("snapshot_id"),
            error=data.get("error"),
        )


@dataclass
class DecisionRecord:
    """Audit log entry capturing administrative and system decisions."""
    decision_id: str = field(default_factory=lambda: f"dec_{uuid.uuid4().hex[:12]}")
    timestamp: float = field(default_factory=time.time)
    actor_id: str = "system:sentinel"
    actor_name: Optional[str] = "Sentinel Security Core"
    decision_type: str = ReviewDecisionType.LOCKDOWN
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "actor_name": self.actor_name,
            "decision_type": self.decision_type,
            "reason": self.reason,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DecisionRecord":
        return cls(
            decision_id=data.get("decision_id", f"dec_{uuid.uuid4().hex[:12]}"),
            timestamp=float(data.get("timestamp", time.time())),
            actor_id=str(data.get("actor_id", "system:sentinel")),
            actor_name=data.get("actor_name", "Sentinel Security Core"),
            decision_type=data.get("decision_type", ReviewDecisionType.LOCKDOWN),
            reason=data.get("reason", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AdminVote:
    """Record of an admin vote on incident resolution."""
    vote_id: str = field(default_factory=lambda: f"vote_{uuid.uuid4().hex[:12]}")
    admin_id: str = ""
    admin_name: Optional[str] = None
    choice: str = "confirm"
    previous_choice: Optional[str] = None
    approved: bool = True
    reason: Optional[str] = None
    voted_at: float = field(default_factory=time.time)
    corrected_at: Optional[float] = None
    correction_history: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def correct(self, new_choice: str, reason: Optional[str] = None) -> None:
        """Records a vote correction with audit history."""
        now = time.time()
        self.correction_history.append({
            "old_choice": self.choice,
            "new_choice": new_choice,
            "timestamp": now,
            "reason": reason,
        })
        self.previous_choice = self.choice
        self.choice = new_choice
        self.corrected_at = now
        self.approved = (new_choice != "dismiss")
        if reason:
            self.reason = reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vote_id": self.vote_id,
            "admin_id": self.admin_id,
            "admin_name": self.admin_name,
            "choice": self.choice,
            "previous_choice": self.previous_choice,
            "approved": self.approved,
            "reason": self.reason,
            "voted_at": self.voted_at,
            "corrected_at": self.corrected_at,
            "correction_history": list(self.correction_history),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdminVote":
        return cls(
            vote_id=data.get("vote_id", f"vote_{uuid.uuid4().hex[:12]}"),
            admin_id=str(data.get("admin_id", "")),
            admin_name=data.get("admin_name"),
            choice=str(data.get("choice", "confirm")),
            previous_choice=data.get("previous_choice"),
            approved=bool(data.get("approved", True)),
            reason=data.get("reason"),
            voted_at=float(data.get("voted_at", time.time())),
            corrected_at=data.get("corrected_at"),
            correction_history=list(data.get("correction_history", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class GuildSecurityPolicy:
    """
    Per-guild security and emergency response policy.
    Crucial: Defaults to shadow mode (testing/simulation) until explicitly enabled.
    """
    guild_id: str = ""
    shadow_mode: bool = True  # DEFAULT TO SHADOW MODE
    auto_lockdown_enabled: bool = False
    recovery_admin_ids: List[str] = field(default_factory=list)
    recovery_channel_id: Optional[str] = None
    exempt_channel_ids: List[str] = field(default_factory=list)
    emergency_threshold_score: float = 75.0
    incident_grouping_window_seconds: float = 300.0  # 5 minutes
    retention_days: int = 90
    vote_quorum: int = 1
    isolate_whitelisted_compromise: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": self.guild_id,
            "shadow_mode": self.shadow_mode,
            "auto_lockdown_enabled": self.auto_lockdown_enabled,
            "recovery_admin_ids": self.recovery_admin_ids,
            "recovery_channel_id": self.recovery_channel_id,
            "exempt_channel_ids": self.exempt_channel_ids,
            "emergency_threshold_score": self.emergency_threshold_score,
            "incident_grouping_window_seconds": self.incident_grouping_window_seconds,
            "retention_days": self.retention_days,
            "vote_quorum": self.vote_quorum,
            "isolate_whitelisted_compromise": self.isolate_whitelisted_compromise,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GuildSecurityPolicy":
        return cls(
            guild_id=str(data.get("guild_id", "")),
            shadow_mode=bool(data.get("shadow_mode", True)),
            auto_lockdown_enabled=bool(data.get("auto_lockdown_enabled", False)),
            recovery_admin_ids=[str(x) for x in data.get("recovery_admin_ids", [])],
            recovery_channel_id=str(data["recovery_channel_id"]) if data.get("recovery_channel_id") else None,
            exempt_channel_ids=[str(x) for x in data.get("exempt_channel_ids", [])],
            emergency_threshold_score=float(data.get("emergency_threshold_score", 75.0)),
            incident_grouping_window_seconds=float(data.get("incident_grouping_window_seconds", 300.0)),
            retention_days=int(data.get("retention_days", 90)),
            vote_quorum=int(data.get("vote_quorum", 1)),
            isolate_whitelisted_compromise=bool(data.get("isolate_whitelisted_compromise", True)),
        )


@dataclass
class Incident:
    """
    Comprehensive Security Incident aggregate root.
    Groups correlated threat signals, forensic facts, snapshots, and administrative
    decision history. Designed for persistence in MongoDB 'security_incidents'.
    """
    incident_id: str = field(default_factory=lambda: f"inc_{uuid.uuid4().hex[:12]}")
    guild_id: str = ""
    title: str = "Detected Security Threat"
    status: str = IncidentStatus.ACTIVE
    severity: str = ThreatSeverity.MEDIUM
    confidence: str = ThreatConfidence.SUSPICIOUS
    attribution_confidence: str = AttributionConfidence.UNKNOWN
    is_emergency: bool = False
    is_shadow_mode: bool = True
    is_whitelisted_actor_involved: bool = False

    # Actors & Targets
    relevant_actors: List[Dict[str, Any]] = field(default_factory=list)
    relevant_targets: List[str] = field(default_factory=list)

    # Patterns & Signals
    matched_patterns: List[str] = field(default_factory=list)
    signal_ids: List[str] = field(default_factory=list)
    trigger_reasons: List[str] = field(default_factory=list)

    # Observation times
    first_seen_at: float = field(default_factory=time.time)
    latest_seen_at: float = field(default_factory=time.time)

    # Distinguish facts from inferences
    observed_facts: Dict[str, Any] = field(default_factory=dict)
    inferred_intent: str = ""

    # Forensics & Reversibility
    evidence_references: List[EvidenceReference] = field(default_factory=list)
    protective_actions: List[ProtectiveActionExecution] = field(default_factory=list)
    snapshot_ids: List[str] = field(default_factory=list)

    # Audit & Consensus
    decision_history: List[DecisionRecord] = field(default_factory=list)
    votes: Dict[str, AdminVote] = field(default_factory=dict)

    recovery_code: Optional[str] = None
    recovery_instructions: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    actor_id: Optional[str] = None
    is_whitelisted_actor: Optional[bool] = None

    def __post_init__(self):
        self.guild_id = str(self.guild_id)
        if self.status not in IncidentStatus.ALL:
            self.status = IncidentStatus.ACTIVE
        if self.severity not in ThreatSeverity.ALL:
            self.severity = ThreatSeverity.MEDIUM
        if self.confidence not in ThreatConfidence.ALL:
            self.confidence = ThreatConfidence.SUSPICIOUS
        if self.actor_id and not any(a.get("actor_id") == str(self.actor_id) for a in self.relevant_actors):
            self.relevant_actors.append({
                "actor_id": str(self.actor_id),
                "is_whitelisted": bool(self.is_whitelisted_actor),
                "attribution_confidence": self.attribution_confidence,
            })
        if self.is_whitelisted_actor:
            self.is_whitelisted_actor_involved = True
        elif not self.actor_id and self.relevant_actors:
            self.actor_id = self.relevant_actors[0].get("actor_id")
        if self.is_whitelisted_actor is None:
            self.is_whitelisted_actor = self.is_whitelisted_actor_involved

    @property
    def trigger_rule_id(self) -> str:
        """Returns the primary trigger rule or matched pattern ID."""
        if self.matched_patterns:
            return self.matched_patterns[0]
        if self.trigger_reasons:
            return self.trigger_reasons[0]
        return str(self.metadata.get("trigger_rule_id", "security_burst"))

    @property
    def event_count(self) -> int:
        """Returns total correlated events or evidence count."""
        return len(self.signal_ids) or len(self.evidence_references) or 1

    def add_signal(self, signal: ThreatSignal) -> None:
        """Merges a correlated ThreatSignal into this active incident."""
        if signal.signal_id not in self.signal_ids:
            self.signal_ids.append(signal.signal_id)

        if signal.pattern_id and signal.pattern_id not in self.matched_patterns:
            self.matched_patterns.append(signal.pattern_id)

        # Update timestamps
        if signal.timestamp < self.first_seen_at:
            self.first_seen_at = signal.timestamp
        if signal.timestamp > self.latest_seen_at:
            self.latest_seen_at = signal.timestamp

        # Upgrade severity if higher
        severity_ranks = {
            ThreatSeverity.LOW: 1,
            ThreatSeverity.MEDIUM: 2,
            ThreatSeverity.HIGH: 3,
            ThreatSeverity.CRITICAL: 4,
        }
        if severity_ranks.get(signal.severity, 0) > severity_ranks.get(self.severity, 0):
            self.severity = signal.severity

        # Upgrade confidence if higher
        confidence_ranks = {
            ThreatConfidence.UNCONFIRMED: 1,
            ThreatConfidence.SUSPICIOUS: 2,
            ThreatConfidence.HIGH_CONFIDENCE: 3,
            ThreatConfidence.CONFIRMED: 4,
        }
        if confidence_ranks.get(signal.confidence, 0) > confidence_ranks.get(self.confidence, 0):
            self.confidence = signal.confidence

        if signal.is_emergency:
            self.is_emergency = True

        if signal.is_whitelisted_actor:
            self.is_whitelisted_actor_involved = True

        # Track actor
        if signal.actor_id:
            actor_entry = {
                "actor_id": str(signal.actor_id),
                "actor_name": signal.actor_name,
                "is_whitelisted": signal.is_whitelisted_actor,
                "attribution_confidence": signal.attribution_confidence,
            }
            if not any(a["actor_id"] == str(signal.actor_id) for a in self.relevant_actors):
                self.relevant_actors.append(actor_entry)

        # Track targets
        for tid in signal.target_ids:
            stid = str(tid)
            if stid not in self.relevant_targets:
                self.relevant_targets.append(stid)

        # Merge trigger reasons
        for r in signal.trigger_reasons:
            if r not in self.trigger_reasons:
                self.trigger_reasons.append(r)

        # Merge observed facts
        for k, v in signal.observed_facts.items():
            if k not in self.observed_facts:
                self.observed_facts[k] = v
            elif isinstance(v, list) and isinstance(self.observed_facts[k], list):
                for item in v:
                    if item not in self.observed_facts[k]:
                        self.observed_facts[k].append(item)
            elif isinstance(v, (int, float)) and isinstance(self.observed_facts[k], (int, float)):
                self.observed_facts[k] = max(self.observed_facts[k], v)

        if signal.inferred_intent and not self.inferred_intent:
            self.inferred_intent = signal.inferred_intent

        # Add evidence references for all event IDs
        for eid in signal.event_ids:
            if not any(ev.event_id == eid for ev in self.evidence_references):
                ev_ref = EvidenceReference(
                    event_id=eid,
                    event_type=signal.pattern_id,
                    actor_id=str(signal.actor_id) if signal.actor_id else None,
                    timestamp=signal.timestamp,
                    summary=f"Event linked to {signal.pattern_name or signal.pattern_id}",
                )
                self.evidence_references.append(ev_ref)

    def record_action(
        self,
        action_type: str,
        status: str,
        is_shadow_mode: bool,
        target_ids: Optional[List[str]] = None,
        details: Optional[Dict[str, Any]] = None,
        snapshot_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> ProtectiveActionExecution:
        """Records a protective action attempt or completion."""
        action = ProtectiveActionExecution(
            action_type=action_type,
            status=status,
            is_shadow_mode=is_shadow_mode,
            target_ids=target_ids or [],
            details=details or {},
            snapshot_id=snapshot_id,
            error=error,
        )
        self.protective_actions.append(action)
        if snapshot_id and snapshot_id not in self.snapshot_ids:
            self.snapshot_ids.append(snapshot_id)
        return action

    def add_decision(
        self,
        actor_id: str,
        decision_type: str,
        reason: str,
        actor_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DecisionRecord:
        """Appends an administrative or autonomous decision to the immutable audit log."""
        record = DecisionRecord(
            actor_id=str(actor_id),
            actor_name=actor_name,
            decision_type=decision_type,
            reason=reason,
            metadata=metadata or {},
        )
        self.decision_history.append(record)
        return record

    def record_vote(self, admin_id: str, approved: bool, reason: Optional[str] = None, admin_name: Optional[str] = None) -> AdminVote:
        """Records an admin consensus vote."""
        aid = str(admin_id)
        vote = AdminVote(admin_id=aid, admin_name=admin_name, approved=approved, reason=reason)
        self.votes[aid] = vote
        self.add_decision(
            actor_id=aid,
            actor_name=admin_name,
            decision_type=ReviewDecisionType.VOTE_APPROVE if approved else ReviewDecisionType.VOTE_REJECT,
            reason=reason or f"Admin vote: {'Approved' if approved else 'Rejected'}",
        )
        return vote

    def add_vote(self, admin_id: str, approved: bool = True, reason: Optional[str] = None, admin_name: Optional[str] = None) -> AdminVote:
        """Convenience alias for record_vote."""
        return self.record_vote(admin_id=admin_id, approved=approved, reason=reason, admin_name=admin_name)

    def add_fact(self, fact_or_key: str, value: Any = True) -> None:
        """Adds an observed forensic fact to the incident."""
        if isinstance(fact_or_key, str):
            self.observed_facts[fact_or_key] = value

    def record_evidence(
        self,
        event_id: Optional[str] = None,
        event_type: str = "",
        summary: str = "",
        actor_id: Optional[str] = None,
        target_id: Optional[str] = None,
        **kwargs: Any,
    ) -> EvidenceReference:
        """Explicitly records an evidence reference to normalized security evidence."""
        eid = event_id or kwargs.pop("evidence_id", None) or f"ev_{uuid.uuid4().hex[:10]}"
        etype = event_type or kwargs.pop("source_type", "evidence")
        details = kwargs.pop("details", {})
        metadata = dict(kwargs)
        if details:
            metadata.update(details)
        if "source_type" not in metadata:
            metadata["source_type"] = etype
        ev = EvidenceReference(
            event_id=eid,
            event_type=etype,
            summary=summary or details.get("choice_label", ""),
            actor_id=actor_id or details.get("respondent_id"),
            target_id=target_id,
            metadata=metadata,
        )
        self.evidence_references.append(ev)
        return ev



    def mark_dismissed(self, admin_id: str, admin_name: Optional[str] = None, reason: str = "") -> None:
        """Marks incident as dismissed (e.g. false alarm) while strictly preserving all forensic evidence."""
        self.status = IncidentStatus.DISMISSED
        self.add_decision(
            actor_id=str(admin_id),
            actor_name=admin_name,
            decision_type=ReviewDecisionType.DISMISS,
            reason=reason or f"Dismissed by {admin_name or admin_id}",
        )

    def transition_status(self, new_status: str, actor_id: str, reason: str) -> None:
        """Safely updates incident status while preserving full audit history."""
        if new_status not in IncidentStatus.ALL:
            raise ValueError(f"Invalid incident status: {new_status}")
        old_status = self.status
        self.status = new_status
        self.add_decision(
            actor_id=actor_id,
            decision_type=f"status_change_{new_status}",
            reason=f"Status transitioned from {old_status} to {new_status}: {reason}",
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the Incident aggregate root to a MongoDB-compliant dictionary."""
        return {
            "incident_id": self.incident_id,
            "guild_id": self.guild_id,
            "title": self.title,
            "status": self.status,
            "severity": self.severity,
            "confidence": self.confidence,
            "attribution_confidence": self.attribution_confidence,
            "is_emergency": self.is_emergency,
            "is_shadow_mode": self.is_shadow_mode,
            "is_whitelisted_actor_involved": self.is_whitelisted_actor_involved,
            "relevant_actors": self.relevant_actors,
            "relevant_targets": self.relevant_targets,
            "matched_patterns": self.matched_patterns,
            "signal_ids": self.signal_ids,
            "trigger_reasons": self.trigger_reasons,
            "first_seen_at": self.first_seen_at,
            "latest_seen_at": self.latest_seen_at,
            "observed_facts": self.observed_facts,
            "evidence_references": [e.to_dict() if hasattr(e, "to_dict") else e for e in self.evidence_references],
            "protective_actions": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.protective_actions],
            "snapshot_ids": self.snapshot_ids,
            "decision_history": [d.to_dict() if hasattr(d, "to_dict") else d for d in self.decision_history],
            "votes": {k: (v.to_dict() if hasattr(v, "to_dict") else v) for k, v in self.votes.items()},
            "recovery_code": self.recovery_code,
            "recovery_instructions": self.recovery_instructions,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Incident":
        """Reconstructs an Incident aggregate root from serialized dictionary data."""
        ev_refs = [EvidenceReference.from_dict(e) for e in data.get("evidence_references", [])]
        actions = [ProtectiveActionExecution.from_dict(a) for a in data.get("protective_actions", [])]
        decisions = [DecisionRecord.from_dict(d) for d in data.get("decision_history", [])]
        votes = {k: AdminVote.from_dict(v) for k, v in data.get("votes", {}).items()}

        return cls(
            incident_id=data.get("incident_id", f"inc_{uuid.uuid4().hex[:12]}"),
            guild_id=str(data.get("guild_id", "")),
            title=data.get("title", "Detected Security Threat"),
            status=data.get("status", IncidentStatus.ACTIVE),
            severity=data.get("severity", ThreatSeverity.MEDIUM),
            confidence=data.get("confidence", ThreatConfidence.SUSPICIOUS),
            attribution_confidence=data.get("attribution_confidence", AttributionConfidence.UNKNOWN),
            is_emergency=bool(data.get("is_emergency", False)),
            is_shadow_mode=bool(data.get("is_shadow_mode", True)),
            is_whitelisted_actor_involved=bool(data.get("is_whitelisted_actor_involved", False)),
            relevant_actors=data.get("relevant_actors", []),
            relevant_targets=data.get("relevant_targets", []),
            matched_patterns=data.get("matched_patterns", []),
            signal_ids=data.get("signal_ids", []),
            trigger_reasons=data.get("trigger_reasons", []),
            first_seen_at=float(data.get("first_seen_at", time.time())),
            latest_seen_at=float(data.get("latest_seen_at", time.time())),
            observed_facts=data.get("observed_facts", {}),
            inferred_intent=data.get("inferred_intent", ""),
            evidence_references=ev_refs,
            protective_actions=actions,
            snapshot_ids=data.get("snapshot_ids", []),
            decision_history=decisions,
            votes=votes,
            recovery_code=data.get("recovery_code"),
            recovery_instructions=data.get("recovery_instructions"),
            metadata=data.get("metadata", {}),
        )
