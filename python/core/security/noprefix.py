import time
from typing import Dict, Any, Optional
from apps.bot.discord.permissions.resolver import parse_duration

class NoPrefixManager:
    """
    Manages users authorized to trigger commands without typing a prefix.
    """
    _cache: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def has_no_prefix(cls, user_id: str) -> bool:
        if not user_id:
            return False
        entry = cls._cache.get(str(user_id))
        if not entry:
            return False

        expires_at = entry.get("expires_at")
        if expires_at and expires_at <= time.time():
            cls._cache.pop(str(user_id), None)
            return False

        return True

    @classmethod
    def grant_no_prefix(cls, user_id: str, added_by: str, duration: Optional[str] = None) -> Dict[str, Any]:
        expires_at = parse_duration(duration) if duration else None
        record = {
            "user_id": str(user_id),
            "added_by": str(added_by),
            "expires_at": expires_at,
            "created_at": time.time(),
        }
        cls._cache[str(user_id)] = record
        return {"success": True, "entry": record}

    @classmethod
    def revoke_no_prefix(cls, user_id: str, removed_by: str) -> Dict[str, Any]:
        if str(user_id) in cls._cache:
            del cls._cache[str(user_id)]
            return {"success": True, "revoked": True}
        return {"success": False, "error": "User does not have no-prefix authorization."}
