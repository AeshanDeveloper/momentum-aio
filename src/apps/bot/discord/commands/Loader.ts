import logger from "@logger";
import { getAllFiles } from "@shared/helpers";
import fs from "node:fs";
import path from "path";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import Commands from "@database/models/Commands";
import {
    REST,
    Routes,
    SlashCommandBuilder,
} from "discord.js";
import type PrefixCommand from "@bot/discord/commands/PrefixCommand";
import type SlashCommand from "@bot/discord/commands/SlashCommand";
import { createRequire } from "node:module";
import { CommandStatus, RegisteredBy, CommandType } from "@shared/types/CommandRecord";

const require = createRequire(import.meta.url);


let commands = new Commands();

export default class CommandsLoader {
	async fromPluginId(id: string){
		if (typeof id != "string") return logger.silly("[CommandLoader] Please provide a valid plugin id.");
		try {
			// Get plugin
			let settings = global.cache.plugins.get(id);
			let commandsDir = path.resolve(path.join(settings.meta.path, settings.autoLoader.commands.directory))
			let files = getAllFiles(commandsDir)
				files.forEach(file => {
					// Actions fot each command file
					
					
				})
		} catch (err) {
			logger.error(`[CommandLoader] An error occured while loading commands for a plugin "${global.cache.plugins.get(id).meta.name}"`);
		} finally {
			return;
		}
	}
	
	
	async autoLoad(id: string) {
    	logger.debug("[AutoLoader] Autoloading plugin commands...");
	
    	if (typeof id !== "string") {
        	return logger.silly(
            	"[CommandLoader] Please provide a valid plugin id."
        	);
    	}
	
    	try {
        	const settings = global.cache.plugins.get(id);
	
        	// Conditions
        	if (!settings.autoLoader.commands.enabled) {
            	return logger.debug(
                	"[Autoloader] The plugin has no autoload configurations!"
            	);
        	}
	
        	if (!settings.autoLoader.commands.mapping) {
            	return logger.debug(
                	"[Autoloader] Autoloader for commands is enabled but mappings aren't setup yet!"
            	);
        	}
	
        	// Discover commands
        	const discovered = await this.discoverCommands(settings);
	
        	// Sync with database
        	await this.syncCommands(id, discovered);
	
    	} catch (err: any) {
        	logger.error(
            	`[CommandLoader] Failed to autoload commands for "${global.cache.plugins.get(id)?.meta?.name || id}": ${err?.stack || err?.message || err}`
        	);
    	}
	}
	
	
	/**
    * Discovers and validates all commands belonging to a plugin.
    */
	private async discoverCommands(settings: any) {
    	const mapper = settings.autoLoader.commands.mapping;
	
    	const commandsDir = path.resolve(
        	settings.meta.path,
        	settings.autoLoader.commands.directory
    	);
	
    	const files = getAllFiles(commandsDir);
	
    	const discovered: any[] = [];
	
    	for (const file of files) {
        	const imported = require(file);
        	const raw = imported?.default ?? imported;
	
        	if (
            	raw == null ||
            	(typeof raw === "object" && Object.keys(raw).length === 0)
        	) {
            	continue;
        	}
	
        	let mapped;
	
        	try {
            	mapped = mapper(raw);
        	} catch (err: any) {
            	logger.debug(
                	`[AutoLoader] Failed to map "${file}"\n${err.message}`
            	);
            	continue;
        	}
	
        	if (
            	mapped == null ||
            	typeof mapped !== "object" ||
            	Object.keys(mapped).length === 0
        	) {
            	logger.error(
                	`[AutoLoader] Misconfigured mappings in plugin ${settings.meta.name}`
            	);
            	continue;
        	}
	
        	const isSlash = this.isSlashCommand(mapped);
        	const isPrefix = this.isPrefixCommand(mapped);
	
        	if (!isSlash && !isPrefix) {
            	logger.debug(
                	`[AutoLoader] Invalid command file: ${path.basename(file)}`
            	);
            	continue;
        	}
	
        	let type: CommandType;
	
        	if (isSlash && isPrefix) {
            	type = CommandType.HYBRID;
        	} else if (isSlash) {
            	type = CommandType.SLASH;
        	} else {
            	type = CommandType.PREFIX;
        	}
	
        	discovered.push({
                raw,
            	file,
            	checksum: await this.calculateChecksum(file),
            	type,
            	mapped,
            	key: `${type}:${mapped.name ?? mapped.data?.name}`,
        	});
    	}
	
    	return discovered;
	}
	
	
	/**
    * Synchronizes discovered commands with the database.
    */
	private async syncCommands(id: string, discovered: any[]) {
    	const dbCommands = await commands.findByPluginId(id);
	
    	const discoveredMap = new Map(
        	discovered.map(c => [c.key, c])
    	);
	
    	const dbMap = new Map(
        	dbCommands.map(c => [`${c.type}:${c.name}`, c])
    	);
	
    	// Insert / Update
    	for (const [key, cmd] of discoveredMap) {
        	const existing = dbMap.get(key);
	
        	if (!existing) {
            	await this.registerNewCommand(id, cmd);
        	} else {
            	await this.syncExistingCommand(existing, cmd, key);
        	}
    	}
	
    	// Mark missing
    	await this.markMissingCommands(dbMap, discoveredMap);
	
    	// Reload commands from database so memory
    	// contains the final/current state.
    	const syncedCommands = await commands.findByPluginId(id);
	
    	if (!global.commands) {
        	global.commands = new Map();
    	}
	
    	for (const command of syncedCommands) {
        	if (command.status === CommandStatus.MISSING) {
            	continue;
        	}

        	const discoveredCommand = discoveredMap.get(
            	`${command.type}:${command.name}`
        	);

        	if (!discoveredCommand) {
            	continue;
        	}

        	global.commands.set(command.commandId, {
            	pluginId: command.pluginId,
            	commandId: command.commandId,
            	name: command.name,
            	type: command.type,
				userPermissions: command?.userPermissions || [],
				botPermissions: command?.botPermissions || [],
            	status: command.status,
            	enabled: Boolean(command.enabled),
            	checksum: command.checksum,
            	file: discoveredCommand.file,
            	command: discoveredCommand.mapped,
                raw: discoveredCommand.raw
        	});
    	}
	
    	logger.debug("[CommandsLoader] Syncrhronization completed successfully!");
	}

	
	/**
    * Registers a newly discovered command.
    */
	private async registerNewCommand(id: string, cmd: any) {
    	await commands.register({
        	commandId: crypto.randomUUID(),
        	pluginId: id,
        	name: cmd.mapped.name ?? cmd.mapped.data?.name,
        	description:
            	cmd.mapped.description ??
            	cmd.mapped.data?.description,
			enabled: true,
			type: cmd.type,
			aliases: cmd.mapped.aliases || [],
        	ownerOnly: `${cmd.mapped.ownerOnly || false}`,
        	developerOnly: `${cmd.mapped.developerOnly || false}`,
        	premiumOnly: `${cmd.mapped.premiumOnly || false}`,
        	guildOnly: `${cmd.mapped.guildOnly || false}`,
        	nsfw: `${cmd.mapped.nsfw || false}`,
			userPermissions: `${cmd.mapped?.userPermissions || []}`,
			botPermissions: `${cmd.mapped?.botPermissions || []}`,
        	cooldown: cmd.mapped.cooldown || 0,
        	status: CommandStatus.ACTIVE,
        	checksum: cmd.checksum,
        	registeredBy: RegisteredBy.SYSTEM,
    	});
	}
	
	
	/**
    * Synchronizes an already existing command.
    */
	private async syncExistingCommand(
    	existing: any,
    	cmd: any,
    	key: string
	) {
    	if (existing.checksum !== cmd.checksum) {
        	await this.updateExistingCommand(existing, cmd);
	
        	//logger.debug(`[AutoLoader] Updated ${key}`);
    	} else if (existing.status !== CommandStatus.ACTIVE) {
        	await commands.setStatus(
            	existing.commandId ?? existing.command_id,
            	CommandStatus.ACTIVE
        	);
    	}
	}
	
	
	/**
    * Updates an existing command when its source file changes.
    */
	private async updateExistingCommand(
    	existing: any,
    	cmd: any
	) {
    	await commands.update(existing.commandId ?? existing.command_id, {
        	checksum: cmd.checksum,
        	pluginId: existing.pluginId,
        	name: cmd.mapped.name ?? cmd.mapped.data?.name ?? existing.name,
        	description:
            	cmd.mapped.description ??
            	cmd.mapped.data?.description,
        	aliases: cmd.mapped.aliases ?? [],
        	cooldown: cmd.mapped.cooldown || 0,
        	ownerOnly: `${cmd.mapped.ownerOnly || false}`,
        	guildOnly: `${cmd.mapped.guildOnly || false}`,
        	nsfw: `${cmd.mapped.nsfw || false}`,
			userPermissions: `${cmd.mapped?.userPermissions || []}`,
			botPermissions: `${cmd.mapped?.botPermissions || []}`,
        	enabled: existing.enabled !== undefined ? existing.enabled : "true",
        	status: CommandStatus.ACTIVE,
    	});
	}
	
	
	/**
    * Marks database commands as missing when they
    * are no longer present in the plugin's command directory.
    */
	private async markMissingCommands(
    	dbMap: Map<string, any>,
    	discoveredMap: Map<string, any>
	) {
    	for (const [key, cmd] of dbMap) {
        	if (!discoveredMap.has(key)) {
            	await commands.setStatus(
                	cmd.commandId ?? cmd.command_id,
                	CommandStatus.MISSING
            	);
	
            	logger.debug(
                	`[AutoLoader] Marked missing ${key}`
            	);
        	}
    	}
	}
	
