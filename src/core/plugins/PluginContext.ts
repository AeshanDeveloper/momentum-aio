import logger from "@logger";
import config from "@config";
import database from "@database/Database";
import PluginManager from "@core/plugins/Manager";
import { Client } from "discord.js";
import EventBus from "@core/events/EventBus"
import AutoLoader from "@sdk/AutoLoader"

class PluginLogger {
	constructor(private readonly pluginName: string) {}

	private prefix(args: any[]): any[] {
		if (args.length === 0) {
			return [`[${this.pluginName}]`];
		}
		return [
			`[${this.pluginName}] ${String(args[0])}`,
			...args.slice(1),
		];
	}

	trace = (...args: any[]) => logger.debug(...this.prefix(args));
	debug = (...args: any[]) => logger.debug(...this.prefix(args));
	info = (...args: unknown[]) => logger.info(...this.prefix(args));
	http = (...args: unknown[]) => logger.http(...this.prefix(args));
	verbose = (...args: unknown[]) => logger.verbose(...this.prefix(args));
	warn = (...args: unknown[]) => logger.warn(...this.prefix(args));
	error = (...args: unknown[]) => logger.error(...this.prefix(args));
	silly = (...args: unknown[]) => logger.silly(...this.prefix(args));
}
export interface PluginContextOptions {
	meta: any;
	client: Client;
}

export default class PluginContext {
	// Plugin metadata
	public readonly meta;
	
	// Context services
	public readonly client: Client;
	public readonly logger: PluginLogger;
	public readonly eventBus: EventBus;
	public readonly EventsList = global.EVENTS;
	public readonly config = config;
	public readonly databaseManager: any = database;
	public readonly cache = global.cache;
	public readonly autoLoader: AutoLoader;

	constructor(options: PluginContextOptions, eventBus: EventBus, autoLoader: AutoLoader) {
		this.meta = options.meta;
		this.client = options.client;
		this.logger = new PluginLogger(this.meta.name);
		this.eventBus = eventBus;
		this.autoLoader = autoLoader;
	}
}


