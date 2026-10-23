from config.settings import settings
from core.logging.logger import logger
from .discord.manager import BotManager

class BotApp:
    def __init__(self):
        self.bot = BotManager()

    async def start(self) -> None:
        if not settings.BOT_ENABLED:
            logger.info("[BOT] Discord bot is disabled by BOT_ENABLED setting.")
            return
        await self.bot.setup()
        if settings.BOT_TOKEN:
            import asyncio
            asyncio.create_task(self.bot.start())
        else:
            logger.info("[BOT] BOT_TOKEN not provided; bot initialized in standby mode.")
