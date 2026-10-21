import os
from typing import Any
from sdk.plugin import Plugin as BasePlugin
from sdk.command import Command
from sdk.event import Event
from apps.bot.discord.commands.registry import commands_registry
from apps.bot.discord.events.registry import events_registry
from core.security.blacklist import BlacklistManager
from core.security.antispam import AntiSpamService
from core.security.noprefix import NoPrefixManager
from core.logging.logger import logger

# Import commands
from .commands import ping, help, ai
from .commands.general import botinfo, server, profile, bug, notifications, update
from .commands.moderation import announce, channel, command_manage
from .commands.security import (
    antinuke,
    setup as sec_setup,
    whitelist,
    unwhitelist,
    punishment,
)
from .commands.tickets import ticket
from .commands.dev import (
    blacklist,
    unblacklist,
    noprefix,
    status,
    reboot,
    reload,
    eval as dev_eval,
    errors,
    audit,
    say,
    listservers,
    botprofile,
)

# Import events
from .events import prefix_handler, slash_handler, component_handler

class Plugin(BasePlugin):
    """
    MomentumOne Toolkit Python plugin.
    Registers commands, event handlers, and activates core security managers.
    """
    def __init__(self, ctx: Any):
        super().__init__(ctx)
        self.plugin_id = "MomentumOneToolkit"

    async def on_load(self) -> None:
        logger.info(f"[{self.plugin_id}] Loading commands and event dispatchers...")

        command_modules = [
            ping,
            help,
            ai,
            botinfo,
            server,
            profile,
            bug,
            notifications,
            update,
            announce,
            channel,
            command_manage,
            antinuke,
            sec_setup,
            whitelist,
            unwhitelist,
            punishment,
            ticket,
            blacklist,
            unblacklist,
            noprefix,
            status,
            reboot,
            reload,
            dev_eval,
            errors,
            audit,
            say,
            listservers,
            botprofile,
        ]

        for mod in command_modules:
            cmd = Command(
                name=getattr(mod, "name"),
                execute=getattr(mod, "execute"),
                description=getattr(mod, "description", ""),
                category=getattr(mod, "category", "General"),
                aliases=getattr(mod, "aliases", []),
                usage=getattr(mod, "usage", ""),
                user_permissions=getattr(mod, "user_permissions", []),
                bot_permissions=getattr(mod, "bot_permissions", []),
                cooldown=float(getattr(mod, "cooldown", 0.0)),
                cooldown_scope=getattr(mod, "cooldown_scope", "user"),
                owner_only=bool(getattr(mod, "owner_only", False)),
                guild_only=bool(getattr(mod, "guild_only", False)),
                nsfw=bool(getattr(mod, "nsfw", False)),
                plugin_id=self.plugin_id
            )
            commands_registry.register(cmd)

        event_modules = [
            prefix_handler,
            slash_handler,
            component_handler,
        ]

        for ev in event_modules:
            evt = Event(
                name=getattr(ev, "name"),
                execute=getattr(ev, "execute"),
                description=getattr(ev, "description", "")
            )
            events_registry.register(evt)

        logger.info(f"[{self.plugin_id}] Successfully registered {len(command_modules)} commands & {len(event_modules)} event listeners.")

    async def on_ready(self) -> None:
        pass

    async def on_enable(self) -> None:
        pass

    async def on_disable(self) -> None:
        pass

PluginClass = Plugin
