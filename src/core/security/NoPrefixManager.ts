import DatabaseManager from "@database/Database";
import logger from "@logger";
import config from "@config";
import AuditLog from "@core/audit/AuditLog";
import { parseDuration } from "./BlacklistManager";

export interface NoPrefixEntry {
	_id?: string;
	userId: string;
	addedBy: string;
	expiresAt: Date | null; // null = permanent
	createdAt: Date;
	updatedAt: Date;
}

export class NoPrefixManager {
	private static readonly COLLECTION = "no_prefix_users";
	private static cache = new Map<string, NoPrefixEntry>();
	private static initialized = false;
	private static syncTimer: NodeJS.Timeout | null = null;

	public static async init(): Promise<void> {
		if (this.initialized) return;
		this.initialized = true;
		await this.syncCache();

		const interval = config.settings?.intervals?.no_prefix_cache_sync || config.settings?.intervals?.blacklist_cache_sync || 60_000;
		this.syncTimer = setInterval(() => {
			void this.syncCache();
		}, interval);
		if (this.syncTimer.unref) this.syncTimer.unref();
	}

	public static async syncCache(): Promise<void> {
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const now = Date.now();
			const docs = (await col.find({}).toArray()) as NoPrefixEntry[];

			const newCache = new Map<string, NoPrefixEntry>();
			for (const doc of docs) {
				if (doc.expiresAt) {
					const expMs = new Date(doc.expiresAt).getTime();
					if (!Number.isNaN(expMs) && expMs <= now) {
						void col.deleteOne({ userId: doc.userId }).catch(() => null);
						continue;
					}
				}
				newCache.set(doc.userId, doc);
			}

			// Preserve existing unexpired cache items and re-sync to DB if missing
			for (const [uid, item] of this.cache.entries()) {
				if (!newCache.has(uid)) {
					const expMs = item.expiresAt ? new Date(item.expiresAt).getTime() : null;
					if (!expMs || (!Number.isNaN(expMs) && expMs > now)) {
						newCache.set(uid, item);
						void col.updateOne({ userId: uid }, { $set: item }, { upsert: true }).catch(() => null);
					}
				}
			}

			this.cache = newCache;
		} catch (error) {
			logger.error("[NoPrefixManager] Failed to sync cache from database:", error);
		}
	}

	public static async hasNoPrefix(userId: string): Promise<boolean> {
		if (!this.initialized) await this.init();

		let entry = this.cache.get(userId);
		if (!entry) {
			try {
				const col = await DatabaseManager.collection(this.COLLECTION);
				const doc = (await col.findOne({ userId })) as NoPrefixEntry | null;
				if (doc) {
					if (doc.expiresAt) {
						const expMs = new Date(doc.expiresAt).getTime();
						if (!Number.isNaN(expMs) && expMs <= Date.now()) {
							void col.deleteOne({ userId }).catch(() => null);
							return false;
						}
					}
					this.cache.set(userId, doc);
					entry = doc;
				} else {
					return false;
				}
			} catch {
				return false;
			}
		}

		if (entry.expiresAt) {
			const expMs = new Date(entry.expiresAt).getTime();
			if (!Number.isNaN(expMs) && expMs <= Date.now()) {
				this.cache.delete(userId);
				const col = await DatabaseManager.collection(this.COLLECTION);
				await col.deleteOne({ userId }).catch(() => null);
				return false;
			}
		}

		return true;
	}

	public static async add(
		userId: string,
		durationStr: string | null,
		addedBy: string
	): Promise<{ success: boolean; entry?: NoPrefixEntry; error?: string }> {
		if (!this.initialized) await this.init();

		const expiresAt = parseDuration(durationStr);
		const now = new Date();
		const entry: NoPrefixEntry = {
			userId,
			addedBy,
			expiresAt,
			createdAt: now,
			updatedAt: now,
		};

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.updateOne(
				{ userId },
				{ $set: entry },
				{ upsert: true }
			);

			this.cache.set(userId, entry);
			logger.info(`[NoPrefixManager] User ${userId} granted no-prefix by ${addedBy} (Expires: ${expiresAt?.toISOString() || "Permanent"})`);

			void AuditLog.record({
				actorType: "discord",
				source: "discord",
				action: "security.noprefix.add",
				resourceType: "user",
				resourceId: userId,
				actorId: addedBy,
				success: true,
				newState: { userId, expiresAt: expiresAt?.toISOString() || null },
			}).catch(() => null);

			return { success: true, entry };
		} catch (error: any) {
			logger.error(`[NoPrefixManager] Failed to add user ${userId}:`, error);
			return { success: false, error: error?.message || "Database error" };
		}
	}

	public static async remove(
		userId: string,
		removedBy: string
	): Promise<{ success: boolean; error?: string }> {
		if (!this.initialized) await this.init();

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.deleteOne({ userId });
			this.cache.delete(userId);
			logger.info(`[NoPrefixManager] User ${userId} revoked no-prefix by ${removedBy}`);

			void AuditLog.record({
				actorType: "discord",
				source: "discord",
				action: "security.noprefix.remove",
				resourceType: "user",
				resourceId: userId,
				actorId: removedBy,
				success: true,
			}).catch(() => null);

			return { success: true };
		} catch (error: any) {
			logger.error(`[NoPrefixManager] Failed to remove user ${userId}:`, error);
			return { success: false, error: error?.message || "Database error" };
		}
	}

	public static async list(): Promise<NoPrefixEntry[]> {
		if (!this.initialized) await this.init();
		await this.syncCache();
		return Array.from(this.cache.values());
	}
}
