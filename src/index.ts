import "dotenv/config";
import "@config/global.d.ts";
import logger from "@logger";

// Log on Startup
logger.info("[MomentumOne] The system is booting up... Please wait...");
global.eBus.publish(global.EventsList.STARTING, {
	executor: "system",
	version: runtime.version
})

import path from "path";
import config from "@config";
import db from "@database/Database";
import Bot from "@bot/Main";
import Server, { attachBot } from "@apps/api/Server";
import { ObservabilityManager } from "@core/telemetry/ObservabilityManager";

ObservabilityManager.init();
ObservabilityManager.recordLifecycleEvent("startup");

// Initializing database connection
try {
    logger.debug(`[${process.env.BOT_NAME || 'MomentumOne'}] Initializing database...`);
	global.eBus.publish(global.EventsList.DATABASE_CONNECTING, {
		executor: "system",
		host: config.database?.production?.connection?.url ? "remote" : "in-memory",
		database: config.database?.production?.connection?.database || "default"
	})
	runtime.services.started++;
	runtime.services.total++;
	runtime.services.registered++;
	await db.initialize("system");
} catch (err) {
	runtime.services.started--;
	runtime.services.stopped++;
    logger.error("Startup failed:", err);
}

// Start the API regardless of Discord configuration so the dashboard can report setup state.
const api = new Server();
await api.start();

// Start bot...
if (process.env.BOT_ENABLED?.trim().toLowerCase() !== "false"){
	// Initialise, setup and start Bot
	runtime.services.started++;
	runtime.services.total++;
	runtime.services.registered++;
	const bot = new Bot();
	attachBot(bot.bot);
	void bot.start().catch(error => logger.error("[BOT] Login failed:", error));
} else {
	logger.info(`[${process.env.BOT_NAME || 'MomentumOne'} ] Could not start the discord bot as it is disabled in the enviorment settings!`);
}

global.eBus.publish(global.EventsList.READY, {
    executor: "system",
    version: runtime.version,
	startupTime: (Date.now() - runtime.startedAt),
	pluginsLoaded: runtime.plugins.loaded,
    modulesLoaded: runtime.modules.loaded,
    servicesStarted: runtime.services.started,
});


// Mark as running
runtime.status = "running";
