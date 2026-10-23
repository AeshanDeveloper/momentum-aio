import time
import asyncio
from typing import TypeVar, Generic, Dict, Optional, Callable, Awaitable, List, Tuple
from dataclasses import dataclass

K = TypeVar("K")
V = TypeVar("V")

@dataclass
class CacheEntry(Generic[V]):
    value: V
    expires_at: float  # timestamp in seconds, 0 = permanent
    updated_at: float

class TTLCache(Generic[K, V]):
    """
    Production-grade in-memory TTL Cache matching TypeScript TTLCache implementation.
    Includes automated lazy expiration, explicit pruning, and background interval synchronization.
    """
    def __init__(self, default_ttl_ms: int = 60_000, cleanup_interval_ms: Optional[int] = None):
        self._store: Dict[K, CacheEntry[V]] = {}
        self.default_ttl = default_ttl_ms / 1000.0
        self.cleanup_interval = (cleanup_interval_ms / 1000.0) if cleanup_interval_ms else self.default_ttl
        self._cleanup_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None
        self._sync_in_progress = False

    def get(self, key: K) -> Optional[V]:
        entry = self._store.get(key)
        if entry is None:
            return None

        if 0 < entry.expires_at <= time.time():
            del self._store[key]
            return None

        return entry.value

    def set(self, key: K, value: V, ttl_ms: Optional[int] = None) -> None:
        ttl = (ttl_ms / 1000.0) if ttl_ms is not None else self.default_ttl
        now = time.time()
        expires_at = (now + ttl) if ttl > 0 else 0
        self._store[key] = CacheEntry(
            value=value,
            expires_at=expires_at,
            updated_at=now
        )

    def has(self, key: K) -> bool:
        return self.get(key) is not None

    def delete(self, key: K) -> bool:
        if key in self._store:
            del self._store[key]
            return True
        return False

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        self.prune_expired()
        return len(self._store)

    def entries(self) -> List[Tuple[K, V]]:
        self.prune_expired()
        return [(k, entry.value) for k, entry in self._store.items()]

    def values(self) -> List[V]:
        self.prune_expired()
        return [entry.value for entry in self._store.values()]

    async def get_or_fetch(
        self,
        key: K,
        fetcher: Callable[[], Awaitable[V]],
        ttl_ms: Optional[int] = None
    ) -> V:
        cached = self.get(key)
        if cached is not None:
            return cached

        fresh = await fetcher()
        self.set(key, fresh, ttl_ms)
        return fresh

    def prune_expired(self) -> int:
        now = time.time()
        to_delete = [k for k, entry in self._store.items() if 0 < entry.expires_at <= now]
        for k in to_delete:
            del self._store[k]
        return len(to_delete)

    def start_cleanup_loop(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._run_cleanup_loop())

    async def _run_cleanup_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.cleanup_interval)
                self.prune_expired()
        except asyncio.CancelledError:
            pass

    def register_interval_sync(
        self,
        interval_ms: int,
        sync_fn: Callable[["TTLCache[K, V]"], Awaitable[None]]
    ) -> None:
        if self._sync_task:
            self._sync_task.cancel()

        interval_sec = interval_ms / 1000.0

        async def _sync_loop():
            try:
                while True:
                    await asyncio.sleep(interval_sec)
                    if self._sync_in_progress:
                        continue
                    self._sync_in_progress = True
                    try:
                        await sync_fn(self)
                    except Exception as err:
                        print(f"[TTLCache] Background sync failed: {err}")
                    finally:
                        self._sync_in_progress = False
            except asyncio.CancelledError:
                pass

        self._sync_task = asyncio.create_task(_sync_loop())

    def destroy(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
        self._store.clear()
