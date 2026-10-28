"""
Sentinel™ Security Protection Service.

Agent 5 of 8 Security Core: High-level orchestrator integrating Incident Manager
event streams, autonomous emergency containment execution, admin DM/fallback notifications,
and startup state hydration.

Key capabilities:
- Auto-Subscribes to IncidentManager lifecycle events to trigger fast emergency containment.
- Hydrates active un-restored lockdowns on bot startup/restart.
- Per-guild policy management with MongoDB persistence and safe defaults.
- Clean public API for automated containment, manual overrides, and posture audits.
"""

from __future__ import annotations

import time
import inspect
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set, Union

import discord

from config.settings import settings, COLORS, EMOJIS, get_color, get_emoji
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
from core.security.admin_notifier import (
    AdminNotifier,
    admin_notifier,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
)
from core.security.threat_assessment import AssessmentResult
from core.security.incident_manager import incident_manager, IncidentManager


class SecurityProtectionService:
    """
    High-level coordinator bridging IncidentManager and EmergencyLockdownManager.
    """
    _instance: Optional["SecurityProtectionService"] = None

    @classmethod
    def get_instance(cls) -> "SecurityProtectionService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(
        self,
        lockdown_mgr: Optional[EmergencyLockdownManager] = None,
        notifier: Optional[AdminNotifier] = None,
        journal_mgr: Optional[LockdownJournalManager] = None,
        inc_mgr: Optional[IncidentManager] = None,
    ):
        self.lockdown_manager: EmergencyLockdownManager = lockdown_mgr or emergency_lockdown_manager
        self.notifier: AdminNotifier = notifier or admin_notifier
        self.journal: LockdownJournalManager = journal_mgr or lockdown_journal_manager
        self.incident_manager: IncidentManager = inc_mgr or incident_manager
        
        # Bot client reference for Discord API calls
        self.bot_client: Optional[Any] = None
        
        # In-memory policy cache: guild_id -> SecurityResponsePolicy
        self._policies: Dict[str, SecurityResponsePolicy] = {}
        self._lock = threading.RLock()
        self._is_attached = False

    def attach_to_incident_manager(self, bot_client: Optional[Any] = None) -> None:
        """Subscribes to IncidentManager event stream and stores client reference."""
        if bot_client:
            self.bot_client = bot_client
        if not self._is_attached:
            self.incident_manager.subscribe_incidents(self.on_incident_event)
            self._is_attached = True
            logger.info("[ProtectionService] Attached to IncidentManager event stream")

    def hydrate_active_lockdowns(self) -> List[LockdownRecord]:
        """
        Hydrates active un-restored lockdowns on bot startup/restart.
        Ensures Sentinel can safely recover servers across reboots.
        """
        active_lockdowns = self.journal.get_all_active_lockdowns()
        logger.info(f"[ProtectionService] Hydrated {len(active_lockdowns)} active/partial lockdown(s) from storage")
        return active_lockdowns

    def is_lockdown_active(self, guild_id: Union[str, int]) -> bool:
        """Checks if a guild currently has an active or partial lockdown in the journal."""
        return self.journal.get_active_lockdown_for_guild(guild_id) is not None

    # Policy Management
    def get_policy(self, guild_id: Union[str, int]) -> SecurityResponsePolicy:
        """Retrieves or loads the security response policy for a guild."""
        gid = str(guild_id)
        with self._lock:
            if gid in self._policies:
                return self._policies[gid]

        # Attempt to load from MongoDB
        try:
            doc = database.find_one("security_response_policies", {"guild_id": gid})
            if inspect.isawaitable(doc):
                # find_one returned a coroutine; schedule background hydration if loop is running
                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(self._hydrate_policy_async(gid, doc))
                except RuntimeError:
                    pass
            elif isinstance(doc, dict):
                policy = SecurityResponsePolicy.from_dict(doc)
                with self._lock:
                    self._policies[gid] = policy
                return policy
        except Exception as err:
            logger.debug(f"[ProtectionService] Failed to load policy from DB: {err}")

        # Return default policy (shadow mode enabled)
        default_pol = get_default_response_policy(gid)
        with self._lock:
            self._policies[gid] = default_pol
        return default_pol

    async def _hydrate_policy_async(self, gid: str, doc_coro: Any) -> None:
        try:
            doc = await doc_coro
            if doc and isinstance(doc, dict):
                policy = SecurityResponsePolicy.from_dict(doc)
                with self._lock:
                    self._policies[gid] = policy
        except Exception as err:
            logger.debug(f"[ProtectionService] Async policy hydration failed for {gid}: {err}")

    async def get_policy_async(self, guild_id: Union[str, int]) -> SecurityResponsePolicy:
        """Asynchronously retrieves or loads the security response policy for a guild."""
        gid = str(guild_id)
        with self._lock:
            if gid in self._policies:
                return self._policies[gid]
        try:
            doc = await database.find_one("security_response_policies", {"guild_id": gid})
            if doc and isinstance(doc, dict):
                policy = SecurityResponsePolicy.from_dict(doc)
                with self._lock:
                    self._policies[gid] = policy
                return policy
        except Exception as err:
            logger.debug(f"[ProtectionService] Failed to load policy async from DB: {err}")
        return self.get_policy(gid)

    def save_policy(self, policy: SecurityResponsePolicy) -> None:
        """Saves a security response policy to memory and MongoDB."""
        gid = str(policy.guild_id)
        with self._lock:
            self._policies[gid] = policy

        try:
            database.update_one(
                "security_response_policies",
                {"guild_id": gid},
                {"$set": policy.to_dict()},
                upsert=True,
            )
            logger.info(f"[ProtectionService] Saved policy for guild {gid} (Auto-lockdown: {policy.auto_lockdown_enabled})")
        except Exception as err:
            logger.error(f"[ProtectionService] Failed to persist policy for guild {gid}: {err}")

    # Incident Stream Handler
    def on_incident_event(self, incident: Incident, assessment: AssessmentResult) -> None:
        """
        Callback invoked by IncidentManager when an incident is created or updated.
        Evaluates emergency response and schedules asynchronous execution.
        """
        # Only act if emergency containment is recommended
        if not assessment.should_trigger_immediate_response:
            return

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self._process_incident_protection(incident, assessment))
                return
        except RuntimeError:
            pass

        # If not inside an active event loop, run in a separate thread or event loop
        asyncio.run(self._process_incident_protection(incident, assessment))

    async def _process_incident_protection(self, incident: Incident, assessment: AssessmentResult) -> None:
        """
        Asynchronously executes emergency containment and dispatches admin notifications.
        """
        gid = str(incident.guild_id)
        policy = self.get_policy(gid)

        # Obtain guild instance and client
        client = getattr(self.bot_client, "client", self.bot_client)
        guild = None
        try:
            target_gid = int(gid)
            if client and hasattr(client, "get_guild"):
                guild = client.get_guild(target_gid)
            elif self.bot_client and hasattr(self.bot_client, "get_guild"):
                guild = self.bot_client.get_guild(target_gid)
        except (ValueError, TypeError):
            pass

        # 1. Execute Emergency Containment
        lockdown_record = await self.lockdown_manager.execute_emergency_lockdown(
            guild=guild,
            incident=incident,
            assessment=assessment,
            policy=policy,
        )

        # 2. Dispatch Interactive Alerts to Trusted Admins
        if policy.response_level in (ResponseLevel.ALERT, ResponseLevel.LOCKDOWN):
            await self.notifier.dispatch_emergency_alert(
                bot_client=client or self.bot_client,
                guild=guild,
                incident=incident,
                lockdown_record=lockdown_record,
                policy=policy,
            )

        # 3. Dispatch Threat Forensic Log directly to server's security forensic logs channel
        await self.dispatch_threat_log(
            guild=guild,
            incident=incident,
            assessment=assessment,
            lockdown_record=lockdown_record,
            policy=policy,
        )

    async def dispatch_threat_log(
        self,
        guild: Any,
        incident: Incident,
        assessment: AssessmentResult,
        lockdown_record: Optional[LockdownRecord] = None,
        policy: Optional[SecurityResponsePolicy] = None,
    ) -> bool:
        """
        Dispatches structured forensic threat log directly to the server's security logs forensic logs channel.
        """
        if not guild:
            return False

        gid = str(guild.id)
        pol = policy or self.get_policy(gid)

        from core.security.antinuke import AntiNukeManager
        cfg = AntiNukeManager.get_guild_config(gid)

        target_channel = None
        candidate_ids = [
            pol.fallback_channel_id,
            cfg.get("warning_channel_id"),
            cfg.get("log_channel_id"),
        ]
        for cid in candidate_ids:
            if cid and hasattr(guild, "get_channel"):
                try:
                    target_channel = guild.get_channel(int(cid))
                    if target_channel:
                        break
                except Exception:
                    pass

        is_shadow = getattr(lockdown_record, "is_shadow_mode", False) if lockdown_record else getattr(incident, "is_shadow_mode", False)
        mode_label = "SHADOW (Simulation)" if is_shadow else "LIVE ENFORCEMENT"
        rec_action = assessment.recommended_action.value if hasattr(assessment.recommended_action, "value") else str(getattr(assessment, "recommended_action", "ALERT"))
        sev_str = (getattr(assessment, "severity", None) or "medium").upper()
        conf_str = (getattr(assessment, "confidence", None) or "inferred").upper()
        score_val = getattr(assessment, "threat_score", 0.0) or 0.0

        from sdk.discord.builders import ContainerBuilder, SeparatorSpacingSize
        threat_box = (
            ContainerBuilder()
            .set_accent_color(COLORS.get("danger", "#ED4245"))
            .add_text_display(f"### {EMOJIS.get('danger', '🚨')} Sentinel™ Threat Forensic Log")
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .add_text_display(
                f"**Aegis Correlation Threat Assessment**\n\n"
                f"• **Incident ID:** `{incident.incident_id}`\n"
                f"• **Threat Score:** `{score_val:.1f} / 100` ({sev_str})\n"
                f"• **Attribution Confidence:** `{conf_str}`\n"
                f"• **Recommended Action:** `{rec_action.upper()}`\n"
                f"• **Operating Mode:** `{mode_label}`\n"
                f"• **Incident Context:** {incident.title}\n"
                f"• **Timestamp:** <t:{int(time.time())}:F> (<t:{int(time.time())}:R>)"
            )
            .add_separator(divider=True, spacing=SeparatorSpacingSize.Small)
            .set_footer(f"{settings.BOT_NAME} Forensic Audit Trail • Tamper-Evident SHA-256")
            .build()
        )

        sent = False
        if target_channel and hasattr(target_channel, "send"):
            try:
                await target_channel.send(view=threat_box)
                sent = True
            except Exception as err:
                logger.warning(f"[ProtectionService] Threat log delivery to forensic channel failed: {err}")

        # Dispatch via UnifiedWebhookLogger under LogCategory.SECURITY
        try:
            from core.logging.webhook_logger import UnifiedWebhookLogger, LogCategory, LogSeverity
            await UnifiedWebhookLogger.dispatch_log(
                guild=guild,
                category=LogCategory.SECURITY,
                title=f"Security Threat Forensic Log: {incident.title}",
                description=f"A threat assessment was executed by Sentinel. Threat score: {score_val:.1f}.",
                reason=f"Action: {rec_action.upper()} | Mode: {mode_label}",
                fields=[
                    {"name": "Incident ID", "value": f"`{incident.incident_id}`", "inline": True},
                    {"name": "Threat Score", "value": f"`{score_val:.1f}`", "inline": True},
                    {"name": "Confidence", "value": f"`{conf_str}`", "inline": True},
                    {"name": "Enforced Action", "value": f"`{rec_action.upper()}`", "inline": True},
                ],
                severity=LogSeverity.CRITICAL if sev_str == "CRITICAL" else LogSeverity.HIGH,
            )
        except Exception as err:
            logger.debug(f"[ProtectionService] Webhook logger dispatch for threat log: {err}")

        return sent

    # Manual Command Helpers
    async def manual_lockdown(
        self,
        guild: Any,
        admin_id: Union[str, int],
        reason: str = "Manual lockdown requested by admin",
    ) -> LockdownRecord:
        """Allows authorized administrators to manually trigger emergency lockdown."""
        gid = str(guild.id if guild else "0")
        policy = self.get_policy(gid)

        # Synthetic incident for manual trigger
        incident = Incident(
            guild_id=gid,
            title=f"Manual Emergency Lockdown: {reason}",
            status=IncidentStatus.ACTIVE,
            severity="high",
            confidence="high",
            is_emergency=True,
            is_shadow_mode=False,  # Manual trigger executes in live mode
        )
        assessment = AssessmentResult(
            signal_id=f"manual_{int(time.time())}",
            threat_score=100.0,
            severity="high",
            confidence="high",
            should_trigger_immediate_response=True,
            recommended_action=ProtectiveActionType.EMERGENCY_LOCKDOWN,
            is_shadow_mode=False,
        )

        # Force live execution for manual command
        active_policy = SecurityResponsePolicy.from_dict(policy.to_dict())
        active_policy.shadow_mode = False
        active_policy.auto_lockdown_enabled = True

        record = await self.lockdown_manager.execute_emergency_lockdown(
            guild=guild,
            incident=incident,
            assessment=assessment,
            policy=active_policy,
        )

        incident.add_decision(
            actor_id=str(admin_id),
            decision_type="manual_lockdown",
            reason=reason,
        )
        return record

    async def manual_recovery(
        self,
        guild: Any,
        lockdown_id: str,
        admin_id: Union[str, int],
        force: bool = False,
    ) -> LockdownRecord:
        """Allows authorized administrators to manually trigger recovery rollback."""
        gid = str(guild.id if guild else "0")
        policy = self.get_policy(gid)
        return await self.lockdown_manager.restore_lockdown(
            guild=guild,
            lockdown_id=lockdown_id,
            admin_user_id=admin_id,
            policy=policy,
            force=force,
        )

    def audit_posture(self, guild: Any) -> Dict[str, Any]:
        """Runs the posture and hierarchy diagnostic audit."""
        gid = str(guild.id if guild else "0")
        policy = self.get_policy(gid)
        return self.lockdown_manager.audit_guild_security_posture(guild, policy)


# Global singleton service
security_protection_service = SecurityProtectionService.get_instance()
