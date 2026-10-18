import { randomUUID } from "crypto";

import DatabaseManager from "@database/Database";
import config from "@config";
import AuditLog from "@core/audit/AuditLog";


DatabaseManager.initialize()
/* =========================================================
 * TYPES
 * ========================================================= */

export interface InventorySettings {
	guildId: string;

	enabled: boolean;

	limits: {
		maxItems: number;
		maxQuantityPerItem: number;
	};

	permissions: {
		manageInventory: string[];
	};

	createdAt: Date;
	updatedAt: Date;
}

export interface InventoryItem {
	_id: string;

	sku: string;
	guildId: string;

	name: string;
	description?: string;
	emoji?: string;

	quantity: number;
	value: number;

	metadata: Record<string, unknown>;

	createdAt: Date;
	updatedAt: Date;
}

interface InventoryCounter {
	guildId: string;
	sequence: number;
}

interface CacheEntry<T> {
	data: T;

	/**
	 * Last time this entry was requested.
	 */
	lastAccess: number;

	/**
	 * Last time this entry was synchronized
	 * with MongoDB.
	 */
	lastSync: number;

	/**
	 * Whether the in-memory value contains
	 * changes which haven't been persisted yet.
	 */
	dirty: boolean;

	/**
	 * Number of times this entry has been requested.
	 *
	 * Used as a secondary priority signal.
	 */
	hits: number;
}

export interface CreateItemData {
	name: string;
	description?: string;
	emoji?: string;

	quantity?: number;
	value?: number;

	metadata?: Record<string, unknown>;
}

export interface UpdateItemData {
	name?: string;
	description?: string;
	emoji?: string;
	value?: number;
	metadata?: Record<string, unknown>;
}

export interface InventoryListOptions {
	limit?: number;
	skip?: number;
	search?: string;
}


/* =========================================================
 * MANAGER
 * ========================================================= */

export default class InventoryManager {
	private static readonly SETTINGS_COLLECTION =
		"inventory_settings";

	private static readonly ITEMS_COLLECTION =
		"inventory_items";

	private static readonly COUNTERS_COLLECTION =
		"inventory_counters";


	/* =========================================================
	 * CACHE
	 * ========================================================= */

	/**
	 * Guild settings cache.
	 *
	 * guildId -> settings
	 */
	private static readonly inventoryCache =
		new Map<string, CacheEntry<InventorySettings>>();


	/**
	 * Item cache.
	 *
	 * guildId -> Map<SKU, cache entry>
	 */
	private static readonly itemCache =
		new Map<
			string,
			Map<string, CacheEntry<InventoryItem>>
		>();


	/**
	 * Prevent multiple simultaneous database requests
	 * for the same guild/item.
	 */
	private static readonly pendingSettings =
		new Map<string, Promise<InventorySettings>>();

	private static readonly pendingItems =
		new Map<string, Promise<InventoryItem | null>>();


	/**
	 * Background synchronization timer.
	 */
	private static syncTimer:
		ReturnType<typeof setInterval> | null = null;


	/**
	 * Prevent overlapping sync operations.
	 */
	private static syncing = false;


	/* =========================================================
	 * CONFIG
	 * ========================================================= */

	private static get settingsCacheSize(): number {
		return Math.max(
			1,
			Number(
				config.setting?.cache?.size?.inventories ?? 100
			)
		);
	}


	private static get itemCacheSize(): number {
		return Math.max(
			1,
			Number(
				config.setting?.cache?.size?.inventory_items ?? 1000
			)
		);
	}


	private static get syncInterval(): number {
		return Math.max(
			1000,
			Number(
				config.settings?.intervals?.caches?.inventory ??
				30_000
			)
		);
	}


	/* =========================================================
	 * START / STOP
	 * ========================================================= */

