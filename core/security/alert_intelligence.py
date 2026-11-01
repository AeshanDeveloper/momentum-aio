"""
Sentinel™ Security Incident Alert Intelligence & Delivery Manager.

Agent 7 & 8 Security Core: Intelligent notification governance, delayed edit coalescing,
material-change evaluation, and Components V2 message delivery.

Key capabilities:
- Notification Decisions: Evaluates whether incoming changes warrant NO_NOTIFICATION,
  CREATE_PRIMARY_ALERT, UPDATE_PRIMARY_ALERT, ESCALATE_ALERT, SEND_URGENT_NOTIFICATION,
  or SEND_RESOLUTION_UPDATE.
- Anti-Alert-Storm Coalescing: Coalesces rapid subsequent events into an existing primary alert.
  Schedules delayed edits (configurable 5.0s window) rather than flooding moderator channels.
- In-Flight Concurrency Protection: Events arriving while an edit is in progress trigger a
  subsequent coalescing pass, guaranteeing zero lost forensic evidence.
- Deleted Message Self-Healing: Gracefully handles 404 / 10008 Unknown Message errors by safely
  recreating the primary alert once and updating persisted state.
- Separation of Concerns: Emergency mitigation operates independently and NEVER waits for
  alert delivery or edit timers.
- Discord Components V2: High-contrast layout utilizing centralized COLORS and EMOJIS.
"""

from __future__ import annotations

import time
import uuid
import asyncio
import inspect
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Tuple, Union

import discord
from discord import ui, ButtonStyle

from config.settings import settings, COLORS, EMOJIS, IMAGES, get_color, get_emoji
from core.logging.logger import logger
from core.security.security_event import AttributionConfidence
from core.security.correlation_engine import (
    ThreatSignal,
    ThreatSeverity,
    ThreatConfidence,
    ResponseCategory,
    PatternID,
)
from core.security.threat_assessment import (
    AssessmentResult,
    threat_assessment_engine,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
    ActionExecutionStatus,
    ReviewDecisionType,
)
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    get_default_response_policy,
)
from sdk.discord.builders import (
    ContainerBuilder,
    ActionRowBuilder,
    ButtonBuilder,
    ButtonStyle as SdkButtonStyle,
    SeparatorSpacingSize,
)


class NotificationDecision:
    """Canonical alert intelligence decisions."""
    NO_NOTIFICATION = "no_notification"
    CREATE_PRIMARY_ALERT = "create_primary_alert"
    UPDATE_PRIMARY_ALERT = "update_primary_alert"
    ESCALATE_ALERT = "escalate_alert"
    SEND_URGENT_NOTIFICATION = "send_urgent_notification"
    SEND_RESOLUTION_UPDATE = "send_resolution_update"

    ALL = {
        NO_NOTIFICATION,
        CREATE_PRIMARY_ALERT,
        UPDATE_PRIMARY_ALERT,
        ESCALATE_ALERT,
        SEND_URGENT_NOTIFICATION,
        SEND_RESOLUTION_UPDATE,
    }


