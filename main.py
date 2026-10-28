import os
import sys
import asyncio
# Add python directory and root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    for env_path in [os.path.join(BASE_DIR, ".env"), os.path.join(BASE_DIR, ".env.example")]:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip('"').strip("'")
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass


from config.settings import settings
from config.strings import get_string
from core.logging.logger import logger
from core.telemetry.observability import ObservabilityManager
from core.events.event_bus import EventBus
from core.events.events_list import EventsList
from database.database import database
from core.security.server_commands import ServerCommandManager
from core.security.blacklist import BlacklistManager
from core.security.noprefix import NoPrefixManager
from core.security.antinuke import AntiNukeManager
from apps.bot.main import BotApp
from apps.api.server import ApiServer

async def main():
    logger.info(get_string("system.booting", "[MomentumOne] The system is booting up... Please wait..."))

    # Initialize observability & lifecycle
    ObservabilityManager.init()
    ObservabilityManager.record_lifecycle_event("startup", {"version": "26.7.20"})

    # Connect Database
    logger.info(get_string("system.database_connecting", "[MomentumOne] Initializing database..."))
    try:
        await database.initialize("system")
        logger.info(get_string("system.database_connected", "[MomentumOne] Connected to database store successfully."))
        # Hydrate persistent security registries
        await ServerCommandManager.initialize()
        await BlacklistManager.initialize()
        await NoPrefixManager.initialize()
        await AntiNukeManager.initialize()
        from core.security.activity_manager import security_activity_manager
        security_activity_manager.attach_to_collector()
        logger.info("[MomentumOne] Security registries (ServerCommands, Blacklist, NoPrefix, AntiNuke) hydrated from storage; ActivityManager attached.")
    except Exception as err:
        logger.error(f"[Startup] Database initialization or hydration failed: {err}")

    # Initialize Bot App
    bot_app = BotApp()
    await bot_app.bot.setup()

    # Initialize & Start Web API / Control Center Server on port 3000
    api_server = ApiServer(bot_manager=bot_app.bot)
    await api_server.start()

    # Start Discord Bot Gateway if enabled
    if settings.BOT_ENABLED:
        asyncio.create_task(bot_app.bot.start())
    else:
        logger.info(get_string("system.bot_disabled", "[MomentumOne] Discord bot is disabled in environment settings."))

    logger.info(get_string("system.ready", "[MomentumOne] System core initialized and ready."))

    # Keep persistent event loop alive
    stop_event = asyncio.Event()
    await stop_event.wait()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("[MomentumOne] System shutting down gracefully.")
