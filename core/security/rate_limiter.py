"""
Sentinel™ Centralized Rate-Limit Aware Execution & Coordination Manager.

Provides:
- Route-aware and global rate-limit detection and backoff with real `retry_after`.
- Bounded exponential retries with jitter for transient errors (429, 500, 502, 503, 504).
- Safe, non-retried handling for permanent/permission errors (403, 404, 400).
- Controlled asynchronous bulk action queue for multi-channel and multi-role operations.
- Per-guild coordination locks to prevent race conditions during containment and recovery.
- Configurable manual, automatic, and recovery lockdown cooldowns.
"""

from __future__ import annotations

import asyncio
import inspect
import random
import time
from typing import Dict, Any, List, Optional, Callable, Awaitable, TypeVar, Tuple
from dataclasses import dataclass, field

import discord

from core.logging.logger import logger
from database.database import database

T = TypeVar("T")


@dataclass
class RateLimitState:
    route_key: str
    reset_at: float = 0.0
    is_global: bool = False
    in_flight_count: int = 0
    max_concurrency: int = 3


class SentinelRateLimiter:
    """
    Centralized rate-limit coordination service for Sentinel security actions.
    Ensures the bot stays responsive to gateway events and avoids API route saturation.
    """
    _instance: Optional["SentinelRateLimiter"] = None

    @classmethod
    def get_instance(cls) -> "SentinelRateLimiter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        # Route keys (e.g. "roles:{guild_id}", "channels:{guild_id}") -> RateLimitState
        self._routes: Dict[str, RateLimitState] = {}
        self._global_reset_at: float = 0.0
        
        # Per-guild concurrency locks
        self._guild_locks: Dict[str, asyncio.Lock] = {}
        
        # Lockdown cooldown timestamps: cooldown_key -> expires_at
        self._cooldowns: Dict[str, float] = {}
        
        # Bulk action queues per guild
        self._bulk_semaphores: Dict[str, asyncio.Semaphore] = {}

    def get_guild_lock(self, guild_id: str | int) -> asyncio.Lock:
        """Returns the synchronized per-guild lock to prevent concurrent containment mutations."""
        gid = str(guild_id)
        if gid not in self._guild_locks:
            self._guild_locks[gid] = asyncio.Lock()
        return self._guild_locks[gid]

    def _get_bulk_semaphore(self, guild_id: str | int, max_concurrent: int = 3) -> asyncio.Semaphore:
        gid = str(guild_id)
        if gid not in self._bulk_semaphores:
            self._bulk_semaphores[gid] = asyncio.Semaphore(max_concurrent)
        return self._bulk_semaphores[gid]

    def _extract_retry_after(self, error: Exception) -> Optional[float]:
        """Safely extracts real retry_after value from Discord exceptions or HTTP responses."""
        if hasattr(error, "retry_after"):
            val = getattr(error, "retry_after")
            if isinstance(val, (int, float)) and val > 0:
                return float(val)

        # Inspect response if present
        resp = getattr(error, "response", None)
        if resp and hasattr(resp, "headers"):
            headers = getattr(resp, "headers", {})
            retry_header = headers.get("Retry-After") or headers.get("X-RateLimit-Reset-After")
            if retry_header:
                try:
                    return float(retry_header)
                except (ValueError, TypeError):
                    pass

        # Parse from string message if explicitly stated (e.g. "retry_after: 2.5")
        err_msg = str(error)
        import re
        m = re.search(r"retry(?:_after|\s+after)[:=\s]+([0-9.]+)", err_msg, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

        return None

    def is_route_rate_limited(self, route_key: str) -> Tuple[bool, float]:
        """Checks if a route or global rate limit is currently active."""
        now = time.time()
        if self._global_reset_at > now:
            return True, self._global_reset_at - now

        state = self._routes.get(route_key)
        if state and state.reset_at > now:
            return True, state.reset_at - now

        return False, 0.0

    async def wait_for_route(self, route_key: str) -> None:
        """Asynchronously waits until the route is clear of active rate limits."""
        limited, wait_sec = self.is_route_rate_limited(route_key)
        if limited and wait_sec > 0:
            logger.warning(f"[RateLimiter] Route '{route_key}' is rate-limited; waiting {wait_sec:.2f}s")
            await asyncio.sleep(min(wait_sec, 60.0))

    async def execute_safe_api_call(
        self,
        func: Callable[[], Awaitable[T]],
        route_key: str,
        is_idempotent: bool = True,
        max_retries: int = 3,
        description: str = "Discord API Operation",
    ) -> T:
        """
        Executes an asynchronous Discord API operation respecting rate limits,
        bounded retries with exponential backoff and jitter for 429/5xx, and no blind retries on 403.
        """
        attempt = 0
        while True:
            attempt += 1
            await self.wait_for_route(route_key)

            try:
                # Yield control briefly to ensure gateway message dispatching is never starved
                await asyncio.sleep(0.01)
                res = func()
                if inspect.isawaitable(res):
                    return await res
                return res

            except Exception as err:
                status_code = getattr(err, "status", None)
                is_rate_limit = (status_code == 429) or ("rate limit" in str(err).lower())
                retry_after = self._extract_retry_after(err)

                # 1. HTTP 429 Rate Limit Handling
                if is_rate_limit or retry_after is not None:
                    backoff = retry_after if retry_after is not None else min(30.0, (2.0 ** attempt) + random.uniform(0.1, 0.5))
                    is_glob = getattr(err, "is_global", False) or ("global" in str(err).lower())
                    
                    now = time.time()
                    if is_glob:
                        self._global_reset_at = now + backoff
                        logger.warning(f"[RateLimiter] GLOBAL rate limit hit during {description}! Backing off for {backoff:.2f}s")
                    else:
                        if route_key not in self._routes:
                            self._routes[route_key] = RateLimitState(route_key=route_key)
                        self._routes[route_key].reset_at = now + backoff
                        logger.warning(f"[RateLimiter] Route limit on '{route_key}' during {description}! Backing off for {backoff:.2f}s")

                    if attempt <= max_retries:
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        logger.error(f"[RateLimiter] Max retries ({max_retries}) exceeded on 429 for {description}.")
                        raise

                # 2. Permanent / Permission Failures (400, 403 Forbidden, 404 Not Found)
                if status_code in (400, 403, 404) or "missing permissions" in str(err).lower() or "hierarchy" in str(err).lower():
                    logger.debug(f"[RateLimiter] Permanent failure ({status_code}) during {description}; skipping retry: {err}")
                    raise

                # 3. Transient Server Errors (500, 502, 503, 504, connection reset)
                is_transient = (
                    status_code in (500, 502, 503, 504)
                    or isinstance(err, (asyncio.TimeoutError, ConnectionError))
                )
                if is_transient and is_idempotent and attempt <= max_retries:
                    backoff = min(15.0, (1.5 ** attempt) + random.uniform(0.2, 0.8))
                    logger.warning(f"[RateLimiter] Transient error ({err}) during {description}; retrying in {backoff:.2f}s (attempt {attempt}/{max_retries})")
                    await asyncio.sleep(backoff)
                    continue

                # Non-retryable or retries exhausted
                raise

    # --------------------------------------------------------------------------
    # Lockdown Cooldown Policies
    # --------------------------------------------------------------------------
    def check_lockdown_cooldown(
        self,
        guild_id: str | int,
        cooldown_type: str = "manual",
        duration_seconds: float = 600.0,
    ) -> Tuple[bool, float]:
        """
        Checks if a lockdown operation of given type is on cooldown.
        cooldown_type: 'manual', 'auto', or 'recovery'.
        Returns (is_on_cooldown, remaining_seconds).
        """
        gid = str(guild_id)
        key = f"cooldown:{cooldown_type}:{gid}"
        now = time.time()
        expires_at = self._cooldowns.get(key, 0.0)
        if expires_at > now:
            return True, expires_at - now
        return False, 0.0

    def apply_lockdown_cooldown(
        self,
        guild_id: str | int,
        cooldown_type: str = "manual",
        duration_seconds: float = 600.0,
    ) -> None:
        """Applies cooldown for a manual, auto, or recovery lockdown operation."""
        gid = str(guild_id)
        key = f"cooldown:{cooldown_type}:{gid}"
        self._cooldowns[key] = time.time() + float(duration_seconds)


# Global singleton rate limiter
sentinel_rate_limiter = SentinelRateLimiter.get_instance()
