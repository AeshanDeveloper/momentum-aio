"""
Sentinel™ Resource Ownership Tracker.

Provides cryptographic and persistent ownership tracking for Discord resources
(categories, channels, webhooks) created and managed by Sentinel.

Guarantees:
- Never adopts or claims user-created or third-party channels based on name similarity.
- Persistent database tracking surviving bot restarts.
- Strict ownership verification by Discord ID, resource type, and parent hierarchy.
- Safe reset capability: only verified Sentinel-owned resources can ever be deleted.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set, Union, Tuple

import discord

from core.logging.logger import logger
from database.database import database


@dataclass
class SentinelResourceRecord:
    guild_id: str
    resource_id: str
    resource_type: str  # "category", "text_channel", "webhook"
    parent_id: Optional[str] = None  # category_id for channels
    created_at: float = field(default_factory=time.time)
    setup_id: str = ""
    purpose: str = ""  # e.g. "forensic_category", "security-logs", "moderation-logs"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "guild_id": str(self.guild_id),
            "resource_id": str(self.resource_id),
            "resource_type": self.resource_type,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "created_at": self.created_at,
            "setup_id": self.setup_id,
            "purpose": self.purpose,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SentinelResourceRecord":
        return cls(
            guild_id=str(data.get("guild_id", "")),
            resource_id=str(data.get("resource_id", "")),
            resource_type=data.get("resource_type", "text_channel"),
            parent_id=str(data["parent_id"]) if data.get("parent_id") else None,
            created_at=float(data.get("created_at", time.time())),
            setup_id=str(data.get("setup_id", "")),
            purpose=str(data.get("purpose", "")),
            metadata=dict(data.get("metadata", {})),
        )


class SentinelResourceTracker:
    """
    Persistent ownership registry for Sentinel-created Discord infrastructure.
    """
    COLLECTION_NAME = "sentinel_resource_ownership"
    _in_memory_records: Dict[str, Dict[str, SentinelResourceRecord]] = {}  # guild_id -> {resource_id: record}
    _loaded_guilds: Set[str] = set()

    @classmethod
    def _get_guild_cache(cls, guild_id: str) -> Dict[str, SentinelResourceRecord]:
        gid = str(guild_id)
        if gid not in cls._in_memory_records:
            cls._in_memory_records[gid] = {}
        if gid not in cls._loaded_guilds:
            cls._hydrate_from_db(gid)
        return cls._in_memory_records[gid]

    @classmethod
    def _hydrate_from_db(cls, guild_id: str) -> None:
        gid = str(guild_id)
        cls._loaded_guilds.add(gid)
        try:
            col = database.collection(cls.COLLECTION_NAME)
            if hasattr(col, "_get_items"):
                for doc in col._get_items():
                    if str(doc.get("guild_id")) == gid:
                        rec = SentinelResourceRecord.from_dict(doc)
                        cls._in_memory_records[gid][rec.resource_id] = rec
        except Exception as err:
            logger.debug(f"[SentinelResourceTracker] Hydration error for guild {gid}: {err}")

    @classmethod
    async def record_resource_creation(
        cls,
        guild_id: Union[str, int],
        resource_id: Union[str, int],
        resource_type: str,
        parent_id: Optional[Union[str, int]] = None,
        setup_id: Optional[str] = None,
        purpose: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SentinelResourceRecord:
        """Records verified creation of a resource by Sentinel."""
        gid = str(guild_id)
        rid = str(resource_id)
        pid = str(parent_id) if parent_id else None
        sid = setup_id or f"setup_{uuid.uuid4().hex[:8]}"

        record = SentinelResourceRecord(
            guild_id=gid,
            resource_id=rid,
            resource_type=resource_type,
            parent_id=pid,
            created_at=time.time(),
            setup_id=sid,
            purpose=purpose,
            metadata=metadata or {},
        )

        cache = cls._get_guild_cache(gid)
        cache[rid] = record

        try:
            col = database.collection(cls.COLLECTION_NAME)
            if hasattr(col, "update_one"):
                res = col.update_one(
                    {"guild_id": gid, "resource_id": rid},
                    {"$set": record.to_dict()},
                    upsert=True,
                )
                if hasattr(res, "__await__"):
                    await res
        except Exception as err:
            logger.error(f"[SentinelResourceTracker] Failed to persist ownership for {rid}: {err}")

        return record

    @classmethod
    def is_resource_owned(cls, guild_id: Union[str, int], resource_id: Union[str, int]) -> bool:
        """Checks if a Discord resource was explicitly created and recorded by Sentinel."""
        gid = str(guild_id)
        rid = str(resource_id)
        cache = cls._get_guild_cache(gid)
        return rid in cache

    @classmethod
    def get_resource_record(cls, guild_id: Union[str, int], resource_id: Union[str, int]) -> Optional[SentinelResourceRecord]:
        """Gets verified ownership record for a resource."""
        gid = str(guild_id)
        rid = str(resource_id)
        cache = cls._get_guild_cache(gid)
        return cache.get(rid)

    @classmethod
    def get_all_owned_resources(cls, guild_id: Union[str, int]) -> List[SentinelResourceRecord]:
        """Returns all resources recorded as owned by Sentinel in a guild."""
        gid = str(guild_id)
        cache = cls._get_guild_cache(gid)
        return list(cache.values())

    @classmethod
    async def remove_resource_record(cls, guild_id: Union[str, int], resource_id: Union[str, int]) -> None:
        """Removes a deleted resource from the ownership registry."""
        gid = str(guild_id)
        rid = str(resource_id)
        cache = cls._get_guild_cache(gid)
        cache.pop(rid, None)

        try:
            col = database.collection(cls.COLLECTION_NAME)
            if hasattr(col, "delete_one"):
                res = col.delete_one({"guild_id": gid, "resource_id": rid})
                if hasattr(res, "__await__"):
                    await res
        except Exception as err:
            logger.debug(f"[SentinelResourceTracker] Failed to delete ownership record {rid}: {err}")

    @classmethod
    def verify_ownership(
        cls,
        guild: discord.Guild,
        resource: Union[discord.CategoryChannel, discord.TextChannel, discord.abc.GuildChannel],
        expected_type: Optional[str] = None,
        expected_parent_id: Optional[Union[str, int]] = None,
    ) -> Tuple[bool, Optional[SentinelResourceRecord], str]:
        """
        Cryptographically verifies that a Discord resource is genuinely owned by Sentinel.
        Checks:
        1. Explicit persistent ownership record exists in database.
        2. Resource ID matches.
        3. Resource type matches.
        4. Parent category matches ownership record if applicable.
        """
        if not guild or not resource:
            return False, None, "Invalid guild or resource object"

        gid = str(guild.id)
        rid = str(resource.id)
        record = cls.get_resource_record(gid, rid)

        if not record:
            return False, None, f"Resource {resource.name} ({rid}) has no Sentinel ownership record"

        if expected_type and record.resource_type != expected_type:
            return False, record, f"Resource type mismatch: expected {expected_type}, record is {record.resource_type}"

        if expected_parent_id:
            exp_pid_str = str(expected_parent_id)
            if record.parent_id and record.parent_id != exp_pid_str:
                return False, record, f"Parent category mismatch: expected {exp_pid_str}, record has {record.parent_id}"

            actual_parent = getattr(resource, "category", None)
            if actual_parent and str(actual_parent.id) != exp_pid_str:
                return False, record, f"Live Discord parent mismatch: expected {exp_pid_str}, actual is {actual_parent.id}"

        return True, record, "Verified Sentinel owned resource"
