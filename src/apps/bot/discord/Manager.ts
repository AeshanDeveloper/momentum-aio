import logger from "@logger";
import { Client, GatewayIntentBits } from "discord.js";
import PluginsManager from "@core/plugins/Manager";
import CommandsLoader from "@bot/discord/commands/Loader"
import EventsLoader from "@bot/discord/events/Loader"
import config from "@config";
import { CommandStatus, RegisteredBy, CommandType } from "@shared/types/CommandRecord";


import DiscordTelemetry from "@core/telemetry/DiscordTelemetry";

export default class Manager {
    client: Client;
	plugins: PluginsManager;
	commandsLoader: CommandsLoader;
	eventsLoader: EventsLoader;
    constructor() {
        //this.client = new Client({ intents: [ "GuildMessages", "GuildMembers", "DirectMessages"] });
		this.client = new Client({
			intents: [
				GatewayIntentBits.Guilds,
				GatewayIntentBits.GuildMembers,
				GatewayIntentBits.GuildMessages,
				GatewayIntentBits.MessageContent,
				GatewayIntentBits.DirectMessages,
			],
		});
		this.plugins = new PluginsManager(this.client);
		this.commandsLoader = new CommandsLoader();
		this.eventsLoader = new EventsLoader(this.client);
		try {
			DiscordTelemetry.hook(this.client);
		} catch (err) {
			logger.warn("[Manager] Could not hook DiscordTelemetry:", err);
		}
    }
	
	async loadPlugins(){
		try {
			await this.plugins.loadAll();
		} catch (err){
			logger.error("[PluginSystem] An error occured while loading the plugins!")
		}
	}
	
	async loadCommands() {
		await this.commandsLoader.autoLoadAll();
	}
	
	async loadEvents(){
		await this.eventsLoader.autoLoadAll();
	}

    async setup(): Promise<{ ready: boolean }> {
        try {
            await this.loadPlugins();
            await this.loadCommands();
            await this.loadEvents();
            await this.plugins.executeAll("onEnable");
            return { ready: true };
        } catch (error) {
            logger.error("[BOT] Discord client setup failed:", error);
            return { ready: false };
        }
    }

    async login() {
        const token = process.env.BOT_TOKEN?.trim();
        if (!token) {
            throw new Error("BOT_TOKEN is not configured");
        }

        this.client.once("ready", async () => {
            logger.info(`[BOT] Logged in as ${this.client.user?.tag} (${this.client.user?.id}) | Guilds: ${this.client.guilds.cache.size}`);
            await this.plugins.executeAll("onReady");
        });

        logger.info("[BOT] Attempting Discord login...");
        await this.client.login(token);
        runtime.services.started++;
        runtime.services.total++;
    }

    status() {
        const ready = this.client.isReady();
        return {
            state: ready ? "online" : (this.client.ws.status === 0 ? "starting" : "disconnected"),
            process: true,
            discordReady: ready,
            username: this.client.user?.tag ?? null,
            userId: this.client.user?.id ?? null,
            guildCount: this.client.guilds.cache.size,
            uptime: this.client.uptime,
            websocketStatus: this.client.ws.status,
            tokenConfigured: Boolean(process.env.BOT_TOKEN),
        };
    }

    registry() {
        return {
            commands: Array.from(global.commands?.values?.() ?? []),
            plugins: Array.from(global.cache?.plugins?.keys?.() ?? []),
            events: []
        };
    }
	
	async refresh(){
		
	}
	
	async logout(){
		this.client.destroy();
	}
}

