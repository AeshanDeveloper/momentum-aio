import time
import asyncio
from typing import Dict, Any, List, Optional
from core.logging.logger import logger

class ObservabilityManager:
    _total_commands = 0
    _successful_commands = 0
    _failed_commands = 0
    _command_latencies: List[float] = []
    _recent_events: List[Dict[str, Any]] = []
    _lifecycle_events: List[Dict[str, Any]] = []

    @classmethod
    def init(cls) -> None:
        logger.info("[Observability] Observability subsystem initialized.")

    @classmethod
    def record_command(
        cls,
        command_name: str,
        command_type: str = "prefix",
        success: bool = True,
        duration_ms: float = 0.0,
        error: Optional[str] = None
    ) -> None:
        cls._total_commands += 1
        if success:
            cls._successful_commands += 1
        else:
            cls._failed_commands += 1

        cls._command_latencies.append(duration_ms)
        if len(cls._command_latencies) > 200:
            cls._command_latencies.pop(0)

        record = {
            "name": command_name,
            "type": command_type,
            "success": success,
            "duration_ms": duration_ms,
            "error": error,
            "timestamp": time.time()
        }
        cls._recent_events.insert(0, record)
        if len(cls._recent_events) > 50:
            cls._recent_events.pop()

    @classmethod
    def record_error(cls, category: str, message: str) -> None:
        logger.error(f"[Observability] Error [{category}]: {message}")

    @classmethod
    def record_lifecycle_event(cls, event_name: str, meta: Optional[Dict[str, Any]] = None) -> None:
        cls._lifecycle_events.append({
            "event": event_name,
            "meta": meta or {},
            "timestamp": time.time()
        })
        logger.info(f"[Observability] Lifecycle Event: {event_name}")

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        avg_latency = (
            sum(cls._command_latencies) / len(cls._command_latencies)
            if cls._command_latencies else 0.0
        )
        return {
            "total_commands": cls._total_commands,
            "successful_commands": cls._successful_commands,
            "failed_commands": cls._failed_commands,
            "average_latency_ms": round(avg_latency, 2),
            "recent_events": cls._recent_events[:10],
            "lifecycle_events": cls._lifecycle_events[-5:],
        }