	/**
	 * Start the inventory cache synchronizer.
	 *
	 * Safe to call multiple times.
	 */
	static start(): void {
		if (this.syncTimer) {
			return;
		}
        console.log(this.syncInterval)

		this.syncTimer = setInterval(
			() => {
				void this.sync();
			},
			this.syncInterval
		);

		/**
		 * Do not keep Node alive only because of the cache.
		 */
		this.syncTimer.unref?.();
	}


	/**
	 * Stop the cache synchronizer.
	 *
	 * Useful during graceful shutdown.
	 */
	static async stop(): Promise<void> {
		if (this.syncTimer) {
			clearInterval(this.syncTimer);
			this.syncTimer = null;
		}

		await this.sync();

		this.inventoryCache.clear();
		this.itemCache.clear();
		this.pendingSettings.clear();
		this.pendingItems.clear();
	}


	/* =========================================================
	 * SETTINGS CACHE
	 * ========================================================= */

	private static touchSettings(
		guildId: string,
		entry: CacheEntry<InventorySettings>
	): void {
		entry.lastAccess = Date.now();
		entry.hits++;

		/**
		 * Map insertion order acts as our LRU order.
		 */
		this.inventoryCache.delete(guildId);
		this.inventoryCache.set(guildId, entry);
	}


	private static evictSettings(): void {
		while (
			this.inventoryCache.size >
			this.settingsCacheSize
		) {
			const entries =
				[...this.inventoryCache.entries()];

			/**
			 * Prefer evicting the least recently used
			 * clean entry.
			 */
			const candidates =
				entries
					.filter(([, entry]) => !entry.dirty)
					.sort(
						(a, b) =>
							a[1].lastAccess -
							b[1].lastAccess
					);

			if (!candidates.length) {
				/**
				 * Everything is dirty.
				 *
				 * Do not silently throw away changes.
				 * Leave the cache temporarily above its
				 * configured size until sync() persists
				 * something.
				 */
				return;
			}

			this.inventoryCache.delete(
				candidates[0][0]
			);
		}
	}


	/**
	 * Get settings from cache.
	 */
	private static getCachedSettings(
		guildId: string
	): InventorySettings | null {
		const entry =
			this.inventoryCache.get(guildId);

		if (!entry) {
			return null;
		}

		this.touchSettings(guildId, entry);

		return entry.data;
	}


	/**
	 * Put settings into cache.
	 */
	private static cacheSettings(
		data: InventorySettings,
		dirty = false
	): InventorySettings {
		const now = Date.now();

		this.inventoryCache.delete(
			data.guildId
		);

		this.inventoryCache.set(
			data.guildId,
			{
				data,
				lastAccess: now,
				lastSync: now,
				dirty,
				hits: 1
			}
		);

		this.evictSettings();

		return data;
	}


	/* =========================================================
	 * ITEM CACHE
	 * ========================================================= */

	private static getGuildItemCache(
		guildId: string,
		create = false
	): Map<string, CacheEntry<InventoryItem>> | null {
		let cache =
			this.itemCache.get(guildId);

		if (!cache && create) {
			cache = new Map();

			this.itemCache.set(
				guildId,
				cache
			);
		}

		return cache ?? null;
	}


	private static touchItem(
		guildId: string,
		sku: string,
		entry: CacheEntry<InventoryItem>
	): void {
		const cache =
			this.getGuildItemCache(
				guildId,
				true
			)!;

		entry.lastAccess = Date.now();
		entry.hits++;

		cache.delete(sku);
		cache.set(sku, entry);
	}


	private static getTotalCachedItems(): number {
		let total = 0;

		for (const cache of this.itemCache.values()) {
			total += cache.size;
		}

		return total;
	}


