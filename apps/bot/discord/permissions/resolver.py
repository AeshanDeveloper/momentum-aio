import re
import time
from typing import List, Dict, Any, Optional, Tuple
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


def get_effective_bot_permissions(guild: Any) -> Any:
    """
    Safely resolves the bot member's effective guild permissions,
    correctly accounting for Administrator granting all capabilities.
    """
    if not guild:
        return None
    me = getattr(guild, "me", None)
    if not me:
        return None
    perms = getattr(me, "guild_permissions", None)
    return perms


def evaluate_role_manageability(bot_member: Any, role: Any) -> Tuple[bool, str, str]:
    """
    Evaluates whether the bot can manage/edit a target role in accordance with Discord API rules.
    Returns: (can_manage: bool, status_code: str, detailed_reason: str)

    Status codes:
      - 'manageable': The bot has permissions and position to manage this role.
      - 'blocked_by_hierarchy': Target role position is >= bot's top role position.
      - 'managed_role': The role is controlled by an external bot or Discord integration.
      - 'missing_permission': Bot lacks Manage Roles (and Administrator) permission.
      - 'api_restriction': Role is bot's own top role or server owner's uneditable role.
    """
    if not bot_member:
        return False, "api_restriction", "Bot member context is unavailable."
    if not role:
        return False, "api_restriction", "Target role is None."

    guild = getattr(bot_member, "guild", None) or getattr(role, "guild", None)
    bot_perms = getattr(bot_member, "guild_permissions", None)
    has_manage_roles = False
    if bot_perms:
        has_manage_roles = getattr(bot_perms, "manage_roles", False) or getattr(bot_perms, "administrator", False)

    if not has_manage_roles:
        return False, "missing_permission", "Bot lacks 'Manage Roles' permission (and Administrator)."

    # Default @everyone role can be modified by anyone with Manage Roles
    is_default = getattr(role, "is_default", lambda: False)() or (guild and role.id == getattr(guild, "id", None))
    if is_default:
        return True, "manageable", "Default @everyone role permissions can be modified."

    # External integration / bot managed role
    if getattr(role, "managed", False):
        return False, "managed_role", f"Role '{role.name}' is managed by an external integration or application."

    bot_top_role = getattr(bot_member, "top_role", None)
    if not bot_top_role:
        return False, "blocked_by_hierarchy", "Bot has no assigned roles in this server."

    # Bot's own top role cannot be edited by the bot
    if role.id == bot_top_role.id:
        return False, "api_restriction", "Bot cannot modify its own highest role (Shielded)."

    # Discord Role Hierarchy Rule: Bot can only manage roles strictly lower than its top role
    if role.position >= bot_top_role.position:
        return False, "blocked_by_hierarchy", (
            f"Role '{role.name}' (pos {role.position}) is higher than or equal to bot's top role "
            f"'{bot_top_role.name}' (pos {bot_top_role.position})."
        )

    return True, "manageable", f"Role '{role.name}' is manageable by the bot."


def get_role_diagnostics(guild: Any) -> Dict[str, Any]:
    """
    Generates comprehensive role hierarchy and manageability diagnostics for a guild.
    """
    if not guild:
        return {
            "safe": False,
            "bot_top_role": None,
            "total_roles": 0,
            "manageable_count": 0,
            "blocked_count": 0,
            "managed_count": 0,
            "missing_perms": True,
            "manageable_roles": [],
            "blocked_roles": [],
            "managed_roles": [],
        }

    me = getattr(guild, "me", None)
    roles = getattr(guild, "roles", [])
    bot_top_role = getattr(me, "top_role", None) if me else None

    manageable = []
    blocked = []
    managed = []

    for r in roles:
        if r.is_default() if hasattr(r, "is_default") else r.position == 0:
            continue
        can_mod, status, reason = evaluate_role_manageability(me, r)
        if can_mod:
            manageable.append((r, reason))
        elif status == "managed_role":
            managed.append((r, reason))
        elif status == "blocked_by_hierarchy":
            blocked.append((r, reason))
        else:
            blocked.append((r, reason))

    bot_perms = getattr(me, "guild_permissions", None) if me else None
    has_admin = getattr(bot_perms, "administrator", False) if bot_perms else False
    has_manage_roles = (getattr(bot_perms, "manage_roles", False) or has_admin) if bot_perms else False

    is_safe = (len(blocked) == 0 and has_manage_roles)

    return {
        "safe": is_safe,
        "bot_top_role": bot_top_role,
        "has_admin": has_admin,
        "has_manage_roles": has_manage_roles,
        "total_roles": len(roles),
        "manageable_count": len(manageable),
        "blocked_count": len(blocked),
        "managed_count": len(managed),
        "manageable_roles": manageable,
        "blocked_roles": blocked,
        "managed_roles": managed,
    }

