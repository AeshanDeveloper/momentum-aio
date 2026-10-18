import os
import time
import asyncio
from typing import Dict, Any, Optional
import discord
from config.settings import settings
from core.logging.logger import logger
from core.container.container import container
from core.events.event_bus import EventBus
from core.plugins.context import PluginContext
from core.plugins.manager import PluginManager
from core.telemetry.discord_telemetry import DiscordTelemetry
from database.database import database
from shared.cache.ttl_cache import TTLCache
from .commands.registry import commands_registry
from .events.registry import events_registry

class BotManager:
    """
    Discord Bot Lifecycle, Gateway, Event Dispatcher, and Diagnostics Manager.
    """
    def __init__(self):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.messages = True
        intents.message_content = True
        intents.dm_messages = True

        self.client = discord.Client(intents=intents)
        self.event_bus = EventBus()
        self.cache = TTLCache(default_ttl_ms=60_000)
        self.plugin_context = PluginContext(
            event_bus=self.event_bus,
            client=self.client,
            logger=logger,
            cache=self.cache,
            database_manager=database
        )
        self.plugins = PluginManager(self.plugin_context)
        self._is_ready = False
        self._started_at = None

        # Hook DiscordTelemetry
        DiscordTelemetry.hook(self.client)

        # Wire client event dispatchers
        self._setup_event_hooks()

    def _setup_event_hooks(self) -> None:
        @self.client.event
        async def on_ready():
            self._is_ready = True
            self._started_at = time.time()
            username = str(self.client.user)
            guilds_count = len(self.client.guilds)
            logger.info(f"[BOT] Connected as {username} | Active in {guilds_count} guild(s).")
            # Trigger on_ready in plugins
            for record in self.plugins.registry.list_all():
                if hasattr(record.instance, "on_ready"):
                    res = record.instance.on_ready()
                    if hasattr(res, "__await__"):
                        await res

        @self.client.event
        async def on_message(message: discord.Message):
            # Dispatch to registered messageCreate event handlers
            handlers = events_registry.get("messageCreate")
            for h in handlers:
                try:
                    await h.execute(self.plugin_context, message)
                except Exception as err:
                    logger.error(f"[BotManager] Error executing message handler {h.name}: {err}")

        @self.client.event
        async def on_interaction(interaction: discord.Interaction):
            if interaction.type == discord.InteractionType.application_command:
                handlers = events_registry.get("interactionCreate")
            elif interaction.type == discord.InteractionType.component:
                handlers = events_registry.get("interactionComponent")
            else:
                handlers = []

            for h in handlers:
                try:
                    await h.execute(self.plugin_context, interaction)
                except Exception as err:
                    logger.error(f"[BotManager] Error executing interaction handler {h.name}: {err}")

    async def setup(self) -> Dict[str, bool]:
        try:
            # 1. Discover and load plugins
            from plugins.MomentumOneToolkit import Plugin as ToolkitPlugin
            tk_instance = ToolkitPlugin(self.plugin_context)
            self.plugins.registry.register("MomentumOneToolkit", {
                "name": "MomentumOneToolkit",
                "version": "1.0.0",
                "description": "Enterprise-grade toolkit"
            }, tk_instance)
            await tk_instance.on_load()
            await self.plugins.enable("MomentumOneToolkit")

            # Also discover additional external plugins in plugins folder
            await self.plugins.discover_and_load()
            await self.plugins.enable_all()
            return {"ready": True}
        except Exception as err:
            logger.error(f"[BotManager] Setup failure: {err}")
            return {"ready": False}

    async def start(self) -> None:
        token = settings.BOT_TOKEN.strip()
        if not token:
            logger.info("[BOT] Discord bot token (BOT_TOKEN) is not configured. Running offline.")
            return

        setup_res = await self.setup()
        if not setup_res.get("ready"):
            logger.error("[BOT] Setup failed; aborting login.")
            return

        logger.info("[BOT] Attempting Discord gateway connection...")
        try:
            await self.client.start(token)
        except Exception as err:
            logger.error(f"[BOT] Login error: {err}")

    def status(self) -> Dict[str, Any]:
        ready = self.client.is_ready()
        uptime = int(time.time() - self._started_at) if (self._started_at and ready) else None
        return {
            "state": "online" if ready else ("starting" if settings.BOT_TOKEN else "offline"),
            "process": True,
            "discordReady": ready,
            "username": str(self.client.user) if self.client.user else None,
            "userId": str(self.client.user.id) if self.client.user else None,
            "guildCount": len(self.client.guilds) if ready else 0,
            "uptime": uptime,
            "latency": round(self.client.latency * 1000, 1) if (ready and self.client.latency is not None) else None,
            "tokenConfigured": bool(settings.BOT_TOKEN),
        }

    def registry(self) -> Dict[str, Any]:
        return {
            "commands": [c.to_dict() for c in commands_registry.list_all()],
            "plugins": self.plugins.registry.list_manifests(),
            "events": [
                {"name": e.name, "description": e.description, "enabled": e.enabled}
                for e in events_registry.list_all()
            ]
        }

    async def logout(self) -> None:
        if not self.client.is_closed():
            await self.client.close()