	private static evictItems(): void {
		while (
			this.getTotalCachedItems() >
			this.itemCacheSize
		) {
			let oldestGuild: string | null = null;
			let oldestSku: string | null = null;
			let oldestEntry:
				CacheEntry<InventoryItem> | null = null;

			for (
				const [guildId, cache]
				of this.itemCache
			) {
				for (
					const [sku, entry]
					of cache
				) {
					if (entry.dirty) {
						continue;
					}

					if (
						!oldestEntry ||
						entry.lastAccess <
						oldestEntry.lastAccess
					) {
						oldestGuild = guildId;
						oldestSku = sku;
						oldestEntry = entry;
					}
				}
			}

			/**
			 * Everything remaining is dirty.
			 */
			if (
				!oldestGuild ||
				!oldestSku
			) {
				return;
			}

			const cache =
				this.itemCache.get(
					oldestGuild
				);

			cache?.delete(oldestSku);

			if (
				cache &&
				cache.size === 0
			) {
				this.itemCache.delete(
					oldestGuild
				);
			}
		}
	}


	private static getCachedItem(
		guildId: string,
		sku: string
	): InventoryItem | null {
		const cache =
			this.getGuildItemCache(
				guildId
			);

		const normalized =
			sku.toUpperCase();

		const entry =
			cache?.get(normalized);

		if (!entry) {
			return null;
		}

		this.touchItem(
			guildId,
			normalized,
			entry
		);

		return entry.data;
	}


	private static cacheItem(
		data: InventoryItem,
		dirty = false
	): InventoryItem {
		const cache =
			this.getGuildItemCache(
				data.guildId,
				true
			)!;

		const now = Date.now();

		cache.delete(data.sku);

		cache.set(
			data.sku,
			{
				data,
				lastAccess: now,
				lastSync: now,
				dirty,
				hits: 1
			}
		);

		this.evictItems();

		return data;
	}


	private static markItemDirty(
		guildId: string,
		sku: string
	): void {
		const cache =
			this.getGuildItemCache(
				guildId
			);

		const entry =
			cache?.get(
				sku.toUpperCase()
			);

		if (entry) {
			entry.dirty = true;
			entry.lastAccess = Date.now();
		}
	}


	/* =========================================================
	 * SETTINGS
	 * ========================================================= */

	static async getSettings(
		guildId: string
	): Promise<InventorySettings | null> {
		const cached =
			this.getCachedSettings(guildId);

		if (cached) {
			return cached;
		}

		const collection =
			await DatabaseManager.collection(
				this.SETTINGS_COLLECTION
			);

		const result =
			await collection.findOne({
				guildId
			}) as InventorySettings | null;

		if (result) {
			this.cacheSettings(result);
		}

		return result;
	}


	static async getOrCreateSettings(
		guildId: string
	): Promise<InventorySettings> {
		const cached =
			this.getCachedSettings(guildId);

		if (cached) {
			return cached;
		}

		/**
		 * Prevent 20 commands arriving at the same time
		 * from causing 20 MongoDB queries.
		 */
		const pending =
			this.pendingSettings.get(guildId);

		if (pending) {
			return pending;
		}

		const promise = (async () => {
			const collection =
				await DatabaseManager.collection(
					this.SETTINGS_COLLECTION
				);

			const now = new Date();

			const result =
				await collection.findOneAndUpdate(
					{
						guildId
					},
					{
						$setOnInsert: {
							guildId,

							enabled: true,

							limits: {
								maxItems: 1000,
								maxQuantityPerItem:
									1_000_000
							},

							permissions: {
								manageInventory: []
							},

							createdAt: now,
							updatedAt: now
						}
					},
					{
						upsert: true,
						returnDocument: "after"
					}
				);

			return this.cacheSettings(
				result as unknown as InventorySettings
			);
		})();

		this.pendingSettings.set(
			guildId,
			promise
		);

		try {
			return await promise;
		} finally {
			this.pendingSettings.delete(
				guildId
			);
		}
	}


