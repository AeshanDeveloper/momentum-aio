import time
from typing import Dict, List, Any
from apps.bot.discord.permissions.resolver import is_blacklist_excluded
from .blacklist import BlacklistManager

class AntiSpamService:
    """
    Sliding-window rate limiter & spam protector.
    Automatically warns and blacklists malicious spam actors.
    """
    _timestamps: Dict[str, List[float]] = {}
    _infractions: Dict[str, int] = {}
    WINDOW_SEC = 30.0
    MAX_PER_WINDOW = 5
    BAN_AFTER_INFRACTIONS = 3

    @classmethod
    def check(cls, user_id: str) -> Dict[str, Any]:
        if is_blacklist_excluded(user_id):
            return {"allowed": True}

        uid = str(user_id)
        now = time.time()
        cutoff = now - cls.WINDOW_SEC

        # Clean timestamps older than sliding window
        times = [t for t in cls._timestamps.get(uid, []) if t > cutoff]
        times.append(now)
        cls._timestamps[uid] = times

        if len(times) > cls.MAX_PER_WINDOW:
            inf = cls._infractions.get(uid, 0) + 1
            cls._infractions[uid] = inf

            if inf >= cls.BAN_AFTER_INFRACTIONS:
                BlacklistManager.blacklist_user(
                    user_id=uid,
                    admin_id="system",
                    reason="Automated restriction: excessive command spam detected",
                    duration="1d"
                )
                return {
                    "allowed": False,
                    "blacklisted": True,
                    "warning": "You have been automatically blacklisted for 24h for excessive spam."
                }

            return {
                "allowed": False,
                "warning": f"Please slow down! Command limit exceeded ({len(times)}/{cls.MAX_PER_WINDOW}).",
                "infraction_count": inf
            }

        return {"allowed": True}
