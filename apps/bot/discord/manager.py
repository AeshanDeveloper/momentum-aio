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

        self._intents = intents
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
        self._is_setup = False
        self._is_starting = False

        # Hook DiscordTelemetry
        DiscordTelemetry.hook(self.client)

        # Wire client event dispatchers
        self._setup_event_hooks()

    def _recreate_client(self) -> None:
        self.client = discord.Client(intents=self._intents)
        self.plugin_context.client = self.client
        DiscordTelemetry.hook(self.client)
        self._setup_event_hooks()

    def _setup_event_hooks(self) -> None:
        if getattr(self.client, "_event_hooks_setup", False):
            return
        setattr(self.client, "_event_hooks_setup", True)
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

        # Wire Anti-Nuke Security Event Listeners
        from core.security.antinuke_service import AntiNukeService

        @self.client.event
        async def on_guild_update(before: discord.Guild, after: discord.Guild):
            try:
                await AntiNukeService.on_guild_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_update: {err}")

        @self.client.event
        async def on_member_ban(guild: discord.Guild, user: discord.User | discord.Member):
            try:
                await AntiNukeService.on_member_ban(guild, user)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_ban: {err}")

        @self.client.event
        async def on_member_unban(guild: discord.Guild, user: discord.User | discord.Member):
            try:
                await AntiNukeService.on_member_unban(guild, user)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_unban: {err}")

        @self.client.event
        async def on_member_remove(member: discord.Member):
            try:
                await AntiNukeService.on_member_remove(member)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_remove: {err}")

        @self.client.event
        async def on_member_join(member: discord.Member):
            try:
                await AntiNukeService.on_member_join(member)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_join: {err}")

        @self.client.event
        async def on_member_update(before: discord.Member, after: discord.Member):
            try:
                await AntiNukeService.on_member_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_update: {err}")

        @self.client.event
        async def on_guild_role_create(role: discord.Role):
            try:
                await AntiNukeService.on_guild_role_create(role)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_role_create: {err}")

        @self.client.event
        async def on_guild_role_delete(role: discord.Role):
            try:
                await AntiNukeService.on_guild_role_delete(role)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_role_delete: {err}")

        @self.client.event
        async def on_guild_role_update(before: discord.Role, after: discord.Role):
            try:
                await AntiNukeService.on_guild_role_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_role_update: {err}")

        @self.client.event
        async def on_guild_channel_create(channel: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_guild_channel_create(channel)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_channel_create: {err}")

        @self.client.event
        async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_guild_channel_delete(channel)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_channel_delete: {err}")

        @self.client.event
        async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_guild_channel_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_channel_update: {err}")

        @self.client.event
        async def on_guild_emojis_update(guild: discord.Guild, before: Any, after: Any):
            try:
                await AntiNukeService.on_guild_emojis_update(guild, before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_emojis_update: {err}")

        @self.client.event
        async def on_guild_stickers_update(guild: discord.Guild, before: Any, after: Any):
            try:
                await AntiNukeService.on_guild_stickers_update(guild, before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_stickers_update: {err}")

        @self.client.event
        async def on_webhooks_update(channel: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_webhooks_update(channel)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_webhooks_update: {err}")

        @self.client.event
        async def on_invite_create(invite: discord.Invite):
            try:
                await AntiNukeService.on_invite_create(invite)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_invite_create: {err}")

        @self.client.event
        async def on_invite_delete(invite: discord.Invite):
            try:
                await AntiNukeService.on_invite_delete(invite)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_invite_delete: {err}")

        @self.client.event
        async def on_guild_integrations_update(guild: discord.Guild):
            try:
                await AntiNukeService.on_guild_integrations_update(guild)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_integrations_update: {err}")

        @self.client.event
        async def on_auto_moderation_rule_create(rule: Any):
            try:
                await AntiNukeService.on_auto_moderation_rule_create(rule)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_auto_moderation_rule_create: {err}")

        @self.client.event
        async def on_auto_moderation_rule_update(rule: Any):
            try:
                await AntiNukeService.on_auto_moderation_rule_update(rule)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_auto_moderation_rule_update: {err}")

        @self.client.event
        async def on_auto_moderation_rule_delete(rule: Any):
            try:
                await AntiNukeService.on_auto_moderation_rule_delete(rule)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_auto_moderation_rule_delete: {err}")

        @self.client.event
        async def on_audit_log_entry_create(entry: discord.AuditLogEntry):
            try:
                await AntiNukeService.on_audit_log_entry_create(entry)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_audit_log_entry_create: {err}")

        @self.client.event
        async def on_scheduled_event_delete(event: Any):
            try:
                await AntiNukeService.on_scheduled_event_delete(event)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_scheduled_event_delete: {err}")

        @self.client.event
        async def on_thread_delete(thread: discord.Thread):
            try:
                await AntiNukeService.on_thread_delete(thread)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_thread_delete: {err}")

    async def setup(self) -> Dict[str, bool]:
        if self._is_setup:
            return {"ready": True}
        try:
            # 1. Discover and load plugins
            from plugins.MomentumOneToolkit import Plugin as ToolkitPlugin
            if not self.plugins.registry.get("MomentumOneToolkit"):
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

            # Startup Diagnostics
            reg_events = events_registry.list_all()
            reg_cmds = commands_registry.list_all()
            from core.security.antinuke import AntiNukeConstants
            antinuke_events = [e for e in reg_events if getattr(e, "canonical_event", None) or e.name.startswith("on_")]
            logger.info(
                f"[BotManager] Startup Diagnostics: {len(reg_cmds)} commands registered | "
                f"{len(reg_events)} total event listeners registered ({len(antinuke_events)} security listeners). "
                f"Enabled security modes: {AntiNukeConstants.get_enabled_modes()}"
            )
            self._is_setup = True
            return {"ready": True}
        except Exception as err:
            logger.error(f"[BotManager] Setup failure: {err}")
            self._is_setup = False
            return {"ready": False}

    async def start(self) -> None:
        token = settings.BOT_TOKEN.strip()
        if not token:
            logger.info("[BOT] Discord bot token (BOT_TOKEN) is not configured. Running offline.")
            return

        if self._is_starting or self.client.is_ready():
            logger.warn("[BOT] Discord client start() called while already connecting or ready.")
            return

        if self.client.is_closed():
            self._recreate_client()

        if not self._is_setup:
            setup_res = await self.setup()
            if not setup_res.get("ready"):
                logger.error("[BOT] Setup failed; aborting login.")
                return

        self._is_starting = True
        logger.info("[BOT] Attempting Discord gateway connection...")
        try:
            await self.client.start(token)
        except Exception as err:
            logger.error(f"[BOT] Login error: {err}")
        finally:
            self._is_starting = False

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
        self._is_starting = False
        self._is_ready = False
        self._started_at = None
        if not self.client.is_closed():
            await self.client.close()
