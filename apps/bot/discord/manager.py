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
            await self._sync_guilds()
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

        # Helper to dispatch events to registered plugin listeners (e.g., dedicated logging handlers)
        async def _dispatch_plugin_events(ev_name: str, *args: Any, **kwargs: Any) -> None:
            handlers = events_registry.get(ev_name)
            for h in handlers:
                if getattr(h, "category", None) == "antinuke":
                    continue
                try:
                    await h.execute(self.plugin_context, *args, **kwargs)
                except Exception as err:
                    logger.error(f"[BotManager] Error in event listener {h.name} ({getattr(h, 'description', '')}): {err}")

        # Wire Anti-Nuke Security Event Listeners and Plugin Listeners
        from core.security.antinuke_service import AntiNukeService

        @self.client.event
        async def on_guild_update(before: discord.Guild, after: discord.Guild):
            try:
                await AntiNukeService.on_guild_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_update: {err}")
            await _dispatch_plugin_events("on_guild_update", before, after)

        @self.client.event
        async def on_member_ban(guild: discord.Guild, user: discord.User | discord.Member):
            try:
                await AntiNukeService.on_member_ban(guild, user)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_ban: {err}")
            await _dispatch_plugin_events("on_member_ban", guild, user)

        @self.client.event
        async def on_member_unban(guild: discord.Guild, user: discord.User | discord.Member):
            try:
                await AntiNukeService.on_member_unban(guild, user)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_unban: {err}")
            await _dispatch_plugin_events("on_member_unban", guild, user)

        @self.client.event
        async def on_member_remove(member: discord.Member):
            try:
                await AntiNukeService.on_member_remove(member)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_remove: {err}")
            await _dispatch_plugin_events("on_member_remove", member)

        @self.client.event
        async def on_member_join(member: discord.Member):
            try:
                await AntiNukeService.on_member_join(member)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_join: {err}")
            await _dispatch_plugin_events("on_member_join", member)

        @self.client.event
        async def on_member_update(before: discord.Member, after: discord.Member):
            try:
                await AntiNukeService.on_member_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_member_update: {err}")
            await _dispatch_plugin_events("on_member_update", before, after)

        @self.client.event
        async def on_guild_role_create(role: discord.Role):
            try:
                await AntiNukeService.on_guild_role_create(role)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_role_create: {err}")
            await _dispatch_plugin_events("on_guild_role_create", role)

        @self.client.event
        async def on_guild_role_delete(role: discord.Role):
            try:
                await AntiNukeService.on_guild_role_delete(role)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_role_delete: {err}")
            await _dispatch_plugin_events("on_guild_role_delete", role)

        @self.client.event
        async def on_guild_role_update(before: discord.Role, after: discord.Role):
            try:
                await AntiNukeService.on_guild_role_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_role_update: {err}")
            await _dispatch_plugin_events("on_guild_role_update", before, after)

        @self.client.event
        async def on_guild_channel_create(channel: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_guild_channel_create(channel)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_channel_create: {err}")
            await _dispatch_plugin_events("on_guild_channel_create", channel)

        @self.client.event
        async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_guild_channel_delete(channel)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_channel_delete: {err}")
            await _dispatch_plugin_events("on_guild_channel_delete", channel)

        @self.client.event
        async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_guild_channel_update(before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_channel_update: {err}")
            await _dispatch_plugin_events("on_guild_channel_update", before, after)

        @self.client.event
        async def on_guild_emojis_update(guild: discord.Guild, before: Any, after: Any):
            try:
                await AntiNukeService.on_guild_emojis_update(guild, before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_emojis_update: {err}")
            await _dispatch_plugin_events("on_guild_emojis_update", guild, before, after)

        @self.client.event
        async def on_guild_stickers_update(guild: discord.Guild, before: Any, after: Any):
            try:
                await AntiNukeService.on_guild_stickers_update(guild, before, after)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_stickers_update: {err}")
            await _dispatch_plugin_events("on_guild_stickers_update", guild, before, after)

        @self.client.event
        async def on_webhooks_update(channel: discord.abc.GuildChannel):
            try:
                await AntiNukeService.on_webhooks_update(channel)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_webhooks_update: {err}")
            await _dispatch_plugin_events("on_webhooks_update", channel)

        @self.client.event
        async def on_invite_create(invite: discord.Invite):
            try:
                await AntiNukeService.on_invite_create(invite)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_invite_create: {err}")
            await _dispatch_plugin_events("on_invite_create", invite)

        @self.client.event
        async def on_invite_delete(invite: discord.Invite):
            try:
                await AntiNukeService.on_invite_delete(invite)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_invite_delete: {err}")
            await _dispatch_plugin_events("on_invite_delete", invite)

        @self.client.event
        async def on_guild_integrations_update(guild: discord.Guild):
            try:
                await AntiNukeService.on_guild_integrations_update(guild)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_guild_integrations_update: {err}")
            await _dispatch_plugin_events("on_guild_integrations_update", guild)

        @self.client.event
        async def on_auto_moderation_rule_create(rule: Any):
            try:
                await AntiNukeService.on_auto_moderation_rule_create(rule)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_auto_moderation_rule_create: {err}")
            await _dispatch_plugin_events("on_auto_moderation_rule_create", rule)

        @self.client.event
        async def on_auto_moderation_rule_update(rule: Any):
            try:
                await AntiNukeService.on_auto_moderation_rule_update(rule)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_auto_moderation_rule_update: {err}")
            await _dispatch_plugin_events("on_auto_moderation_rule_update", rule)

        @self.client.event
        async def on_auto_moderation_rule_delete(rule: Any):
            try:
                await AntiNukeService.on_auto_moderation_rule_delete(rule)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_auto_moderation_rule_delete: {err}")
            await _dispatch_plugin_events("on_auto_moderation_rule_delete", rule)

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
        @self.client.event
        async def on_thread_delete(thread: discord.Thread):
            try:
                await AntiNukeService.on_thread_delete(thread)
            except Exception as err:
                logger.error(f"[AntiNuke] Error in on_thread_delete: {err}")

        @self.client.event
        async def on_guild_join(guild: discord.Guild):
            await _dispatch_plugin_events("on_guild_join", guild)
            await _dispatch_plugin_events("guild_join", guild)

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

            # Sync and hydrate client guilds before startup diagnostics
            await self._sync_guilds()

            # Startup Diagnostics
            reg_events = events_registry.list_all()
            reg_cmds = commands_registry.list_all()
            from core.security.antinuke import AntiNukeConstants
            antinuke_events = [e for e in reg_events if getattr(e, "category", None) == "antinuke" or getattr(e, "canonical_event", None)]
            logging_events = [e for e in reg_events if getattr(e, "category", None) == "logging"]
            logger.info(
                f"[BotManager] Startup Diagnostics: {len(reg_cmds)} commands registered | "
                f"{len(reg_events)} total event listeners registered ({len(antinuke_events)} security listeners, "
                f"{len(logging_events)} dedicated logging listeners). "
                f"Enabled security modes: {AntiNukeConstants.get_enabled_modes()}"
            )
            self._is_setup = True
            return {"ready": True}
        except Exception as err:
            logger.error(f"[BotManager] Setup failure: {err}")
            self._is_setup = False
            return {"ready": False}

    async def _sync_guilds(self) -> None:
        """
        Synchronizes client guilds with active Anti-Nuke configurations,
        database logging configs, and standard Sentinel servers so that
        the bot is always active in its designated server environments.
        """
        from core.security.antinuke import AntiNukeManager, AntiNukeConstants

        existing_ids = {str(g.id) for g in self.client.guilds}

        # 1. Pull from in-memory AntiNukeManager
        guild_sources: Dict[str, Dict[str, Any]] = dict(AntiNukeManager._guild_configs)

        # 2. Pull from database collections (antinuke_configs & guild_logging_configs)
        try:
            an_col = database.collection("antinuke_configs")
            cursor = an_col.find({})
            records = await cursor.to_list(100) if hasattr(cursor, "to_list") else await cursor
            for r in (records or []):
                gid = str(r.get("guild_id", ""))
                if gid and gid not in guild_sources:
                    guild_sources[gid] = r

            log_col = database.collection("guild_logging_configs")
            cursor_log = log_col.find({})
            log_records = await cursor_log.to_list(100) if hasattr(cursor_log, "to_list") else await cursor_log
            for r in (log_records or []):
                gid = str(r.get("guild_id", ""))
                if gid and gid not in guild_sources:
                    guild_sources[gid] = {"guild_id": gid, "guild_name": f"Server {gid}"}
        except Exception as err:
            logger.debug(f"[BotManager] Guild sync database query: {err}")

        has_real_token = bool(
            settings.BOT_TOKEN
            and len(settings.BOT_TOKEN.strip()) > 20
            and not settings.BOT_TOKEN.strip().startswith("sentinel_")
        )

        # In real Discord mode, strictly retain live Discord guilds and do not inject mock guilds
        if has_real_token:
            for guild in self.client.guilds:
                gid_str = str(guild.id)
                if gid_str not in AntiNukeManager._guild_configs:
                    AntiNukeManager._guild_configs[gid_str] = {
                        "guild_id": gid_str,
                        "guild_name": guild.name,
                        "setup_completed": True,
                        "enabled": True,
                        "mode": "hard",
                        "monitored_events": list(AntiNukeConstants.ALL_EVENTS),
                    }
            return

        # 3. In local / standalone simulation mode, ensure the 3 default Sentinel production servers exist
        default_sentinel_guilds = [
            {
                "guild_id": "987654321",
                "guild_name": "Sentinel Production Nexus",
                "owner_id": 111222333,
                "member_count": 142
            },
            {
                "guild_id": "876543210",
                "guild_name": "Sentinel Operations Hub",
                "owner_id": 111222333,
                "member_count": 88
            },
            {
                "guild_id": "765432109",
                "guild_name": "Sentinel Security Gateway",
                "owner_id": 111222333,
                "member_count": 64
            }
        ]
        for def_g in default_sentinel_guilds:
            gid = def_g["guild_id"]
            if gid not in guild_sources:
                guild_sources[gid] = def_g
            if gid not in AntiNukeManager._guild_configs:
                AntiNukeManager._guild_configs[gid] = {
                    "guild_id": gid,
                    "guild_name": def_g["guild_name"],
                    "setup_completed": True,
                    "enabled": True,
                    "mode": "hard",
                    "monitored_events": list(AntiNukeConstants.ALL_EVENTS),
                }

        # 4. Create and populate discord.Guild objects in self.client.guilds (mock / local mode)
        for gid_str, g_data in guild_sources.items():
            if gid_str in existing_ids:
                continue
            try:
                gid = int(gid_str)
            except ValueError:
                continue

            name = g_data.get("guild_name") or g_data.get("name") or f"Sentinel Server {gid}"
            guild = discord.Guild(id=gid, name=name)
            guild.owner_id = int(g_data.get("owner_id", 111222333))
            guild.member_count = int(g_data.get("member_count", 100))

            # Setup bot member inside guild
            bot_user = self.client.user or discord.User(id=1563628961379123302, name="Sentinel™")
            me = discord.Member(id=bot_user.id, name=bot_user.name, guild=guild)
            me_perms = discord.Permissions(
                administrator=True,
                manage_guild=True,
                manage_roles=True,
                manage_channels=True,
                ban_members=True,
                kick_members=True,
                view_audit_log=True
            )
            me.guild_permissions = me_perms
            top_role = discord.Role(id=999001, name="Sentinel™ Security", position=50)
            me.top_role = top_role
            guild.me = me
            guild.roles = [
                discord.Role(id=gid, name="@everyone", position=0),
                top_role,
                discord.Role(id=999002, name="Administrator", position=40),
                discord.Role(id=999003, name="Moderator", position=30),
            ]

            # Default channels
            ch_general = discord.TextChannel(id=gid + 1, name="general")
            ch_general.guild = guild
            ch_sec = discord.TextChannel(id=gid + 2, name="security-logs")
            ch_sec.guild = guild
            ch_warn = discord.TextChannel(id=gid + 3, name="warning-logs")
            ch_warn.guild = guild

            guild.channels = [ch_general, ch_sec, ch_warn]
            guild.text_channels = [ch_general, ch_sec, ch_warn]

            self.client.guilds.append(guild)
            existing_ids.add(gid_str)

    async def start(self) -> None:
        token = settings.BOT_TOKEN.strip() if settings.BOT_TOKEN else "sentinel_local_gateway"

        is_ready = self.client.is_ready() if hasattr(self.client, "is_ready") else False
        if self._is_starting or is_ready:
            logger.warn("[BOT] Discord client start() called while already connecting or ready.")
            return

        is_closed = self.client.is_closed() if hasattr(self.client, "is_closed") else False
        if is_closed:
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
        is_closed = self.client.is_closed() if hasattr(self.client, "is_closed") else False
        if not is_closed and hasattr(self.client, "close"):
            await self.client.close()
