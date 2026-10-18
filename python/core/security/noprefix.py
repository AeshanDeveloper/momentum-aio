import time
from typing import Dict, Any, List, Optional
from apps.bot.discord.permissions.resolver import parse_duration
from core.security.blacklist import parse_duration_str

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

        expires_at = entry.get("expiresAt") or entry.get("expires_at")
        if expires_at and expires_at <= time.time():
            cls._cache.pop(str(user_id), None)
            return False

        return True

    @classmethod
    def add(cls, user_id: str, duration: Optional[str] = None, added_by: str = "System") -> Dict[str, Any]:
        expires_at = parse_duration_str(duration) if duration else None
        record = {
            "userId": str(user_id),
            "user_id": str(user_id),
            "addedBy": str(added_by),
            "added_by": str(added_by),
            "expiresAt": expires_at,
            "expires_at": expires_at,
            "createdAt": time.time(),
        }
        cls._cache[str(user_id)] = record
        return {"success": True, "entry": record}

    @classmethod
    def remove(cls, user_id: str, removed_by: str = "System") -> Dict[str, Any]:
        if str(user_id) in cls._cache:
            del cls._cache[str(user_id)]
            return {"success": True, "revoked": True}
        return {"success": False, "error": "User does not have no-prefix authorization."}

    @classmethod
    def list(cls) -> List[Dict[str, Any]]:
        now = time.time()
        res = []
        for uid, entry in list(cls._cache.items()):
            exp = entry.get("expiresAt") or entry.get("expires_at")
            if exp and exp <= now:
                cls._cache.pop(uid, None)
                continue
            res.append(entry)
        return res

    # Parity aliases
    grant_no_prefix = add
    revoke_no_prefix = remove
    hasNoPrefix = has_no_prefix