		/**
    * Register slash commands currently stored in the command cache.
    */
	async registerSlash(data?: any, type: string = "global") {
		const token = process.env.BOT_TOKEN?.trim();
		const clientId = process.env.CLIENT_ID?.trim();
		if (!token || token === "NO_TOKEN" || !clientId) {
			logger.debug("[CommandsLoader] Skipping REST slash command registration: BOT_TOKEN or CLIENT_ID not configured.");
			return;
		}
		
		const rest = new REST({ version: "10" })
				.setToken(token);
				
		try {
			
	
			let commandsToRegister: any[] = [];
	
			// If data is explicitly provided, use it.
			if (data !== undefined && data !== null) {
				commandsToRegister = Array.isArray(data)
					? data
					: [data];
			} else {
				// Otherwise populate from cache.
				for (const [, command] of global.commands) {
					if (
						command.status !== CommandStatus.ACTIVE ||
						command.enabled !== true
					) {
						continue;
					}
	
					if (
						![CommandType.SLASH, CommandType.HYBRID].includes(command.type)
					) {
						continue;
					}
	
					if (!command.command?.data) {
						continue;
					}
	
					commandsToRegister.push(
						typeof command.command.data.toJSON === "function"
							? command.command.data.toJSON()
							: command.command.data
					);
				}
			}
	
			if (commandsToRegister.length === 0) {
				return logger.debug(
					"[CommandsLoader] No active slash commands found in cache."
				);
			}
	
			if (type === "global") {
				const timeoutMs = Number(process.env.DISCORD_REGISTRATION_TIMEOUT || 15000);
				const timeoutPromise = new Promise((_, reject) =>
					setTimeout(() => reject(new Error("Discord REST registration timed out")), timeoutMs)
				);
				const result = await Promise.race([
					rest.put(Routes.applicationCommands(clientId), { body: commandsToRegister }),
					timeoutPromise,
				]);
				logger.info(`[CommandsLoader] Successfully registered ${commandsToRegister.length} slash commands globally.`);
				return result;
			}
	
			logger.error(
				`[CommandsLoader] Unknown slash command registration type: ${type}`
			);
		} catch (err: any) {
			logger.warn(
				`[CommandsLoader] Could not complete slash command registration with Discord REST API (${err?.message || "unknown"}). Bot will continue operating.`
			);
		}
	}
	
	
	/**
    * Register prefix commands currently stored in the command cache.
    */
	async registerPrefix() {
    	try {
            let commandCount = 0;
        	for (const [, command] of global.commands) {
            	if (
                	command.status !== CommandStatus.ACTIVE ||
                	command.enabled !== true
            	) {
                	continue;
            	}
	
            	if (
                	command.type !== CommandType.PREFIX &&
                	command.type !== CommandType.HYBRID
            	) {
                	continue;
            	}
	
            	if (!command.command) {
                	continue;
            	}
	
            	commandCount++
        	}
	
        	logger.debug(
            	`[CommandsLoader] ${commandCount} prefix commands loaded successfully into memory.`
        	);
    	} catch (err) {
        	logger.error(
            	"[CommandsLoader] Failed to register prefix commands.",
            	err
        	);
    	}
	}
	
	
	/**
    * Register all command types from the command cache.
    */
	async registerAll() {
    	try {
        	await this.registerSlash();
        	await this.registerPrefix();
	
        	logger.debug(
            	"[CommandsLoader] All commands registered successfully."
        	);
    	} catch (err) {
        	logger.error(
            	"[CommandsLoader] Failed to register all commands.",
            	err
        	);
    	}
	}
	
async autoLoadAll() {
    for (const [key] of global.cache.plugins) {
        await this.autoLoad(key);
    }

    await this.loadCommandsIntoMemory();

    await this.registerAll();
}
	