	static async updateSettings(
		guildId: string,
		updates: Partial<
			Omit<
				InventorySettings,
				"guildId" |
				"createdAt" |
				"updatedAt"
			>
		>
	): Promise<InventorySettings> {
		const current =
			await this.getOrCreateSettings(
				guildId
			);

		const updated: InventorySettings = {
			...current,
			...updates,
			updatedAt: new Date()
		};

		/**
		 * Update memory immediately.
		 *
		 * Command gets the new data without
		 * waiting for the periodic sync.
		 */
		this.cacheSettings(
			updated,
			true
		);

		void AuditLog.record({
			guildId,
			actorType: "system",
			action: "inventory.settings.updated",
			resourceType: "inventory_settings",
			resourceId: guildId,
			source: "system",
			success: true,
			previousState: current,
			newState: updated,
		});

		return updated;
	}


	static async setEnabled(
		guildId: string,
		enabled: boolean
	): Promise<InventorySettings> {
		return this.updateSettings(
			guildId,
			{
				enabled
			}
		);
	}


	static async resetSettings(
		guildId: string
	): Promise<InventorySettings> {
		const settings: InventorySettings = {
			guildId,

			enabled: true,

			limits: {
				maxItems: 1000,
				maxQuantityPerItem:
					1_000_000
			},

			permissions: {
				manageInventory: []
			},

			createdAt: new Date(),
			updatedAt: new Date()
		};

		this.cacheSettings(
			settings,
			true
		);

		return settings;
	}


	/* =========================================================
	 * SKU
	 * ========================================================= */

	static async generateSKU(
		guildId: string
	): Promise<string> {
		const collection =
			await DatabaseManager.collection(
				this.COUNTERS_COLLECTION
			);

		const result =
			await collection.findOneAndUpdate(
				{
					guildId
				},
				{
					$inc: {
						sequence: 1
					}
				},
				{
					upsert: true,
					returnDocument: "after"
				}
			);

		const counter =
			result as unknown as InventoryCounter;

		return `SKU-${counter.sequence
			.toString()
			.padStart(5, "0")}`;
	}


	/* =========================================================
	 * ITEM GET
	 * ========================================================= */

	static async getItem(
		guildId: string,
		sku: string
	): Promise<InventoryItem | null> {
		const normalized =
			sku.toUpperCase();

		/**
		 * FAST PATH
		 */
		const cached =
			this.getCachedItem(
				guildId,
				normalized
			);

		if (cached) {
			return cached;
		}

		/**
		 * Prevent duplicate database requests.
		 */
		const pendingKey =
			`${guildId}:${normalized}`;

		const pending =
			this.pendingItems.get(
				pendingKey
			);

		if (pending) {
			return pending;
		}

		const promise = (async () => {
			const collection =
				await DatabaseManager.collection(
					this.ITEMS_COLLECTION
				);

			const result =
				await collection.findOne({
					guildId,
					sku: normalized
				}) as InventoryItem | null;

			if (result) {
				this.cacheItem(result);
			}

			return result;
		})();

		this.pendingItems.set(
			pendingKey,
			promise
		);

		try {
			return await promise;
		} finally {
			this.pendingItems.delete(
				pendingKey
			);
		}
	}


	static async getItemById(
		guildId: string,
		id: string
	): Promise<InventoryItem | null> {
		/**
		 * Mongo ID lookup is uncommon enough that
		 * we don't need another cache index.
		 */
		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const result =
			await collection.findOne({
				_id: id,
				guildId
			}) as InventoryItem | null;

		if (result) {
			this.cacheItem(result);
		}

		return result;
	}


	/* =========================================================
	 * CREATE
	 * ========================================================= */

