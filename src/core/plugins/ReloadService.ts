import path from "node:path";
import { createRequire } from "node:module";
import logger from "@logger";
import CommandsLoader from "@bot/discord/commands/Loader";
import EventsLoader from "@bot/discord/events/Loader";
import PluginContext from "@core/plugins/PluginContext";
import AutoLoader from "@sdk/AutoLoader";
import { getAllFiles } from "@shared/helpers";

const require = createRequire(import.meta.url);

export class ReloadService {
	/**
	 * Safely purge a module and its cached exports from Node's require.cache.
	 */
	public static purgeRequireCache(filePath: string): void {
		try {
			const resolved = require.resolve(filePath);
			if (require.cache[resolved]) {
				delete require.cache[resolved];
			}
		} catch {
			// File may not be resolved or already deleted
		}
	}

	/**
	 * Reload a specific command by name or alias without restarting the bot.
	 */
	public static async reloadCommand(commandQuery: string): Promise<{
		success: boolean;
		commandName?: string;
		pluginName?: string;
		error?: string;
	}> {
		const query = commandQuery.trim().toLowerCase();
		let targetCommandRecord: any = null;

		for (const [, cmd] of global.commands || []) {
			const name = cmd.name?.toLowerCase();
			const aliases = (cmd.command?.aliases || cmd.aliases || []).map((a: string) => a.toLowerCase());
			if (name === query || aliases.includes(query)) {
				targetCommandRecord = cmd;
				break;
			}
		}

		if (!targetCommandRecord) {
			return {
				success: false,
				error: `Command \`${commandQuery}\` was not found in active registrations.`,
			};
		}

		const filePath = targetCommandRecord.file;
		if (!filePath) {
			return {
				success: false,
				error: `Command \`${targetCommandRecord.name}\` has no associated file path.`,
			};
		}

		const pluginId = targetCommandRecord.pluginId;
		const pluginSettings = global.cache?.plugins?.get(pluginId);
		if (!pluginSettings) {
			return {
				success: false,
				error: `Parent plugin for \`${targetCommandRecord.name}\` was not found in cache.`,
			};
		}

		try {
			// Purge require cache
			this.purgeRequireCache(filePath);

			// Re-require raw module
			const freshRaw = require(filePath);
			const raw = freshRaw?.default ?? freshRaw;

			const mapper = pluginSettings.autoLoader?.commands?.mapping;
			if (!mapper || typeof mapper !== "function") {
				return {
					success: false,
					error: `Plugin \`${pluginSettings.meta.name}\` has no command mapper.`,
				};
			}

			const freshMapped = mapper(raw);

			// Update registration in memory
			targetCommandRecord.command = freshMapped;
			targetCommandRecord.raw = raw;
			targetCommandRecord.name = freshMapped.name ?? freshMapped.data?.name ?? targetCommandRecord.name;
			targetCommandRecord.aliases = freshMapped.aliases ?? [];
			global.commands.set(targetCommandRecord.commandId, targetCommandRecord);

			logger.info(
				`[ReloadService] Successfully reloaded command "${targetCommandRecord.name}" from plugin "${pluginSettings.meta.name}".`
			);

			return {
				success: true,
				commandName: targetCommandRecord.name,
				pluginName: pluginSettings.meta.name,
			};
		} catch (error: any) {
			logger.error(`[ReloadService] Failed to reload command "${targetCommandRecord.name}":`, error);
			return {
				success: false,
				commandName: targetCommandRecord.name,
				error: error?.message || "Internal error during reload.",
			};
		}
	}

	/**
	 * Reload all commands belonging to a given plugin.
	 */
	public static async reloadPluginCommands(pluginIdOrName: string): Promise<{
		success: boolean;
		count?: number;
		pluginName?: string;
		error?: string;
	}> {
		let pluginId = pluginIdOrName;
		let pluginSettings = global.cache?.plugins?.get(pluginId);

		if (!pluginSettings) {
			// Try finding by plugin manifest name
			for (const [id, entry] of global.cache?.plugins || []) {
				if (entry.meta?.name?.toLowerCase() === pluginIdOrName.toLowerCase()) {
					pluginId = id;
					pluginSettings = entry;
					break;
				}
			}
		}

		if (!pluginSettings) {
			return {
				success: false,
				error: `Plugin \`${pluginIdOrName}\` was not found.`,
			};
		}

		try {
			const commandsDir = path.resolve(
				pluginSettings.meta.path,
				pluginSettings.autoLoader.commands.directory
			);

			const files = getAllFiles(commandsDir);
			for (const f of files) {
				this.purgeRequireCache(f);
			}

			const loader = new CommandsLoader();
			await loader.autoLoad(pluginId);

			logger.info(
				`[ReloadService] Successfully reloaded ${files.length} commands for plugin "${pluginSettings.meta.name}".`
			);

			return {
				success: true,
				count: files.length,
				pluginName: pluginSettings.meta.name,
			};
		} catch (error: any) {
			logger.error(`[ReloadService] Failed to reload commands for plugin "${pluginId}":`, error);
			return {
				success: false,
				error: error?.message || "Failed to reload plugin commands.",
			};
		}
	}