	private isPrefixCommand(value: unknown): value is PrefixCommand {
    	if (typeof value !== "object" || value === null) return false;
	
    	const cmd = value as Record<string, unknown>;
	
    	return (
        	typeof cmd.name === "string" &&
        	typeof cmd.execute === "function" &&
	
        	(cmd.aliases === undefined || Array.isArray(cmd.aliases)) &&
        	(cmd.description === undefined || typeof cmd.description === "string") &&
        	(cmd.category === undefined || typeof cmd.category === "string") &&
        	(cmd.usage === undefined || typeof cmd.usage === "string") &&
        	(cmd.examples === undefined || Array.isArray(cmd.examples)) &&
        	(cmd.userPermissions === undefined || Array.isArray(cmd.userPermissions)) &&
        	(cmd.botPermissions === undefined || Array.isArray(cmd.botPermissions)) &&
        	(cmd.cooldown === undefined || typeof cmd.cooldown === "number") &&
        	(cmd.guildOnly === undefined || typeof cmd.guildOnly === "boolean") &&
        	(cmd.ownerOnly === undefined || typeof cmd.ownerOnly === "boolean") &&
        	(cmd.nsfw === undefined || typeof cmd.nsfw === "boolean") &&
        	(cmd.enabled === undefined || typeof cmd.enabled === "boolean") &&
        	(cmd.hidden === undefined || typeof cmd.hidden === "boolean")
    	);
	}
	
