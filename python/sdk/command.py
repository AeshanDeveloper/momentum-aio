from typing import Dict, Any, List, Optional, Callable
from shared.types.command_record import CommandType, CommandStatus, RegisteredBy

class Command:
    def __init__(
        self,
        name: str,
        execute: Callable[..., Any],
        description: str = "",
        category: str = "general",
        aliases: Optional[List[str]] = None,
        usage: str = "",
        examples: Optional[List[str]] = None,
        user_permissions: Optional[List[Any]] = None,
        bot_permissions: Optional[List[Any]] = None,
        cooldown: float = 0.0,
        cooldown_scope: str = "user",
        owner_only: bool = False,
        guild_only: bool = False,
        nsfw: bool = False,
        command_type: str = CommandType.HYBRID,
        status: str = CommandStatus.ACTIVE,
        enabled: bool = True,
        hidden: bool = False,
        subcommands: Optional[List[Dict[str, Any]]] = None,
        sub_commands: Optional[List[Dict[str, Any]]] = None,
        builder: Optional[Any] = None,
        plugin_id: Optional[str] = None
    ):
        self.name = name.lower()
        self.execute = execute
        self.description = description
        self.category = category
        self.aliases = [a.lower() for a in (aliases or [])]
        self.usage = usage
        self.examples = examples or []
        self.user_permissions = user_permissions or []
        self.bot_permissions = bot_permissions or []
        self.cooldown = cooldown
        self.cooldown_scope = cooldown_scope
        self.owner_only = owner_only
        self.guild_only = guild_only
        self.nsfw = nsfw
        self.command_type = command_type
        self.status = status
        self.enabled = enabled
        self.hidden = hidden
        self.sub_commands = sub_commands or subcommands or []
        self.subcommands = self.sub_commands
        self.subCommands = self.sub_commands
        self.builder = builder
        self.plugin_id = plugin_id

        # TypeScript-parity aliases
        self.type = self.command_type
        self.command = self
        self.raw = self
        self.userPermissions = self.user_permissions
        self.botPermissions = self.bot_permissions
        self.ownerOnly = self.owner_only

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "aliases": self.aliases,
            "usage": self.usage,
            "userPermissions": self.user_permissions,
            "botPermissions": self.bot_permissions,
            "cooldown": self.cooldown,
            "cooldownScope": self.cooldown_scope,
            "ownerOnly": self.owner_only,
            "guildOnly": self.guild_only,
            "nsfw": self.nsfw,
            "type": self.command_type,
            "status": self.status,
            "enabled": self.enabled,
            "hidden": self.hidden,
            "sub_commands": self.sub_commands,
            "pluginId": self.plugin_id
        }
