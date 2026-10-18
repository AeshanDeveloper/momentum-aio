import time
from typing import Dict, Any, List, Optional
from apps.bot.discord.permissions.resolver import is_bot_owner, is_blacklist_excluded, parse_duration
from config.settings import settings

def parse_duration_str(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    raw_lower = raw.lower().strip()
    if raw_lower in ["perm", "permanent", "never", "forever", "0"]:
        return None
    try:
        val = parse_duration(raw)
        return val
    except Exception:
        return None

class BlacklistManager:
    """
    Centralized User & Guild Blacklist Security Manager.
    Includes persistent caching, auto-expiration, and exclusion guarantees.
    """
    _user_cache: Dict[str, Dict[str, Any]] = {}
    _guild_cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def is_user_blacklisted(cls, user_id: str) -> Dict[str, Any]:
        if not user_id:
            return {"blacklisted": False}

        if is_blacklist_excluded(user_id):
            return {"blacklisted": False}

        entry = cls._user_cache.get(str(user_id))
        if not entry:
            return {"blacklisted": False}

        expires_at = entry.get("expiresAt") or entry.get("expires_at")
        if expires_at and expires_at <= time.time():
            cls._user_cache.pop(str(user_id), None)
            return {"blacklisted": False}

        return {
            "blacklisted": True,
            "reason": entry.get("reason", "No reason provided"),
            "adminId": entry.get("adminId") or entry.get("admin_id"),
            "expiresAt": expires_at,
        }

    @classmethod
    def is_guild_blacklisted(cls, guild_id: str) -> Dict[str, Any]:
        if not guild_id:
            return {"blacklisted": False}

        entry = cls._guild_cache.get(str(guild_id))
        if not entry:
            return {"blacklisted": False}

        expires_at = entry.get("expiresAt") or entry.get("expires_at")
        if expires_at and expires_at <= time.time():
            cls._guild_cache.pop(str(guild_id), None)
            return {"blacklisted": False}

        return {
            "blacklisted": True,
            "reason": entry.get("reason", "No reason provided"),
            "adminId": entry.get("adminId") or entry.get("admin_id"),
            "expiresAt": expires_at,
        }

    @classmethod
    def blacklist_user(
        cls,
        user_id: str,
        duration: Optional[str] = None,
        reason: str = "Violation of bot rules / terms of service",
        admin_id: str = "System",
        client: Any = None,
    ) -> Dict[str, Any]:
        if is_blacklist_excluded(user_id):
            return {"success": False, "error": "This user is protected from blacklisting."}

        expires_at = parse_duration_str(duration)
        record = {
            "targetId": str(user_id),
            "target_id": str(user_id),
            "type": "user",
            "reason": reason,
            "adminId": str(admin_id),
            "admin_id": str(admin_id),
            "expiresAt": expires_at,
            "expires_at": expires_at,
            "createdAt": time.time(),
        }
        cls._user_cache[str(user_id)] = record
        return {"success": True, "entry": record}

    @classmethod
    def unblacklist_user(cls, user_id: str, admin_id: str = "System") -> Dict[str, Any]:
        if str(user_id) in cls._user_cache:
            del cls._user_cache[str(user_id)]
            return {"success": True, "unblacklisted": True}
        return {"success": False, "error": "User is not currently blacklisted."}

    @classmethod
    def blacklist_guild(
        cls,
        guild_id: str,
        duration: Optional[str] = None,
        reason: str = "Violation of bot rules / terms of service",
        admin_id: str = "System",
        client: Any = None,
    ) -> Dict[str, Any]:
        expires_at = parse_duration_str(duration)
        record = {
            "targetId": str(guild_id),
            "target_id": str(guild_id),
            "type": "guild",
            "reason": reason,
            "adminId": str(admin_id),
            "admin_id": str(admin_id),
            "expiresAt": expires_at,
            "expires_at": expires_at,
            "createdAt": time.time(),
        }
        cls._guild_cache[str(guild_id)] = record
        return {"success": True, "entry": record}

    @classmethod
    def unblacklist_guild(cls, guild_id: str, admin_id: str = "System") -> Dict[str, Any]:
        if str(guild_id) in cls._guild_cache:
            del cls._guild_cache[str(guild_id)]
            return {"success": True, "unblacklisted": True}
        return {"success": False, "error": "Server is not currently blacklisted."}

    @classmethod
    def list_blacklists(cls, target_type: str = "user") -> List[Dict[str, Any]]:
        now = time.time()
        cache = cls._user_cache if target_type == "user" else cls._guild_cache
        res = []
        for k, entry in list(cache.items()):
            exp = entry.get("expiresAt") or entry.get("expires_at")
            if exp and exp <= now:
                cache.pop(k, None)
                continue
            res.append(entry)
        return res

    # Parity aliases
    listBlacklists = list_blacklists
    blacklistUser = blacklist_user
    unblacklistUser = unblacklist_user
    blacklistGuild = blacklist_guild
    unblacklistGuild = unblacklist_guild
    isUserBlacklisted = is_user_blacklisted
    isGuildBlacklisted = is_guild_blacklisted
