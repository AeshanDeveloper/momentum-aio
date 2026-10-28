"""
Sentinel™ Security Unified Pipeline Orchestrator.

Agent 7 of 8 Security Core: Master integration hub binding observation, activity counting,
pattern detection, risk assessment, incident lifecycle, emergency lockdown containment,
and autonomous communications into an integrated, deterministic security system.

Pipeline Stages:
1. Observe & Normalize: SecurityEventNormalizer -> SecurityEventCollector
2. Rolling Activity Counting: SecurityActivityManager (actor & guild-wide windows)
3. Pattern Detection & Thresholds: SecurityCorrelationEngine (deterministic rules)
4. Risk Assessment & Incident Aggregation: ThreatAssessmentEngine & IncidentManager
5. Immediate Autonomous Protection: SecurityProtectionService & EmergencyLockdownManager
6. Autonomous Communication & Clarification: SecurityCommunicationService
7. Multi-Admin Consensus Review & Reversible Recovery: IncidentConsensusManager
"""

from __future__ import annotations

import time
import asyncio
import threading
from typing import Dict, Any, List, Optional, Set, Tuple, Union, Callable

import discord
from discord import Permissions

from config.settings import settings, COLORS, EMOJIS, IMAGES
from core.logging.logger import logger
from core.container.container import container
from database.database import database

