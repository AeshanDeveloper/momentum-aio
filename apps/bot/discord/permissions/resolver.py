import re
import time
from typing import List, Dict, Any, Optional
from .permission import Permissions, PERMISSION_NAMES
from config.settings import settings

def get_permission_name(permission: Any) -> str:
    if isinstance(permission, int):
        return PERMISSION_NAMES.get(permission, f"Permission({permission})")
    if isinstance(permission, str):
        # Convert camelCase to title case
        s = re.sub(r"([A-Z])", r" \1", permission).strip().title()
        return s
    return str(permission)

def has_permission(member: Any, permission: Any) -> bool:
    """
    Checks if a member has a specific permission.
    Handles discord.py Member / Permissions or raw integers/names.
    """
    if member is None:
        return False
    if hasattr(member, "guild_permissions"):
        if member.guild_permissions.administrator:
            return True
        if isinstance(permission, str):
            attr = permission.lower().replace(" ", "_")
            if hasattr(member.guild_permissions, attr):
                return bool(getattr(member.guild_permissions, attr))
        elif isinstance(permission, int):
            return bool(member.guild_permissions.value & permission)
    elif hasattr(member, "permissions"):
        if callable(member.permissions.has):
            return bool(member.permissions.has(permission))
        elif isinstance(permission, int):
            return bool(member.permissions & permission)
    return False

def is_bot_owner(user_id: Optional[str]) -> bool:
    """Returns True if the user ID is configured as a bot owner."""
    if not user_id:
        return False
    return str(user_id) in [str(x) for x in settings.OWNER_IDS]

def is_blacklist_excluded(user_id: Optional[str]) -> bool:
    """Returns True if user is excluded from blacklists (owners or explicitly exempt)."""
    if not user_id:
        return False
    if is_bot_owner(user_id):
        return True
    return str(user_id) in [str(x) for x in settings.BLACKLIST_EXCLUSIONS]

def check_permissions(
    member: Any,
    bot_member: Any,
    user_perms: Optional[List[Any]] = None,
    bot_perms: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """
    Proper permission check algorithm matching TypeScript checkPermissions().
    Validates both invoking user and bot member permissions on the target channel/guild.
    """
    user_perms = user_perms or []
    bot_perms = bot_perms or []

    missing_user = []
    missing_bot = []

    # Check member permissions
    for perm in user_perms:
        has_perm = False
        if member is None:
            has_perm = True
        elif hasattr(member, "guild_permissions"):
            # discord.py Member
            if member.guild_permissions.administrator:
                has_perm = True
            elif isinstance(perm, str) and hasattr(member.guild_permissions, perm.lower()):
                has_perm = getattr(member.guild_permissions, perm.lower())
            elif isinstance(perm, int):
                has_perm = bool(member.guild_permissions.value & perm)
        elif hasattr(member, "permissions"):
            if callable(member.permissions.has):
                has_perm = member.permissions.has(perm)
            elif isinstance(perm, int):
                has_perm = bool(member.permissions & perm)
        else:
            has_perm = True

        if not has_perm:
            missing_user.append(perm)

    # Check bot permissions
    for perm in bot_perms:
        has_perm = False
        if bot_member is None:
            has_perm = True
        elif hasattr(bot_member, "guild_permissions"):
            if bot_member.guild_permissions.administrator:
                has_perm = True
            elif isinstance(perm, str) and hasattr(bot_member.guild_permissions, perm.lower()):
                has_perm = getattr(bot_member.guild_permissions, perm.lower())
            elif isinstance(perm, int):
                has_perm = bool(bot_member.guild_permissions.value & perm)
        elif hasattr(bot_member, "permissions"):
            if callable(bot_member.permissions.has):
                has_perm = bot_member.permissions.has(perm)
            elif isinstance(perm, int):
                has_perm = bool(bot_member.permissions & perm)
        else:
            has_perm = True

        if not has_perm:
            missing_bot.append(perm)

    allowed = (len(missing_user) == 0 and len(missing_bot) == 0)

    return {
        "allowed": allowed,
        "missing_user": missing_user,
        "missing_bot": missing_bot,
        "missing_user_names": [get_permission_name(p) for p in missing_user],
        "missing_bot_names": [get_permission_name(p) for p in missing_bot],
    }

def parse_duration(input_str: Optional[str]) -> Optional[float]:
    """
    Parses duration strings like '5m', '1h', '7d', 'permanent' into a future UNIX timestamp in seconds.
    Returns None for permanent/infinite durations.
    """
    if not input_str:
        return None
    trimmed = str(input_str).strip().lower()
    if trimmed in ["perm", "permanent", "never", "forever", "none", "0"]:
        return None

    match = re.match(
        r"^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|wk|wks|week|weeks|mo|mon|month|months|y|yr|year|years)?$",
        trimmed
    )
    if match:
        val = int(match.group(1))
        unit = (match.group(2) or "d").lower()

        multipliers = {
            "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
            "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
            "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
            "d": 86400, "day": 86400, "days": 86400,
            "w": 7 * 86400, "wk": 7 * 86400, "wks": 7 * 86400, "week": 7 * 86400, "weeks": 7 * 86400,
            "mo": 30 * 86400, "mon": 30 * 86400, "month": 30 * 86400, "months": 30 * 86400,
            "y": 365 * 86400, "yr": 365 * 86400, "year": 365 * 86400, "years": 365 * 86400,
        }
        sec = val * multipliers.get(unit, 86400)
        return time.time() + sec

    return None
