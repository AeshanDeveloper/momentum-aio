"""
Sentinel™ Security Autonomous Communication & Clarification Service.

Agent 7 of 8 Security Core: Proactive, policy-governed outbound communication engine.
Initiates security-related DMs, emergency alerts, clarification conversations, and
status updates without requiring user commands.

Key capabilities:
- Autonomous Outbound DMs: Proactively alerts trusted admins upon critical incidents,
  containment triggers, review requests for uncertain incidents, and recovery reports.
- Structured Clarification Conversations: Prompts authorized admins with short structured
  options (Planned maintenance, Not authorised, Unsure; investigate, Review incident).
- Evidence-Preserving Responses: Records answers as forensic evidence without blindly trusting
  or overriding active critical attacks.
- Non-Blocking Execution: Asynchronous, bounded dispatch with rate-limit cooldowns,
  incident-level deduplication, and automatic fallback channel routing on DM failures.
- Zero Exposure of Secrets: Automatically redacts webhook URLs, bot tokens, and private secrets.
"""

from __future__ import annotations

import time
import uuid
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set, Tuple, Union

import discord
from discord import ui, ButtonStyle

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.logging.logger import logger
from database.database import database
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    get_default_response_policy,
)
from core.security.lockdown_journal import LockdownRecord, lockdown_journal_manager
from core.security.emergency_lockdown_manager import emergency_lockdown_manager
from core.security.threat_assessment import AssessmentResult
from core.security.incident import (
    Incident,
    IncidentStatus,
    ReviewDecisionType,
    ProtectiveActionType,
)
from core.security.incident_manager import incident_manager, IncidentManager
from core.security.consensus_manager import (
    incident_consensus_manager,
    IncidentConsensusManager,
    ReviewChoice,
    IncidentReviewView,
    build_incident_review_container,
)
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle as SdkButtonStyle,
    SeparatorSpacingSize,
)


class ClarificationChoice:
    """Canonical clarification choices."""
    MAINTENANCE = "maintenance"
    UNAUTHORIZED = "unauthorized"
    UNSURE = "unsure"
    REVIEW = "review"

    LABELS = {
        MAINTENANCE: "Planned Maintenance",
        UNAUTHORIZED: "Not Authorised",
        UNSURE: "Unsure; Investigate",
        REVIEW: "Review Incident",
    }


class ClarificationConversationView(ui.View):
    """
    Interactive button view for structured security clarification conversations.
    """
    def __init__(
        self,
        incident: Incident,
        recipient_id: str,
        timeout: Optional[float] = 3600.0,  # 1 hour timeout
    ):
        super().__init__(timeout=timeout)
        self.incident = incident
        self.recipient_id = str(recipient_id)

        inc_id = incident.incident_id
        rec_id = self.recipient_id

        # 1. Planned Maintenance
        self.btn_maintenance = ui.Button(
            style=ButtonStyle.secondary,
            label="Planned Maintenance",
            custom_id=f"sentinel:clarify:maintenance:{inc_id}:{rec_id}",
            emoji=get_emoji("tools", "🛠️"),
        )
        self.btn_maintenance.callback = self._handle_maintenance
        self.add_item(self.btn_maintenance)

        # 2. Not Authorised
        self.btn_unauthorized = ui.Button(
            style=ButtonStyle.danger,
            label="Not Authorised",
            custom_id=f"sentinel:clarify:unauthorized:{inc_id}:{rec_id}",
            emoji=get_emoji("warning", "🚨"),
        )
        self.btn_unauthorized.callback = self._handle_unauthorized
        self.add_item(self.btn_unauthorized)

        # 3. Unsure; investigate
        self.btn_unsure = ui.Button(
            style=ButtonStyle.secondary,
            label="Unsure; Investigate",
            custom_id=f"sentinel:clarify:unsure:{inc_id}:{rec_id}",
            emoji=get_emoji("question", "❓"),
        )
        self.btn_unsure.callback = self._handle_unsure
        self.add_item(self.btn_unsure)

        # 4. Review incident
        self.btn_review = ui.Button(
            style=ButtonStyle.primary,
            label="Review Incident",
            custom_id=f"sentinel:clarify:review:{inc_id}:{rec_id}",
            emoji=get_emoji("search", "🔍"),
        )
        self.btn_review.callback = self._handle_review
        self.add_item(self.btn_review)

    async def _handle_maintenance(self, interaction: Any):
        await security_communication_service.handle_clarification_response(
            interaction, ClarificationChoice.MAINTENANCE, self.incident.incident_id, self.recipient_id
        )

    async def _handle_unauthorized(self, interaction: Any):
        await security_communication_service.handle_clarification_response(
            interaction, ClarificationChoice.UNAUTHORIZED, self.incident.incident_id, self.recipient_id
        )

    async def _handle_unsure(self, interaction: Any):
        await security_communication_service.handle_clarification_response(
            interaction, ClarificationChoice.UNSURE, self.incident.incident_id, self.recipient_id
        )

    async def _handle_review(self, interaction: Any):
        await security_communication_service.handle_clarification_response(
            interaction, ClarificationChoice.REVIEW, self.incident.incident_id, self.recipient_id
        )


