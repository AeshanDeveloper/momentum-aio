import DatabaseManager from "@database/Database";
import logger from "@logger";
import config from "@config";
import AuditLog from "@core/audit/AuditLog";
import { MessageFlags, SeparatorSpacingSize } from "discord.js";
import { ContainerBuilder } from "@sdk/discord";
import { isBotOwner, isBlacklistExcluded, parseDuration } from "./SecurityHelpers";
export { parseDuration };

export interface BlacklistEntry {
	_id?: string;
	targetId: string;
	type: "user" | "guild";
	reason: string;
	adminId: string;
	expiresAt: Date | null; // null = permanent
	createdAt: Date;
	updatedAt: Date;
}

export class BlacklistManager {
	private static readonly COLLECTION = "global_blacklists";
	private static userCache = new Map<string, BlacklistEntry>();
	private static guildCache = new Map<string, BlacklistEntry>();
	private static initialized = false;
	private static syncTimer: NodeJS.Timeout | null = null;

	public static async init(): Promise<void> {
		if (this.initialized) return;
		this.initialized = true;
		await this.syncCache();

		const interval = config.settings?.intervals?.blacklist_cache_sync || 60_000;
		this.syncTimer = setInterval(() => {
			void this.syncCache();
		}, interval);
		if (this.syncTimer.unref) this.syncTimer.unref();
	}