	static async createItem(
		guildId: string,
		data: CreateItemData
	): Promise<InventoryItem> {
		const settings =
			await this.getOrCreateSettings(
				guildId
			);

		if (!data.name?.trim()) {
			throw new Error(
				"Inventory item name is required."
			);
		}

		const quantity =
			data.quantity ?? 0;

		const value =
			data.value ?? 0;

		if (
			!Number.isInteger(quantity) ||
			quantity < 0
		) {
			throw new Error(
				"Quantity must be a non-negative integer."
			);
		}

		if (value < 0) {
			throw new Error(
				"Value cannot be negative."
			);
		}

		if (
			quantity >
			settings.limits.maxQuantityPerItem
		) {
			throw new Error(
				`Maximum quantity is ${settings.limits.maxQuantityPerItem}.`
			);
		}

		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const count =
			await collection.countDocuments({
				guildId
			});

		if (
			count >= settings.limits.maxItems
		) {
			throw new Error(
				`Maximum inventory items reached (${settings.limits.maxItems}).`
			);
		}

		const sku =
			await this.generateSKU(guildId);

		const now = new Date();

		const item: InventoryItem = {
			_id: randomUUID(),

			sku,
			guildId,

			name: data.name.trim(),
			description:
				data.description?.trim(),
			emoji: data.emoji,

			quantity,
			value,

			metadata:
				data.metadata ?? {},

			createdAt: now,
			updatedAt: now
		};

		await collection.insertOne(item);

		/**
		 * Immediately put the newly-created item into
		 * the hot cache.
		 */
		this.cacheItem(item);

		return item;
	}


	/* =========================================================
	 * UPDATE ITEM
	 * ========================================================= */

	static async updateItem(
		guildId: string,
		sku: string,
		updates: UpdateItemData
	): Promise<InventoryItem | null> {
        console.log(guildId, sku, updates)
		const item =
			await this.getItem(
				guildId,
				sku
			);

		if (!item) {
			return null;
		}

		if (
			updates.name !== undefined &&
			!updates.name.trim()
		) {
			throw new Error(
				"Item name cannot be empty."
			);
		}

		if (
			updates.value !== undefined &&
			updates.value < 0
		) {
			throw new Error(
				"Value cannot be negative."
			);
		}

		const updated: InventoryItem = {
			...item,

			...(updates.name !== undefined
				? {
					name: updates.name.trim()
				}
				: {}),

			...(updates.description !== undefined
				? {
					description:
						updates.description.trim()
				}
				: {}),

			...(updates.emoji !== undefined
				? {
					emoji: updates.emoji
				}
				: {}),

			...(updates.value !== undefined
				? {
					value: updates.value
				}
				: {}),

			...(updates.metadata !== undefined
				? {
					metadata: updates.metadata
				}
				: {}),

			updatedAt: new Date()
		};

		/**
		 * Memory first.
		 */
		this.cacheItem(
			updated,
			true
		);

        
		return updated;
	}


	/* =========================================================
	 * DELETE
	 * ========================================================= */

	static async deleteItem(
		guildId: string,
		sku: string
	): Promise<boolean> {
		const normalized =
			sku.toUpperCase();

		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const result =
			await collection.deleteOne({
				guildId,
				sku: normalized
			});

		if (result.deletedCount) {
			const cache =
				this.getGuildItemCache(
					guildId
				);

			cache?.delete(normalized);

			if (
				cache &&
				cache.size === 0
			) {
				this.itemCache.delete(
					guildId
				);
			}
		}

		return result.deletedCount === 1;
	}


	/* =========================================================
	 * QUANTITY
	 * ========================================================= */

	static async addQuantity(
		guildId: string,
		sku: string,
		amount: number
	): Promise<InventoryItem | null> {
		if (
			!Number.isInteger(amount) ||
			amount <= 0
		) {
			throw new Error(
				"Amount must be a positive integer."
			);
		}

		const item =
			await this.getItem(
				guildId,
				sku
			);

		if (!item) {
			return null;
		}

		const settings =
			await this.getOrCreateSettings(
				guildId
			);

		const newQuantity =
			item.quantity + amount;

		if (
			newQuantity >
			settings.limits.maxQuantityPerItem
		) {
			throw new Error(
				`Maximum quantity is ${settings.limits.maxQuantityPerItem}.`
			);
		}

		const updated: InventoryItem = {
			...item,

			quantity: newQuantity,

			updatedAt: new Date()
		};

		this.cacheItem(
			updated,
			true
		);

		return updated;
	}