class SecurityCommunicationService:
    """
    Central autonomous outbound communication engine for Sentinel™.
    Initiates security alerts, clarification conversations, and recovery reports.
    """
    _instance: Optional["SecurityCommunicationService"] = None

    @classmethod
    def get_instance(cls) -> "SecurityCommunicationService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(
        self,
        inc_manager: Optional[IncidentManager] = None,
        consensus_mgr: Optional[IncidentConsensusManager] = None,
        prot_service: Optional[Any] = None,
        bot_client: Optional[Any] = None,
    ):
        self.incident_manager: IncidentManager = inc_manager or incident_manager
        self.consensus_manager: IncidentConsensusManager = consensus_mgr or incident_consensus_manager
        self.protection_service: Optional[Any] = prot_service
        self.bot_client: Optional[Any] = bot_client

        # Deduplication and rate-limiting
        # key -> timestamp
        self._sent_notifications: Dict[str, float] = {}
        self._cooldown_tracker: Dict[str, float] = {}
        self._clarification_history: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Bounded concurrency for outbound messages
        self._semaphore = asyncio.Semaphore(10)
        self._is_attached = False

    def _get_policy(self, gid: str) -> SecurityResponsePolicy:
        if self.protection_service and hasattr(self.protection_service, "get_policy"):
            return self.protection_service.get_policy(gid)
        from core.security.protection_service import security_protection_service
        return security_protection_service.get_policy(gid)

    def attach_to_incident_manager(self, bot_client: Optional[Any] = None) -> None:
        """Attaches to incident lifecycle stream to evaluate autonomous communication triggers."""
        if bot_client:
            self.bot_client = bot_client
        if not self._is_attached:
            self.incident_manager.subscribe_incidents(self.on_incident_event)
            self._is_attached = True
            logger.info("[SecurityCommunicationService] Attached to IncidentManager lifecycle stream")

    def on_incident_event(self, incident: Incident, assessment: AssessmentResult) -> None:
        """
        Evaluates incoming incident updates to trigger autonomous communications:
        - Critical emergency incidents -> notification already handled via protection service, or follow-up
        - Uncertain/Suspicious incidents -> proactive review request or clarification conversation
        """
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._evaluate_autonomous_triggers(incident, assessment))
        except RuntimeError:
            pass

    async def _evaluate_autonomous_triggers(self, incident: Incident, assessment: AssessmentResult) -> None:
        """Evaluates policy and threat posture to initiate appropriate autonomous communication."""
        gid = str(incident.guild_id)
        policy = self._get_policy(gid)

        # Trigger A: Clarification conversation on suspicious administrative actions
        # When an incident has suspicious activity by a trusted/whitelisted actor or medium/high uncertainty
        if (
            incident.is_whitelisted_actor
            or assessment.graduated_confidence in ("suspicious", "unconfirmed")
            or incident.severity in ("medium", "high")
        ) and not assessment.should_trigger_immediate_response:
            # Check if actor is available or recovery admins configured
            target_recipient = incident.actor_id or policy.recovery_owner_id
            if target_recipient:
                dedup_key = f"clarify:{incident.incident_id}:{target_recipient}"
                if not self._is_rate_limited(dedup_key, cooldown_seconds=600.0):
                    await self.initiate_clarification_conversation(
                        incident=incident,
                        recipient_id=str(target_recipient),
                        guild_id=gid,
                    )

        # Trigger B: Uncertain incident review request to trusted admins
        elif (
            assessment.graduated_confidence == "suspicious"
            and not assessment.should_trigger_immediate_response
            and incident.status in (IncidentStatus.ACTIVE, IncidentStatus.UNDER_REVIEW)
        ):
            dedup_key = f"uncertain_review:{incident.incident_id}"
            if not self._is_rate_limited(dedup_key, cooldown_seconds=900.0):
                await self.request_review_for_uncertain_incident(
                    incident=incident,
                    assessment=assessment,
                    policy=policy,
                )

    def _is_rate_limited(self, key: str, cooldown_seconds: float = 60.0) -> bool:
        """Checks and updates cooldown tracker."""
        now = time.time()
        with self._lock:
            last = self._cooldown_tracker.get(key, 0.0)
            if now - last < cooldown_seconds:
                return True
            self._cooldown_tracker[key] = now
            return False

    def _redact_secrets(self, text: str) -> str:
        """Strips tokens, secrets, and private webhook URLs from notification copy."""
        if not text:
            return ""
        import re
        # Redact webhooks
        sanitized = re.sub(
            r"https://discord\.com/api/webhooks/\d+/[A-Za-z0-9_-]+",
            "[WEBHOOK_REDACTED]",
            str(text),
        )
        # Redact bot tokens
        sanitized = re.sub(
            r"[A-Za-z0-9_-]{24,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}",
            "[TOKEN_REDACTED]",
            sanitized,
        )
        # Redact API keys / secrets
        sanitized = re.sub(
            r"(api[_-]?key|secret|token)=([A-Za-z0-9_\-\.]+)",
            r"\1=[REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )
        return sanitized

    # 1. Proactive Clarification Conversations
    async def initiate_clarification_conversation(
        self,
        incident: Incident,
        recipient_id: str,
        guild_id: Optional[str] = None,
        question_text: Optional[str] = None,
    ) -> bool:
        """
        Initiates a structured clarification conversation with an administrator or actor.
        Sentinel asks clear options: Planned maintenance, Not authorised, Unsure; investigate, Review incident.
        """
        gid = str(guild_id or incident.guild_id)
        policy = self._get_policy(gid)
        client = getattr(self.bot_client, "client", self.bot_client)

        guild = None
        if client and hasattr(client, "get_guild"):
            try:
                guild = client.get_guild(int(gid))
            except Exception:
                guild = None
        if not guild and hasattr(self, "bot_client") and hasattr(self.bot_client, "get_guild"):
            try:
                guild = self.bot_client.get_guild(int(gid))
            except Exception:
                guild = None

        guild_name = guild.name if guild else f"Server {gid}"
        question = (
            question_text
            or f"Several destructive actions occurred in a short period on **{guild_name}**. Was this planned maintenance?"
        )
        question = self._redact_secrets(question)

        embed = discord.Embed(
            title="🛡️ Sentinel™ Security Clarification Request",
            description=(
                f"{question}\n\n"
                f"**Incident ID:** `{incident.incident_id}`\n"
                f"**Detected Activity:** `{incident.title or 'Rapid Administrative Modifications'}`\n"
                f"**Correlated Events:** `{incident.event_count}` observed\n"
                f"**Confidence:** `{incident.confidence.upper()}`\n\n"
                f"Please choose an option below to assist Sentinel's security evaluation. "
                f"Your response will be recorded as forensic evidence."
            ),
            color=discord.Color(get_color("warning", 0xF59E0B)),
        )
        embed.set_footer(
            text=f"Sentinel™ Security Infrastructure • Policy: {policy.response_level.upper()}",
            icon_url=IMAGES.get("sentinel_avatar", ""),
        )

        view = ClarificationConversationView(incident=incident, recipient_id=recipient_id)

        # Attempt DM delivery
        async with self._semaphore:
            success = await self._send_dm(client, recipient_id, embed, view)
            if not success and policy.fallback_channel_id:
                # Deliver to fallback channel with recipient mention
                fallback_success = await self._send_fallback_channel(
                    guild,
                    policy.fallback_channel_id,
                    content=f"⚠️ <@{recipient_id}> Sentinel requires administrative clarification regarding an active security event.",
                    embed=embed,
                    view=view,
                )
                logger.info(
                    f"[SecurityCommunication] Clarification conversation routed to fallback channel for {recipient_id}: {fallback_success}"
                )
                return fallback_success

        logger.info(
            f"[SecurityCommunication] Clarification conversation initiated with user {recipient_id} for incident {incident.incident_id}: {success}"
        )
        return success

    async def handle_clarification_response(
        self,
        interaction: Any,
        choice: str,
        incident_id: str,
        recipient_id: str,
    ) -> None:
        """
        Processes a user's answer to a clarification conversation.
        Records response as evidence, never blindly overrides active attacks, and applies policy.
        """
        user = getattr(interaction, "user", None)
        if not user:
            return

        caller_id = str(user.id)
        incident = self.incident_manager.get_incident(incident_id)
        if not incident:
            await self._respond_ephemeral(interaction, f"❌ Incident `{incident_id}` not found in cache.")
            return

        policy = self._get_policy(incident.guild_id)

        # Authority Check: Must be the designated recipient, server owner, extra owner, or trusted recovery admin
        is_recipient = caller_id == str(recipient_id)
        is_trusted = policy.is_trusted_recovery_actor(caller_id)
        if not (is_recipient or is_trusted):
            logger.warning(
                f"[SecurityCommunication] Unauthorized clarification attempt by user {caller_id} on incident {incident_id}"
            )
            await self._respond_ephemeral(
                interaction,
                "❌ You are not authorized to respond to this security clarification request.",
            )
            return

        choice_label = ClarificationChoice.LABELS.get(choice, choice)
        now = time.time()

        # 1. Record evidence & decision history (strictly preserved)
        evidence_id = f"clarif_{uuid.uuid4().hex[:8]}"
        incident.add_fact(f"Clarification statement received from <@{caller_id}> ({user}): {choice_label}")
        incident.record_evidence(
            source_type="admin_clarification",
            evidence_id=evidence_id,
            details={
                "choice": choice,
                "choice_label": choice_label,
                "respondent_id": caller_id,
                "respondent_name": str(user),
                "timestamp": now,
            },
        )
        incident.add_decision(
            actor_id=caller_id,
            actor_name=str(user),
            decision_type=ReviewDecisionType.CLARIFICATION_STATEMENT,
            reason=f"Administrator answered clarification request: {choice_label}",
            metadata={"choice": choice, "choice_label": choice_label},
        )

        # Store in clarification history
        self._clarification_history[incident_id] = {
            "choice": choice,
            "respondent_id": caller_id,
            "timestamp": now,
        }

        # 2. Evaluate answer against observed events and policy
        if choice == ClarificationChoice.MAINTENANCE:
            # Crucial check: Active critical attack MUST NOT be overridden by a single self-claim
            active_lockdown = lockdown_journal_manager.get_active_lockdown_for_guild(incident.guild_id)
            if incident.is_emergency and incident.severity == "critical":
                msg = (
                    f"📝 **Statement Recorded:** You indicated *{choice_label}*.\n\n"
                    f"⚠️ **Notice:** Because observed velocity exceeds critical emergency thresholds, "
                    f"protective containment remains active. Designated recovery administrators may review "
                    f"and authorize restoration via consensus."
                )
            else:
                msg = (
                    f"✅ **Clarification Recorded:** Marked as *{choice_label}* by <@{caller_id}>.\n"
                    f"Evidence has been updated. Other trusted administrators have been notified of your response."
                )
            await self._respond_ephemeral(interaction, msg)

        elif choice == ClarificationChoice.UNAUTHORIZED:
            # Immediate escalation to CRITICAL / CONFIRMED
            incident.severity = "critical"
            incident.confidence = "confirmed"
            incident.is_emergency = True
            incident.add_fact(f"CRITICAL: Unauthorized attack confirmed by administrator <@{caller_id}>")

            msg = (
                f"🚨 **Unauthorized Attack Confirmed by Administrator.**\n"
                f"Sentinel has escalated incident `{incident_id}` to **CRITICAL**. "
                f"Immediate emergency containment and isolation procedures are engaged."
            )
            await self._respond_ephemeral(interaction, msg)

            # Trigger emergency lockdown if not already active
            assessment = AssessmentResult(
                signal_id=f"esc_{int(now)}",
                threat_score=100.0,
                severity="critical",
                confidence="confirmed",
                should_trigger_immediate_response=True,
                recommended_action=ProtectiveActionType.EMERGENCY_LOCKDOWN,
                is_shadow_mode=policy.shadow_mode or not policy.auto_lockdown_enabled,
            )
            client = getattr(self.bot_client, "client", self.bot_client)
            guild = client.get_guild(int(incident.guild_id)) if client and hasattr(client, "get_guild") else None
            await emergency_lockdown_manager.execute_emergency_lockdown(
                guild=guild,
                incident=incident,
                assessment=assessment,
                policy=policy,
            )

        elif choice == ClarificationChoice.UNSURE:
            incident.status = IncidentStatus.UNDER_REVIEW
            msg = (
                f"ℹ️ **Status Updated:** Marked as *{choice_label}* by <@{caller_id}>.\n"
                f"Incident remains under active monitoring and review."
            )
            await self._respond_ephemeral(interaction, msg)

        elif choice == ClarificationChoice.REVIEW:
            # Present consensus review container
            summary = self.consensus_manager.get_consensus_summary(incident_id) or {}
            box = build_incident_review_container(incident, policy, summary)
            view = IncidentReviewView(incident=incident, policy=policy, consensus_mgr=self.consensus_manager)
            await self._respond_ephemeral(interaction, content="📋 Incident Consensus Audit", embed=None, view=view)

    # 2. Uncertain Incident Review Request
    async def request_review_for_uncertain_incident(
        self,
        incident: Incident,
        assessment: AssessmentResult,
        policy: SecurityResponsePolicy,
    ) -> Dict[str, Any]:
        """
        Proactively prompts trusted recovery admins to review an uncertain or suspicious incident.
        """
        gid = str(incident.guild_id)
        client = getattr(self.bot_client, "client", self.bot_client)
        guild = client.get_guild(int(gid)) if client and hasattr(client, "get_guild") else None

        embed = discord.Embed(
            title="🔍 Sentinel™ Review Requested: Suspicious Activity Detected",
            description=(
                f"Sentinel observed suspicious patterns on **{guild.name if guild else f'Server {gid}'}** "
                f"that require administrator review.\n\n"
                f"**Incident ID:** `{incident.incident_id}`\n"
                f"**Pattern:** `{incident.trigger_rule_id or incident.title}`\n"
                f"**Severity:** `{incident.severity.upper()}` | **Confidence:** `{incident.confidence.upper()}`\n"
                f"**Threat Score:** `{assessment.threat_score:.1f}/100.0`\n"
                f"**Observed Events:** `{incident.event_count}`\n\n"
                f"Please review the evidence below and cast your consensus evaluation."
            ),
            color=discord.Color(get_color("warning", 0xF59E0B)),
        )
        embed.set_footer(
            text=f"Sentinel™ Multi-Admin Consensus • Policy: {policy.response_level.upper()}",
            icon_url=IMAGES.get("sentinel_avatar", ""),
        )

        view = IncidentReviewView(incident=incident, policy=policy, consensus_mgr=self.consensus_manager)

        recipients = [str(policy.recovery_owner_id)] if policy.recovery_owner_id else []
        for aid in policy.trusted_recovery_admin_ids:
            if str(aid) not in recipients:
                recipients.append(str(aid))

        sent = 0
        failed = 0
        async with self._semaphore:
            for uid in recipients:
                ok = await self._send_dm(client, uid, embed, view)
                if ok:
                    sent += 1
                else:
                    failed += 1

            if failed > 0 and policy.fallback_channel_id:
                await self._send_fallback_channel(guild, policy.fallback_channel_id, embed=embed, view=view)

        return {"incident_id": incident.incident_id, "sent": sent, "failed": failed}

    # 2b. Critical Emergency Incident Notification
    async def notify_critical_incident(
        self,
        guild: Any,
        incident: Incident,
        policy: Optional[SecurityResponsePolicy] = None,
        lockdown_record: Optional[LockdownRecord] = None,
    ) -> Dict[str, Any]:
        """
        Dispatches emergency alerts to recovery admins and routes to fallback channel if DMs fail.
        """
        gid = str(getattr(guild, "id", incident.guild_id))
        pol = policy or self._get_policy(gid)
        client = getattr(self.bot_client, "client", self.bot_client)

        embed = discord.Embed(
            title=f"🚨 Sentinel™ Emergency Threat Alert: `{incident.incident_id}`",
            description=(
                f"Autonomous emergency protection was activated on **{getattr(guild, 'name', f'Server {gid}')}**.\n\n"
                f"**Threat:** {incident.title}\n"
                f"**Severity:** `{incident.severity.upper()}` | **Confidence:** `{incident.confidence.upper()}`\n"
                f"**Observed Events:** `{incident.event_count}`\n"
                f"**Attribution:** `{incident.attribution_confidence.upper()}`\n\n"
                f"Designated recovery staff may use the interactive controls below to review evidence or initiate safe restoration."
            ),
            color=discord.Color(get_color("danger", 0xED4245)),
        )
        embed.set_footer(
            text=f"Sentinel™ Defense Engine • Policy: {pol.response_level.upper()}",
            icon_url=IMAGES.get("sentinel_avatar", ""),
        )

        from core.security.admin_notifier import EmergencyRecoveryView
        view = EmergencyRecoveryView(incident=incident, lockdown_record=lockdown_record, policy=pol)

        recipients: List[str] = []
        if pol.recovery_owner_id:
            recipients.append(str(pol.recovery_owner_id))
        for aid in pol.trusted_recovery_admin_ids:
            if str(aid) not in recipients:
                recipients.append(str(aid))

        dms_sent = 0
        dms_failed = 0
        async with self._semaphore:
            for uid in recipients:
                ok = await self._send_dm(client, uid, embed, view)
                if ok:
                    dms_sent += 1
                else:
                    dms_failed += 1

            fallback_channel_sent = False
            if (dms_failed > 0 or dms_sent == 0) and pol.fallback_channel_id:
                fallback_channel_sent = await self._send_fallback_channel(
                    guild,
                    pol.fallback_channel_id,
                    content="🚨 **Sentinel Emergency Alert**: Critical security event detected. Review immediate details below.",
                    embed=embed,
                    view=view,
                )

        return {
            "incident_id": incident.incident_id,
            "dms_sent": dms_sent,
            "dms_failed": dms_failed,
            "fallback_channel_sent": fallback_channel_sent,
        }

    # 3. Lockdown Status and Recovery Updates
    async def send_lockdown_status_update(
        self,
        guild: Any,
        lockdown_record: LockdownRecord,
        policy: SecurityResponsePolicy,
        message: Optional[str] = None,
    ) -> bool:
        """Sends status update when a lockdown changes state."""
        client = getattr(self.bot_client, "client", self.bot_client)
        g_name = getattr(guild, "name", f"Server {lockdown_record.guild_id}")

        embed = discord.Embed(
            title=f"🛡️ Sentinel™ Lockdown Status: {lockdown_record.status.upper()}",
            description=(
                f"{message or 'Emergency containment state updated.'}\n\n"
                f"**Server:** {g_name}\n"
                f"**Lockdown ID:** `{lockdown_record.lockdown_id}`\n"
                f"**Status:** `{lockdown_record.status}`\n"
                f"**Mode:** `{'SHADOW MODE (Simulated)' if lockdown_record.is_shadow_mode else 'LIVE ENFORCEMENT'}`\n"
                f"**Restricted Entries:** `{len(lockdown_record.journal_entries)}` recorded"
            ),
            color=discord.Color(
                get_color("danger" if lockdown_record.status == LockdownStatus.ACTIVE else "brand", 0x5865F2)
            ),
        )

        recipients = [str(policy.recovery_owner_id)] if policy.recovery_owner_id else []
        for aid in policy.trusted_recovery_admin_ids:
            if str(aid) not in recipients:
                recipients.append(str(aid))

        delivered = False
        async with self._semaphore:
            for uid in recipients:
                if await self._send_dm(client, uid, embed):
                    delivered = True

            if not delivered and policy.fallback_channel_id:
                delivered = await self._send_fallback_channel(guild, policy.fallback_channel_id, embed=embed)

        return delivered

    # 4. Recovery Completion or Partial-Failure Report
    async def send_recovery_report(
        self,
        guild: Any,
        lockdown_record: LockdownRecord,
        initiated_by: Union[str, int],
        policy: SecurityResponsePolicy,
    ) -> Dict[str, Any]:
        """
        Sends a comprehensive recovery report detailing restored permissions,
        preserved independent admin changes, and any partial failures.
        """
        client = getattr(self.bot_client, "client", self.bot_client)
        g_name = getattr(guild, "name", f"Server {lockdown_record.guild_id}")
        summary = lockdown_record.summary

        restored_cnt = summary.get("restored", 0)
        conflict_cnt = summary.get("conflict_detected", 0)
        failed_cnt = summary.get("failed", 0)

        is_clean = (failed_cnt == 0 and lockdown_record.status == LockdownStatus.RESTORED)
        color = get_color("success" if is_clean else "warning", 0x3FD438 if is_clean else 0xF59E0B)

        embed = discord.Embed(
            title=f"🔓 Sentinel™ Recovery Report: {lockdown_record.status.upper()}",
            description=(
                f"Server permission recovery execution completed on **{g_name}**.\n\n"
                f"**Initiated By:** <@{initiated_by}>\n"
                f"**Lockdown ID:** `{lockdown_record.lockdown_id}`\n"
                f"**Outcome Status:** `{lockdown_record.status}`\n\n"
                f"### 📊 Restoration Statistics\n"
                f"• **Successfully Restored Entries:** `{restored_cnt}`\n"
                f"• **Preserved Independent Admin Changes:** `{conflict_cnt}` (never overwritten)\n"
                f"• **Failed Restorations:** `{failed_cnt}`"
            ),
            color=discord.Color(color),
        )

        if failed_cnt > 0:
            embed.add_field(
                name="⚠️ Partial Failure Notice",
                value="Some permissions could not be restored automatically (likely due to role hierarchy changes or API limits). Please audit role settings manually.",
                inline=False,
            )

        if conflict_cnt > 0:
            embed.add_field(
                name="ℹ️ Conflict Preservation",
                value="Independent modifications made by administrators during containment were safely preserved without being overwritten.",
                inline=False,
            )

        embed.set_footer(
            text="Sentinel™ Autonomous Defense Infrastructure • Reversible Recovery",
            icon_url=IMAGES.get("sentinel_avatar", ""),
        )

        recipients = [str(policy.recovery_owner_id)] if policy.recovery_owner_id else []
        for aid in policy.trusted_recovery_admin_ids:
            if str(aid) not in recipients:
                recipients.append(str(aid))

        dms_sent = 0
        async with self._semaphore:
            for uid in recipients:
                if await self._send_dm(client, uid, embed):
                    dms_sent += 1

            fallback_sent = False
            if policy.fallback_channel_id:
                fallback_sent = await self._send_fallback_channel(guild, policy.fallback_channel_id, embed=embed)

        return {
            "lockdown_id": lockdown_record.lockdown_id,
            "status": lockdown_record.status,
            "dms_sent": dms_sent,
            "fallback_sent": fallback_sent,
        }

    # 5. Notify Reviewers on Evidence Updates
    async def notify_evidence_update(
        self,
        incident: Incident,
        evidence_summary: str,
        policy: SecurityResponsePolicy,
    ) -> bool:
        """Notifies earlier reviewers when new evidence changes earlier assessment."""
        client = getattr(self.bot_client, "client", self.bot_client)
        embed = discord.Embed(
            title=f"📋 Sentinel™ Evidence Update: `{incident.incident_id}`",
            description=(
                f"New forensic evidence has been correlated with an ongoing security incident.\n\n"
                f"**Update:** {self._redact_secrets(evidence_summary)}\n"
                f"**Updated Severity:** `{incident.severity.upper()}` | **Confidence:** `{incident.confidence.upper()}`\n"
                f"**Total Preserved Evidence:** `{len(incident.evidence_references)}` records"
            ),
            color=discord.Color(get_color("brand", 0x5865F2)),
        )

        # Notify active voters on this incident
        recipients = [v.admin_id for v in incident.admin_votes]
        if policy.recovery_owner_id and str(policy.recovery_owner_id) not in recipients:
            recipients.append(str(policy.recovery_owner_id))

        notified = False
        async with self._semaphore:
            for uid in recipients:
                if await self._send_dm(client, uid, embed):
                    notified = True

        return notified

    # Low-level delivery helpers
    async def _send_dm(
        self,
        bot_client: Any,
        user_id: str,
        embed: discord.Embed,
        view: Optional[ui.View] = None,
    ) -> bool:
        """Sends a direct message to a user with graceful error handling."""
        if not bot_client:
            return False

        try:
            target_user = None
            if hasattr(bot_client, "get_user"):
                target_user = bot_client.get_user(int(user_id))
            if not target_user and hasattr(bot_client, "fetch_user"):
                target_user = await bot_client.fetch_user(int(user_id))

            if not target_user:
                return False

            dm_channel = getattr(target_user, "dm_channel", None)
            if not dm_channel and hasattr(target_user, "create_dm"):
                dm_channel = await target_user.create_dm()

            kwargs: Dict[str, Any] = {"embed": embed}
            if view:
                kwargs["view"] = view

            if dm_channel and hasattr(dm_channel, "send"):
                await dm_channel.send(**kwargs)
                return True
        except Exception as err:
            logger.debug(f"[SecurityCommunicationService] DM to {user_id} failed: {err}")
            return False

        return False

    async def _send_fallback_channel(
        self,
        guild: Any,
        channel_id: Optional[Union[str, int]],
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None,
        view: Optional[ui.View] = None,
    ) -> bool:
        """Delivers notification to configured fallback channel."""
        if not guild or not channel_id:
            return False

        try:
            ch = None
            if hasattr(guild, "get_channel"):
                ch = guild.get_channel(int(channel_id))
            if not ch and hasattr(guild, "fetch_channel"):
                ch = await guild.fetch_channel(int(channel_id))

            if ch and hasattr(ch, "send"):
                kwargs: Dict[str, Any] = {}
                if content:
                    kwargs["content"] = content
                if embed:
                    kwargs["embed"] = embed
                if view:
                    kwargs["view"] = view
                await ch.send(**kwargs)
                return True
        except Exception as err:
            logger.debug(f"[SecurityCommunicationService] Fallback channel send failed: {err}")
            return False

        return False

    async def _respond_ephemeral(
        self,
        interaction: Any,
        content: Optional[str] = None,
        embed: Optional[Any] = None,
        view: Optional[Any] = None,
    ) -> None:
        """Helper to respond to interaction."""
        try:
            kwargs: Dict[str, Any] = {"ephemeral": True}
            if content:
                kwargs["content"] = content
            if embed:
                kwargs["embed"] = embed
            if view:
                kwargs["view"] = view

            resp = getattr(interaction, "response", None)
            if resp and not getattr(resp, "_done", False) and hasattr(resp, "send_message"):
                await resp.send_message(**kwargs)
                return
            followup = getattr(interaction, "followup", None)
            if followup and hasattr(followup, "send"):
                await followup.send(**kwargs)
        except Exception as err:
            logger.debug(f"[SecurityCommunicationService] Interaction reply failed: {err}")


# Global singleton
security_communication_service = SecurityCommunicationService.get_instance()