	/**
	 * Reload an entire plugin: runs lifecycle methods, replaces event listeners,
	 * clears file caches, re-initializes plugin instance, and re-registers commands & events.
	 */
	public static async reloadPlugin(
		pluginIdOrName: string,
		client: any
	): Promise<{
		success: boolean;
		pluginName?: string;
		error?: string;
	}> {
		let pluginId = pluginIdOrName;
		let pluginSettings = global.cache?.plugins?.get(pluginId);

		if (!pluginSettings) {
			for (const [id, entry] of global.cache?.plugins || []) {
				if (entry.meta?.name?.toLowerCase() === pluginIdOrName.toLowerCase()) {
					pluginId = id;
					pluginSettings = entry;
					break;
				}
			}
		}

		if (!pluginSettings) {
			return {
				success: false,
				error: `Plugin \`${pluginIdOrName}\` was not found in cache.`,
			};
		}

		const meta = pluginSettings.meta;
		const oldInstance = pluginSettings.instance;

		try {
			// 1. Run onDisable lifecycle method
			if (typeof oldInstance?.onDisable === "function") {
				try {
					await oldInstance.onDisable();
				} catch (disableErr) {
					logger.warn(`[ReloadService] onDisable threw an error for "${meta.name}":`, disableErr);
				}
			}

			// 2. Safely unload all Discord event listeners registered by this plugin
			const activeClient = client || (global as any).bot?.client || (global as any).client;
			const eventsLoader = activeClient ? new EventsLoader(activeClient) : null;
			if (eventsLoader) {
				eventsLoader.unloadPluginEvents(pluginId);
			}

			// 3. Purge require cache for all files inside the plugin folder
			const pluginDir = path.resolve(meta.path);
			for (const cachedPath of Object.keys(require.cache)) {
				if (cachedPath.startsWith(pluginDir)) {
					delete require.cache[cachedPath];
				}
			}

			// 4. Re-instantiate plugin class
			const folderName = path.basename(meta.path);
			const entryPath = path.resolve(meta.path, meta.main);
			this.purgeRequireCache(entryPath);

			const freshImport = require(entryPath);
			const PluginClass =
				freshImport.default ??
				freshImport.Plugin ??
				freshImport.plugin ??
				freshImport;

			if (typeof PluginClass !== "function") {
				return {
					success: false,
					error: `Plugin entry file does not export a valid constructor class.`,
				};
			}

			const freshAutoLoader = new AutoLoader();
			const freshContext = new PluginContext(
				{ meta, client: activeClient },
				global.eBus,
				freshAutoLoader
			);

			const freshInstance = new PluginClass(freshContext);

			global.cache.plugins.set(pluginId, {
				autoLoader: freshAutoLoader,
				instance: freshInstance,
				meta,
				pluginContext: freshContext,
			});

			// 5. Run onLoad
			if (typeof freshInstance.onLoad === "function") {
				await freshInstance.onLoad();
			}

			// 6. Reload commands
			const commandsLoader = new CommandsLoader();
			await commandsLoader.autoLoad(pluginId);

			// 7. Reload events
			if (eventsLoader) {
				await eventsLoader.fromPluginId(pluginId);
			}

			// 8. Run onEnable & onReady
			if (typeof freshInstance.onEnable === "function") {
				await freshInstance.onEnable();
			}
			if (typeof freshInstance.onReady === "function") {
				await freshInstance.onReady();
			}

			logger.info(`[ReloadService] Successfully reloaded entire plugin "${meta.name}".`);

			return {
				success: true,
				pluginName: meta.name,
			};
		} catch (error: any) {
			logger.error(`[ReloadService] Error while reloading plugin "${meta.name}":`, error);
			return {
				success: false,
				pluginName: meta.name,
				error: error?.message || "Encountered an exception while reloading plugin.",
			};
		}
	}

	/**
	 * Reload events belonging to a given plugin.
	 */
	public static async reloadPluginEvents(
		pluginIdOrName: string,
		client?: any
	): Promise<{
		success: boolean;
		pluginName?: string;
		error?: string;
	}> {
		let pluginId = pluginIdOrName;
		let pluginSettings = global.cache?.plugins?.get(pluginId);

		if (!pluginSettings) {
			for (const [id, entry] of global.cache?.plugins || []) {
				if (entry.meta?.name?.toLowerCase() === pluginIdOrName.toLowerCase()) {
					pluginId = id;
					pluginSettings = entry;
					break;
				}
			}
		}

		if (!pluginSettings) {
			return {
				success: false,
				error: `Plugin \`${pluginIdOrName}\` was not found.`,
			};
		}

		try {
			const activeClient = client || (global as any).bot?.client || (global as any).client;
			if (activeClient) {
				const eventsLoader = new EventsLoader(activeClient);
				eventsLoader.unloadPluginEvents(pluginId);

				const eventsDir = path.resolve(
					pluginSettings.meta.path,
					pluginSettings.autoLoader.events.directory
				);
				const files = getAllFiles(eventsDir);
				for (const f of files) {
					this.purgeRequireCache(f);
				}

				await eventsLoader.fromPluginId(pluginId);
			}

			return {
				success: true,
				pluginName: pluginSettings.meta.name,
			};
		} catch (error: any) {
			logger.error(`[ReloadService] Failed to reload events for plugin "${pluginId}":`, error);
			return {
				success: false,
				error: error?.message || "Failed to reload plugin events.",
			};
		}
	}
}
