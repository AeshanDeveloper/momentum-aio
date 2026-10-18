import DatabaseManager from "@database/Database";
import logger from "@logger";
import config from "@config";
import { BlacklistManager } from "./BlacklistManager";
import { isBlacklistExcluded } from "./SecurityHelpers";

export interface AntiSpamResult {
	allowed: boolean;
	warning?: string;
	blacklisted?: boolean;
	reason?: string;
	infractionCount?: number;
}

export class AntiSpamService {
	// userId -> array of timestamps within window
	private static timestamps = new Map<string, number[]>();
	// userId -> total infraction count
	private static infractions = new Map<string, number>();
	private static infractionsInitialized = false;

	public static async init(): Promise<void> {
		if (this.infractionsInitialized) return;
		this.infractionsInitialized = true;
		try {
			const col = await DatabaseManager.collection("anti_spam_infractions");
			const docs = (await col.find({}).toArray()) as { userId: string; count: number }[];
			for (const d of docs) {
				if (d.userId && typeof d.count === "number") {
					this.infractions.set(d.userId, d.count);
				}
			}
		} catch (error) {
			logger.error("[AntiSpamService] Failed to load infractions from DB:", error);
		}

		// Periodic cleanup of stale timestamps
		setInterval(() => {
			const cutoff = Date.now() - (config.settings?.intervals?.anti_spam_window || 30_000);
			for (const [userId, list] of this.timestamps.entries()) {
				const filtered = list.filter((ts) => ts > cutoff);
				if (filtered.length === 0) {
					this.timestamps.delete(userId);
				} else {
					this.timestamps.set(userId, filtered);
				}
			}
		}, 60_000).unref?.();
	}

	public static async check(
		userId: string,
		client?: any
	): Promise<AntiSpamResult> {
		if (!this.infractionsInitialized) await this.init();

		// Bot owners and excluded users are immune to anti-spam limits
		if (isBlacklistExcluded(userId)) {
			return { allowed: true };
		}

		// If user is already blacklisted, don't count rejected commands repeatedly
		const blCheck = await BlacklistManager.isUserBlacklisted(userId);
		if (blCheck.blacklisted) {
			return {
				allowed: false,
				blacklisted: true,
				reason: blCheck.entry?.reason || "Account is blacklisted",
			};
		}

		const now = Date.now();
		const windowMs = config.settings?.intervals?.anti_spam_window || 30_000;
		const cutoff = now - windowMs;

		const userTimestamps = (this.timestamps.get(userId) || []).filter((ts) => ts > cutoff);
		userTimestamps.push(now);
		this.timestamps.set(userId, userTimestamps);

		const count = userTimestamps.length;

		// Commands 1-7: completely allowed
		if (count <= 7) {
			return { allowed: true };
		}

		// Commands 8-9: allowed but with explicit warning
		if (count >= 8 && count <= 9) {
			const warnNumber = count - 7;
			return {
				allowed: true,
				warning: `⚠️ **Anti-Spam Warning (${warnNumber}/3):** You are sending commands too quickly. Please slow down or you will be automatically blacklisted.`,
			};
		}

		// On 10th command attempt (or higher): trigger automatic blacklist
		const currentInfractions = (this.infractions.get(userId) || 0) + 1;
		this.infractions.set(userId, currentInfractions);

		// Persist infraction count
		try {
			const col = await DatabaseManager.collection("anti_spam_infractions");
			await col.updateOne(
				{ userId },
				{ $set: { userId, count: currentInfractions, updatedAt: new Date() } },
				{ upsert: true }
			);
		} catch (err) {
			logger.error("[AntiSpamService] Failed to persist infraction count:", err);
		}

		// Progressive durations:
		// 1st time: 5m
		// 2nd time: 15m
		// 3rd time: 1h
		// 4th time+: permanent
		let durationStr: string | null = "5m";
		if (currentInfractions === 2) durationStr = "15m";
		else if (currentInfractions === 3) durationStr = "1h";
		else if (currentInfractions >= 4) durationStr = null; // permanent

		const durationLabel = durationStr ? durationStr : "permanent";
		const reason = `Automated Anti-Spam: Exceeded rate limit (10 commands in 30s) — Infraction #${currentInfractions} (${durationLabel})`;

		await BlacklistManager.blacklistUser(userId, durationStr, reason, "system", client);

		// Clear timestamp window for this user so they don't immediately re-trigger on expiry
		this.timestamps.delete(userId);

		logger.warn(`[AntiSpamService] User ${userId} blacklisted for anti-spam: Infraction #${currentInfractions} (${durationLabel})`);

		return {
			allowed: false,
			blacklisted: true,
			infractionCount: currentInfractions,
			reason,
		};
	}
}
