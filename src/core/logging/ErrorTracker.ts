import { randomUUID } from "node:crypto";
import DatabaseManager from "@database/Database";
import logger from "@logger";
import AuditLog from "@core/audit/AuditLog";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";

export interface CommandErrorRecord {
	errorId: string;
	commandName: string;
	userId?: string;
	username?: string;
	guildId?: string;
	commandType?: string;
	args?: string[];
	message: string;
	stack?: string;
	timestamp: Date;
}

export class ErrorTracker {
	private static readonly COLLECTION = "command_errors";
	private static recentErrors: CommandErrorRecord[] = [];

	public static generateErrorId(): string {
		const part = randomUUID().replace(/-/g, "").slice(0, 8).toUpperCase();
		return `ERR-${part}`;
	}

	public static async record(
		commandName: string,
		error: any,
		context: {
			userId?: string;
			username?: string;
			guildId?: string;
			commandType?: string;
			args?: string[];
		} = {}
	): Promise<CommandErrorRecord> {
		const errorId = this.generateErrorId();
		const message = error?.message || String(error) || "Unknown error";
		const stack = error?.stack || undefined;
		const now = new Date();

		const record: CommandErrorRecord = {
			errorId,
			commandName,
			userId: context.userId,
			username: context.username,
			guildId: context.guildId,
			commandType: context.commandType,
			args: context.args,
			message,
			stack,
			timestamp: now,
		};

		// Keep in memory ring-buffer
		this.recentErrors.unshift(record);
		if (this.recentErrors.length > 100) {
			this.recentErrors.pop();
		}

		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.insertOne(record);
		} catch (dbErr) {
			logger.error(`[ErrorTracker] Failed to persist error ${errorId} to database:`, dbErr);
		}

		// Also record into centralized AuditLog
		try {
			await AuditLog.record({
				actorType: "bot",
				source: "bot",
				action: "command.error",
				resourceType: "command",
				resourceId: commandName,
				guildId: context.guildId,
				actorId: context.userId,
				success: false,
				error: `[${errorId}] ${message}`,
			});
		} catch (auditErr) {
			logger.warn(`[ErrorTracker] Failed to record error to AuditLog:`, auditErr);
		}

		ObservabilityManager.recordError("command_error", `[${errorId}] ${commandName}: ${message.slice(0, 100)}`);

		logger.error(`[ErrorTracker] [${errorId}] Error in command "${commandName}":`, error);

		return record;
	}

	public static async list(
		skip = 0,
		limit = 20,
		filter: Record<string, any> = {}
	): Promise<CommandErrorRecord[]> {
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			return (await col
				.find(filter)
				.sort({ timestamp: -1 })
				.skip(skip)
				.limit(limit)
				.toArray()) as CommandErrorRecord[];
		} catch {
			let res = this.recentErrors;
			if (filter.commandName) {
				res = res.filter((e) => e.commandName.toLowerCase() === String(filter.commandName).toLowerCase());
			}
			if (filter.userId) {
				res = res.filter((e) => e.userId === filter.userId);
			}
			return res.slice(skip, skip + limit);
		}
	}

	public static async get(errorId: string): Promise<CommandErrorRecord | null> {
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const doc = (await col.findOne({ errorId })) as CommandErrorRecord | null;
			if (doc) return doc;
		} catch {
			// fallback to in-memory
		}
		return this.recentErrors.find((e) => e.errorId.toUpperCase() === errorId.toUpperCase()) || null;
	}

	public static async count(filter: Record<string, any> = {}): Promise<number> {
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			return await col.countDocuments(filter);
		} catch {
			return this.recentErrors.length;
		}
	}

	public static async delete(errorId: string): Promise<boolean> {
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			await col.deleteOne({ errorId });
		} catch {
			// fallback
		}
		const idx = this.recentErrors.findIndex((e) => e.errorId.toUpperCase() === errorId.toUpperCase());
		if (idx !== -1) {
			this.recentErrors.splice(idx, 1);
			return true;
		}
		return false;
	}

	public static async clear(): Promise<number> {
		let count = 0;
		try {
			const col = await DatabaseManager.collection(this.COLLECTION);
			const res = await col.deleteMany({});
			count = res.deletedCount || 0;
		} catch {
			count = this.recentErrors.length;
		}
		this.recentErrors = [];
		return count;
	}
}
