"""
Sentinel™ Threat Assessment Engine.

Agent 4 of 8 Security Core: Real-time risk evaluation, graduated confidence scoring,
emergency containment determination, and reversible recovery planning.

Key principles:
- Immediate Emergency Response: When destructive threshold is crossed, triggers
  protective action without blocking on human consensus, external lookups, or DB roundtrips.
- Graduated Confidence: Differentiates confirmed destructive activity, strong suspicious
  patterns, and uncertain events. Unknown actor attribution evaluates guild-wide velocity
  to protect the server without stall.
- Strict Non-Suppression of Trusted Actors: Whitelisted admins are fully evaluated.
  Compromised trusted accounts receive targeted isolation recommendations.
- Reversible Protection (Not Punishment): Recommends bounded channel lockdowns,
  invite pauses, and actor role isolations. Never performs permanent bans or mass unbans.
- Preserved Recovery Path: Always shields Sentinel's bot role and designated recovery admins.
  Generates verification unlock tokens and documentation.
- Shadow Mode by Default: Ensures automated emergency actions remain simulated unless
  explicitly authorized by server policy.
"""

from __future__ import annotations

import time
import uuid
import secrets
import inspect
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.logging.logger import logger
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
    GuildSecurityPolicy,
    PermissionSnapshot,
)


@dataclass
class AssessmentResult:
    """
    Evaluated risk assessment for a ThreatSignal.
    Contains computed threat score, action recommendation, and emergency verdict.
    """
    assessment_id: str = field(default_factory=lambda: f"asmt_{uuid.uuid4().hex[:12]}")
    signal_id: str = ""
    guild_id: str = ""
    threat_score: float = 0.0  # 0.0 to 100.0
    graduated_confidence: str = ThreatConfidence.SUSPICIOUS
    attribution_confidence: str = AttributionConfidence.UNKNOWN
    is_emergency: bool = False
    should_trigger_immediate_response: bool = False
    recommended_action: str = ProtectiveActionType.EMERGENCY_LOCKDOWN
    is_shadow_mode: bool = True
    is_whitelisted_actor: bool = False
    actor_id: Optional[str] = None
    target_ids: List[str] = field(default_factory=list)
    recovery_plan: Dict[str, Any] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    severity: Optional[str] = None
    confidence: Optional[str] = None


    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "signal_id": self.signal_id,
            "guild_id": self.guild_id,
            "threat_score": self.threat_score,
            "graduated_confidence": self.graduated_confidence,
            "attribution_confidence": self.attribution_confidence,
            "is_emergency": self.is_emergency,
            "should_trigger_immediate_response": self.should_trigger_immediate_response,
            "recommended_action": self.recommended_action,
            "is_shadow_mode": self.is_shadow_mode,
            "is_whitelisted_actor": self.is_whitelisted_actor,
            "actor_id": self.actor_id,
            "target_ids": self.target_ids,
            "recovery_plan": self.recovery_plan,
            "reasons": self.reasons,
            "timestamp": self.timestamp,
        }


