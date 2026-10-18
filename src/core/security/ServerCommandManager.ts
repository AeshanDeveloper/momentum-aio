import DatabaseManager from "@database/Database";
import logger from "@logger";
import AuditLog from "@core/audit/AuditLog";

export interface ServerCommandSettings {
	guildId: string;
	disabledCommands: string[];
	disabledCategories: string[];
	updatedAt: Date;
	updatedBy?: string;
}

export class ServerCommandManager {
	private static readonly COLLECTION = "guild_disabled_commands";
	private static readonly CACHE_TTL_MS = 300_000; // 5 minutes

	// Essential commands that can NEVER be disabled to prevent server lockout
	public static readonly ESSENTIAL_COMMANDS = new Set<string>([
		"help",
		"command",
		"command-manage",
		"enable",
		"disable",
		"settings",
		"economy-settings",
		"ping",
	]);

	private static cache = new Map<
		string,
		{ disabledCommands: Set<string>; disabledCategories: Set<string>; expiresAt: number }
	>();

	public static async getGuildSettings(guildId: string): Promise<{ disabledCommands: Set<string>; disabledCategories: Set<string> }> {
		const cached = this.cache.get(guildId);
		if (cached && Date.now() < cached.expiresAt) {
			return {
				disabledCommands: cached.disabledCommands,
				disabledCategories: cached.disabledCategories,
			};
		}

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const doc = await col.findOne({ guildId });

			const disabledCommands = new Set<string>(
				Array.isArray(doc?.disabledCommands)
					? doc.disabledCommands.map((c: string) => c.toLowerCase())
					: []
			);
			const disabledCategories = new Set<string>(
				Array.isArray(doc?.disabledCategories)
					? doc.disabledCategories.map((c: string) => c.toLowerCase())
					: []
			);

			this.cache.set(guildId, {
				disabledCommands,
				disabledCategories,
				expiresAt: Date.now() + this.CACHE_TTL_MS,
			});

			return { disabledCommands, disabledCategories };
		} catch (err) {
			logger.error(`[ServerCommandManager] Failed to fetch settings for guild ${guildId}:`, err);
			return { disabledCommands: new Set(), disabledCategories: new Set() };
		}
	}

	public static async isCommandDisabled(guildId: string, commandName: string, category?: string): Promise<boolean> {
		if (!guildId || !commandName) return false;
		const lowerName = commandName.toLowerCase();
		if (this.ESSENTIAL_COMMANDS.has(lowerName)) return false;

		const { disabledCommands, disabledCategories } = await this.getGuildSettings(guildId);
		if (disabledCommands.has(lowerName)) return true;
		if (category && disabledCategories.has(category.toLowerCase())) return true;

		return false;
	}

	public static async disableCommand(
		guildId: string,
		commandName: string,
		actorId: string
	): Promise<{ success: boolean; message: string }> {
		const lowerName = commandName.toLowerCase();
		if (this.ESSENTIAL_COMMANDS.has(lowerName)) {
			return {
				success: false,
				message: `Command \`${commandName}\` is an essential management command and cannot be disabled.`,
			};
		}

		// Verify command exists
		const commandExists = Array.from(global.commands?.values?.() || []).some(
			(cmd: any) => cmd.name?.toLowerCase() === lowerName || cmd.command?.aliases?.includes(lowerName)
		);

		if (!commandExists) {
			return {
				success: false,
				message: `Command \`${commandName}\` was not found in the bot's command registry.`,
			};
		}

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const doc = await col.findOne({ guildId });
			const current: string[] = Array.isArray(doc?.disabledCommands) ? [...doc.disabledCommands] : [];
			if (!current.includes(lowerName)) {
				current.push(lowerName);
			}

			await col.updateOne(
				{ guildId },
				{
					$set: {
						guildId,
						disabledCommands: current,
						updatedAt: new Date(),
						updatedBy: actorId,
					},
				},
				{ upsert: true }
			);

			this.cache.delete(guildId);

			void AuditLog.record({
				actorType: "user",
				actorId,
				guildId,
				action: "command.server_disable",
				resourceType: "command",
				resourceId: lowerName,
				success: true,
			});

			return {
				success: true,
				message: `Command \`${commandName}\` has been disabled in this server.`,
			};
		} catch (err: any) {
			logger.error(`[ServerCommandManager] Failed to disable command ${commandName} in ${guildId}:`, err);
			return { success: false, message: `Database error: ${err?.message || "Unknown"}` };
		}
	}

	public static async enableCommand(
		guildId: string,
		commandName: string,
		actorId: string
	): Promise<{ success: boolean; message: string }> {
		const lowerName = commandName.toLowerCase();

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const doc = await col.findOne({ guildId });
			const current: string[] = Array.isArray(doc?.disabledCommands) ? [...doc.disabledCommands] : [];
			const updated = current.filter((c: string) => c.toLowerCase() !== lowerName);

			await col.updateOne(
				{ guildId },
				{
					$set: {
						disabledCommands: updated,
						updatedAt: new Date(),
						updatedBy: actorId,
					},
				},
				{ upsert: true }
			);

			this.cache.delete(guildId);

			void AuditLog.record({
				actorType: "user",
				actorId,
				guildId,
				action: "command.server_enable",
				resourceType: "command",
				resourceId: lowerName,
				success: true,
			});

			return {
				success: true,
				message: `Command \`${commandName}\` has been re-enabled in this server.`,
			};
		} catch (err: any) {
			logger.error(`[ServerCommandManager] Failed to enable command ${commandName} in ${guildId}:`, err);
			return { success: false, message: `Database error: ${err?.message || "Unknown"}` };
		}
	}

	public static getAllManageableCommands(): Array<{
		name: string;
		category: string;
		description: string;
		essential: boolean;
	}> {
		const result: Array<{ name: string; category: string; description: string; essential: boolean }> = [];
		const seen = new Set<string>();

		for (const [, cmd] of global.commands || []) {
			const name = cmd.name?.toLowerCase();
			if (!name || seen.has(name)) continue;
			seen.add(name);

			const isOwnerOnly =
				Boolean(cmd.command?.ownerOnly) ||
				Boolean(cmd.command?.ownersOnly) ||
				["dev", "owner"].includes(cmd.command?.category?.toLowerCase());
			if (isOwnerOnly) continue;

			result.push({
				name: cmd.name,
				category: cmd.command?.category || cmd.category || "General",
				description: cmd.description || cmd.command?.description || "No description provided",
				essential: this.ESSENTIAL_COMMANDS.has(name),
			});
		}

		return result.sort((a, b) => a.name.localeCompare(b.name));
	}
}
