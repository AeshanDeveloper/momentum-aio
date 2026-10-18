import os
import sys
import asyncio
from dotenv import load_dotenv

# Add python directory and root to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

load_dotenv()

from config.settings import settings
from config.strings import get_string
from core.logging.logger import logger
from core.telemetry.observability import ObservabilityManager
from core.events.event_bus import EventBus
from core.events.events_list import EventsList
from database.database import database
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
    except Exception as err:
        logger.error(f"[Startup] Database initialization failed: {err}")

    # Initialize Bot App
    bot_app = BotApp()
    await bot_app.bot.setup()

    # Initialize & Start Web API / Control Center Server on port 3000
    api_server = ApiServer(bot_manager=bot_app.bot)
    await api_server.start()

    # Start Discord Bot Gateway if enabled and token present
    if settings.BOT_ENABLED:
        if settings.BOT_TOKEN:
            asyncio.create_task(bot_app.bot.start())
        else:
            logger.info("[MomentumOne] Discord bot token is not configured. Running in standby mode.")
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