class ThreatAssessmentEngine:
    """
    High-performance real-time threat evaluation engine.
    Calculates composite risk scores, enforces safety guardrails, and produces
    deterministic mitigation recommendations.
    """

    _instance: Optional["ThreatAssessmentEngine"] = None

    @classmethod
    def get_instance(cls) -> "ThreatAssessmentEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._guild_policies: Dict[str, GuildSecurityPolicy] = {}
        self._assessment_subscribers: List[Any] = []

    def set_guild_policy(self, guild_id: str, policy: GuildSecurityPolicy) -> None:
        """Configures or updates security policy for a guild."""
        self._guild_policies[str(guild_id)] = policy

    def get_guild_policy(self, guild_id: str) -> GuildSecurityPolicy:
        """Retrieves active policy for a guild; defaults to strict shadow mode."""
        gid = str(guild_id)
        if gid not in self._guild_policies:
            # Default to shadow mode: true, auto_lockdown_enabled: false
            self._guild_policies[gid] = GuildSecurityPolicy(
                guild_id=gid,
                shadow_mode=True,
                auto_lockdown_enabled=False,
            )
        return self._guild_policies[gid]

    def subscribe_assessments(self, subscriber: Any) -> None:
        """Registers a callback for completed threat assessments."""
        if subscriber not in self._assessment_subscribers:
            self._assessment_subscribers.append(subscriber)

    def assess_signal(
        self,
        signal: ThreatSignal,
        policy: Optional[GuildSecurityPolicy] = None,
    ) -> AssessmentResult:
        """
        Fast-path risk evaluation executing in sub-millisecond synchronous time.
        Calculates calibrated score, checks emergency thresholds, ensures trusted
        actor monitoring, and respects shadow mode boundaries.
        """
        gid = str(signal.guild_id)
        guild_policy = policy or self.get_guild_policy(gid)
        reasons: List[str] = []

        # 1. Base Score from Threat Severity
        severity_weights = {
            ThreatSeverity.CRITICAL: 85.0,
            ThreatSeverity.HIGH: 65.0,
            ThreatSeverity.MEDIUM: 40.0,
            ThreatSeverity.LOW: 15.0,
        }
        base_score = severity_weights.get(signal.severity, 40.0)

        # 2. Graduated Confidence Multiplier
        confidence_multipliers = {
            ThreatConfidence.CONFIRMED: 1.25,
            ThreatConfidence.HIGH_CONFIDENCE: 1.10,
            ThreatConfidence.SUSPICIOUS: 1.0,
            ThreatConfidence.UNCONFIRMED: 0.70,
        }
        conf_multiplier = confidence_multipliers.get(signal.confidence, 1.0)
        threat_score = base_score * conf_multiplier

        # 3. High-Impact Vector Adjustment
        destructive_patterns = {
            PatternID.RAPID_BAN_BURST: 20.0,
            PatternID.REPEATED_CHANNEL_DELETIONS: 25.0,
            PatternID.REPEATED_ROLE_DELETIONS: 25.0,
            PatternID.PERMISSION_ESCALATION_THEN_DESTRUCTION: 25.0,
            PatternID.COORDINATED_MULTI_VECTOR: 30.0,
            PatternID.WEBHOOK_INTEGRATION_ABUSE: 15.0,
            PatternID.DANGEROUS_ROLE_CHANGES_THEN_DESTRUCTION: 20.0,
            PatternID.SECURITY_WEAKENING_PRIOR_TO_DESTRUCTION: 20.0,
            PatternID.RAPID_KICK_BURST: 15.0,
        }
        if signal.pattern_id in destructive_patterns:
            pattern_bonus = destructive_patterns[signal.pattern_id]
            threat_score += pattern_bonus
            reasons.append(f"Destructive pattern matched: {signal.pattern_name or signal.pattern_id} (+{pattern_bonus} pts)")

        # 4. Unknown vs Verified Actor Attribution
        if signal.attribution_confidence == AttributionConfidence.UNKNOWN:
            # Crucial rule: Unknown actor attribution must NOT prevent response to clearly dangerous attack
            if signal.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL):
                reasons.append("Uncertain actor attribution: guild-wide velocity indicates active server compromise")
                # Maintain high score so guild-level protection triggers
                threat_score = max(threat_score, 75.0)
            else:
                threat_score *= 0.85
                reasons.append("Uncertain actor attribution with low velocity; monitoring guild scope")
        elif signal.attribution_confidence == AttributionConfidence.VERIFIED:
            threat_score += 10.0
            reasons.append("Verified actor identity via gateway & audit logs")

        # 5. Trusted / Whitelisted Actor Non-Suppression
        if signal.is_whitelisted_actor:
            # Whitelisted users must still be monitored and evaluated
            reasons.append("Warning: Whitelisted/trusted actor performed high-impact administrative actions")
            if signal.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL):
                # Potential token compromise or rogue account
                reasons.append("Critical risk: Possible account compromise of trusted administrator")
                threat_score = max(threat_score, 80.0)

        # Clamp threat score between 0.0 and 100.0
        threat_score = max(0.0, min(100.0, round(threat_score, 2)))

        # 6. Immediate Emergency Threshold Evaluation
        # Immediate protection triggers if:
        # - Signal explicitly requested immediate protection, OR
        # - Threat score crosses configured threshold, OR
        # - Severity is CRITICAL and recommendation is emergency lockdown.
        is_emergency = (
            signal.requires_immediate_protection
            or (signal.severity == ThreatSeverity.CRITICAL and signal.recommended_response == ResponseCategory.EMERGENCY_LOCKDOWN)
            or (threat_score >= guild_policy.emergency_threshold_score)
        )

        should_trigger_immediate_response = is_emergency

        # 7. Action Selection (Protection Separated from Punishment)
        # Sentinel protects through reversible containment; NEVER permanent bans or mass unbans
        if signal.pattern_id in (PatternID.WEBHOOK_INTEGRATION_ABUSE,):
            recommended_action = ProtectiveActionType.ISOLATE_INTEGRATION
        elif signal.is_whitelisted_actor and signal.actor_id and guild_policy.isolate_whitelisted_compromise:
            # Isolate actor permissions rather than shutting down entire server if targeted
            recommended_action = ProtectiveActionType.ISOLATE_ACTOR if signal.severity != ThreatSeverity.CRITICAL else ProtectiveActionType.EMERGENCY_LOCKDOWN
        elif is_emergency:
            recommended_action = ProtectiveActionType.EMERGENCY_LOCKDOWN
        elif signal.recommended_response == ResponseCategory.RESTRICT_ACTOR:
            recommended_action = ProtectiveActionType.ISOLATE_ACTOR
        else:
            recommended_action = ProtectiveActionType.ALERT_DISPATCH

        # 8. Shadow Mode Enforcement
        # Crucial requirement: Default to shadow mode; real emergency actions must be explicitly enabled
        is_shadow_mode = guild_policy.shadow_mode or (not guild_policy.auto_lockdown_enabled)
        if is_shadow_mode:
            reasons.append("Action evaluated under SHADOW MODE: live permission changes will be simulated")

        # 9. Recovery Path & Boundary Safeguards
        # Generates verification recovery code and ensures Sentinel and Recovery Admins are shielded
        recovery_code = f"SENTINEL-REC-{secrets.token_hex(4).upper()}-{secrets.token_hex(4).upper()}"
        recovery_plan = {
            "recovery_code": recovery_code,
            "shielded_bot_id": settings.CLIENT_ID,
            "shielded_admin_ids": list(guild_policy.recovery_admin_ids),
            "exempt_channel_ids": list(guild_policy.exempt_channel_ids),
            "recovery_channel_id": guild_policy.recovery_channel_id,
            "instructions": (
                f"Sentinel Recovery Procedure:\n"
                f"1. A reversible lockdown snapshot has been recorded.\n"
                f"2. To restore permissions, run: `{settings.BOT_PREFIX}unlock {recovery_code}`\n"
                f"3. Designated recovery admins ({len(guild_policy.recovery_admin_ids)} users) retain full administrative access.\n"
                f"4. Sentinel bot permissions have been explicitly preserved."
            ),
        }

        result = AssessmentResult(
            signal_id=signal.signal_id,
            guild_id=gid,
            threat_score=threat_score,
            graduated_confidence=signal.confidence,
            attribution_confidence=signal.attribution_confidence,
            is_emergency=is_emergency,
            should_trigger_immediate_response=should_trigger_immediate_response,
            recommended_action=recommended_action,
            is_shadow_mode=is_shadow_mode,
            is_whitelisted_actor=signal.is_whitelisted_actor,
            actor_id=signal.actor_id,
            target_ids=list(signal.target_ids),
            recovery_plan=recovery_plan,
            reasons=reasons,
        )

        self._notify_subscribers(result)
        return result

    def _notify_subscribers(self, result: AssessmentResult) -> None:
        """Dispatches completed assessments to registered listeners."""
        for sub in list(self._assessment_subscribers):
            try:
                if inspect.iscoroutinefunction(sub):
                    try:
                        loop = asyncio.get_running_loop()
                        if loop.is_running():
                            loop.create_task(sub(result))
                    except RuntimeError:
                        pass
                else:
                    sub(result)
            except Exception as err:
                logger.error(f"[ThreatAssessmentEngine] Error in assessment subscriber: {err}")


# Singleton instance
threat_assessment_engine = ThreatAssessmentEngine.get_instance()
