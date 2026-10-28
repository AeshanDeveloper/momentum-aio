"""
Sentinel™ Security Event Collector.

Fast, non-blocking observation pipeline for Discord security events.
Provides:
- Instant in-memory ingestion with zero gateway lag
- Deduplication of overlapping gateway and audit log signals
- Asynchronous actor attribution enrichment with graduated confidence (verified, probable, unknown)
- Persistent event logging to database (security_events)
- Observer / pub-sub subscription interface for downstream threat analysis (Agent 2)
- Strict non-suppression of whitelisted actors
"""

import time
import inspect
import asyncio
import collections
from typing import Dict, List, Callable, Optional, Any, Set, Tuple
import discord

from core.logging.logger import logger
from database.database import database
from core.security.security_event import (
    SecurityEvent,
    SecurityEventType,
    AttributionConfidence,
    SecurityEventStatus,
)
from core.security.antinuke import AntiNukeManager


class SecurityEventCollector:
    """
    Central event ingestion, deduplication, asynchronous attribution enrichment,
    and subscriber dispatch hub for Sentinel™.
    """

    _instance: Optional["SecurityEventCollector"] = None

    def __init__(self, max_recent_events: int = 2000, dedup_ttl_seconds: float = 15.0):
        # Ring buffer of recent normalized security events (bounded memory)
        self._recent_events: collections.deque[SecurityEvent] = collections.deque(maxlen=max_recent_events)
        self._events_by_id: Dict[str, SecurityEvent] = {}
        self._events_by_guild: Dict[str, collections.deque[SecurityEvent]] = collections.defaultdict(
            lambda: collections.deque(maxlen=200)
        )

        # Bounded deduplication tracking: dedup_key -> (timestamp, SecurityEvent)
        self._dedup_cache: Dict[str, Tuple[float, SecurityEvent]] = {}
        self._dedup_ttl_seconds = dedup_ttl_seconds

        # Subscribers: list of (callback, event_types_filter, min_confidence_filter)
        self._subscribers: List[Tuple[Callable[[SecurityEvent], Any], Optional[Set[str]], Optional[str]]] = []

        # Background enrichment tasks tracking
        self._pending_tasks: Set[asyncio.Task] = set()

    @classmethod
    def get_instance(cls) -> "SecurityEventCollector":
        """Singleton accessor for the security event collector."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Resets the singleton instance (primarily for isolated test fixtures)."""
        cls._instance = None

    def subscribe(
        self,
        callback: Callable[[SecurityEvent], Any],
        event_types: Optional[List[str]] = None,
        min_confidence: Optional[str] = None,
    ) -> Callable[[SecurityEvent], Any]:
        """
        Subscribes a downstream component (such as Agent 2 threat evaluators) to enriched events.

        :param callback: Async coroutine function or synchronous callable accepting SecurityEvent.
        :param event_types: Optional list of SecurityEventType strings to filter on.
        :param min_confidence: Optional minimum AttributionConfidence required ("unknown", "probable", "verified").
        :return: The registered callback for easy unsubscription.
        """
        types_set = set(event_types) if event_types else None
        self._subscribers.append((callback, types_set, min_confidence))
        return callback

    def unsubscribe(self, callback: Callable[[SecurityEvent], Any]) -> bool:
        """Removes a registered subscriber callback."""
        initial_len = len(self._subscribers)
        self._subscribers = [s for s in self._subscribers if s[0] != callback]
        return len(self._subscribers) < initial_len

    def clear_subscribers(self) -> None:
        """Removes all subscribers."""
        self._subscribers.clear()

    def _purge_expired_dedup(self) -> None:
        """Evicts expired keys from the deduplication cache."""
        now = time.time()
        expired = [k for k, (t, _) in self._dedup_cache.items() if now - t > self._dedup_ttl_seconds]
        for k in expired:
            self._dedup_cache.pop(k, None)

    @staticmethod
    def _check_actor_whitelist(guild_id: str, actor_id: str, event_type: str) -> bool:
        """
        Safely evaluates if an actor is whitelisted without throwing exceptions.
        Whitelisted actors are marked in metadata, but never suppressed by the observation layer.
        """
        try:
            if not AntiNukeManager.is_setup_completed(guild_id):
                return False
            cfg = AntiNukeManager.get_guild_config(str(guild_id))
            if str(actor_id) in [str(x) for x in cfg.get("extra_owners", [])]:
                return True
            whitelists = cfg.get("whitelists", {})
            if str(actor_id) in whitelists:
                data = whitelists[str(actor_id)]
                allowed = data.get("events", []) if isinstance(data, dict) else data
                if not allowed or "*" in allowed or "all" in allowed or event_type in allowed:
                    return True
            if "user" in whitelists:
                user_list = whitelists["user"]
                if isinstance(user_list, list) and (str(actor_id) in user_list or any(str(x) == str(actor_id) for x in user_list)):
                    return True
            return AntiNukeManager.is_whitelisted(guild_id, actor_id, event_type)
        except Exception:
            return False

    def ingest(
        self,
        event: SecurityEvent,
        audit_lookup_coro: Optional[Callable[[], Any]] = None,
        discord_guild: Optional[discord.Guild] = None,
    ) -> SecurityEvent:
        """
        Ingests a normalized security event into the observation layer.
        Returns immediately, running audit enrichment and subscriber notification asynchronously.

        :param event: The normalized SecurityEvent instance.
        :param audit_lookup_coro: Optional async callable that resolves a matching discord.AuditLogEntry.
        :param discord_guild: Optional discord.Guild context.
        :return: The ingested SecurityEvent (or merged existing event if deduplicated).
        """
        self._purge_expired_dedup()

        # Check deduplication cache
        if event.dedup_key in self._dedup_cache:
            _, existing_event = self._dedup_cache[event.dedup_key]
            # If the incoming event has verified attribution while existing was unknown, upgrade existing!
            if event.is_verified and existing_event.is_unknown:
                existing_event.enrich_actor(
                    actor_id=event.actor_id or "",
                    actor_name=event.actor_name,
                    reason=event.reason,
                    confidence=AttributionConfidence.VERIFIED,
                    is_whitelisted=event.is_whitelisted_actor,
                    source_id=event.source_id,
                )
                self._dispatch_event(existing_event)
                return existing_event

            # Otherwise suppress duplicate signal
            event.status = SecurityEventStatus.SUPPRESSED_DUPLICATE
            return existing_event

        # Check whitelist if actor is present
        if event.actor_id and event.is_whitelisted_actor is None:
            event.is_whitelisted_actor = self._check_actor_whitelist(event.guild_id, event.actor_id, event.event_type)

        # Record in dedup cache and in-memory ring buffers
        now = time.time()
        self._dedup_cache[event.dedup_key] = (now, event)
        self._recent_events.append(event)
        self._events_by_id[event.event_id] = event
        self._events_by_guild[event.guild_id].append(event)

        # Asynchronous enrichment and dispatch
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                task = loop.create_task(
                    self._enrich_and_dispatch(
                        event=event,
                        audit_lookup_coro=audit_lookup_coro,
                        discord_guild=discord_guild,
                    )
                )
                self._pending_tasks.add(task)
                task.add_done_callback(self._pending_tasks.discard)
            else:
                self._dispatch_event(event)
        except RuntimeError:
            # No running event loop (e.g. sync unit test without loop); dispatch immediately
            self._dispatch_event(event)

        return event

    async def _enrich_and_dispatch(
        self,
        event: SecurityEvent,
        audit_lookup_coro: Optional[Callable[[], Any]] = None,
        discord_guild: Optional[discord.Guild] = None,
    ) -> None:
        """
        Background worker task:
        1. If actor is unknown and audit query is provided, queries audit log with timeout and short retry.
        2. Evaluates whitelisted actor status (without suppressing the event!).
        3. Persists event to MongoDB collection 'security_events'.
        4. Notifies all downstream subscribers.
        """
        try:
            # 1. Audit log enrichment if actor attribution is unknown
            if event.is_unknown and audit_lookup_coro is not None:
                event.status = SecurityEventStatus.ENRICHING
                audit_entry = None

                # Attempt 1: immediate query
                try:
                    audit_entry = await asyncio.wait_for(audit_lookup_coro(), timeout=2.5)
                except (asyncio.TimeoutError, Exception) as err:
                    logger.debug(f"[EventCollector] Initial audit log lookup timeout/err for {event.event_type}: {err}")

                # Attempt 2: brief delay for Discord audit log ingestion propagation
                if audit_entry is None:
                    await asyncio.sleep(0.8)
                    try:
                        audit_entry = await asyncio.wait_for(audit_lookup_coro(), timeout=2.0)
                    except (asyncio.TimeoutError, Exception) as err:
                        logger.debug(f"[EventCollector] Retry audit log lookup timeout/err for {event.event_type}: {err}")

                if audit_entry and getattr(audit_entry, "user", None):
                    actor = audit_entry.user
                    actor_id = str(actor.id)
                    actor_name = str(actor)
                    reason = getattr(audit_entry, "reason", None)
                    source_id = str(audit_entry.id)

                    is_whitelisted = self._check_actor_whitelist(event.guild_id, actor_id, event.event_type)

                    event.enrich_actor(
                        actor_id=actor_id,
                        actor_name=actor_name,
                        reason=reason,
                        confidence=AttributionConfidence.VERIFIED,
                        is_whitelisted=is_whitelisted,
                        source_id=source_id,
                    )
                else:
                    # Retain observation with UNKNOWN confidence (never discarded)
                    event.status = SecurityEventStatus.ENRICHED

            # If actor is already present, verify whitelist status for downstream policy
            if event.actor_id and event.is_whitelisted_actor is None:
                event.is_whitelisted_actor = self._check_actor_whitelist(event.guild_id, event.actor_id, event.event_type)

            # 2. Persist to database safely
            await self._persist_event(event)

            # 3. Dispatch to subscribers
            self._dispatch_event(event)

        except Exception as err:
            logger.error(f"[EventCollector] Error during enrichment/dispatch of {event.event_id}: {err}")
            # Ensure dispatch still happens even if persistence or enrichment failed
            self._dispatch_event(event)

    async def _persist_event(self, event: SecurityEvent) -> None:
        """Persists the event to the 'security_events' collection with graceful fallback."""
        try:
            col = database.collection("security_events")
            doc = event.to_dict()
            if hasattr(col, "insert_one"):
                res = col.insert_one(doc)
                if inspect.isawaitable(res):
                    await res
        except Exception as err:
            logger.warn(f"[EventCollector] Failed to persist security event {event.event_id} to database: {err}")

    def dispatch(self, event: SecurityEvent) -> None:
        """Dispatches an enriched SecurityEvent to all matching subscribers."""
        self._dispatch_event(event)

    def _dispatch_event(self, event: SecurityEvent) -> None:
        """Dispatches an enriched SecurityEvent to all matching subscribers."""
        event.status = SecurityEventStatus.DISPATCHED
        for callback, types_filter, min_conf in list(self._subscribers):
            # Type filter
            if types_filter is not None and event.event_type not in types_filter:
                continue

            # Confidence filter
            if min_conf == AttributionConfidence.VERIFIED and not event.is_verified:
                continue
            if min_conf == AttributionConfidence.PROBABLE and event.is_unknown:
                continue

            # Execute callback safely
            try:
                if inspect.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event))
                else:
                    callback(event)
            except Exception as err:
                logger.error(f"[EventCollector] Error in subscriber {callback}: {err}")

    # Query APIs for downstream components (Agent 2)
    def get_recent_events(
        self,
        guild_id: str,
        limit: int = 50,
        event_type: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> List[SecurityEvent]:
        """
        Retrieves recent in-memory security events for a guild, sorted newest to oldest.
        """
        guild_events = list(self._events_by_guild.get(str(guild_id), []))
        filtered = guild_events

        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        if actor_id:
            filtered = [e for e in filtered if e.actor_id == str(actor_id)]

        filtered.sort(key=lambda e: e.timestamp, reverse=True)
        return filtered[:limit]

    def get_recent_events_for_guild(self, guild_id: str) -> List[SecurityEvent]:
        """Returns recent events recorded for a specific guild."""
        return list(self._events_by_guild.get(str(guild_id), []))

    def get_event_by_id(self, event_id: str) -> Optional[SecurityEvent]:
        """Retrieves a security event by its unique event ID."""
        return self._events_by_id.get(str(event_id))

    def get_events_by_correlation(self, correlation_id: str) -> List[SecurityEvent]:
        """Finds all events sharing a correlation ID."""
        return [e for e in self._recent_events if e.correlation_id == correlation_id]

    async def fetch_historical_events(
        self,
        guild_id: str,
        limit: int = 100,
        event_type: Optional[str] = None,
    ) -> List[SecurityEvent]:
        """
        Queries historical events from the database with in-memory fallback.
        """
        query: Dict[str, Any] = {"guild_id": str(guild_id)}
        if event_type:
            query["event_type"] = event_type

        try:
            col = database.collection("security_events")
            if hasattr(col, "find"):
                cursor = col.find(query)
                if hasattr(cursor, "sort"):
                    cursor = cursor.sort("timestamp", -1)
                if hasattr(cursor, "limit"):
                    cursor = cursor.limit(limit)

                docs = []
                if hasattr(cursor, "to_list"):
                    docs = await cursor.to_list(limit)
                else:
                    async for doc in cursor:
                        docs.append(doc)
                return [SecurityEvent.from_dict(d) for d in docs]
        except Exception as err:
            logger.warn(f"[EventCollector] DB query failed, falling back to in-memory events: {err}")

        return self.get_recent_events(guild_id, limit=limit, event_type=event_type)


# Module-level default collector singleton instance
security_event_collector = SecurityEventCollector.get_instance()
