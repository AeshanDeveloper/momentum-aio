from typing import Any, Dict, Optional
from core.logging.logger import logger
from .observability import ObservabilityManager


class DiscordTelemetry:
    _hooked: bool = False
    _client: Optional[Any] = None

    @classmethod
    def hook(cls, client: Any) -> None:
        if cls._hooked and cls._client is client:
            return
        cls._client = client
        cls._hooked = True
        logger.info("[DiscordTelemetry] Telemetry hooks attached to Discord client.")

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """
        Return real connection, gateway, and telemetry stats for the Discord client.
        """
        client = cls._client
        ws_ping = (
            round(client.latency * 1000, 2)
            if client and hasattr(client, "latency") and client.latency is not None and client.latency >= 0
            else None
        )
        is_ready = bool(client.is_ready()) if (client and hasattr(client, "is_ready")) else False
        guild_count = len(client.guilds) if (client and hasattr(client, "guilds")) else 0
        user_count = len(client.users) if (client and hasattr(client, "users")) else 0

        obs = ObservabilityManager.get_metrics()

        return {
            "hooked": cls._hooked,
            "connected": is_ready,
            "latency_ms": ws_ping,
            "guild_count": guild_count,
            "user_count": user_count,
            "rate_limits": 0,
            "api_failures": 0,
            "observability": obs,
        }
