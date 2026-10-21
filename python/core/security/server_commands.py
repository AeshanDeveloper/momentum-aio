import asyncio
from typing import Set, Dict, List, Any, Optional
from database.database import database
from core.logging.logger import logger


class ServerCommandManager:
    """
    Per-guild command enabling/disabling manager.
    Protects essential commands from being disabled and persists settings to database.
    """
    ESSENTIAL_COMMANDS: Set[str] = {"help", "settings", "ping", "command-manage", "command", "cmdmanage"}
    _disabled_commands: Dict[str, Set[str]] = {}  # guild_id -> set of command names
    _authorized_roles: Dict[str, Set[str]] = {}  # guild_id -> set of role IDs authorized for virtual moderation
    _initialized: bool = False

    @classmethod
    async def initialize(cls) -> None:
        try:
            col = database.collection("server_commands")
            cursor = col.find({})
            records = await cursor.to_list(1000) if hasattr(cursor, "to_list") else await cursor
            for r in records:
                gid = str(r.get("guild_id", ""))
                dis = r.get("disabled_commands", [])
                auth = r.get("authorized_roles", [])
                if gid:
                    cls._disabled_commands[gid] = set(str(c).lower() for c in dis)
                    cls._authorized_roles[gid] = set(str(x) for x in auth)
            cls._initialized = True
            logger.info(f"[ServerCommandManager] Initialized server command records for {len(cls._disabled_commands)} guild(s).")
        except Exception as err:
            logger.warning(f"[ServerCommandManager] Failed to hydrate server command records from DB: {err}")

    @classmethod
    def get_all_manageable_commands(cls) -> List[Dict[str, Any]]:
        from apps.bot.discord.commands.registry import commands_registry
        all_cmds = commands_registry.list_all()
        manageable = []
        for cmd in all_cmds:
            if getattr(cmd, "owner_only", False) or getattr(cmd, "hidden", False):
                continue
            manageable.append({
                "name": cmd.name,
                "category": getattr(cmd, "category", "General") or "General",
                "description": getattr(cmd, "description", "") or "",
                "essential": cmd.name.lower() in cls.ESSENTIAL_COMMANDS
            })
        manageable.sort(key=lambda x: x["name"])
        return manageable

    @classmethod
    def get_guild_settings(cls, guild_id: str) -> Dict[str, Any]:
        gid = str(guild_id)
        return {
            "guild_id": gid,
            "disabledCommands": set(cls._disabled_commands.get(gid, set()))
        }

    @classmethod
    def is_command_disabled(cls, guild_id: str, command_name: str) -> bool:
        if not guild_id or not command_name:
            return False
        name = command_name.lower().strip()
        if name in cls.ESSENTIAL_COMMANDS:
            return False
        return name in cls._disabled_commands.get(str(guild_id), set())

    @classmethod
    def disable_command(cls, guild_id: str, command_name: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        from apps.bot.discord.commands.registry import commands_registry
        name = command_name.lower().strip()
        gid = str(guild_id)

        if name in cls.ESSENTIAL_COMMANDS:
            return {
                "success": False,
                "message": f"Command `/{name}` is an essential system command and cannot be disabled."
            }

        if commands_registry.list_all():
            cmd = commands_registry.get(name)
            if not cmd or getattr(cmd, "owner_only", False):
                return {
                    "success": False,
                    "message": f"Command `/{name}` was not found in manageable commands."
                }

        if gid not in cls._disabled_commands:
            cls._disabled_commands[gid] = set()

        if name in cls._disabled_commands[gid]:
            return {
                "success": False,
                "message": f"Command `/{name}` is already disabled in this server."
            }

        cls._disabled_commands[gid].add(name)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(cls._persist_guild(gid))
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Command `/{name}` has been successfully disabled in this server."
        }

    @classmethod
    def enable_command(cls, guild_id: str, command_name: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        name = command_name.lower().strip()
        gid = str(guild_id)

        if gid not in cls._disabled_commands or name not in cls._disabled_commands[gid]:
            return {
                "success": False,
                "message": f"Command `/{name}` is not currently disabled in this server."
            }

        cls._disabled_commands[gid].remove(name)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(cls._persist_guild(gid))
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Command `/{name}` has been successfully re-enabled in this server."
        }

    @classmethod
    def is_authorized_moderator(cls, guild_id: str, member: Any, command_name: Optional[str] = None) -> bool:
        """
        Validates if member is authorized to run moderation commands through MomentumOne.
        Allows servers to run locked-down Discord permissions while giving controlled
        moderators command access through MomentumOne's authorization system.
        """
        if not member or not guild_id:
            return False

        gid = str(guild_id)
        # Guild Owner is always authorized
        guild = getattr(member, "guild", None)
        if guild and getattr(guild, "owner_id", None) and member.id == guild.owner_id:
            return True

        # Native Administrator
        guild_perms = getattr(member, "guild_permissions", None)
        if guild_perms and getattr(guild_perms, "administrator", False):
            return True

        # Anti-Nuke Extra Owner
        try:
            from core.security.antinuke import AntiNukeManager
            if AntiNukeManager.is_owner_or_extra_owner(guild, str(member.id)):
                return True
        except Exception:
            pass

        # Check virtualized authorized moderator roles
        auth_roles = cls._authorized_roles.get(gid, set())
        if auth_roles and hasattr(member, "roles"):
            member_role_ids = {str(r.id) for r in member.roles}
            if not auth_roles.isdisjoint(member_role_ids):
                return True

        return False

    @classmethod
    def get_authorized_roles(cls, guild_id: str) -> Set[str]:
        return set(cls._authorized_roles.get(str(guild_id), set()))

    @classmethod
    def authorize_moderator_role(cls, guild_id: str, role_id: str) -> Dict[str, Any]:
        gid = str(guild_id)
        rid = str(role_id)
        if gid not in cls._authorized_roles:
            cls._authorized_roles[gid] = set()
        cls._authorized_roles[gid].add(rid)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(cls._persist_guild(gid))
        except Exception:
            pass
        return {"success": True, "message": f"Role `{rid}` successfully authorized as virtual moderator."}

    @classmethod
    def deauthorize_moderator_role(cls, guild_id: str, role_id: str) -> Dict[str, Any]:
        gid = str(guild_id)
        rid = str(role_id)
        if gid in cls._authorized_roles and rid in cls._authorized_roles[gid]:
            cls._authorized_roles[gid].remove(rid)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(cls._persist_guild(gid))
            except Exception:
                pass
            return {"success": True, "message": f"Role `{rid}` removed from authorized virtual moderators."}
        return {"success": False, "message": f"Role `{rid}` was not an authorized moderator role."}

    @classmethod
    async def _persist_guild(cls, guild_id: str) -> None:
        try:
            col = database.collection("server_commands")
            disabled_list = list(cls._disabled_commands.get(guild_id, set()))
            auth_roles_list = list(cls._authorized_roles.get(guild_id, set()))
            await col.update_one(
                {"guild_id": guild_id},
                {"$set": {
                    "guild_id": guild_id,
                    "disabled_commands": disabled_list,
                    "authorized_roles": auth_roles_list,
                }},
                upsert=True
            )
        except Exception as err:
            logger.error(f"[ServerCommandManager] Failed to persist command settings for {guild_id}: {err}")