	static async removeQuantity(
		guildId: string,
		sku: string,
		amount: number
	): Promise<InventoryItem | null> {
		if (
			!Number.isInteger(amount) ||
			amount <= 0
		) {
			throw new Error(
				"Amount must be a positive integer."
			);
		}

		const item =
			await this.getItem(
				guildId,
				sku
			);

		if (!item) {
			return null;
		}

		if (
			item.quantity < amount
		) {
			throw new Error(
				"Not enough inventory quantity."
			);
		}

		const updated: InventoryItem = {
			...item,

			quantity:
				item.quantity - amount,

			updatedAt: new Date()
		};

		this.cacheItem(
			updated,
			true
		);

		return updated;
	}


	static async setQuantity(
		guildId: string,
		sku: string,
		quantity: number
	): Promise<InventoryItem | null> {
		if (
			!Number.isInteger(quantity) ||
			quantity < 0
		) {
			throw new Error(
				"Quantity must be a non-negative integer."
			);
		}

		const settings =
			await this.getOrCreateSettings(
				guildId
			);

		if (
			quantity >
			settings.limits.maxQuantityPerItem
		) {
			throw new Error(
				`Maximum quantity is ${settings.limits.maxQuantityPerItem}.`
			);
		}

		const item =
			await this.getItem(
				guildId,
				sku
			);

		if (!item) {
			return null;
		}

		const updated: InventoryItem = {
			...item,

			quantity,

			updatedAt: new Date()
		};

		this.cacheItem(
			updated,
			true
		);

		return updated;
	}


	/* =========================================================
	 * LIST ITEMS
	 * ========================================================= */

	static async getItems(
		guildId: string,
		options: InventoryListOptions = {}
	): Promise<InventoryItem[]> {
		const limit =
			Math.min(
				Math.max(
					options.limit ?? 25,
					1
				),
				100
			);

		const skip =
			Math.max(
				options.skip ?? 0,
				0
			);

		const cache =
			this.getGuildItemCache(
				guildId
			);

		/**
		 * If we already have enough cached items and
		 * there is no search, serve entirely from memory.
		 */
		if (
			cache &&
			!options.search &&
			cache.size >=
				skip + limit
		) {
			const items =
				[...cache.values()]
					.sort(
						(a, b) =>
							a.data.sku.localeCompare(
								b.data.sku
							)
					)
					.slice(
						skip,
						skip + limit
					)
					.map(
						entry => {
							this.touchItem(
								guildId,
								entry.data.sku,
								entry
							);

							return entry.data;
						}
					);

			return items;
		}

		/**
		 * Cache miss / insufficient cache.
		 *
		 * Load from MongoDB.
		 */
		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const filter: Record<string, unknown> = {
			guildId
		};

		if (options.search?.trim()) {
			const search =
				options.search.trim();

			filter.$or = [
				{
					sku: {
						$regex: search,
						$options: "i"
					}
				},
				{
					name: {
						$regex: search,
						$options: "i"
					}
				}
			];
		}

		const items =
			await collection
				.find(filter)
				.sort({
					sku: 1
				})
				.skip(skip)
				.limit(limit)
				.toArray() as unknown as InventoryItem[];

		for (const item of items) {
			this.cacheItem(item);
		}

		return items;
	}


	static async countItems(
		guildId: string
	): Promise<number> {
		const cache =
			this.getGuildItemCache(
				guildId
			);

		/**
		 * Don't use cache size as count because the cache
		 * is intentionally bounded.
		 */
		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		return collection.countDocuments({
			guildId
		});
	}


	/* =========================================================
	 * SERVER CLONING
	 * ========================================================= */

