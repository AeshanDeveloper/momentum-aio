import config from "@config";
import logger from "@logger";

export interface CacheEntry<T> {
	value: T;
	expiresAt: number; // timestamp in ms
	updatedAt: number;
}

export class TTLCache<K, V> {
	private readonly store = new Map<K, CacheEntry<V>>();
	private readonly defaultTTL: number;
	private cleanupTimer: NodeJS.Timeout | null = null;
	private syncTimer: NodeJS.Timeout | null = null;
	private syncInProgress = false;

	constructor(defaultTTLMs?: number, cleanupIntervalMs?: number) {
		this.defaultTTL = defaultTTLMs ?? config.settings?.intervals?.cache_ttl ?? 60_000;
		const cleanup = cleanupIntervalMs ?? this.defaultTTL;

		this.cleanupTimer = setInterval(() => {
			this.pruneExpired();
		}, cleanup);
		if (this.cleanupTimer.unref) this.cleanupTimer.unref();
	}

	public get(key: K): V | undefined {
		const entry = this.store.get(key);
		if (!entry) return undefined;

		if (entry.expiresAt > 0 && entry.expiresAt <= Date.now()) {
			this.store.delete(key);
			return undefined;
		}

		return entry.value;
	}

	public set(key: K, value: V, ttlMs?: number): void {
		const ttl = ttlMs !== undefined ? ttlMs : this.defaultTTL;
		const now = Date.now();
		this.store.set(key, {
			value,
			expiresAt: ttl > 0 ? now + ttl : 0,
			updatedAt: now,
		});
	}

	public has(key: K): boolean {
		return this.get(key) !== undefined;
	}

	public delete(key: K): boolean {
		return this.store.delete(key);
	}

	public clear(): void {
		this.store.clear();
	}

	public size(): number {
		this.pruneExpired();
		return this.store.size;
	}

	public entries(): [K, V][] {
		this.pruneExpired();
		const result: [K, V][] = [];
		for (const [k, entry] of this.store.entries()) {
			result.push([k, entry.value]);
		}
		return result;
	}

	public values(): V[] {
		this.pruneExpired();
		return Array.from(this.store.values()).map((e) => e.value);
	}

	/**
	 * First-party cache retriever: returns immediately if present and unexpired;
	 * otherwise fetches from the provider, caches it, and returns the fresh value.
	 */
	public async getOrFetch(
		key: K,
		fetcher: () => Promise<V>,
		ttlMs?: number
	): Promise<V> {
		const cached = this.get(key);
		if (cached !== undefined) {
			return cached;
		}

		const fresh = await fetcher();
		this.set(key, fresh, ttlMs);
		return fresh;
	}

	/**
	 * Registers an automated background interval sync that regularly updates
	 * the cache without blocking caller lookups.
	 */
	public registerIntervalSync(
		intervalMs: number,
		syncFn: (cache: TTLCache<K, V>) => Promise<void>
	): void {
		if (this.syncTimer) {
			clearInterval(this.syncTimer);
			this.syncTimer = null;
		}

		this.syncTimer = setInterval(async () => {
			if (this.syncInProgress) return;
			this.syncInProgress = true;
			try {
				await syncFn(this);
			} catch (err) {
				logger.error("[TTLCache] Background sync failed:", err);
			} finally {
				this.syncInProgress = false;
			}
		}, intervalMs);

		if (this.syncTimer.unref) this.syncTimer.unref();
	}

	public pruneExpired(): void {
		const now = Date.now();
		for (const [key, entry] of this.store.entries()) {
			if (entry.expiresAt > 0 && entry.expiresAt <= now) {
				this.store.delete(key);
			}
		}
	}

	public destroy(): void {
		if (this.cleanupTimer) {
			clearInterval(this.cleanupTimer);
			this.cleanupTimer = null;
		}
		if (this.syncTimer) {
			clearInterval(this.syncTimer);
			this.syncTimer = null;
		}
		this.store.clear();
	}
}