	public static async syncCache(): Promise<void> {
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const now = Date.now();
			const docs = (await col.find({}).toArray()) as BlacklistEntry[];

			const newUserCache = new Map<string, BlacklistEntry>();
			const newGuildCache = new Map<string, BlacklistEntry>();

			for (const doc of docs) {
				if (doc.expiresAt) {
					const expMs = new Date(doc.expiresAt).getTime();
					if (!Number.isNaN(expMs) && expMs <= now) {
						// Auto-expire in database
						void col.deleteOne({ targetId: doc.targetId, type: doc.type }).catch(() => null);
						continue;
					}
				}

				if (doc.type === "user") {
					newUserCache.set(doc.targetId, doc);
				} else if (doc.type === "guild") {
					newGuildCache.set(doc.targetId, doc);
				}
			}

			// Merge existing active cache to prevent accidental wipes
			for (const [uid, item] of this.userCache.entries()) {
				if (!newUserCache.has(uid)) {
					const expMs = item.expiresAt ? new Date(item.expiresAt).getTime() : null;
					if (!expMs || (!Number.isNaN(expMs) && expMs > now)) {
						newUserCache.set(uid, item);
						void col.updateOne({ targetId: uid, type: "user" }, { $set: item }, { upsert: true }).catch(() => null);
					}
				}
			}

			for (const [gid, item] of this.guildCache.entries()) {
				if (!newGuildCache.has(gid)) {
					const expMs = item.expiresAt ? new Date(item.expiresAt).getTime() : null;
					if (!expMs || (!Number.isNaN(expMs) && expMs > now)) {
						newGuildCache.set(gid, item);
						void col.updateOne({ targetId: gid, type: "guild" }, { $set: item }, { upsert: true }).catch(() => null);
					}
				}
			}

			this.userCache = newUserCache;
			this.guildCache = newGuildCache;
		} catch (error) {
			logger.error("[BlacklistManager] Failed to sync cache from database:", error);
		}
	}

	public static async isUserBlacklisted(
		userId: string
	): Promise<{ blacklisted: boolean; entry?: BlacklistEntry }> {
		if (isBlacklistExcluded(userId)) {
			return { blacklisted: false };
		}
		if (!this.initialized) await this.init();

		let entry = this.userCache.get(userId);
		if (!entry) {
			// First-party retrieval if missing from cache
			try {
				const col = await DatabaseManager.collection(this.COLLECTION);
				const doc = (await col.findOne({ targetId: userId, type: "user" })) as BlacklistEntry | null;
				if (doc) {
					if (doc.expiresAt && new Date(doc.expiresAt).getTime() <= Date.now()) {
						void col.deleteOne({ targetId: userId, type: "user" }).catch(() => null);
						return { blacklisted: false };
					}
					this.userCache.set(userId, doc);
					entry = doc;
				} else {
					return { blacklisted: false };
				}
			} catch {
				return { blacklisted: false };
			}
		}

		if (entry.expiresAt && new Date(entry.expiresAt).getTime() <= Date.now()) {
			this.userCache.delete(userId);
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.deleteOne({ targetId: userId, type: "user" }).catch(() => null);
			return { blacklisted: false };
		}

		return { blacklisted: true, entry };
	}

	public static async isGuildBlacklisted(
		guildId: string
	): Promise<{ blacklisted: boolean; entry?: BlacklistEntry }> {
		if (!this.initialized) await this.init();

		let entry = this.guildCache.get(guildId);
		if (!entry) {
			// First-party retrieval if missing from cache
			try {
				const col = await DatabaseManager.collection(this.COLLECTION);
				const doc = (await col.findOne({ targetId: guildId, type: "guild" })) as BlacklistEntry | null;
				if (doc) {
					if (doc.expiresAt && new Date(doc.expiresAt).getTime() <= Date.now()) {
						void col.deleteOne({ targetId: guildId, type: "guild" }).catch(() => null);
						return { blacklisted: false };
					}
					this.guildCache.set(guildId, doc);
					entry = doc;
				} else {
					return { blacklisted: false };
				}
			} catch {
				return { blacklisted: false };
			}
		}

		if (entry.expiresAt && new Date(entry.expiresAt).getTime() <= Date.now()) {
			this.guildCache.delete(guildId);
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.deleteOne({ targetId: guildId, type: "guild" }).catch(() => null);
			return { blacklisted: false };
		}

		return { blacklisted: true, entry };
	}

	public static async blacklistUser(
		userId: string,
		durationStr: string | null,
		reason: string,
		adminId: string,
		client?: any
	): Promise<{ success: boolean; entry?: BlacklistEntry; error?: string }> {
		if (isBlacklistExcluded(userId)) {
			return { success: false, error: "Cannot blacklist a bot owner or excluded user." };
		}
		if (!this.initialized) await this.init();

		const expiresAt = parseDuration(durationStr);
		const now = new Date();
		const entry: BlacklistEntry = {
			targetId: userId,
			type: "user",
			reason: reason.trim() || "Violating bot terms of service / automated rules",
			adminId,
			expiresAt,
			createdAt: now,
			updatedAt: now,
		};

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.updateOne(
				{ targetId: userId, type: "user" },
				{ $set: entry },
				{ upsert: true }
			);

			this.userCache.set(userId, entry);

			// Direct message the user
			if (client?.users?.fetch) {
				try {
					const user = await client.users.fetch(userId).catch(() => null);
					if (user?.send) {
						const expiryText = expiresAt
							? `Temporary until <t:${Math.floor(expiresAt.getTime() / 1000)}:F> (<t:${Math.floor(expiresAt.getTime() / 1000)}:R>)`
							: "Permanent";

						const dmContent = new ContainerBuilder()
							.setAccentColor(config.Colors?.error || "#EF4444")
							.addTextDisplay(`### ${ config.Emojis.blacklist || config.Emojis.error || config.Emojis.no_access || ``} You have been blacklisted from ${config.settings?.bot?.name || "the bot"}`)
							.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
							.addTextDisplay(
								`You are restricted from executing bot commands.\n\n` +
								`• **Reason:** ${entry.reason}\n` +
								`• **Duration:** ${expiryText}\n` +
								`• **Appeals:** Please contact the bot administration if you believe this was in error.`
							)
							.build();

						await user.send({
							components: [dmContent],
							flags: MessageFlags.IsComponentsV2,
						}).catch(() => null);
					}
				} catch (dmErr) {
					logger.debug(`[BlacklistManager] Could not send DM to user ${userId}:`, dmErr);
				}
			}

			logger.info(`[BlacklistManager] User ${userId} blacklisted by ${adminId} (Expires: ${expiresAt?.toISOString() || "Permanent"})`);

			void AuditLog.record({
				actorType: "discord",
				source: "discord",
				action: "security.blacklist.user",
				resourceType: "user",
				resourceId: userId,
				actorId: adminId,
				success: true,
				newState: { userId, reason: entry.reason, expiresAt: expiresAt?.toISOString() || null },
			}).catch(() => null);

			return { success: true, entry };
		} catch (error: any) {
			logger.error(`[BlacklistManager] Failed to blacklist user ${userId}:`, error);
			return { success: false, error: error?.message || "Database error" };
		}
	}

	public static async unblacklistUser(
		userId: string,
		adminId: string
	): Promise<{ success: boolean; error?: string }> {
		if (!this.initialized) await this.init();

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.deleteOne({ targetId: userId, type: "user" });
			this.userCache.delete(userId);

			logger.info(`[BlacklistManager] User ${userId} unblacklisted by ${adminId}`);

			void AuditLog.record({
				actorType: "discord",
				source: "discord",
				action: "security.unblacklist.user",
				resourceType: "user",
				resourceId: userId,
				actorId: adminId,
				success: true,
			}).catch(() => null);

			return { success: true };
		} catch (error: any) {
			logger.error(`[BlacklistManager] Failed to unblacklist user ${userId}:`, error);
			return { success: false, error: error?.message || "Database error" };
		}
	}

	public static async blacklistGuild(
		guildId: string,
		durationStr: string | null,
		reason: string,
		adminId: string,
		client?: any
	): Promise<{ success: boolean; entry?: BlacklistEntry; error?: string }> {
		if (!this.initialized) await this.init();

		const expiresAt = parseDuration(durationStr);
		const now = new Date();
		const entry: BlacklistEntry = {
			targetId: guildId,
			type: "guild",
			reason: reason.trim() || "Server violation of bot policies",
			adminId,
			expiresAt,
			createdAt: now,
			updatedAt: now,
		};

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.updateOne(
				{ targetId: guildId, type: "guild" },
				{ $set: entry },
				{ upsert: true }
			);

			this.guildCache.set(guildId, entry);

			// Direct message the server owner
			if (client?.guilds?.fetch) {
				try {
					const guild = await client.guilds.fetch(guildId).catch(() => null);
					if (guild) {
						const owner = await guild.fetchOwner?.().catch(() => null);
						if (owner?.send) {
							const expiryText = expiresAt
								? `Temporary until <t:${Math.floor(expiresAt.getTime() / 1000)}:F> (<t:${Math.floor(expiresAt.getTime() / 1000)}:R>)`
								: "Permanent";

							const dmContent = new ContainerBuilder()
								.setAccentColor(config.Colors?.error || "#EF4444")
								.addTextDisplay(`### ${ config.Emojis.blacklist || config.Emojis.error || config.Emojis.no_access || ``} Your server has been blacklisted`)
								.addSeparator({ divider: true, spacing: SeparatorSpacingSize.Small })
								.addTextDisplay(
									`Your server **${guild.name}** (\`${guild.id}\`) has been blacklisted from using ${config.settings?.bot?.name || "the bot"}.\n\n` +
									`• **Reason:** ${entry.reason}\n` +
									`• **Duration:** ${expiryText}\n` +
									`• **Admin Note:** Bot commands and operations are deactivated for this server.`
								)
								.build();

							await owner.send({
								components: [dmContent],
								flags: MessageFlags.IsComponentsV2,
							}).catch(() => null);
						}
					}
				} catch (dmErr) {
					logger.debug(`[BlacklistManager] Could not send DM to guild owner for ${guildId}:`, dmErr);
				}
			}

			logger.info(`[BlacklistManager] Guild ${guildId} blacklisted by ${adminId}`);

			void AuditLog.record({
				actorType: "discord",
				source: "discord",
				action: "security.blacklist.guild",
				resourceType: "guild",
				resourceId: guildId,
				guildId,
				actorId: adminId,
				success: true,
				newState: { guildId, reason: entry.reason, expiresAt: expiresAt?.toISOString() || null },
			}).catch(() => null);

			return { success: true, entry };
		} catch (error: any) {
			logger.error(`[BlacklistManager] Failed to blacklist guild ${guildId}:`, error);
			return { success: false, error: error?.message || "Database error" };
		}
	}

	public static async unblacklistGuild(
		guildId: string,
		adminId: string
	): Promise<{ success: boolean; error?: string }> {
		if (!this.initialized) await this.init();

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.deleteOne({ targetId: guildId, type: "guild" });
			this.guildCache.delete(guildId);

			logger.info(`[BlacklistManager] Guild ${guildId} unblacklisted by ${adminId}`);

			void AuditLog.record({
				actorType: "discord",
				source: "discord",
				action: "security.unblacklist.guild",
				resourceType: "guild",
				resourceId: guildId,
				guildId,
				actorId: adminId,
				success: true,
			}).catch(() => null);

			return { success: true };
		} catch (error: any) {
			logger.error(`[BlacklistManager] Failed to unblacklist guild ${guildId}:`, error);
			return { success: false, error: error?.message || "Database error" };
		}
	}

	public static async listBlacklists(
		type?: "user" | "guild"
	): Promise<BlacklistEntry[]> {
		if (!this.initialized) await this.init();
		await this.syncCache();

		if (type === "user") {
			return Array.from(this.userCache.values());
		}
		if (type === "guild") {
			return Array.from(this.guildCache.values());
		}
		return [...this.userCache.values(), ...this.guildCache.values()];
	}
}