	static async cloneSettings(
		sourceGuildId: string,
		targetGuildId: string
	): Promise<InventorySettings> {
		if (
			sourceGuildId === targetGuildId
		) {
			throw new Error(
				"Source and target guild cannot be the same."
			);
		}

		const source =
			await this.getSettings(
				sourceGuildId
			);

		if (!source) {
			throw new Error(
				"Source guild has no inventory settings."
			);
		}

		const now = new Date();

		const cloned: InventorySettings = {
			...structuredClone(source),

			guildId: targetGuildId,

			createdAt: now,
			updatedAt: now
		};

		/**
		 * Cache target immediately.
		 *
		 * It is marked dirty, so the periodic worker
		 * persists it.
		 */
		this.cacheSettings(
			cloned,
			true
		);

		return cloned;
	}


	static async cloneItems(
		sourceGuildId: string,
		targetGuildId: string
	): Promise<InventoryItem[]> {
		if (
			sourceGuildId === targetGuildId
		) {
			throw new Error(
				"Source and target guild cannot be the same."
			);
		}

		const sourceCollection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const sourceItems =
			await sourceCollection
				.find({
					guildId: sourceGuildId
				})
				.sort({
					sku: 1
				})
				.toArray() as unknown as InventoryItem[];

		if (!sourceItems.length) {
			return [];
		}

		const settings =
			await this.getOrCreateSettings(
				targetGuildId
			);

		const existing =
			await sourceCollection.countDocuments({
				guildId: targetGuildId
			});

		if (
			existing + sourceItems.length >
			settings.limits.maxItems
		) {
			throw new Error(
				"Cloning these items would exceed the target inventory limit."
			);
		}

		const cloned: InventoryItem[] = [];

		for (const source of sourceItems) {
			const sku =
				await this.generateSKU(
					targetGuildId
				);

			const now = new Date();

			const item: InventoryItem = {
				...structuredClone(source),

				_id: randomUUID(),

				sku,

				guildId: targetGuildId,

				/**
				 * Do not clone stock.
				 */
				quantity: 0,

				createdAt: now,
				updatedAt: now
			};

			this.cacheItem(
				item,
				true
			);

			cloned.push(item);
		}

		return cloned;
	}


	static async cloneServer(
		sourceGuildId: string,
		targetGuildId: string,
		options: {
			settings?: boolean;
			items?: boolean;
		} = {}
	): Promise<{
		settings?: InventorySettings;
		items: InventoryItem[];
	}> {
		if (
			sourceGuildId === targetGuildId
		) {
			throw new Error(
				"Source and target guild cannot be the same."
			);
		}

		const result: {
			settings?: InventorySettings;
			items: InventoryItem[];
		} = {
			items: []
		};

		if (options.settings ?? true) {
			result.settings =
				await this.cloneSettings(
					sourceGuildId,
					targetGuildId
				);
		}

		if (options.items ?? true) {
			result.items =
				await this.cloneItems(
					sourceGuildId,
					targetGuildId
				);
		}

		return result;
	}


	/* =========================================================
	 * CACHE SYNCHRONIZATION
	 * ========================================================= */

	/**
	 * Persist dirty settings/items and refresh clean
	 * cached entries.
	 *
	 * Important:
	 * Commands always get the in-memory value immediately.
	 * MongoDB synchronization happens independently.
	 */
	static async sync(): Promise<void> {
		if (this.syncing) {
			return;
		}

		this.syncing = true;

		try {
			await this.syncSettings();
			await this.syncItems();
		} finally {
			this.syncing = false;
		}
	}


