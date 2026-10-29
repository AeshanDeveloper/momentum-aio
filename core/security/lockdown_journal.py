"""
Sentinel™ Security Lockdown Permission Journal.

Agent 5 of 8 Security Core: Atomic journaling of permission mutations,
reversibility tracking, conflict detection for post-lockdown admin alterations,
and persistent audit logging.

Key capabilities:
- Detailed record of before_state, applied_state, current_state, restored_state.
- Post-lockdown conflict detection: if an admin independently modified a role/channel
  after Sentinel applied lockdown, Sentinel preserves the admin's changes and marks
  the entry as CONFLICT_DETECTED rather than clobbering it.
- SHA-256 baseline state checksum for cryptographic integrity.
- Safe recovery retry support for interrupted recovery procedures.
- Persistent MongoDB storage with synchronized in-memory fallback.
"""

from __future__ import annotations

import time
import uuid
import json
import hashlib
import threading
import asyncio

import inspect
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Union

from config.settings import settings
from core.logging.logger import logger
from database.database import database
from core.security.response_policy import LockdownStatus



class JournalEntryStatus:
    """State of an individual role or channel permission modification."""
    CAPTURED = "captured"
    PLANNED = "planned"
    APPLIED = "applied"
    VERIFIED = "verified"
    SIMULATED = "simulated"
    SKIPPED_HIERARCHY = "skipped_hierarchy"
    SKIPPED_PRESERVED = "skipped_preserved"
    FAILED_API = "failed_api"
    RESTORED = "restored"
    CONFLICT_DETECTED = "conflict_detected"
    FAILED_RESTORE = "failed_restore"

    ALL = {
        CAPTURED,
        PLANNED,
        APPLIED,
        VERIFIED,
        SIMULATED,
        SKIPPED_HIERARCHY,
        SKIPPED_PRESERVED,
        FAILED_API,
        RESTORED,
        CONFLICT_DETECTED,
        FAILED_RESTORE,
    }


