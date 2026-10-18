import time
from typing import Dict, Any, Optional
from apps.bot.discord.permissions.resolver import is_bot_owner, is_blacklist_excluded, parse_duration
from config.settings import settings

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

        expires_at = entry.get("expires_at")
        if expires_at and expires_at <= time.time():
            cls._user_cache.pop(str(user_id), None)
            return {"blacklisted": False}

        return {
            "blacklisted": True,
            "reason": entry.get("reason", "No reason provided"),
            "admin_id": entry.get("admin_id"),
            "expires_at": expires_at,
        }

    @classmethod
    def is_guild_blacklisted(cls, guild_id: str) -> Dict[str, Any]:
        if not guild_id:
            return {"blacklisted": False}

        entry = cls._guild_cache.get(str(guild_id))
        if not entry:
            return {"blacklisted": False}

        expires_at = entry.get("expires_at")
        if expires_at and expires_at <= time.time():
            cls._guild_cache.pop(str(guild_id), None)
            return {"blacklisted": False}

        return {
            "blacklisted": True,
            "reason": entry.get("reason", "No reason provided"),
            "admin_id": entry.get("admin_id"),
            "expires_at": expires_at,
        }

    @classmethod
    def blacklist_user(
        cls,
        user_id: str,
        admin_id: str,
        reason: str = "Administrative restriction",
        duration: Optional[str] = None
    ) -> Dict[str, Any]:
        if is_blacklist_excluded(user_id):
            return {"success": False, "error": "This user is protected from blacklisting."}

        expires_at = parse_duration(duration) if duration else None
        record = {
            "target_id": str(user_id),
            "type": "user",
            "reason": reason,
            "admin_id": str(admin_id),
            "expires_at": expires_at,
            "created_at": time.time(),
        }
        cls._user_cache[str(user_id)] = record
        return {"success": True, "entry": record}

    @classmethod
    def unblacklist_user(cls, user_id: str, admin_id: str) -> Dict[str, Any]:
        if str(user_id) in cls._user_cache:
            del cls._user_cache[str(user_id)]
            return {"success": True, "unblacklisted": True}
        return {"success": False, "error": "User is not currently blacklisted."}

    @classmethod
    def blacklist_guild(
        cls,
        guild_id: str,
        admin_id: str,
        reason: str = "Guild-level policy restriction",
        duration: Optional[str] = None
    ) -> Dict[str, Any]:
        expires_at = parse_duration(duration) if duration else None
        record = {
            "target_id": str(guild_id),
            "type": "guild",
            "reason": reason,
            "admin_id": str(admin_id),
            "expires_at": expires_at,
            "created_at": time.time(),
        }
        cls._guild_cache[str(guild_id)] = record
        return {"success": True, "entry": record}

    @classmethod
    def unblacklist_guild(cls, guild_id: str, admin_id: str) -> Dict[str, Any]:
        if str(guild_id) in cls._guild_cache:
            del cls._guild_cache[str(guild_id)]
            return {"success": True, "unblacklisted": True}
        return {"success": False, "error": "Guild is not currently blacklisted."}