	private isSlashCommand(value: unknown): value is SlashCommand {
    	if (typeof value !== "object" || value === null) return false;
	
    	const cmd = value as Record<string, unknown>;
	
    	return (
        	typeof cmd.execute === "function" &&
        	typeof (cmd.data as any)?.toJSON === "function" &&
        	(cmd.category === undefined || typeof cmd.category === "string") &&
        	(cmd.botPermissions === undefined || Array.isArray(cmd.botPermissions)) &&
        	(cmd.userPermissions === undefined || Array.isArray(cmd.userPermissions)) &&
        	(cmd.cooldown === undefined || typeof cmd.cooldown === "number") &&
        	(cmd.ownerOnly === undefined || typeof cmd.ownerOnly === "boolean") &&
        	(cmd.enabled === undefined || typeof cmd.enabled === "boolean") &&
        	(cmd.hidden === undefined || typeof cmd.hidden === "boolean")
    	);
	}
	
	
	private async loadCommandsIntoMemory() {
    	if (!global.commands) {
        	global.commands = new Map();
    	}
	
    	global.commands.clear();
	
    	for (const [pluginId] of global.cache.plugins) {
        	try {
            	const settings = global.cache.plugins.get(pluginId);
	
            	if (!settings?.autoLoader?.commands?.enabled) {
                	continue;
            	}
	
            	if (!settings.autoLoader.commands.mapping) {
                	continue;
            	}
	
            	// Discover the actual command source files again.
            	const discovered = await this.discoverCommands(settings);
	
            	// Get the commands belonging to this plugin from DB.
            	const dbCommands = await commands.findByPluginId(pluginId);
	
            	const discoveredMap = new Map(
                	discovered.map(command => [
                    	`${command.type}:${command.mapped.name ?? command.mapped.data?.name}`,
                    	command
                	])
            	);
	
            	for (const command of dbCommands) {
                	const commandId = command.commandId;
	
                	if (!commandId) {
                    	logger.error(
                        	`[CommandLoader] Command "${command.name}" has no command ID.`
                    	);
                    	continue;
                	}
	
                	const discoveredCommand = discoveredMap.get(
                    	`${command.type}:${command.name}`
                	);
	
                	if (!discoveredCommand) {
                    	logger.debug(
                        	`[CommandLoader] Source command not found for ${command.type}:${command.name}`
                    	);
                    	continue;
                	}
	
                	global.commands.set(commandId, {
                    	pluginId: command.pluginId,
                    	commandId,
                    	name: command.name,
                    	type: command.type,
                    	status: command.status,
                    	enabled:
Boolean(command.enabled),
                    	checksum: command.checksum,
                    	file: discoveredCommand.file,
                    	command: discoveredCommand.mapped,
                        raw: discoveredCommand.raw
                	});
            	}
	
        	} catch (err) {
            	logger.error(
                	`[CommandLoader] Failed to load commands into memory for plugin "${pluginId}".`,
                	err
            	);
        	}
    	}
	
    	logger.debug(
        	`[CommandLoader] Loaded ${global.commands.size} commands into memory.`
    	);
	}
	
	private async calculateChecksum(filePath: string): Promise<string> {
		return new Promise((resolve, reject) => {
			const hash = createHash("sha256");
			const stream = createReadStream(filePath);
	
			stream.on("error", reject);
	
			stream.on("data", (chunk) => {
				hash.update(chunk);
			});
	
			stream.on("end", () => {
				resolve(hash.digest("hex"));
			});
		});
	}
}