class AlertIntelligenceManager:
    """
    Evaluates incident state changes to determine appropriate communication actions.
    Eliminates alert flooding while ensuring critical escalations and resolutions are published.
    """

    _instance: Optional["AlertIntelligenceManager"] = None

    @classmethod
    def get_instance(cls) -> "AlertIntelligenceManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Baseline tracking for change detection: incident_id -> snapshot dict
        self._incident_snapshots: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def capture_snapshot(self, incident: Incident) -> None:
        """Saves current state snapshot of an incident for future delta comparisons."""
        with self._lock:
            self._incident_snapshots[incident.incident_id] = {
                "severity": incident.severity,
                "urgency": incident.urgency,
                "confidence": incident.confidence,
                "status": incident.status,
                "event_count": incident.event_count,
                "target_count": len(incident.relevant_targets),
                "action_count": len(incident.protective_actions),
                "is_emergency": incident.is_emergency,
            }

    def evaluate_incident(
        self,
        incident: Incident,
        assessment: Optional[AssessmentResult] = None,
        previous_state: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Determines the notification decision based on incident state and deltas.
        """
        # Rule 1: Resolution or Dismissal Update
        if incident.status in (IncidentStatus.RESOLVED, IncidentStatus.DISMISSED):
            if incident.primary_alert_message_id:
                incident.suppression_reason = None
                return NotificationDecision.SEND_RESOLUTION_UPDATE
            incident.suppression_reason = "resolved_without_primary_alert"
            return NotificationDecision.NO_NOTIFICATION

        # Rule 2: Emergency Containment Urgent Dispatch
        # When immediate response is required and not yet delivered
        is_emergency = incident.is_emergency or (assessment and assessment.should_trigger_immediate_response)
        has_executed_emergency = any(
            a.action_type == ProtectiveActionType.EMERGENCY_LOCKDOWN and a.status in (ActionExecutionStatus.EXECUTED, ActionExecutionStatus.ATTEMPTED)
            for a in incident.protective_actions
        )

        if is_emergency and not incident.primary_alert_message_id:
            incident.suppression_reason = None
            return NotificationDecision.CREATE_PRIMARY_ALERT

        # Rule 3: First Primary Alert Creation
        if not incident.primary_alert_message_id:
            if self.is_alert_worthy(incident, assessment):
                incident.suppression_reason = None
                return NotificationDecision.CREATE_PRIMARY_ALERT
            else:
                incident.suppression_reason = "below_alert_threshold"
                return NotificationDecision.NO_NOTIFICATION

        # Rule 4: Existing Alert Check for Material Changes
        prev = previous_state or self._incident_snapshots.get(incident.incident_id)
        if not prev:
            # Baseline snapshot established on first observation / restart
            self.capture_snapshot(incident)
            if assessment is None and not incident.pending_alert_edit:
                incident.suppression_reason = "rehydrated_baseline_established"
                return NotificationDecision.NO_NOTIFICATION
            return NotificationDecision.UPDATE_PRIMARY_ALERT

        is_material, is_escalation, change_reason = self.check_material_change(incident, prev, assessment)

        if is_escalation:
            incident.suppression_reason = None
            return NotificationDecision.ESCALATE_ALERT
        elif is_material:
            incident.suppression_reason = None
            return NotificationDecision.UPDATE_PRIMARY_ALERT
        else:
            incident.suppression_reason = f"suppressed_no_material_change ({change_reason})"
            return NotificationDecision.NO_NOTIFICATION

    def is_alert_worthy(
        self,
        incident: Incident,
        assessment: Optional[AssessmentResult] = None,
    ) -> bool:
        """
        Evaluates whether an incident crosses the threshold for publishing an alert.
        """
        if incident.is_emergency:
            return True
        if assessment and assessment.should_trigger_immediate_response:
            return True
        if incident.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL):
            return True
        if incident.urgency in ("high", "critical"):
            return True
        if assessment and assessment.threat_score >= 40.0:
            return True
        if incident.severity == ThreatSeverity.MEDIUM and incident.confidence in (ThreatConfidence.HIGH_CONFIDENCE, ThreatConfidence.CONFIRMED):
            return True
        return False

    def check_material_change(
        self,
        incident: Incident,
        prev: Dict[str, Any],
        assessment: Optional[AssessmentResult] = None,
    ) -> Tuple[bool, bool, str]:
        """
        Detects whether changes between previous snapshot and current incident are material.
        Returns: (is_material, is_escalation, reason)
        """
        severity_ranks = {
            ThreatSeverity.LOW: 1,
            ThreatSeverity.MEDIUM: 2,
            ThreatSeverity.HIGH: 3,
            ThreatSeverity.CRITICAL: 4,
        }
        urgency_ranks = {"low": 1, "medium": 2, "high": 3, "critical": 4}

        old_sev_rank = severity_ranks.get(prev.get("severity", "medium"), 2)
        new_sev_rank = severity_ranks.get(incident.severity, 2)

        # Escalation: Severity jump to CRITICAL or jump of >= 2 levels
        if new_sev_rank > old_sev_rank and incident.severity == ThreatSeverity.CRITICAL:
            return True, True, "severity_escalated_to_critical"
        if new_sev_rank >= old_sev_rank + 2:
            return True, True, "severity_jump_multiple_levels"

        # Severity increased
        if new_sev_rank > old_sev_rank:
            return True, False, f"severity_increased_{prev.get('severity')}_to_{incident.severity}"

        # Urgency increased
        old_urg_rank = urgency_ranks.get(prev.get("urgency", "medium"), 2)
        new_urg_rank = urgency_ranks.get(incident.urgency, 2)
        if new_urg_rank > old_urg_rank:
            return True, (incident.urgency == "critical"), f"urgency_increased_to_{incident.urgency}"

        # Status changed (e.g. CONTAINED, UNDER_REVIEW)
        if incident.status != prev.get("status"):
            return True, False, f"status_changed_to_{incident.status}"

        # New protective action recorded
        if len(incident.protective_actions) > prev.get("action_count", 0):
            return True, False, "protective_action_recorded"

        # Target count doubled or increased significantly
        old_targets = prev.get("target_count", 0)
        new_targets = len(incident.relevant_targets)
        if new_targets >= max(2, old_targets * 2):
            return True, False, f"targets_expanded_{old_targets}_to_{new_targets}"

        # Correlated events increased by significant delta (>= 3)
        old_events = prev.get("event_count", 0)
        new_events = incident.event_count
        if new_events - old_events >= 3:
            return True, False, f"evidence_volume_surge_+{new_events - old_events}"

        return False, False, "minor_fluctuation_only"


class AlertDeliveryManager:
    """
    Manages Discord message delivery, Components V2 rendering, and delayed edit coalescing.
    Ensures message editing is throttled, missing messages are self-healed, and emergency response
    remains completely decoupled from notification delivery.
    """

    _instance: Optional["AlertDeliveryManager"] = None

    @classmethod
    def get_instance(cls) -> "AlertDeliveryManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, bot_client: Optional[Any] = None):
        self.bot_client = bot_client
        self.intelligence_manager = AlertIntelligenceManager.get_instance()

        # Coalescing configuration
        self.edit_delay_seconds: float = 5.0
        self.max_coalesce_seconds: float = 30.0

        # Background tasks and concurrency control: incident_id -> Task
        self._delayed_tasks: Dict[str, asyncio.Task] = {}
        self._in_flight_edits: Set[str] = set()
        self._incident_locks: Dict[str, asyncio.Lock] = {}
        self._sync_lock = threading.RLock()

        # Delivery statistics for observability
        self.total_primary_alerts_sent = 0
        self.total_edits_executed = 0
        self.total_edits_coalesced = 0
        self.total_edits_suppressed = 0
        self.total_recreations_on_404 = 0
        self.total_resolution_updates = 0

    def _get_lock(self, incident_id: str) -> asyncio.Lock:
        with self._sync_lock:
            if incident_id not in self._incident_locks:
                self._incident_locks[incident_id] = asyncio.Lock()
            return self._incident_locks[incident_id]

    # Primary Entry Point
    async def process_incident_notification(
        self,
        incident: Incident,
        assessment: Optional[AssessmentResult] = None,
        guild: Optional[discord.Guild] = None,
        channel_id: Optional[Union[str, int]] = None,
    ) -> str:
        """
        Evaluates and dispatches notification decision with delayed coalescing.
        """
        decision = self.intelligence_manager.evaluate_incident(incident, assessment)
        logger.debug(f"[AlertDelivery] Incident {incident.incident_id} decision: {decision}")

        if decision == NotificationDecision.NO_NOTIFICATION:
            self.total_edits_suppressed += 1
            return decision

        elif decision == NotificationDecision.CREATE_PRIMARY_ALERT:
            await self.create_primary_alert(incident, assessment, guild=guild, channel_id=channel_id)
            self.intelligence_manager.capture_snapshot(incident)
            return decision

        elif decision in (NotificationDecision.UPDATE_PRIMARY_ALERT, NotificationDecision.ESCALATE_ALERT):
            # Schedule delayed coalescing edit
            self.schedule_delayed_edit(incident, reason=decision)
            self.intelligence_manager.capture_snapshot(incident)
            return decision

        elif decision == NotificationDecision.SEND_RESOLUTION_UPDATE:
            # Immediate resolution update to primary alert
            await self.update_primary_alert_now(incident, is_resolution=True)
            self.intelligence_manager.capture_snapshot(incident)
            return decision

        return decision

    # Delayed Coalescing Logic
    def schedule_delayed_edit(self, incident: Incident, reason: str = "") -> None:
        """
        Schedules or updates a delayed edit timer for the incident.
        Coalesces all events arriving within the delay window into a single message update.
        """
        inc_id = incident.incident_id
        incident.pending_alert_edit = True
        incident.pending_alert_version += 1

        with self._sync_lock:
            existing_task = self._delayed_tasks.get(inc_id)
            if existing_task and not existing_task.done():
                # Timer already in progress; version counter updated, coalesce
                self.total_edits_coalesced += 1
                logger.debug(
                    f"[AlertDelivery] Coalescing update for {inc_id} into running timer (v{incident.pending_alert_version})"
                )
                return

            incident.alert_delivery_state = "scheduled"
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                if loop and not loop.is_closed():
                    task = loop.create_task(self._delayed_edit_worker(incident, self.edit_delay_seconds))
                    self._delayed_tasks[inc_id] = task
            except Exception as err:
                logger.warning(f"[AlertDelivery] No running event loop to schedule delayed edit for {inc_id}: {err}")

    async def _delayed_edit_worker(self, incident: Incident, delay: float) -> None:
        """Asynchronous worker that sleeps for the coalesce window then applies the edit."""
        inc_id = incident.incident_id
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

        async with self._get_lock(inc_id):
            if not incident.pending_alert_edit:
                incident.alert_delivery_state = "idle"
                return

            incident.alert_delivery_state = "delivering"
            # Reset flag before delivering to catch any in-flight arrival
            incident.pending_alert_edit = False

            success = await self._perform_message_edit(incident)

            if success:
                incident.last_alert_update_at = time.time()
                self.total_edits_executed += 1
                logger.info(f"[AlertDelivery] Successfully edited primary alert for incident {inc_id}")
            else:
                incident.alert_delivery_state = "failed"
                logger.warning(f"[AlertDelivery] Primary alert edit failed for incident {inc_id}")

            # Concurrency check: If another event arrived during delivery, schedule next cycle
            if incident.pending_alert_edit:
                logger.info(f"[AlertDelivery] Event arrived during in-flight edit for {inc_id}; re-scheduling pass")
                incident.alert_delivery_state = "scheduled"
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = asyncio.get_event_loop()
                if loop and not loop.is_closed():
                    task = loop.create_task(self._delayed_edit_worker(incident, self.edit_delay_seconds))
                    with self._sync_lock:
                        self._delayed_tasks[inc_id] = task
            else:
                incident.alert_delivery_state = "idle"

    # Immediate Message Edit
    async def update_primary_alert_now(self, incident: Incident, is_resolution: bool = False) -> bool:
        """Forces an immediate edit of the primary alert message (e.g. on resolution)."""
        inc_id = incident.incident_id
        async with self._get_lock(inc_id):
            incident.alert_delivery_state = "delivering"
            incident.pending_alert_edit = False
            success = await self._perform_message_edit(incident, is_resolution=is_resolution)
            if success:
                incident.last_alert_update_at = time.time()
                incident.alert_delivery_state = "idle"
                if is_resolution:
                    self.total_resolution_updates += 1
            else:
                incident.alert_delivery_state = "failed"
            return success

    # Discord Message Operations
    async def create_primary_alert(
        self,
        incident: Incident,
        assessment: Optional[AssessmentResult] = None,
        guild: Optional[discord.Guild] = None,
        channel_id: Optional[Union[str, int]] = None,
    ) -> Optional[str]:
        """
        Creates the single primary alert message in the designated channel.
        Stores primary_alert_message_id and alert_channel_id on the incident.
        """
        client = getattr(self.bot_client, "client", self.bot_client)
        gid = incident.guild_id

        # Resolve Guild
        target_guild = guild
        if not target_guild and client and hasattr(client, "get_guild"):
            try:
                target_guild = client.get_guild(int(gid))
            except Exception:
                target_guild = None

        # Resolve Channel
        target_ch_id = channel_id or incident.alert_channel_id
        policy = get_default_response_policy(gid)
        if not target_ch_id:
            target_ch_id = getattr(policy, "recovery_channel_id", None) or getattr(policy, "fallback_channel_id", None)

        target_channel = None
        if target_guild and target_ch_id:
            if hasattr(target_guild, "get_channel"):
                target_channel = target_guild.get_channel(int(target_ch_id))
            if not target_channel and hasattr(target_guild, "fetch_channel"):
                try:
                    target_channel = await target_guild.fetch_channel(int(target_ch_id))
                except Exception:
                    target_channel = None

        if not target_channel and target_guild:
            # Fall back to system channel or first writable text channel
            target_channel = getattr(target_guild, "system_channel", None)
            if not target_channel and hasattr(target_guild, "text_channels") and target_guild.text_channels:
                target_channel = target_guild.text_channels[0]

        if not target_channel or not hasattr(target_channel, "send"):
            logger.warning(f"[AlertDelivery] No valid alert channel found for guild {gid}")
            return None

        # Build Container and View
        container_builder, view = self.build_incident_container(incident, assessment)
        kwargs = self._prepare_discord_kwargs(container_builder, view)

        try:
            sent_msg = await target_channel.send(**kwargs)
            if sent_msg and hasattr(sent_msg, "id"):
                msg_id_str = str(sent_msg.id)
                incident.primary_alert_message_id = msg_id_str
                incident.alert_channel_id = str(target_channel.id)
                incident.last_alert_update_at = time.time()
                incident.alert_delivery_state = "idle"
                self.total_primary_alerts_sent += 1
                logger.info(
                    f"[AlertDelivery] Created primary alert {msg_id_str} in channel {target_channel.id} for incident {incident.incident_id}"
                )
                return msg_id_str
        except Exception as err:
            logger.error(f"[AlertDelivery] Failed to create primary alert: {err}")

        return None

    async def _perform_message_edit(self, incident: Incident, is_resolution: bool = False) -> bool:
        """
        Executes message.edit with bounded retry and 404 self-healing recreation.
        """
        client = getattr(self.bot_client, "client", self.bot_client)
        msg_id = incident.primary_alert_message_id
        ch_id = incident.alert_channel_id

        if not msg_id or not ch_id:
            logger.warning(f"[AlertDelivery] Cannot edit primary alert: missing message/channel ID for {incident.incident_id}")
            return False

        target_channel = None
        if client and hasattr(client, "get_channel"):
            try:
                target_channel = client.get_channel(int(ch_id))
            except Exception:
                target_channel = None
        if not target_channel and client and hasattr(client, "fetch_channel"):
            try:
                target_channel = await client.fetch_channel(int(ch_id))
            except Exception:
                target_channel = None

        if not target_channel:
            logger.warning(f"[AlertDelivery] Target alert channel {ch_id} not reachable")
            return False

        # Attempt to retrieve message
        target_message = None
        if hasattr(target_channel, "get_partial_message"):
            target_message = target_channel.get_partial_message(int(msg_id))
        elif hasattr(target_channel, "fetch_message"):
            try:
                target_message = await target_channel.fetch_message(int(msg_id))
            except discord.NotFound:
                target_message = None
            except Exception as err:
                logger.warning(f"[AlertDelivery] Error fetching message {msg_id}: {err}")
                target_message = None

        container_builder, view = self.build_incident_container(incident)
        kwargs = self._prepare_discord_kwargs(container_builder, view)

        # Case A: Message found -> Edit it
        if target_message and hasattr(target_message, "edit"):
            for attempt in range(1, 4):
                try:
                    await target_message.edit(**kwargs)
                    return True
                except discord.NotFound:
                    logger.warning(f"[AlertDelivery] Message {msg_id} was deleted during edit attempt; recreating")
                    target_message = None
                    break
                except discord.HTTPException as http_err:
                    if getattr(http_err, "status", 0) == 429:
                        retry_after = getattr(http_err, "retry_after", 1.5) or 1.5
                        logger.warning(f"[AlertDelivery] Rate limited on edit; waiting {retry_after}s")
                        await asyncio.sleep(min(retry_after, 5.0))
                    elif getattr(http_err, "code", 0) == 10008:  # Unknown message
                        logger.warning(f"[AlertDelivery] Discord 10008 Unknown Message; recreating")
                        target_message = None
                        break
                    else:
                        logger.error(f"[AlertDelivery] Discord HTTP exception editing message: {http_err}")
                        if attempt == 3:
                            return False
                except Exception as err:
                    logger.error(f"[AlertDelivery] Unexpected error editing message: {err}")
                    return False

        # Case B: Message was deleted / 404 -> Recreate once without spamming
        if not target_message and hasattr(target_channel, "send"):
            logger.info(f"[AlertDelivery] Self-healing primary alert for incident {incident.incident_id}...")
            try:
                new_msg = await target_channel.send(**kwargs)
                if new_msg and hasattr(new_msg, "id"):
                    incident.primary_alert_message_id = str(new_msg.id)
                    self.total_recreations_on_404 += 1
                    logger.info(f"[AlertDelivery] Successfully recreated primary alert as {new_msg.id}")
                    return True
            except Exception as send_err:
                logger.error(f"[AlertDelivery] Failed to recreate deleted primary alert: {send_err}")
                return False

        return False

    def _prepare_discord_kwargs(
        self,
        container_builder: ContainerBuilder,
        view: Optional[ui.View] = None,
    ) -> Dict[str, Any]:
        """Converts ContainerBuilder and View into discord.py send/edit kwargs."""
        kwargs: Dict[str, Any] = {}
        # Try Components V2 container payload
        try:
            built = container_builder.build()
            if isinstance(built, dict):
                # Check for components key or embed fallback
                if "components" in built:
                    kwargs["components"] = built["components"]
                if "embed" in built:
                    kwargs["embed"] = built["embed"]
                elif "embeds" in built:
                    kwargs["embeds"] = built["embeds"]
                if "content" in built:
                    kwargs["content"] = built["content"]
        except Exception:
            pass

        # If components wasn't populated or fallback needed, create clean fallback embed
        if not kwargs.get("embed") and not kwargs.get("components"):
            embed = discord.Embed(
                title=f"🛡️ Sentinel™ Security Incident",
                description="Live incident intelligence update.",
                color=discord.Color(0xED4245),
            )
            kwargs["embed"] = embed

        if view:
            kwargs["view"] = view

        return kwargs

    # Components V2 Container Builder
    def build_incident_container(
        self,
        incident: Incident,
        assessment: Optional[AssessmentResult] = None,
    ) -> Tuple[ContainerBuilder, ui.View]:
        """
        Builds modern Components V2 message container and interactive action row buttons.
        Zero hardcoded raw hex colors; strictly adheres to global COLORS and EMOJIS.
        """
        # Determine theme color & badge icon
        if incident.status == IncidentStatus.RESOLVED:
            accent_color = COLORS.get("success", "#3FD438")
            status_badge = f"{get_emoji('check', '✅')} **RESOLVED**"
        elif incident.status == IncidentStatus.DISMISSED:
            accent_color = COLORS.get("brand", "#5865F2")
            status_badge = f"{get_emoji('check', '✅')} **DISMISSED (FALSE ALARM)**"
        elif incident.severity == ThreatSeverity.CRITICAL or incident.is_emergency:
            accent_color = COLORS.get("danger", "#ED4245")
            status_badge = f"{get_emoji('warning', '🚨')} **CRITICAL EMERGENCY**"
        elif incident.severity == ThreatSeverity.HIGH:
            accent_color = COLORS.get("warning", "#F59E0B")
            status_badge = f"{get_emoji('shield', '🛡️')} **HIGH SEVERITY ALERT**"
        else:
            accent_color = COLORS.get("warning", "#F59E0B")
            status_badge = f"{get_emoji('info', 'ℹ️')} **SECURITY INCIDENT**"

        # Actors summary
        actors_str = ", ".join(f"<@{a.get('actor_id')}>" for a in incident.relevant_actors[:3]) or (f"<@{incident.actor_id}>" if incident.actor_id else "Unknown / System")

        # Targets summary
        targets_str = f"`{len(incident.relevant_targets)}` target(s)"
        if incident.relevant_targets:
            targets_sample = ", ".join(f"`{t}`" for t in incident.relevant_targets[:3])
            targets_str += f" ({targets_sample})"

        # Protective Actions summary
        if incident.protective_actions:
            actions_list = []
            for act in incident.protective_actions[-3:]:
                mode_tag = "SHADOW (Simulated)" if act.is_shadow_mode else "LIVE"
                actions_list.append(f"• `{act.action_type}` [{mode_tag}] -> `{act.status}`")
            actions_str = "\n".join(actions_list)
        else:
            actions_str = "• *None taken / Observing*"

        # Reason codes formatted
        reason_codes_str = ", ".join(f"`{r}`" for r in (incident.reason_codes or ["ACTIVITY_BURST"]))

        # Resolution details if resolved/dismissed
        resolution_block = ""
        if incident.status in (IncidentStatus.RESOLVED, IncidentStatus.DISMISSED) and incident.resolved_by:
            resolution_block = (
                f"\n\n### ⚖️ Reviewer Resolution\n"
                f"• **Reviewed By:** <@{incident.resolved_by}>\n"
                f"• **Outcome:** `{incident.status.upper()}`\n"
                f"• **Explanation:** {incident.resolution_reason or 'No additional notes provided'}\n"
                f"• **Forensic Evidence:** Preserved in audit database"
            )

        # Header and Body Content
        body_text = (
            f"**Status:** {status_badge}\n"
            f"**Pattern:** `{incident.trigger_rule_id or 'Burst Activity'}`\n"
            f"**Severity:** `{incident.severity.upper()}` | **Urgency:** `{incident.urgency.upper()}` | **Confidence:** `{incident.confidence.upper()}`\n"
            f"**Observed Actor(s):** {actors_str}\n"
            f"**Affected Target(s):** {targets_str}\n"
            f"**Correlated Evidence:** `{incident.event_count}` events preserved\n"
            f"**Detection Reasons:** {reason_codes_str}\n\n"
            f"### 🛡️ Protective Actions\n"
            f"{actions_str}"
            f"{resolution_block}"
        )

        container_builder = (
            ContainerBuilder()
            .set_accent_color(accent_color)
            .add_text_display(f"## {get_emoji('shield', '🛡️')} Sentinel™ Incident Intelligence: `{incident.incident_id}`")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(body_text)
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"-# Sentinel™ Security Core • Coalesced Updates: v{incident.pending_alert_version} • Reversible Protection"
            )
        )

        # View with action buttons
        view = ui.View(timeout=86400.0)

        # Confirm Threat Button
        btn_confirm = ui.Button(
            style=ButtonStyle.danger,
            label="Confirm Threat",
            custom_id=f"sentinel:alert:confirm:{incident.incident_id}",
            emoji=get_emoji("shield", "🛡️"),
            disabled=(incident.status in (IncidentStatus.RESOLVED, IncidentStatus.DISMISSED)),
        )
        view.add_item(btn_confirm)

        # Dismiss Button
        btn_dismiss = ui.Button(
            style=ButtonStyle.secondary,
            label="Dismiss (False Alarm)",
            custom_id=f"sentinel:alert:dismiss:{incident.incident_id}",
            emoji=get_emoji("check", "✅"),
            disabled=(incident.status in (IncidentStatus.RESOLVED, IncidentStatus.DISMISSED)),
        )
        view.add_item(btn_dismiss)

        # Clarify Button
        btn_clarify = ui.Button(
            style=ButtonStyle.secondary,
            label="Clarification Request",
            custom_id=f"sentinel:alert:clarify:{incident.incident_id}",
            emoji=get_emoji("tools", "🛠️"),
            disabled=(incident.status in (IncidentStatus.RESOLVED, IncidentStatus.DISMISSED)),
        )
        view.add_item(btn_clarify)

        return container_builder, view


# Global singleton instance
alert_intelligence_manager = AlertIntelligenceManager.get_instance()
alert_delivery_manager = AlertDeliveryManager.get_instance()