@dataclass
class JournalEntry:
    """
    Atomic record of a single role or channel overwrite mutation.
    """
    entry_id: str = field(default_factory=lambda: f"jrn_{uuid.uuid4().hex[:12]}")
    lockdown_id: str = ""
    guild_id: str = ""
    target_type: str = "role"                   # "role" or "channel_overwrite"
    target_id: str = ""                         # role ID or target ID in overwrite
    secondary_id: Optional[str] = None         # channel_id when target_type == "channel_overwrite"
    target_name: Optional[str] = None
    
    # State tracking for strict reversibility and conflict avoidance
    before_state: Dict[str, Any] = field(default_factory=dict)
    applied_state: Dict[str, Any] = field(default_factory=dict)
    current_state: Optional[Dict[str, Any]] = None
    restored_state: Optional[Dict[str, Any]] = None
    original_state: Optional[Dict[str, Any]] = None
    modified_state: Optional[Dict[str, Any]] = None
    
    status: str = JournalEntryStatus.APPLIED
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    restored_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    entity_id: Optional[str] = None
    entity_type: Optional[str] = None
    entity_name: Optional[str] = None

    def __post_init__(self):
        if self.entity_id and not self.target_id:
            self.target_id = str(self.entity_id)
        elif self.target_id and not self.entity_id:
            self.entity_id = str(self.target_id)
        if self.entity_type and not self.target_type:
            self.target_type = str(self.entity_type)
        elif self.target_type and not self.entity_type:
            self.entity_type = str(self.target_type)
        if self.entity_name and not self.target_name:
            self.target_name = str(self.entity_name)
        elif self.target_name and not self.entity_name:
            self.entity_name = str(self.target_name)

        # Synchronize before_state <-> original_state and applied_state <-> modified_state
        if self.original_state is not None and not self.before_state:
            self.before_state = dict(self.original_state)
        elif self.before_state and self.original_state is None:
            self.original_state = dict(self.before_state)

        if self.modified_state is not None and not self.applied_state:
            self.applied_state = dict(self.modified_state)
        elif self.applied_state and self.modified_state is None:
            self.modified_state = dict(self.applied_state)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "lockdown_id": self.lockdown_id,
            "guild_id": str(self.guild_id),
            "target_type": self.target_type,
            "target_id": str(self.target_id),
            "secondary_id": str(self.secondary_id) if self.secondary_id else None,
            "target_name": self.target_name,
            "before_state": self.before_state,
            "applied_state": self.applied_state,
            "original_state": self.before_state,
            "modified_state": self.applied_state,
            "current_state": self.current_state,
            "restored_state": self.restored_state,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at,
            "restored_at": self.restored_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JournalEntry":
        before = data.get("before_state") or data.get("original_state", {})
        applied = data.get("applied_state") or data.get("modified_state", {})
        return cls(
            entry_id=data.get("entry_id", f"jrn_{uuid.uuid4().hex[:12]}"),
            lockdown_id=data.get("lockdown_id", ""),
            guild_id=str(data.get("guild_id", "")),
            target_type=data.get("target_type", "role"),
            target_id=str(data.get("target_id", "")),
            secondary_id=str(data.get("secondary_id")) if data.get("secondary_id") else None,
            target_name=data.get("target_name"),
            before_state=before,
            applied_state=applied,
            original_state=before,
            modified_state=applied,
            current_state=data.get("current_state"),
            restored_state=data.get("restored_state"),
            status=data.get("status", JournalEntryStatus.APPLIED),
            error=data.get("error"),
            created_at=float(data.get("created_at", time.time())),
            restored_at=data.get("restored_at"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LockdownRecord:
    """
    Comprehensive record of an emergency lockdown session.
    Tracks all journal entries, checksum, shadow mode status, and restoration state.
    """
    lockdown_id: str = field(default_factory=lambda: f"lck_{uuid.uuid4().hex[:12]}")
    guild_id: str = ""
    incident_id: str = ""
    status: str = LockdownStatus.REQUESTED
    is_shadow_mode: bool = False
    trigger_pattern: str = ""
    trigger_score: float = 0.0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    restored_at: Optional[float] = None
    restored_by: Optional[str] = None
    checksum: str = ""
    entries: List[JournalEntry] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def calculate_checksum(self) -> str:
        """Computes SHA-256 fingerprint across all baseline before_state dictionaries."""
        baseline_payload = {
            "guild_id": str(self.guild_id),
            "entries": [
                {
                    "target_type": e.target_type,
                    "target_id": str(e.target_id),
                    "secondary_id": str(e.secondary_id) if e.secondary_id else None,
                    "before_state": e.before_state,
                }
                for e in self.entries
            ],
        }
        raw_json = json.dumps(baseline_payload, sort_keys=True, default=str)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def add_entry(self, entry: JournalEntry) -> None:
        """Appends a journal entry and updates summary counters and checksum."""
        if self.lockdown_id and not entry.lockdown_id:
            entry.lockdown_id = self.lockdown_id
        if self.guild_id and not entry.guild_id:
            entry.guild_id = self.guild_id
        self.entries.append(entry)
        self.update_summary()
        self.checksum = self.calculate_checksum()

    def update_summary(self) -> None:
        """Calculates counters for modified, skipped, failed, and conflict entries."""
        counts: Dict[str, int] = {}
        for e in self.entries:
            counts[e.status] = counts.get(e.status, 0) + 1

        applied_entries = counts.get(JournalEntryStatus.APPLIED, 0) + counts.get(JournalEntryStatus.VERIFIED, 0)
        skipped_total = counts.get(JournalEntryStatus.SKIPPED_HIERARCHY, 0) + counts.get(JournalEntryStatus.SKIPPED_PRESERVED, 0)

        self.summary = {
            "total_entries": len(self.entries),
            "planned": len(self.entries),
            "applied": applied_entries,
            "verified": counts.get(JournalEntryStatus.VERIFIED, 0),
            "simulated": counts.get(JournalEntryStatus.SIMULATED, 0),
            "skipped_hierarchy": counts.get(JournalEntryStatus.SKIPPED_HIERARCHY, 0),
            "skipped_preserved": counts.get(JournalEntryStatus.SKIPPED_PRESERVED, 0),
            "skipped": skipped_total,
            "failed_api": counts.get(JournalEntryStatus.FAILED_API, 0),
            "failed": counts.get(JournalEntryStatus.FAILED_API, 0),
            "restored": counts.get(JournalEntryStatus.RESTORED, 0),
            "conflict_detected": counts.get(JournalEntryStatus.CONFLICT_DETECTED, 0),
            "failed_restore": counts.get(JournalEntryStatus.FAILED_RESTORE, 0),
            "is_partial": (
                counts.get(JournalEntryStatus.SKIPPED_HIERARCHY, 0) > 0
                or counts.get(JournalEntryStatus.FAILED_API, 0) > 0
            ),
        }

    @property
    def summary_metrics(self) -> Dict[str, Any]:
        """Provides direct access to summary counters dictionary."""
        if not self.summary:
            self.update_summary()
        return self.summary

    def to_dict(self) -> Dict[str, Any]:
        self.update_summary()
        return {
            "lockdown_id": self.lockdown_id,
            "guild_id": str(self.guild_id),
            "incident_id": str(self.incident_id),
            "status": self.status,
            "is_shadow_mode": self.is_shadow_mode,
            "trigger_pattern": self.trigger_pattern,
            "trigger_score": self.trigger_score,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "restored_at": self.restored_at,
            "restored_by": str(self.restored_by) if self.restored_by else None,
            "checksum": self.checksum or self.calculate_checksum(),
            "entries": [e.to_dict() for e in self.entries],
            "summary": self.summary,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LockdownRecord":
        record = cls(
            lockdown_id=data.get("lockdown_id", f"lck_{uuid.uuid4().hex[:12]}"),
            guild_id=str(data.get("guild_id", "")),
            incident_id=str(data.get("incident_id", "")),
            status=data.get("status", LockdownStatus.REQUESTED),
            is_shadow_mode=bool(data.get("is_shadow_mode", False)),
            trigger_pattern=data.get("trigger_pattern", ""),
            trigger_score=float(data.get("trigger_score", 0.0)),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
            restored_at=data.get("restored_at"),
            restored_by=data.get("restored_by"),
            checksum=data.get("checksum", ""),
            entries=[JournalEntry.from_dict(e) for e in data.get("entries", [])],
            summary=data.get("summary", {}),
            metadata=data.get("metadata", {}),
        )
        if not record.checksum:
            record.checksum = record.calculate_checksum()
        record.update_summary()
        return record


class LockdownJournalManager:
    """
    Manages in-memory caching and persistent storage for lockdown records and journal entries.
    Thread-safe and resilient against database connection failures.
    """
    _instance: Optional["LockdownJournalManager"] = None

    @classmethod
    def get_instance(cls) -> "LockdownJournalManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # lockdown_id -> LockdownRecord
        self._lockdowns: Dict[str, LockdownRecord] = {}
        # guild_id -> list of lockdown_ids
        self._guild_lockdowns: Dict[str, List[str]] = {}
        self._lock = threading.RLock()

    def save_lockdown(self, record: LockdownRecord) -> None:
        """Saves a lockdown record in-memory and persists asynchronously to MongoDB."""
        record.updated_at = time.time()
        record.update_summary()
        if not record.checksum:
            record.checksum = record.calculate_checksum()

        with self._lock:
            self._lockdowns[record.lockdown_id] = record
            gid = str(record.guild_id)
            if gid not in self._guild_lockdowns:
                self._guild_lockdowns[gid] = []
            if record.lockdown_id not in self._guild_lockdowns[gid]:
                self._guild_lockdowns[gid].append(record.lockdown_id)

        try:
            col = database.collection("security_lockdowns")
            if hasattr(col, "update_one"):
                async def _persist_record_async():
                    try:
                        res = col.update_one(
                            {"lockdown_id": record.lockdown_id},
                            {"$set": record.to_dict()},
                            upsert=True,
                        )
                        if inspect.isawaitable(res):
                            await res
                    except Exception as e:
                        logger.debug(f"[LockdownJournal] Async persist error: {e}")

                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(_persist_record_async())
                except RuntimeError:
                    pass
        except Exception as err:
            logger.debug(f"[LockdownJournal] Persisting lockdown to MongoDB skipped/errored: {err}")

    def get_lockdown(self, lockdown_id: str) -> Optional[LockdownRecord]:
        """Retrieves a lockdown record by ID."""
        with self._lock:
            if lockdown_id in self._lockdowns:
                return self._lockdowns[lockdown_id]

        try:
            col = database.collection("security_lockdowns")
            if hasattr(col, "_get_items"):
                for doc in col._get_items():
                    if doc.get("lockdown_id") == lockdown_id:
                        rec = LockdownRecord.from_dict(doc)
                        with self._lock:
                            self._lockdowns[rec.lockdown_id] = rec
                        return rec
        except Exception as err:
            logger.debug(f"[LockdownJournal] Failed to fetch lockdown {lockdown_id} from DB: {err}")

        return None

    def get_active_lockdown_for_guild(self, guild_id: Union[str, int]) -> Optional[LockdownRecord]:
        """
        Retrieves current ACTIVE or PARTIAL lockdown for a guild.
        Used for idempotency to avoid applying duplicate lockdown actions.
        """
        gid = str(guild_id)
        with self._lock:
            for lid in reversed(self._guild_lockdowns.get(gid, [])):
                lck = self._lockdowns.get(lid)
                if lck and lck.status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL, LockdownStatus.ATTEMPTED):
                    return lck

        try:
            col = database.collection("security_lockdowns")
            if hasattr(col, "_get_items"):
                for doc in reversed(col._get_items()):
                    if str(doc.get("guild_id")) == gid and doc.get("status") in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL, LockdownStatus.ATTEMPTED):
                        rec = LockdownRecord.from_dict(doc)
                        with self._lock:
                            self._lockdowns[rec.lockdown_id] = rec
                        return rec
        except Exception as err:
            logger.debug(f"[LockdownJournal] Failed to query active lockdown for guild {gid}: {err}")

        return None

    def get_all_active_lockdowns(self) -> List[LockdownRecord]:
        """Returns all un-restored lockdowns across all guilds for restart hydration."""
        results: List[LockdownRecord] = []
        with self._lock:
            for lck in self._lockdowns.values():
                if lck.status in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL, LockdownStatus.ATTEMPTED):
                    results.append(lck)

        try:
            col = database.collection("security_lockdowns")
            if hasattr(col, "_get_items"):
                for d in col._get_items():
                    if d.get("status") in (LockdownStatus.ACTIVE, LockdownStatus.PARTIAL, LockdownStatus.ATTEMPTED):
                        rec = LockdownRecord.from_dict(d)
                        if rec.lockdown_id not in [r.lockdown_id for r in results]:
                            results.append(rec)
                            with self._lock:
                                self._lockdowns[rec.lockdown_id] = rec
        except Exception as err:
            logger.debug(f"[LockdownJournal] Failed to hydrate active lockdowns from DB: {err}")

        return results



# Global singleton journal manager
lockdown_journal_manager = LockdownJournalManager.get_instance()
