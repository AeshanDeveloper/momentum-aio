import time
from typing import Dict, Optional, Any
from apps.bot.discord.permissions.resolver import is_bot_owner, parse_duration

class CooldownManager:
    """
    Command execution cooldown manager.
    Supports user, guild, and global scopes, duration parsing, and owner exemptions.
    """
    _cooldowns: Dict[str, float] = {}

    @classmethod
    def _get_canonical_name(cls, command: Any) -> str:
        if isinstance(command, str):
            return command.lower()
        if hasattr(command, "name"):
            return command.name.lower()
        if isinstance(command, dict):
            return (command.get("name") or command.get("command_id") or "unknown").lower()
        return "unknown"

    @classmethod
    def _get_cooldown_sec(cls, command: Any) -> float:
        raw = None
        if isinstance(command, dict):
            raw = command.get("cooldown")
        elif hasattr(command, "cooldown"):
            raw = getattr(command, "cooldown")

        if isinstance(raw, str):
            parsed = parse_duration(raw)
            if parsed:
                return max(0.0, parsed - time.time())
            try:
                raw = float(raw)
            except Exception:
                return 0.0

        if isinstance(raw, (int, float)) and raw > 0:
            # If >= 1000, value is specified in milliseconds
            return (raw / 1000.0) if raw >= 1000 else float(raw)

        return 0.0

    @classmethod
    def _get_key(cls, name: str, scope: str, user_id: str, guild_id: Optional[str] = None) -> str:
        if scope == "guild" and guild_id:
            return f"{name}:guild:{guild_id}"
        if scope == "global":
            return f"{name}:global"
        return f"{name}:user:{user_id}"

    @classmethod
    def check(cls, command: Any, user_id: str, guild_id: Optional[str] = None) -> Dict[str, Any]:
        if is_bot_owner(user_id):
            return {"on_cooldown": False, "remaining_seconds": 0.0, "expires_at": 0.0, "scope": "user"}

        sec = cls._get_cooldown_sec(command)
        scope = "user"
        if isinstance(command, dict):
            scope = command.get("cooldownScope", "user")
        elif hasattr(command, "cooldown_scope"):
            scope = getattr(command, "cooldown_scope", "user")

        if sec <= 0:
            return {"on_cooldown": False, "remaining_seconds": 0.0, "expires_at": 0.0, "scope": scope}

        name = cls._get_canonical_name(command)
        key = cls._get_key(name, scope, user_id, guild_id)
        now = time.time()
        expires_at = cls._cooldowns.get(key, 0.0)

        if expires_at > now:
            remaining = round(max(0.1, expires_at - now), 1)
            return {
                "on_cooldown": True,
                "remaining_seconds": remaining,
                "expires_at": expires_at,
                "scope": scope
            }

        return {"on_cooldown": False, "remaining_seconds": 0.0, "expires_at": 0.0, "scope": scope}

    @classmethod
    def apply(cls, command: Any, user_id: str, guild_id: Optional[str] = None) -> None:
        if is_bot_owner(user_id):
            return

        sec = cls._get_cooldown_sec(command)
        if sec <= 0:
            return

        name = cls._get_canonical_name(command)
        scope = "user"
        if isinstance(command, dict):
            scope = command.get("cooldownScope", "user")
        elif hasattr(command, "cooldown_scope"):
            scope = getattr(command, "cooldown_scope", "user")

        key = cls._get_key(name, scope, user_id, guild_id)
        cls._cooldowns[key] = time.time() + sec

    @classmethod
    def prune_expired(cls) -> int:
        now = time.time()
        to_del = [k for k, exp in cls._cooldowns.items() if exp <= now]
        for k in to_del:
            del cls._cooldowns[k]
        return len(to_del)

    @classmethod
    def reset(cls, command_name: str, user_id: str, guild_id: Optional[str] = None) -> None:
        name = command_name.lower()
        cls._cooldowns.pop(f"{name}:user:{user_id}", None)
        if guild_id:
            cls._cooldowns.pop(f"{name}:guild:{guild_id}", None)
        cls._cooldowns.pop(f"{name}:global", None)
