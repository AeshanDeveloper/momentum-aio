import DatabaseManager from "@database/Database";
import type CommandRecord from "@shared/types/CommandRecord";
import { CommandType } from "@shared/types/CommandRecord";
import type { Filter } from "mongodb";

export default class CommandModel {
	private readonly database;

	constructor() {
		this.database = DatabaseManager;
	}

	/**
	 * Convert a MongoDB document into the CommandRecord
	 * shape used by the rest of MomentumOne.
	 *
	 * MongoDB:
	 * {
	 *   _id: commandId,
	 *   command_id: commandId,
	 *   plugin_id: pluginId,
	 *   ...
	 * }
	 *
	 * Returned:
	 * {
	 *   commandId,
	 *   pluginId,
	 *   ...
	 * }
	 */
	private normalize(document: any): CommandRecord {
		if (!document) return document;

		const {
			_id,
			command_id,
			plugin_id,
			owner_only,
			developer_only,
			premium_only,
			guild_only,
			user_permissions,
			bot_permissions,
			registered_by,
			...command
		} = document;

		let aliases = command.aliases;

		if (typeof aliases === "string") {
			try {
				aliases = JSON.parse(aliases);
			} catch {
				aliases = [];
			}
		}

		if (!Array.isArray(aliases)) {
			aliases = [];
		}

		return {
			commandId: command_id ?? _id,
			pluginId: plugin_id,

			name: command.name,
			description: command.description,

			enabled: command.enabled,
			type: command.type,

			aliases,

			ownerOnly: owner_only,
			developerOnly: developer_only,
			premiumOnly: premium_only,
			guildOnly: guild_only,
			nsfw: command.nsfw,

			userPermissions: this.normalizeArray(
				user_permissions
			),

			botPermissions: this.normalizeArray(
				bot_permissions
			),

			cooldown: command.cooldown,

			status: command.status,
			checksum: command.checksum,

			registeredBy: registered_by,
		} as CommandRecord;
	}

	/**
	 * Normalize permission fields.
	 */
	private normalizeArray(value: unknown): string[] {
		if (Array.isArray(value)) {
			return value.map(String);
		}

		if (typeof value === "string") {
			try {
				const parsed = JSON.parse(value);

				if (Array.isArray(parsed)) {
					return parsed.map(String);
				}
			} catch {
				// Not JSON.
			}

			// Handles values like:
			// "Administrator,ManageGuild"
			if (value.includes(",")) {
				return value
					.split(",")
					.map(v => v.trim())
					.filter(Boolean);
			}

			return value ? [value] : [];
		}

		return [];
	}

	/**
	 * Register a command.
	 *
	 * MongoDB _id is deliberately the same as commandId.
	 */
	async register(command: CommandRecord): Promise<void> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		await collection.insertOne({
			_id: command.commandId,

			command_id: command.commandId,
			plugin_id: command.pluginId,

			name: command.name,
			description: command.description,

			enabled: command.enabled,
			type: command.type,

			aliases: Array.isArray(command.aliases)
				? command.aliases
				: [],

			owner_only: command.ownerOnly,
			developer_only: command.developerOnly,
			premium_only: command.premiumOnly,
			guild_only: command.guildOnly,
			nsfw: command.nsfw,

			user_permissions:
				Array.isArray(command.userPermissions)
					? command.userPermissions
					: [],

			bot_permissions:
				Array.isArray(command.botPermissions)
					? command.botPermissions
					: [],

			cooldown: command.cooldown,

			status: command.status,
			checksum: command.checksum,

			registered_by: command.registeredBy,
		});
	}

	/**
	 * Update a command.
	 */
	async update(
		id: string,
		command: any
	): Promise<void> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		await collection.updateOne(
			{
				_id: id,
			},
			{
				$set: {
					command_id: id,

					plugin_id: command.pluginId,

					name: command.name,
					description: command.description,

					enabled: command.enabled,
					type: command.type,

					aliases: Array.isArray(command.aliases)
						? command.aliases
						: [],

					owner_only: command.ownerOnly,
					developer_only: command.developerOnly,
					premium_only: command.premiumOnly,
					guild_only: command.guildOnly,
					nsfw: command.nsfw,

					user_permissions:
						Array.isArray(command.userPermissions)
							? command.userPermissions
							: [],

					bot_permissions:
						Array.isArray(command.botPermissions)
							? command.botPermissions
							: [],

					cooldown: command.cooldown,

					status: command.status,
					checksum: command.checksum,

					registered_by: command.registeredBy,
				},
			}
		);
	}

	/**
	 * Delete a command.
	 */
	async delete(
		commandId: string
	): Promise<boolean> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const result =
			await collection.deleteOne({
				_id: commandId,
			});

		return result.deletedCount > 0;
	}

	/**
	 * Alias for delete().
	 */
	async unregister(
		commandId: string
	): Promise<boolean> {
		return this.delete(commandId);
	}

	/**
	 * Get commands by field.
	 */
	async get<K extends keyof CommandRecord>(
		field: K,
		value: CommandRecord[K]
	): Promise<CommandRecord[]> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const fieldMap: Record<string, string> = {
			commandId: "command_id",
			pluginId: "plugin_id",
			ownerOnly: "owner_only",
			developerOnly: "developer_only",
			premiumOnly: "premium_only",
			guildOnly: "guild_only",
			userPermissions: "user_permissions",
			botPermissions: "bot_permissions",
			registeredBy: "registered_by",
		};

		const mongoField =
			fieldMap[field as string] ?? field;

		const rows =
			await collection.find({
				[mongoField]: value,
			}).toArray();

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Get every command.
	 */
	async getAll(): Promise<CommandRecord[]> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const rows =
			await collection.find({}).toArray();

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Find one command by ID.
	 */
	async findById(
		commandId: string
	): Promise<CommandRecord | null> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const command =
			await collection.findOne({
				_id: commandId,
			});

		return command
			? this.normalize(command)
			: null;
	}

	/**
	 * Find commands belonging to a plugin.
	 */
	async findByPluginId(
		pluginId: string
	): Promise<CommandRecord[]> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const rows =
			await collection.find({
				plugin_id: pluginId,
			}).toArray();

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Check whether a command exists.
	 */
	async exists(
		commandId: string
	): Promise<boolean> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const command =
			await collection.findOne(
				{
					_id: commandId,
				},
				{
					projection: {
						_id: 1,
					},
				}
			);

		return command !== null;
	}

	/**
	 * Check whether a command exists by
	 * plugin ID + name + command type.
	 */
	async existsByPluginNameType(
		pluginId: string,
		name: string,
		type: CommandType
	): Promise<boolean> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		const command =
			await collection.findOne(
				{
					plugin_id: pluginId,
					name,
					type,
				},
				{
					projection: {
						_id: 1,
					},
				}
			);

		return command !== null;
	}

	/**
	 * Update command status.
	 */
	async setStatus(
		commandId: string,
		status: any
	): Promise<void> {
		const collection =
			await this.database.collection<any>(
				"shop_commands"
			);

		await collection.updateOne(
			{
				_id: commandId,
			},
			{
				$set: {
					status,
				},
			}
		);
	}
}