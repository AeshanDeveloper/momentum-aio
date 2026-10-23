import time
import asyncio
from typing import Dict, Any, List, Optional
from apps.bot.discord.permissions.resolver import parse_duration
from core.security.blacklist import parse_duration_str
from database.database import database


class NoPrefixManager:
    """
    Manages users and servers authorized to trigger commands without typing a prefix.
    Supports persistent storage, auto-expiration, and a runtime enable/disable switch.
    """
    _user_cache: Dict[str, Dict[str, Any]] = {}
    _guild_cache: Dict[str, Dict[str, Any]] = {}
    _enabled: bool = True
    _initialized: bool = False

    @classmethod
    async def initialize(cls) -> None:
        """Hydrate in-memory no-prefix cache from database storage."""
        try:
            col = database.collection("no_prefix")
            cursor = col.find({})
            if hasattr(cursor, "to_list"):
                docs = await cursor.to_list(10000)
            else:
                docs = await cursor

            now = time.time()
            cls._user_cache.clear()
            cls._guild_cache.clear()

            for doc in (docs or []):
                t_type = doc.get("type", "user")
                t_id = str(doc.get("targetId") or doc.get("target_id") or doc.get("userId") or doc.get("guildId") or "")
                if not t_id:
                    continue
                exp = doc.get("expiresAt") or doc.get("expires_at")
                if exp and exp <= now:
                    continue
                if t_type == "guild":
                    cls._guild_cache[t_id] = doc
                else:
                    cls._user_cache[t_id] = doc

            cls._initialized = True
        except Exception:
            cls._initialized = True

    @classmethod
    def _schedule_db_persist(cls, target_id: str, entry: Optional[Dict[str, Any]]) -> None:
        async def _run():
            try:
                col = database.collection("no_prefix")
                if entry is None:
                    await col.delete_one({"$or": [{"targetId": str(target_id)}, {"userId": str(target_id)}, {"guildId": str(target_id)}]})
                else:
                    await col.update_one(
                        {"targetId": str(target_id)},
                        {"$set": entry},
                        upsert=True
                    )
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_run())
        except RuntimeError:
            pass

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if no-prefix evaluation is globally enabled at runtime."""
        return cls._enabled

    @classmethod
    def set_enabled(cls, enabled: bool) -> None:
        """Enable or disable no-prefix evaluation globally without deleting assignments."""
        cls._enabled = bool(enabled)

    @classmethod
    def has_no_prefix(cls, user_id: str, guild_id: Optional[str] = None) -> bool:
        """Check if user or current guild has active no-prefix permissions."""
        if not cls._enabled:
            return False

        now = time.time()
        # 1. Check user cache
        if user_id:
            entry = cls._user_cache.get(str(user_id))
            if entry:
                exp = entry.get("expiresAt") or entry.get("expires_at")
                if exp and exp <= now:
                    cls._user_cache.pop(str(user_id), None)
                    cls._schedule_db_persist(str(user_id), None)
                else:
                    return True

        # 2. Check guild cache
        if guild_id:
            entry = cls._guild_cache.get(str(guild_id))
            if entry:
                exp = entry.get("expiresAt") or entry.get("expires_at")
                if exp and exp <= now:
                    cls._guild_cache.pop(str(guild_id), None)
                    cls._schedule_db_persist(str(guild_id), None)
                else:
                    return True

        return False

    @classmethod
    def has_guild_no_prefix(cls, guild_id: str) -> bool:
        if not cls._enabled or not guild_id:
            return False
        entry = cls._guild_cache.get(str(guild_id))
        if not entry:
            return False
        exp = entry.get("expiresAt") or entry.get("expires_at")
        if exp and exp <= time.time():
            cls._guild_cache.pop(str(guild_id), None)
            cls._schedule_db_persist(str(guild_id), None)
            return False
        return True

    @classmethod
    def add(
        cls,
        target_id: str,
        duration: Optional[str] = None,
        added_by: str = "System",
        target_type: str = "user"
    ) -> Dict[str, Any]:
        """Add user or guild to no-prefix list with optional duration and persistence."""
        if not target_id:
            return {"success": False, "error": "Target ID is required."}

        expires_at = parse_duration_str(duration) if duration else None
        target_type_clean = "guild" if target_type in ["guild", "server"] else "user"
        record = {
            "targetId": str(target_id),
            "target_id": str(target_id),
            "type": target_type_clean,
            "addedBy": str(added_by),
            "added_by": str(added_by),
            "expiresAt": expires_at,
            "expires_at": expires_at,
            "createdAt": time.time(),
        }
        if target_type_clean == "guild":
            record["guildId"] = str(target_id)
            cls._guild_cache[str(target_id)] = record
        else:
            record["userId"] = str(target_id)
            cls._user_cache[str(target_id)] = record

        cls._schedule_db_persist(str(target_id), record)
        return {"success": True, "entry": record}

    @classmethod
    def remove(
        cls,
        target_id: str,
        removed_by: str = "System",
        target_type: str = "user"
    ) -> Dict[str, Any]:
        """Remove user or guild from no-prefix list."""
        if not target_id:
            return {"success": False, "error": "Target ID is required."}

        target_type_clean = "guild" if target_type in ["guild", "server"] else "user"
        cache = cls._guild_cache if target_type_clean == "guild" else cls._user_cache

        if str(target_id) in cache:
            del cache[str(target_id)]
            cls._schedule_db_persist(str(target_id), None)
            return {"success": True, "revoked": True}

        # Check the other cache just in case
        other_cache = cls._user_cache if target_type_clean == "guild" else cls._guild_cache
        if str(target_id) in other_cache:
            del other_cache[str(target_id)]
            cls._schedule_db_persist(str(target_id), None)
            return {"success": True, "revoked": True}

        return {"success": False, "error": f"{target_type_clean.capitalize()} does not have no-prefix authorization."}

    @classmethod
    def list(cls, target_type: str = "user") -> List[Dict[str, Any]]:
        """List active no-prefix entries for users or guilds."""
        now = time.time()
        cache = cls._guild_cache if target_type in ["guild", "server"] else cls._user_cache
        res = []
        for tid, entry in list(cache.items()):
            exp = entry.get("expiresAt") or entry.get("expires_at")
            if exp and exp <= now:
                cache.pop(tid, None)
                cls._schedule_db_persist(tid, None)
                continue
            res.append(entry)
        return res

    # Parity aliases
    grant_no_prefix = add
    revoke_no_prefix = remove
    hasNoPrefix = has_no_prefix
