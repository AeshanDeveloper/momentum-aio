import DatabaseManager from "@database/Database";
import logger from "@logger";

export interface GetPluginOptions {
	pluginId?: string;
	name?: string;
	author?: string;
	repositoryUrl?: string;
}

export default class PluginModel {
	/**
	 * Convert MongoDB document to the same object shape
	 * that the old MySQL model returned.
	 */
	private static normalize(row: any) {
		if (!row) return null;

		return {
			pluginId: row.plugin_id,
			name: row.name,
			description: row.description,
			version: row.version,
			author: row.author,
			source: row.source,
			installPath: row.install_path,
			checksum: row.checksum,
			repositoryUrl: row.repository_url,
			requiredMomentumOneVersion:
				row.required_momentushop_version,

			// Preserve the old model's output.
			enabled:
				typeof row.enabled === "string"
					? row.enabled === "true"
					: Boolean(row.enabled),
		};
	}

	/**
	 * Add a plugin.
	 */
	static async add(data: {
		pluginId: string;
		name: string;
		description?: string;
		version: string;
		author: string;
		source:
			| "unknown"
			| "mone-registry"
			| "github"
			| "local";
		enabled: string;
		installPath?: string;
		checksum?: string;
		repositoryUrl?: string;
		requiredCoreVersion?: string;
	}) {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		const result = await collection.insertOne({
			plugin_id: data.pluginId,
			name: data.name,
			description: data.description ?? null,
			version: data.version,
			author: data.author,
			source: data.source,
			enabled: data.enabled,
			install_path: data.installPath ?? null,
			checksum: data.checksum ?? null,
			repository_url:
				data.repositoryUrl ?? null,
			required_momentushop_version:
				data.requiredCoreVersion ?? null,
		});

		/*
		 * MySQL returned a ResultSetHeader.
		 *
		 * MongoDB returns InsertOneResult instead.
		 * Returning it keeps the result available to callers
		 * without changing the operation itself.
		 */
		return result;
	}

	/**
	 * Get one plugin using one or more search options.
	 */
	static async get(
		options: GetPluginOptions
	) {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		const filter: Record<string, unknown> = {};

		if (options.pluginId) {
			filter.plugin_id = options.pluginId;
		}

		if (options.name) {
			filter.name = options.name;
		}

		if (options.author) {
			filter.author = options.author;
		}

		if (options.repositoryUrl) {
			filter.repository_url =
				options.repositoryUrl;
		}

		if (Object.keys(filter).length === 0) {
			logger.error(
				"[DB] At least one search option must be provided."
			);

			return [];
		}

		const row = await collection.findOne(
			filter
		);

		if (!row) {
			return [];
		}

		return [this.normalize(row)];
	}

	/**
	 * Get all plugins.
	 */
	static async getAll() {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		const rows =
			await collection.find({}).toArray();

		if (!rows || rows.length === 0) {
			return [];
		}

		return rows.map(row =>
			this.normalize(row)
		);
	}

	/**
	 * Check whether a plugin exists.
	 */
	static async exists(
		pluginId: string
	): Promise<boolean> {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		const row =
			await collection.findOne(
				{
					plugin_id: pluginId,
				},
				{
					projection: {
						_id: 1,
					},
				}
			);

		return row !== null;
	}

	/**
	 * Update a plugin.
	 */
	static async update(
		pluginId: string,
		data: Record<string, unknown>
	): Promise<boolean> {
		const columnMap: Record<string, string> = {
			pluginId: "plugin_id",
			installPath: "install_path",
			repositoryUrl: "repository_url",
			requiredMomentumOneVersion:
				"required_momentushop_version",
		};

		const entries = Object.entries(data)
			.filter(
				([, value]) =>
					value !== undefined
			)
			.map(
				([key, value]) =>
					[
						columnMap[key] ?? key,
						value,
					] as const
			);

		if (entries.length === 0) {
			throw new Error(
				"No fields were provided to update."
			);
		}

		const updates: Record<string, unknown> = {};

		for (const [field, value] of entries) {
			updates[field] = value;
		}

		const result =
			await DatabaseManager.collection(
				"shop_plugins"
			).then(collection =>
				collection.updateOne(
					{
						plugin_id: pluginId,
					},
					{
						$set: updates,
					}
				)
			);

		return result.modifiedCount > 0;
	}

	/**
	 * Remove a plugin.
	 */
	static async remove(
		pluginId: string
	) {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		await collection.deleteOne({
			plugin_id: pluginId,
		});
	}

	/**
	 * Enable/disable a plugin.
	 */
	static async setEnabled(
		pluginId: string,
		enabled: boolean
	) {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		await collection.updateOne(
			{
				plugin_id: pluginId,
			},
			{
				$set: {
					enabled,
				},
			}
		);
	}

	/**
	 * Check whether a plugin is enabled.
	 */
	static async isEnabled(
		pluginId: string
	): Promise<boolean> {
		const plugin =
			await this.get({ pluginId });

		return plugin?.[0]?.enabled ?? false;
	}

	/**
	 * Count all plugins.
	 */
	static async count(): Promise<number> {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		return collection.countDocuments({});
	}

	/**
	 * Count enabled plugins.
	 */
	static async countEnabled(): Promise<number> {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		return collection.countDocuments({
			$or: [
				{ enabled: true },
				{ enabled: "true" },
			],
		});
	}

	/**
	 * Count disabled plugins.
	 */
	static async countDisabled(): Promise<number> {
		const collection =
			await DatabaseManager.collection(
				"shop_plugins"
			);

		return collection.countDocuments({
			$or: [
				{ enabled: false },
				{ enabled: "false" },
			],
		});
	}
}