	private static async syncSettings(): Promise<void> {
		const collection =
			await DatabaseManager.collection(
				this.SETTINGS_COLLECTION
			);

		const now = Date.now();

		for (
			const [guildId, entry]
			of this.inventoryCache
		) {
			/**
			 * Dirty = write memory → MongoDB.
			 */
			if (entry.dirty) {
				await collection.replaceOne(
					{
						guildId
					},
					entry.data,
					{
						upsert: true
					}
				);

				entry.dirty = false;
				entry.lastSync = now;

				continue;
			}

			/**
			 * Clean = refresh MongoDB → memory.
			 *
			 * This allows external changes to eventually
			 * reach the cache.
			 */
			if (
				now - entry.lastSync <
				this.syncInterval
			) {
				continue;
			}

			const fresh =
				await collection.findOne({
					guildId
				}) as InventorySettings | null;

			if (!fresh) {
				continue;
			}

			/**
			 * Preserve current cache priority.
			 */
			entry.data = fresh;
			entry.lastSync = now;
		}

		this.evictSettings();
	}


	private static async syncItems(): Promise<void> {
		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const now = Date.now();

		for (
			const [guildId, cache]
			of this.itemCache
		) {
			for (
				const [sku, entry]
				of cache
			) {
				/**
				 * Dirty = memory → MongoDB.
				 */
				if (entry.dirty) {
					await collection.replaceOne(
						{
							guildId,
							sku
						},
						entry.data,
						{
							upsert: true
						}
					);

					entry.dirty = false;
					entry.lastSync = now;

					continue;
				}

				/**
				 * Clean = periodically refresh.
				 */
				if (
					now - entry.lastSync <
					this.syncInterval
				) {
					continue;
				}

				const fresh =
					await collection.findOne({
						guildId,
						sku
					}) as InventoryItem | null;

				if (!fresh) {
					cache.delete(sku);
					continue;
				}

				entry.data = fresh;
				entry.lastSync = now;
			}

			if (cache.size === 0) {
				this.itemCache.delete(
					guildId
				);
			}
		}

		this.evictItems();
	}


	/* =========================================================
	 * CACHE MANAGEMENT
	 * ========================================================= */

	/**
	 * Force a specific item to be refreshed from MongoDB.
	 */
	static async refreshItem(
		guildId: string,
		sku: string
	): Promise<InventoryItem | null> {
		const normalized =
			sku.toUpperCase();

		const collection =
			await DatabaseManager.collection(
				this.ITEMS_COLLECTION
			);

		const item =
			await collection.findOne({
				guildId,
				sku: normalized
			}) as InventoryItem | null;

		if (item) {
			this.cacheItem(item);
		}

		return item;
	}


	/**
	 * Force guild settings to refresh.
	 */
	static async refreshSettings(
		guildId: string
	): Promise<InventorySettings | null> {
		const collection =
			await DatabaseManager.collection(
				this.SETTINGS_COLLECTION
			);

		const settings =
			await collection.findOne({
				guildId
			}) as InventorySettings | null;

		if (settings) {
			this.cacheSettings(settings);
		}

		return settings;
	}


	/**
	 * Remove a guild from memory.
	 *
	 * Does NOT delete database data.
	 */
	static invalidateGuild(
		guildId: string
	): void {
		this.inventoryCache.delete(
			guildId
		);

		this.itemCache.delete(
			guildId
		);
	}


	/**
	 * Remove one item from memory.
	 */
	static invalidateItem(
		guildId: string,
		sku: string
	): void {
		const cache =
			this.getGuildItemCache(
				guildId
			);

		cache?.delete(
			sku.toUpperCase()
		);

		if (
			cache &&
			cache.size === 0
		) {
			this.itemCache.delete(
				guildId
			);
		}
	}


	/**
	 * Useful for debugging.
	 */
	static getCacheStats() {
		let itemCount = 0;

		for (const cache of this.itemCache.values()) {
			itemCount += cache.size;
		}

		return {
			settings: {
				cached: this.inventoryCache.size,
				max: this.settingsCacheSize
			},

			items: {
				cached: itemCount,
				max: this.itemCacheSize
			},

			interval: this.syncInterval,

			running:
				this.syncTimer !== null
		};
	}
}

InventoryManager.start()
