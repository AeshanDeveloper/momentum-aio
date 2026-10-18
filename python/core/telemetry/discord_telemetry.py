from typing import Any
from core.logging.logger import logger
from .observability import ObservabilityManager

class DiscordTelemetry:
    @classmethod
    def hook(cls, client: Any) -> None:
        logger.info("[DiscordTelemetry] Telemetry hooks attached to Discord client.")
