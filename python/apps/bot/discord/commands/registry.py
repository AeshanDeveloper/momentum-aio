from typing import Dict, Any, List, Optional
from sdk.command import Command

class CommandRegistry:
    def __init__(self):
        self._commands: Dict[str, Command] = {}
        self._aliases: Dict[str, str] = {}

    def register(self, command: Command) -> bool:
        name = command.name.lower()
        if name in self._commands and self._commands[name].execute == command.execute:
            return False
        self._commands[name] = command
        for a in command.aliases:
            self._aliases[a.lower()] = name
        return True

    def get(self, name_or_alias: str) -> Optional[Command]:
        target = name_or_alias.lower()
        if target in self._commands:
            return self._commands[target]
        canonical = self._aliases.get(target)
        if canonical and canonical in self._commands:
            return self._commands[canonical]
        return None

    def list_all(self) -> List[Command]:
        return list(self._commands.values())

    def clear(self) -> None:
        self._commands.clear()
        self._aliases.clear()

    def size(self) -> int:
        return len(self._commands)

commands_registry = CommandRegistry()