# Security Core Components
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
from core.security.activity_manager import (
    SecurityActivityManager,
    security_activity_manager,
    ActivityCategory,
    EmergencySignal,
)
from core.security.correlation_engine import (
    SecurityCorrelationEngine,
    security_correlation_engine,
    ThreatSignal,
    ThreatSeverity,
    ThreatConfidence,
    ResponseCategory,
)
from core.security.threat_assessment import (
    ThreatAssessmentEngine,
    threat_assessment_engine,
    AssessmentResult,
)
from core.security.incident import (
    Incident,
    IncidentStatus,
    ProtectiveActionType,
)
from core.security.incident_manager import (
    IncidentManager,
    incident_manager,
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
from core.security.response_policy import (
    SecurityResponsePolicy,
    ResponseLevel,
    LockdownStatus,
    get_default_response_policy,
)
from core.security.protection_service import (
    SecurityProtectionService,
    security_protection_service,
)
from core.security.communication_service import (
    SecurityCommunicationService,
    security_communication_service,
)
from core.security.consensus_manager import (
    IncidentConsensusManager,
    incident_consensus_manager,
)
from core.security.antinuke import AntiNukeManager, AntiNukeConstants


class SentinelSecurityPipeline:
    """
    Central Coordinator of the Sentinel™ autonomous security architecture.
    Ensures safe initialization, single-pipeline event routing, dependency injection binding,
    and unified health diagnostics.
    """
    _instance: Optional["SentinelSecurityPipeline"] = None

    @classmethod
    def get_instance(cls) -> "SentinelSecurityPipeline":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(
        self,
        collector: Optional[SecurityEventCollector] = None,
        activity_mgr: Optional[SecurityActivityManager] = None,
        corr_engine: Optional[SecurityCorrelationEngine] = None,
        threat_engine: Optional[ThreatAssessmentEngine] = None,
        inc_manager: Optional[IncidentManager] = None,
        prot_service: Optional[SecurityProtectionService] = None,
        comm_service: Optional[SecurityCommunicationService] = None,
        consensus_mgr: Optional[IncidentConsensusManager] = None,
    ):
        self.collector: SecurityEventCollector = collector or security_event_collector
        self.activity_manager: SecurityActivityManager = activity_mgr or security_activity_manager
        self.correlation_engine: SecurityCorrelationEngine = corr_engine or security_correlation_engine
        self.threat_engine: ThreatAssessmentEngine = threat_engine or threat_assessment_engine
        self.incident_manager: IncidentManager = inc_manager or incident_manager
        self.protection_service: SecurityProtectionService = prot_service or security_protection_service
        self.communication_service: SecurityCommunicationService = comm_service or security_communication_service
        self.consensus_manager: IncidentConsensusManager = consensus_mgr or incident_consensus_manager

        self.bot_client: Optional[Any] = None
        self._is_initialized = False
        self._init_lock = threading.RLock()
        self._processed_event_count = 0

    def initialize(self, bot_client: Optional[Any] = None) -> bool:
        """
        Idempotent startup initializer.
        Wires all downstream subscribers, hydrates un-restored lockdowns across reboots,
        and registers singletons in IoC container.
        """
        with self._init_lock:
            if bot_client:
                self.bot_client = bot_client

            if self._is_initialized:
                if bot_client:
                    self.protection_service.bot_client = bot_client
                    self.communication_service.bot_client = bot_client
                return True

            logger.info("[SentinelPipeline] Initializing Sentinel Autonomous Security Core...")

            # 1. Attach ActivityManager to SecurityEventCollector
            self.activity_manager.attach_to_collector(self.collector)

            # 2. Attach CorrelationEngine to SecurityEventCollector & ActivityManager
            self.correlation_engine.attach_to_collector(self.collector)
            self.correlation_engine.attach_to_activity_manager(self.activity_manager)

            # 3. Attach IncidentManager to CorrelationEngine threat stream
            self.incident_manager.attach_to_correlation_engine(self.correlation_engine)

            # 4. Attach ProtectionService to IncidentManager stream
            self.protection_service.attach_to_incident_manager(self.bot_client)

            # 5. Attach CommunicationService to IncidentManager stream
            self.communication_service.protection_service = self.protection_service
            self.communication_service.attach_to_incident_manager(self.bot_client)

            # 6. Hydrate active un-restored lockdowns on startup
            active_lockdowns = self.protection_service.hydrate_active_lockdowns()

            # 7. Register singletons in IoC container
            container.bind("security_event_collector", self.collector)
            container.bind("security_activity_manager", self.activity_manager)
            container.bind("security_correlation_engine", self.correlation_engine)
            container.bind("threat_assessment_engine", self.threat_engine)
            container.bind("incident_manager", self.incident_manager)
            container.bind("security_protection_service", self.protection_service)
            container.bind("security_communication_service", self.communication_service)
            container.bind("incident_consensus_manager", self.consensus_manager)
            container.bind("sentinel_security_pipeline", self)

            self._is_initialized = True
            logger.info(
                f"[SentinelPipeline] Security Core successfully initialized. "
                f"Hydrated {len(active_lockdowns)} active lockdown(s)."
            )
            return True

    def process_gateway_event(
        self,
        event_name: str,
        *args: Any,
        audit_lookup_coro: Optional[Callable[[], Any]] = None,
        guild: Optional[discord.Guild] = None,
        actor: Optional[Union[discord.Member, discord.User]] = None,
        audit_entry_id: Optional[Union[int, str]] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Optional[SecurityEvent]:
        """
        Unified gateway event ingestion entry point.
        Normalizes any Heterogeneous Discord gateway vector, handles actor attribution,
        and injects into the fast-path observation pipeline.
        """
        try:
            sec_event: Optional[SecurityEvent] = None
            resolved_guild = guild

            # Normalization dispatch based on event_name / canonical_event
            canonical = AntiNukeConstants.normalize_event(event_name) or event_name

            if canonical == AntiNukeConstants.EVENT_CHANNEL_CREATE and args:
                ch = args[0]
                sec_event = SecurityEventNormalizer.normalize_channel_create(ch)
                resolved_guild = resolved_guild or getattr(ch, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_CHANNEL_DELETE and args:
                ch = args[0]
                sec_event = SecurityEventNormalizer.normalize_channel_delete(ch)
                resolved_guild = resolved_guild or getattr(ch, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_CHANNEL_UPDATE and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_channel_update(args[0], args[1])
                resolved_guild = resolved_guild or getattr(args[1], "guild", None)

            elif canonical == AntiNukeConstants.EVENT_ROLE_CREATE and args:
                role = args[0]
                sec_event = SecurityEventNormalizer.normalize_role_create(role)
                resolved_guild = resolved_guild or getattr(role, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_ROLE_DELETE and args:
                role = args[0]
                sec_event = SecurityEventNormalizer.normalize_role_delete(role, guild=resolved_guild)
                resolved_guild = resolved_guild or getattr(role, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_ROLE_UPDATE and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_role_update(args[0], args[1])
                resolved_guild = resolved_guild or getattr(args[1], "guild", None)

            elif canonical in (AntiNukeConstants.EVENT_BAN_ADD, "member_ban") and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_member_ban(args[0], args[1])
                resolved_guild = resolved_guild or args[0]

            elif canonical in (AntiNukeConstants.EVENT_BAN_REMOVE, "member_unban") and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_member_unban(args[0], args[1])
                resolved_guild = resolved_guild or args[0]

            elif canonical in (AntiNukeConstants.EVENT_MEMBER_REMOVE, "member_remove") and args:
                member = args[0]
                is_kick = kwargs.get("is_kick", False)
                actor_id = str(actor.id) if actor else None
                sec_event = SecurityEventNormalizer.normalize_member_remove(member, is_kick=is_kick, actor_id=actor_id)
                resolved_guild = resolved_guild or getattr(member, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_MEMBER_UPDATE and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_member_update(args[0], args[1])
                resolved_guild = resolved_guild or getattr(args[1], "guild", None)

            elif canonical == AntiNukeConstants.EVENT_GUILD_UPDATE and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_guild_update(args[0], args[1])
                resolved_guild = resolved_guild or args[1]

            elif canonical == AntiNukeConstants.EVENT_EMOJIS_UPDATE and len(args) >= 3:
                sec_event = SecurityEventNormalizer.normalize_emojis_update(args[0], args[1], args[2])
                resolved_guild = resolved_guild or args[0]

            elif canonical == AntiNukeConstants.EVENT_STICKERS_UPDATE and len(args) >= 3:
                sec_event = SecurityEventNormalizer.normalize_stickers_update(args[0], args[1], args[2])
                resolved_guild = resolved_guild or args[0]

            elif canonical == AntiNukeConstants.EVENT_WEBHOOKS_UPDATE and args:
                ch = args[0]
                sec_event = SecurityEventNormalizer.normalize_webhooks_update(ch)
                resolved_guild = resolved_guild or getattr(ch, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_INVITE_CREATE and args:
                inv = args[0]
                sec_event = SecurityEventNormalizer.normalize_invite_create(inv)
                resolved_guild = resolved_guild or getattr(inv, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_INVITE_DELETE and args:
                inv = args[0]
                sec_event = SecurityEventNormalizer.normalize_invite_delete(inv)
                resolved_guild = resolved_guild or getattr(inv, "guild", None)

            elif canonical == AntiNukeConstants.EVENT_INTEGRATIONS_UPDATE and args:
                g = args[0]
                sec_event = SecurityEventNormalizer.normalize_integrations_update(g)
                resolved_guild = resolved_guild or g

            elif canonical == AntiNukeConstants.EVENT_AUTOMOD_CREATE and args:
                sec_event = SecurityEventNormalizer.normalize_automod_create(args[0])

            elif canonical == AntiNukeConstants.EVENT_AUTOMOD_UPDATE and len(args) >= 2:
                sec_event = SecurityEventNormalizer.normalize_automod_update(args[1])

            elif canonical == AntiNukeConstants.EVENT_AUTOMOD_DELETE and args:
                sec_event = SecurityEventNormalizer.normalize_automod_delete(args[0])

            elif canonical == AntiNukeConstants.EVENT_AUDIT_LOG_CREATE and args:
                sec_event = SecurityEventNormalizer.normalize_audit_log_entry(args[0])

            elif canonical == AntiNukeConstants.EVENT_SCHEDULED_EVENT_DELETE and args:
                sec_event = SecurityEventNormalizer.normalize_scheduled_event_delete(args[0])

            elif canonical == AntiNukeConstants.EVENT_THREAD_DELETE and args:
                sec_event = SecurityEventNormalizer.normalize_thread_delete(args[0])

            elif canonical == AntiNukeConstants.EVENT_BOT_ADD and args:
                sec_event = SecurityEventNormalizer.normalize_bot_add(args[0])

            if not sec_event:
                return None

            # Enrich with known actor if already resolved in calling context
            if actor:
                is_wl = None
                if details:
                    if "is_whitelisted" in details:
                        is_wl = bool(details["is_whitelisted"])
                    elif "is_whitelisted_actor" in details:
                        is_wl = bool(details["is_whitelisted_actor"])
                sec_event.enrich_actor(
                    actor_id=str(actor.id),
                    actor_name=str(actor),
                    reason=details.get("reason") if details else None,
                    confidence=AttributionConfidence.VERIFIED,
                    is_whitelisted=is_wl,
                    source_id=str(audit_entry_id) if audit_entry_id else None,
                )

            if details:
                sec_event.metadata.update(details)
                if sec_event.is_whitelisted_actor is None:
                    if "is_whitelisted" in details:
                        sec_event.is_whitelisted_actor = bool(details["is_whitelisted"])
                    elif "is_whitelisted_actor" in details:
                        sec_event.is_whitelisted_actor = bool(details["is_whitelisted_actor"])

            # Ingest into observation layer
            self._processed_event_count += 1
            return self.collector.ingest(
                event=sec_event,
                audit_lookup_coro=audit_lookup_coro,
                discord_guild=resolved_guild,
            )

        except Exception as err:
            logger.error(f"[SentinelPipeline] Error processing gateway event {event_name}: {err}")
            return None

    # Diagnostic & Health Reporting
    async def get_health_status(self, guild: Optional[discord.Guild] = None) -> Dict[str, Any]:
        """
        Gathers comprehensive diagnostics for the securitycheck command.
        Evaluates collector status, counters, detector health, protection service,
        shadow mode, queue health, database reachability (with timeout), permissions,
        trusted admin configs, active lockdowns, and incident counts.
        """
        now = time.time()
        gid = str(guild.id) if guild else "0"
        policy = self.protection_service.get_policy(gid)

        # 1. Collector status & queues
        collector_healthy = self.collector is not None
        recent_events_count = len(self.collector._recent_events)
        guild_events_count = len(self.collector.get_recent_events_for_guild(gid)) if gid != "0" else recent_events_count
        pending_tasks = len(self.collector._pending_tasks)
        subscribers_count = len(self.collector._subscribers)
        dedup_cache_size = len(self.collector._dedup_cache)

        # 2. Activity Manager health
        tracked_actors_count = 0
        actors_map = getattr(self.activity_manager, "_actor_buckets", getattr(self.activity_manager, "_guild_actors", {}))
        if gid in actors_map:
            tracked_actors_count = len(actors_map[gid])

        # 3. Correlation Engine health
        loaded_rules_count = len(self.correlation_engine.list_rules())
        processed_dedup_count = len(self.correlation_engine._processed_events)

        # 4. Protection Service & Shadow Mode
        is_shadow_mode = policy.shadow_mode or not policy.auto_lockdown_enabled
        journal = getattr(self.protection_service, "journal", lockdown_journal_manager)
        active_lockdowns_total = len(journal.get_all_active_lockdowns())
        guild_active_lockdown = journal.get_active_lockdown_for_guild(gid)

        # 5. Incident Counts
        guild_incidents = self.incident_manager.get_active_incidents(gid) if gid != "0" else []
        open_incidents_count = len(guild_incidents)

        # 6. Database reachability with strict timeout
        db_reachable = False
        db_latency_ms: Optional[float] = None
        db_error: Optional[str] = None
        try:
            start_t = time.perf_counter()
            col = database.collection("security_response_policies")

            async def _check_db():
                if hasattr(col, "find_one"):
                    cursor = col.find_one({"guild_id": gid})
                    if asyncio.iscoroutine(cursor):
                        return await cursor
                    return cursor
                return None

            await asyncio.wait_for(_check_db(), timeout=1.5)
            db_latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            db_reachable = True
        except asyncio.TimeoutError:
            db_reachable = False
            db_error = "Database query timed out (> 1.5s)"
        except Exception as err:
            db_reachable = False
            db_error = str(err)

        # 7. Bot Permissions and Role Hierarchy Auditing
        hierarchy_status = {"can_act": True, "reasons": [], "bot_top_role": None, "higher_roles": []}
        if guild:
            me = getattr(guild, "me", None)
            if me:
                bot_top = me.top_role
                hierarchy_status["bot_top_role"] = bot_top.name
                perms = me.guild_permissions
                needed_perms = {
                    "administrator": perms.administrator,
                    "manage_roles": perms.manage_roles,
                    "manage_channels": perms.manage_channels,
                    "ban_members": perms.ban_members,
                    "kick_members": perms.kick_members,
                    "view_audit_log": perms.view_audit_log,
                }
                missing = [p for p, has in needed_perms.items() if not has]
                if not perms.administrator and missing:
                    hierarchy_status["reasons"].append(f"Missing permissions: {', '.join(missing)}")
                    hierarchy_status["can_act"] = False

                bot_pos = getattr(bot_top, "position", 0)
                higher_roles = [
                    getattr(r, "name", str(r))
                    for r in getattr(guild, "roles", [])
                    if getattr(r, "position", 0) > bot_pos and not getattr(r, "managed", False)
                ]
                hierarchy_status["higher_roles"] = higher_roles[:5]
                if higher_roles:
                    hierarchy_status["reasons"].append(
                        f"{len(higher_roles)} role(s) above bot role '{getattr(bot_top, 'name', 'bot')}' cannot be restricted during emergency"
                    )

        # 8. Supported Handlers Count (all 23 vectors)
        registered_handlers_count = len(AntiNukeConstants.ALL_EVENTS)

        return {
            "timestamp": now,
            "pipeline_initialized": self._is_initialized,
            "collector": {
                "running": collector_healthy,
                "recent_events_count": recent_events_count,
                "guild_events_count": guild_events_count,
                "subscribers_count": subscribers_count,
                "pending_tasks": pending_tasks,
                "dedup_cache_size": dedup_cache_size,
            },
            "activity_manager": {
                "healthy": True,
                "tracked_actors_count": tracked_actors_count,
            },
            "correlation_engine": {
                "healthy": True,
                "loaded_rules_count": loaded_rules_count,
                "processed_dedup_count": processed_dedup_count,
            },
            "protection_service": {
                "enabled": policy.auto_lockdown_enabled,
                "response_level": policy.response_level,
                "shadow_mode": is_shadow_mode,
                "active_lockdowns_total": active_lockdowns_total,
                "guild_lockdown_status": guild_active_lockdown.status if guild_active_lockdown else None,
                "guild_lockdown_id": guild_active_lockdown.lockdown_id if guild_active_lockdown else None,
            },
            "database": {
                "reachable": db_reachable,
                "latency_ms": db_latency_ms,
                "error": db_error,
            },
            "hierarchy": hierarchy_status,
            "notifications": {
                "recovery_owner_configured": bool(policy.recovery_owner_id),
                "trusted_admins_count": len(policy.trusted_recovery_admin_ids),
                "fallback_channel_configured": bool(policy.fallback_channel_id),
            },
            "open_incidents_count": open_incidents_count,
            "registered_handlers_count": registered_handlers_count,
            "processed_events_total": self._processed_event_count,
        }


# Global singleton
sentinel_pipeline = SentinelSecurityPipeline.get_instance()
