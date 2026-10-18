from typing import Set, Dict

class ServerCommandManager:
    """
    Per-guild command enabling/disabling manager.
    Protects essential commands (like help and settings) from being disabled.
    """
    ESSENTIAL_COMMANDS: Set[str] = {"help", "settings", "ping"}
    _disabled_commands: Dict[str, Set[str]] = {}  # guild_id -> set of command names

    @classmethod
    def is_command_disabled(cls, guild_id: str, command_name: str) -> bool:
        if not guild_id:
            return False
        name = command_name.lower()
        if name in cls.ESSENTIAL_COMMANDS:
            return False
        return name in cls._disabled_commands.get(str(guild_id), set())

    @classmethod
    def disable_command(cls, guild_id: str, command_name: str) -> bool:
        name = command_name.lower()
        if name in cls.ESSENTIAL_COMMANDS:
            return False  # Protected
        gid = str(guild_id)
        if gid not in cls._disabled_commands:
            cls._disabled_commands[gid] = set()
        cls._disabled_commands[gid].add(name)
        return True

    @classmethod
    def enable_command(cls, guild_id: str, command_name: str) -> bool:
        gid = str(guild_id)
        name = command_name.lower()
        if gid in cls._disabled_commands and name in cls._disabled_commands[gid]:
            cls._disabled_commands[gid].remove(name)
            return True
        return False
