import config from "@config";
import logger from "@logger";
import { isBotOwner, parseDuration } from "./SecurityHelpers";

export interface CooldownCheckResult {
	onCooldown: boolean;
	remainingSeconds: number;
	expiresAt: number;
	scope: "user" | "guild" | "global";
}

export class CooldownManager {
	// key: `${canonicalCommandName}:${targetId}` -> timestamp (ms)
	private static cooldowns = new Map<string, number>();
	private static cleanupTimer: NodeJS.Timeout | null = null;

	public static init(): void {
		if (this.cleanupTimer) return;
		this.cleanupTimer = setInterval(() => {
			this.pruneExpired();
		}, 60_000);
		if (this.cleanupTimer.unref) this.cleanupTimer.unref();
	}

	private static getCanonicalName(command: any): string {
		return (
			command?.name?.toLowerCase() ||
			command?.command?.name?.toLowerCase() ||
			command?.commandId ||
			"unknown_command"
		);
	}

	private static getCooldownMs(command: any): number {
		let raw = command?.command?.cooldown ?? command?.cooldown;
		if (typeof raw === "string") {
			const parsed = parseDuration(raw);
			if (parsed) return Math.max(0, parsed.getTime() - Date.now());
			raw = Number(raw);
		}
		if (typeof raw === "number" && Number.isFinite(raw) && raw > 0) {
			// If >= 1000, value is specified in milliseconds (e.g. 3000ms = 3s, 5000ms = 5s, 10000ms = 10s)
			// If < 1000, value is specified in seconds (e.g. 5s = 5000ms, 60s = 60000ms, 300s = 300000ms)
			return raw < 1000 ? raw * 1000 : raw;
		}
		return 0;
	}

	private static getKey(
		canonicalName: string,
		scope: "user" | "guild" | "global",
		userId: string,
		guildId?: string | null
	): string {
		if (scope === "guild" && guildId) {
			return `${canonicalName}:guild:${guildId}`;
		}
		if (scope === "global") {
			return `${canonicalName}:global`;
		}
		return `${canonicalName}:user:${userId}`;
	}

	/**
	 * Checks if the user or guild is currently on cooldown for the given command.
	 * Bot owners always bypass cooldown checks.
	 */
	public static check(
		command: any,
		userId: string,
		guildId?: string | null
	): CooldownCheckResult {
		if (isBotOwner(userId)) {
			return { onCooldown: false, remainingSeconds: 0, expiresAt: 0, scope: "user" };
		}

		const ms = this.getCooldownMs(command);
		const scope: "user" | "guild" | "global" =
			command?.command?.cooldownScope || command?.cooldownScope || "user";

		if (ms <= 0) {
			return { onCooldown: false, remainingSeconds: 0, expiresAt: 0, scope };
		}

		const canonicalName = this.getCanonicalName(command);
		const key = this.getKey(canonicalName, scope, userId, guildId);
		const expiresAt = this.cooldowns.get(key);
		const now = Date.now();

		if (expiresAt && expiresAt > now) {
			const remainingSeconds = Math.max(0.1, Number(((expiresAt - now) / 1000).toFixed(1)));
			return {
				onCooldown: true,
				remainingSeconds,
				expiresAt,
				scope,
			};
		}

		return {
			onCooldown: false,
			remainingSeconds: 0,
			expiresAt: 0,
			scope,
		};
	}

	/**
	 * Applies the command's configured cooldown to the user, guild, or global bucket.
	 * Bot owners are never put on cooldown.
	 */
	public static apply(
		command: any,
		userId: string,
		guildId?: string | null
	): void {
		if (isBotOwner(userId)) return;

		const ms = this.getCooldownMs(command);
		if (ms <= 0) return;

		const canonicalName = this.getCanonicalName(command);
		const scope: "user" | "guild" | "global" =
			command?.command?.cooldownScope || command?.cooldownScope || "user";
		const key = this.getKey(canonicalName, scope, userId, guildId);
		const expiresAt = Date.now() + ms;

		this.cooldowns.set(key, expiresAt);
		logger.debug(`[CooldownManager] Applied ${ms}ms cooldown to "${key}"`);
	}

	/**
	 * Cleans up expired cooldown timestamps to prevent memory growth.
	 */
	public static pruneExpired(): void {
		const now = Date.now();
		let pruned = 0;
		for (const [key, expiresAt] of this.cooldowns.entries()) {
			if (expiresAt <= now) {
				this.cooldowns.delete(key);
				pruned++;
			}
		}
		if (pruned > 0) {
			logger.debug(`[CooldownManager] Pruned ${pruned} expired cooldown entries.`);
		}
	}

	/**
	 * Resets cooldown for a specific user and command (useful for admin/tests).
	 */
	public static reset(
		commandName: string,
		userId: string,
		guildId?: string | null
	): void {
		const name = commandName.toLowerCase();
		this.cooldowns.delete(`${name}:user:${userId}`);
		if (guildId) this.cooldowns.delete(`${name}:guild:${guildId}`);
		this.cooldowns.delete(`${name}:global`);
	}
}

CooldownManager.init();
